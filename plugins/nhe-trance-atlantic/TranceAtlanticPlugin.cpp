/*
 * Trance Atlantic - New Horizon Electronics
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * An envelope "whale call": your picking drives a resonant throat filter (Throat switch,
 * v2.5: Off / Fixed / Follow; its width fixed * at half way after the first hardware test), a pitch swoop and a slow-gear
 * swell. The call is then sent out to sea and blended back with the dry.
 *
 *   in --+------------------------------------------------- dry -------------------(+)--> out L/R
 *        |                                                                          ^
 *        +-> envelopes (fast, slow, 2-pole pitch env)                               |
 *        +-> throat SVF -> swoop delay -> swell = call --+--- near call ------------+ wet
 *                                                        |                          | (soft-limited)
 *                                                        +-> THE OCEAN -------------+
 *
 *   THE OCEAN (v2.3; replaces the hall, which sounded like a cave):
 *     pre-delay -> steep low-pass (24 dB/oct) -> dispersion (48 stretched all-passes:
 *     lows arrive late, a pluck becomes a "pew") -> multipath bounces (6 arrivals,
 *     alternating polarity, each darker) -> soft Dattorro wash fed by the late bounces
 *     -> narrow stereo -> moving surface mirror (inverted, drifting reflection) per side
 *
 * Traits (playbook docs/effect-profile.md): every, tail, feedback (tank), buffer,
 * level-sensitive, modulated delay, stereo, mix.
 * Tank and diffuser lengths are Dattorro's (1997), as in NHE Taj Mahal.
 */
#include "DistrhoPlugin.hpp"

#include <cmath>
#include <cstdint>
#include <cstring>
#include <vector>

START_NAMESPACE_DISTRHO

static const double kMaxSampleRate = 96000.0;
static const double kRefRate       = 29761.0;   // Dattorro reference rate
static const float  kAntiDenormal  = 1e-18f;

static uint32_t nextPow2(uint32_t v) { uint32_t p = 1; while (p < v) p <<= 1; return p; }
static inline float clampf(float x, float lo, float hi) { return x < lo ? lo : (x > hi ? hi : x); }
static inline float tauCoef(float sec, float sr) { return 1.0f - std::exp(-1.0f / (sec * sr)); }
static inline float hzCoef(float hz, float sr)   { return 1.0f - std::exp(-6.2831853f * hz / sr); }

static inline float softClip(float x)
{
    if (x >  3.0f) return  1.0f;
    if (x < -3.0f) return -1.0f;
    const float x2 = x * x;
    return x * (27.0f + x2) / (27.0f + 9.0f * x2);
}
static inline float softKnee(float x, float k, float r)
{
    const float a = std::fabs(x);
    if (a <= k) return x;
    const float y = k + r * softClip((a - k) / r);
    return x < 0.0f ? -y : y;
}
static inline float fastSin(float ph)   // phase in [0, 1)
{
    const float x = ph * 2.0f - 1.0f;
    return -4.0f * x * (1.0f - std::fabs(x));
}

struct DelayLine
{
    std::vector<float> buf;
    uint32_t mask = 0, pos = 0;
    void init(uint32_t maxLen) { const uint32_t n = nextPow2(maxLen + 4); buf.assign(n, 0.0f); mask = n - 1; pos = 0; }
    void clear() { for (float& s : buf) s = 0.0f; pos = 0; }
    inline float tap(uint32_t d) const { return buf[(pos - d) & mask]; }
    inline float tapFrac(float d) const
    {
        const uint32_t i = (uint32_t)d; const float f = d - (float)i;
        const float a = buf[(pos - i) & mask], b = buf[(pos - i - 1) & mask];
        return a + (b - a) * f;
    }
    inline float tapHermite(float d) const
    {
        const uint32_t i = (uint32_t)d; const float f = d - (float)i;
        const float xm1 = buf[(pos - i + 1) & mask], x0 = buf[(pos - i) & mask];
        const float x1  = buf[(pos - i - 1) & mask], x2 = buf[(pos - i - 2) & mask];
        const float c1 = 0.5f * (x1 - xm1);
        const float c2 = xm1 - 2.5f * x0 + 2.0f * x1 - 0.5f * x2;
        const float c3 = 0.5f * (x2 - xm1) + 1.5f * (x0 - x1);
        return ((c3 * f + c2) * f + c1) * f + x0;
    }
    inline void write(float x) { buf[pos & mask] = x; ++pos; }
};

struct Allpass
{
    DelayLine dl;
    inline float process(float x, float len, float g)
    { const float d = dl.tapFrac(len); const float w = x + g * d; dl.write(w); return d - g * w; }
    inline float processInt(float x, uint32_t len, float g)
    { const float d = dl.tap(len); const float w = x + g * d; dl.write(w); return d - g * w; }
};

// TPT state-variable low-pass (coefficients set at control rate)
struct SvfLP
{
    float ic1 = 0.0f, ic2 = 0.0f, a1 = 1.0f, a2 = 0.0f, a3 = 0.0f;
    void set(float fc, float q, float sr)
    {
        const float g = std::tan(3.14159265f * fc / sr), k = 1.0f / q;
        a1 = 1.0f / (1.0f + g * (g + k)); a2 = g * a1; a3 = g * a2;
    }
    inline float process(float x)
    {
        const float v3 = x - ic2;
        const float v1 = a1 * ic1 + a2 * v3;
        const float v2 = ic2 + a2 * ic1 + a3 * v3;
        ic1 = 2.0f * v1 - ic1 + kAntiDenormal;
        ic2 = 2.0f * v2 - ic2 + kAntiDenormal;
        return v2;
    }
    void clear() { ic1 = ic2 = 0.0f; }
};

class TranceAtlanticPlugin : public Plugin
{
public:
    TranceAtlanticPlugin()
        : Plugin(kParameterCount, 0, 0)
    {
        fParams[kSense] = 50.0f;  fParams[kSong] = 5.0f;   fParams[kSwim] = 250.0f;
        fParams[kDepth] = 35.83f;  fParams[kThroat] = 50.0f;  fParams[kScatter] = 80.71f; fParams[kBlend] = 76.77f;
        fParams[kTravel] = 2.0f; fParams[kMode] = 2.0f; fParams[kTails] = 1.0f; fParams[kInputLevel] = 0.0f; fParams[kBypass] = 0.0f;

        const double k = kMaxSampleRate / kRefRate;
        const uint32_t mod = (uint32_t)(60.0 * k) + 8;

        fSwoop.init((uint32_t)(kMaxSwoop * kMaxSampleRate) + 8);
        fPre.init((uint32_t)(0.125 * kMaxSampleRate));
        fBounce.init((uint32_t)(0.42 * kMaxSampleRate));
        fSurfL.init((uint32_t)(0.016 * kMaxSampleRate));
        fSurfR.init((uint32_t)(0.016 * kMaxSampleRate));
        for (int i = 0; i < 4; ++i) fIn[i].dl.init((uint32_t)(kInLen[i] * k));
        fApA1.dl.init((uint32_t)(672.0 * k) + mod);
        fApB1.dl.init((uint32_t)(908.0 * k) + mod);
        fDlA1.init((uint32_t)(4453.0 * k));
        fDlB1.init((uint32_t)(4217.0 * k));
        fApA2.dl.init((uint32_t)(1800.0 * k));
        fApB2.dl.init((uint32_t)(2656.0 * k));
        fDlA2.init((uint32_t)(3720.0 * k));
        fDlB2.init((uint32_t)(3163.0 * k));

        activate();
    }

protected:
    const char* getLabel()       const override { return "TranceAtlantic"; }
    const char* getDescription() const override { return "Envelope whale call: a singing auto-wah with a pitch swoop, sent out to sea and blended with the dry."; }
    const char* getMaker()       const override { return "New Horizon Electronics"; }
    const char* getHomePage()    const override { return "https://github.com/Kiwooky/NHE-Trance-Atlantic"; }
    const char* getLicense()     const override { return "GPL-3.0-or-later"; }
    uint32_t    getVersion()     const override { return d_version(1, 0, 5); }   // = lv2:minorVersion 2, microVersion 5 (factory presets)
    int64_t     getUniqueId()    const override { return d_cconst('T', 'r', 'A', 't'); }

    void initParameter(uint32_t index, Parameter& p) override
    {
        p.hints = kParameterIsAutomatable;
        p.ranges.min = 0.0f; p.ranges.max = 100.0f;
        switch (index) {
        case kSense:
            p.name = "Sense"; p.symbol = "sense"; p.unit = "%"; p.ranges.def = 50.0f;
            break;
        case kSong:
            p.hints |= kParameterIsInteger;
            p.name = "Song"; p.symbol = "song"; p.unit = "st";
            p.ranges.max = 24.0f; p.ranges.def = 5.0f;
            break;
        case kSwim:
            p.hints |= kParameterIsLogarithmic;
            p.name = "Swim"; p.symbol = "swim"; p.unit = "ms";
            p.ranges.min = 100.0f; p.ranges.max = 2000.0f; p.ranges.def = 250.0f;
            break;
        case kDepth:
            p.name = "Depth"; p.symbol = "depth"; p.unit = "%"; p.ranges.def = 35.83f;
            break;
        case kScatter:
            p.name = "Scatter"; p.symbol = "scatter"; p.unit = "%"; p.ranges.def = 80.71f;
            break;
        case kThroat:
            p.name = "Throat"; p.symbol = "throat"; p.unit = "%"; p.ranges.def = 50.0f;
            break;
        case kBlend:
            p.name = "Blend"; p.symbol = "blend"; p.unit = "%"; p.ranges.def = 76.77f;
            break;
        case kTravel: {
            p.hints |= kParameterIsInteger;
            p.name = "Travel"; p.symbol = "travel";
            p.ranges.max = 2.0f; p.ranges.def = 2.0f;
            static ParameterEnumerationValue ev[3];
            ev[0].label = "Up";   ev[0].value = 0.0f;
            ev[1].label = "Down"; ev[1].value = 1.0f;
            ev[2].label = "Arc";  ev[2].value = 2.0f;
            p.enumValues.count = 3; p.enumValues.restrictedMode = true; p.enumValues.values = ev;
            p.enumValues.deleteLater = false;
            break;
        }
        case kMode: {
            p.hints |= kParameterIsInteger;
            p.name = "Mode"; p.symbol = "mode";
            p.ranges.max = 2.0f; p.ranges.def = 2.0f;
            static ParameterEnumerationValue tv[3];
            tv[0].label = "Off";    tv[0].value = 0.0f;
            tv[1].label = "Fix";  tv[1].value = 1.0f;
            tv[2].label = "Env"; tv[2].value = 2.0f;
            p.enumValues.count = 3; p.enumValues.restrictedMode = true; p.enumValues.values = tv;
            p.enumValues.deleteLater = false;
            break;
        }
        case kTails:
            p.hints |= kParameterIsInteger | kParameterIsBoolean;
            p.name = "Tails"; p.symbol = "tails";
            p.ranges.max = 1.0f; p.ranges.def = 1.0f;
            break;
        case kInputLevel:                                     // for the face's orb ripples
            p.hints = kParameterIsOutput;
            p.name = "Input Level"; p.symbol = "input_level";
            p.ranges.min = 0.0f; p.ranges.max = 1.0f; p.ranges.def = 0.0f;
            break;
        case kBypass:
            p.initDesignation(kParameterDesignationBypass);
            break;
        }
    }

    float getParameterValue(uint32_t i) const override { return i < kParameterCount ? fParams[i] : 0.0f; }
    void  setParameterValue(uint32_t i, float v) override { if (i < kParameterCount) fParams[i] = v; }

    void activate() override
    {
        fSr = (float)getSampleRate();
        if (fSr <= 0.0f) fSr = 48000.0f;
        if (fSr > (float)kMaxSampleRate) fSr = (float)kMaxSampleRate;
        fM = fSr > 60000.0f ? 4u : 2u;        // the ocean runs at 22-24 kHz: everything in it is below 2.5 kHz
        fOsr = fSr / (float)fM;
        fK = fOsr / (float)kRefRate;
        fApK = 2u;                            // dispersion stretch at the ocean rate (= 4 at 48 kHz)
        fPh = 0; fFarPL = fFarPR = fFarL = fFarR = 0.0f;
        clearAll();
        fClearStage = -1;
        fFirst = true; fFirstPos = true; fThrPos = 0.0f;
        fFast = fSlow = fP1 = fP2 = 0.0f;
        fModA = 0.0f; fModB = 0.25f; fSurf1 = 0.0f; fSurf2 = 0.37f;
        fCtr = 0;
    }

    void clearAll() { for (int s = 0; s < kClearStages; ++s) clearStage(s); }

    // Tails off: wipe state one slice per run() so no single block does a huge memset
    void clearStage(int s)
    {
        switch (s) {
        case 0: fSwoop.clear(); fIc1 = fIc2 = 0.0f; break;
        case 1: fPre.clear(); fLp1.clear(); fLp2.clear(); std::memset(fAp, 0, sizeof(fAp)); fApPos = 0; break;
        case 2: fBounce.clear(); for (int t = 0; t < kTaps; ++t) fTapLp[t] = 0.0f; break;
        case 3: for (int i = 0; i < 4; ++i) fIn[i].dl.clear(); fApA1.dl.clear(); fApB1.dl.clear(); break;
        case 4: fDlA1.clear(); break;
        case 5: fDlB1.clear(); break;
        case 6: fApA2.dl.clear(); fApB2.dl.clear(); break;
        case 7: fDlA2.clear(); fDlB2.clear(); fDampA = fDampB = fHpA = fHpB = 0.0f; fSurfL.clear(); fSurfR.clear();
                fImL1 = fImL2 = fImR1 = fImR2 = fFarPL = fFarPR = fFarL = fFarR = 0.0f; break;
        }
    }

    void run(const float** inputs, float** outputs, uint32_t frames) override
    {
        const float* in   = inputs[0];
        float*       outL = outputs[0];
        float*       outR = outputs[1];
        const float sr = fSr, k = fK, osr = fOsr;

        // ---- controls -> targets (once per block) ------------------------
        const float senseGain = 10.0f * std::pow(10.0f, (clampf(fParams[kSense], 0.0f, 100.0f) - 50.0f) / 50.0f);
        // Throat (v2.6, back as a centred knob): 12 o'clock = the v2.2-2.5 sound. Left shifts the
        // throat down and widens it (bass), right shifts it up and narrows it (more vocal).
        const float tb        = (clampf(fParams[kThroat], 0.0f, 100.0f) - 50.0f) / 50.0f;   // -1 .. +1
        const float tShift    = std::pow(2.0f, 1.5f * tb);    // +-1.5 octaves
        const float tQ        = 3.3f * std::pow(2.0f, 0.8f * tb);   // Q 1.9 .. 3.3 .. 5.8
        const float tGain     = tb < 0.0f ? std::pow(2.0f, 1.1f * tb) : std::pow(2.0f, 0.33f * tb);   // +2 dB at full right   // the wide, low throat passes more: level-match it
        const float song      = clampf(fParams[kSong], 0.0f, 24.0f);
        const float swim      = clampf(fParams[kSwim], 100.0f, 2000.0f) * 0.001f;
        const float depthT    = clampf(fParams[kDepth], 0.0f, 100.0f) * 0.01f;
        const float dispT     = clampf(fParams[kScatter], 0.0f, 100.0f) * 0.01f;
        const float blend     = clampf(fParams[kBlend], 0.0f, 100.0f) * 0.01f;
        const int   dir       = (int)(clampf(fParams[kTravel], 0.0f, 2.0f) + 0.5f);
        const int   thrMode   = (int)(clampf(fParams[kMode], 0.0f, 2.0f) + 0.5f);   // 0 Off, 1 Fixed, 2 Follow
        const float thrMixT   = thrMode == 0 ? 0.0f : 1.0f;
        const bool  bypassed  = fParams[kBypass] > 0.5f;
        const bool  tails     = fParams[kTails] > 0.5f;

        // envelopes: fast follower (1 ms / 120 ms); slow "swim" (rise = Swim, fall = 2x, >= 150 ms);
        // pitch env = two one-poles at Swim/2 each, so the swoop rises and settles smoothly
        const float cFastA = tauCoef(0.001f, sr), cFastR = tauCoef(0.120f, sr);
        const float cSlowA = tauCoef(swim, sr);
        const float cSlowR = tauCoef(swim * 2.0f > 0.15f ? swim * 2.0f : 0.15f, sr);
        const float cPA    = tauCoef(0.5f * swim, sr);
        const float cPR    = tauCoef((dir == 2 ? 0.5f : 2.0f) * swim, sr);   // Arc: falls as fast as it rose

        // swoop depth: peak pitch ratio r at a full pluck. Peak slope of the 2-pole step
        // response is 1/(tau*e) = 0.736/Swim, so depth = (r - 1) * Swim / 0.736 seconds.
        // Down: the read slows to 1/r at the peak (a delay can't go below 0x speed, so Down
        // needs (1 - 1/r), not (r - 1): two octaves down = quarter speed, never reverse).
        const float r = std::pow(2.0f, song / 12.0f);
        float depthSec = (dir == 1 ? (1.0f - 1.0f / r) : (r - 1.0f)) * swim / 0.7358f;
        if (depthSec > kMaxSwoop) depthSec = kMaxSwoop;
        // Throat Mode Off (v2.7): no envelope anywhere, so no swoop either (the delay glides to its minimum)
        const float depthST = thrMode == 0 ? 0.0f : depthSec * sr;
        const float dMin = 3.0f;
        const float cDepth = tauCoef(0.080f, sr);

        // throat at 12 o'clock: 180 Hz at rest, opens to 1330 Hz, Q 3.3 (from 64-470 Hz to 510-3760 Hz)
        const float fLow = 180.0f * tShift;
        const float logTop = std::log(1330.0f / 180.0f);
        const float kq = 1.0f / tQ;

        // dispersion: each stage's low-frequency delay D = 1 .. 16 (x stretch) samples, linear in the
        // dial; all-pass coefficient a = (1 - D) / (1 + D): 0 = a plain short delay, -0.88 = a long "pew"
        const float apD = 1.0f + 15.0f * dispT;
        const float apT = (1.0f - apD) / (1.0f + apD);

        // bypass / tails / blend: smoothed gains (~10 ms). Dry at unity in bypass whatever Blend says.
        const float cFade = tauCoef(0.010f, sr);
        const float inT   = bypassed ? 0.0f : 1.0f;
        const float wetMix = blend * 2.0f < 1.0f ? blend * 2.0f : 1.0f;
        const float dryMix = (1.0f - blend) * 2.0f < 1.0f ? (1.0f - blend) * 2.0f : 1.0f;
        const float wetT  = (bypassed && !tails) ? 0.0f : wetMix;
        const float dryT  = bypassed ? 1.0f : dryMix;

        if (fFirst) {                        // controls arrive with the first run()
            fFirst = false;
            fInG = inT; fWetG = wetT; fDryG = dryT;
            fDepthS = depthST; fDm = depthT; fApA = apT; fThrMix = thrMixT;
            updateDepth(sr, osr);
            fPreS = fPreTarget; fScaleS = fScaleTarget;
        }

        // Tails off: once the wet has faded out, clear the state a slice per block
        if (bypassed && !tails) {
            if (fWetG < 1e-4f && fClearStage < 0) fClearStage = 0;
        } else {
            fClearStage = -1;
        }
        if (fClearStage >= 0 && fClearStage < kClearStages) clearStage(fClearStage++);

        const float modExc = 36.0f * k;                 // movement in the wash: the warble, and it smears ringing modes
        const float modInA = 0.71f / osr, modInB = 0.93f / osr;
        // the surface: an inverted reflection 2..10 ms behind, drifting with the swell (two slow LFOs)
        const float sBase = 0.0060f * osr, sDep1 = 0.0035f * osr, sDep2 = 0.0012f * osr;
        const float sInc1 = 0.13f / osr, sInc2 = 0.47f / osr;
        const uint32_t lenIn[4] = { (uint32_t)(kInLen[0]*k), (uint32_t)(kInLen[1]*k), (uint32_t)(kInLen[2]*k), (uint32_t)(kInLen[3]*k) };
        const float lenA1 = 672.0f * k, lenB1 = 908.0f * k;
        const uint32_t dA1 = (uint32_t)(4453.0f * k), dB1 = (uint32_t)(4217.0f * k);
        const uint32_t lenA2 = (uint32_t)(1800.0f * k), lenB2 = (uint32_t)(2656.0f * k);
        const uint32_t dA2 = (uint32_t)(3720.0f * k), dB2 = (uint32_t)(3163.0f * k);
        const float cPre = hzCoef(8.0f, osr);
        const float invM = 1.0f / (float)fM;
        const float cImg = hzCoef(5000.0f, sr);
        const float cBlk = tauCoef(0.050f / 16.0f, sr);   // control-rate glides ~50 ms
        const float cPos = tauCoef(0.030f / 16.0f, sr);   // throat position glide (Fixed <-> Follow)
        const uint32_t K = fApK;

        #define TAP(n) ((uint32_t)((n) * k) + 1)

        for (uint32_t i = 0; i < frames; ++i)
        {
            const float x = in[i];
            fInG  += cFade * (inT  - fInG);
            fWetG += cFade * (wetT - fWetG);
            fDryG += cFade * (dryT - fDryG);
            const float xr = x * fInG;

            // ---- envelopes ---------------------------------------------------
            float a = std::fabs(xr) * senseGain;
            if (a > 1.5f) a = 1.5f;              // so the release starts soon after the note fades
            fFast += (a > fFast ? cFastA : cFastR) * (a - fFast) + kAntiDenormal;
            const float ef = fFast < 1.0f ? fFast : 1.0f;
            fSlow += (ef > fSlow ? cSlowA : cSlowR) * (ef - fSlow) + kAntiDenormal;
            fP1 += (ef  > fP1 ? cPA : cPR) * (ef  - fP1) + kAntiDenormal;
            fP2 += (fP1 > fP2 ? cPA : cPR) * (fP1 - fP2) + kAntiDenormal;

            // ---- control rate: throat, Depth macro, Dispersion -----------------
            if ((fCtr++ & 15u) == 0) {
                // Fixed holds the throat half open (about 490 Hz); Follow rides the swim envelope.
                // The position glides (~30 ms) so switching modes doesn't click.
                const float posT = thrMode == 1 ? 0.5f : fSlow;
                fThrPos += (thrMode == 2 && fFirstPos) ? (posT - fThrPos) : cPos * (posT - fThrPos);
                fFirstPos = false;
                float fc = fLow * std::exp(logTop * fThrPos);
                if (fc > 0.45f * sr) fc = 0.45f * sr;
                const float g = std::tan(3.14159265f * fc / sr);
                fA1 = 1.0f / (1.0f + g * (g + kq));
                fA2 = g * fA1;
                fA3 = g * fA2;
                if (std::fabs(depthT - fDm) > 1e-5f) {
                    fDm += cBlk * (depthT - fDm);
                    if (std::fabs(depthT - fDm) < 1e-4f) fDm = depthT;
                    updateDepth(sr, osr);
                }
                fApA += cBlk * (apT - fApA);
                if (std::fabs(apT - fApA) < 1e-4f) fApA = apT;
            }

            // ---- throat: TPT state-variable band-pass (before the swoop since v2.4, so a deep
            //      dive keeps its level instead of falling out of the throat's band) ----
            const float v3 = xr - fIc2;
            const float v1 = fA1 * fIc1 + fA2 * v3;
            const float v2 = fIc2 + fA2 * fIc1 + fA3 * v3;
            fIc1 = 2.0f * v1 - fIc1 + kAntiDenormal;
            fIc2 = 2.0f * v2 - fIc2 + kAntiDenormal;
            fThrMix += cFade * (thrMixT - fThrMix);                 // Off: crossfade to the full-range signal
            const float throatOut = fThrMix * tGain * (kq * v1 * 2.4f + 0.35f * v2) + (1.0f - fThrMix) * kThroatOffG * xr;

            // ---- swoop: the delay moves with the pitch env, bending pitch ----
            fDepthS += cDepth * (depthST - fDepthS);
            const float env = (dir == 1) ? fP2 : (1.0f - fP2);   // Down: delay grows; Up/Arc: delay shrinks
            fSwoop.write(throatOut);
            float call = fSwoop.tapHermite(dMin + fDepthS * env);

            // ---- swell: slow-gear bloom (slow env / fast env) ------------------
            const float swell = ef > 1e-4f ? (fSlow < ef ? fSlow / ef : 1.0f) : 1.0f;
            call *= 1.0f + fThrMix * (swell - 1.0f);   // Off: no bloom (fades with the mode switch)

            // ================= THE OCEAN =====================================
            // steep darkness (4th-order Butterworth low-pass) at full rate; it is also the
            // anti-alias filter for the ocean, which runs at half (quarter at 96 kHz) rate
            const float lp = fLp2.process(fLp1.process(call));
            if (++fPh >= fM) {
            fPh = 0;
            // distance: pre-delay
            fPreS += cPre * (fPreTarget - fPreS);
            fPre.write(lp);
            float o = fPre.tapFrac(fPreS + 1.0f);

            // dispersion: 48 stretched first-order all-passes. Low frequencies are delayed
            // most, so a pluck arrives as a falling chirp, like sound in a shallow sea.
            {
                const float ap = fApA;
                const uint32_t rd = (fApPos - K) & 7u, wr = fApPos & 7u;
                float v = o + kAntiDenormal;
                for (int s = 0; s < kApStages; ++s) {
                    const float old = fAp[s][rd];
                    const float w = v - ap * old;
                    fAp[s][wr] = w;
                    v = ap * w + old;
                }
                ++fApPos;
                o = v;
            }

            // multipath: direct, then surface/seabed bounces; each flipped and darker
            fScaleS += cPre * (fScaleTarget - fScaleS);
            fBounce.write(o);
            float direct = 0.0f, late = 0.0f;
            for (int t = 0; t < kTaps; ++t) {
                const float s = fBounce.tapFrac(kTapMs[t] * fScaleS + 1.0f);
                fTapLp[t] += fTapC[t] * (s - fTapLp[t]);
                if (t == 0) direct = fTapLp[0];
                else        late  += kTapG[t] * fTapLp[t];
            }
            const float mp = direct + late;

            // the wash: a soft, slowly moving Dattorro tank fed by the late bounces only
            float p = late + kAntiDenormal;
            p = fIn[0].processInt(p, lenIn[0], 0.75f);
            p = fIn[1].processInt(p, lenIn[1], 0.75f);
            p = fIn[2].processInt(p, lenIn[2], 0.625f);
            p = fIn[3].processInt(p, lenIn[3], 0.625f);

            fModA += modInA; if (fModA >= 1.0f) fModA -= 1.0f;
            fModB += modInB; if (fModB >= 1.0f) fModB -= 1.0f;
            const float mA = modExc * (1.0f + fastSin(fModA));
            const float mB = modExc * (1.0f + fastSin(fModB));
            const float g = fLoopG;

            const float fbToA = fDlB2.tap(dB2) * g;
            const float fbToB = fDlA2.tap(dA2) * g;
            float ta = fApA1.process(p + fbToA, lenA1 + mA, -0.70f);
            fDlA1.write(ta);
            ta = fDlA1.tap(dA1);
            fDampA += fDampCoef * (ta - fDampA);
            fHpA += fHpCoef * (fDampA - fHpA);          // lows drain each lap: no booming modes
            ta = fApA2.processInt((fDampA - fHpA) * g, lenA2, 0.5f);
            fDlA2.write(ta + kAntiDenormal);

            float tb = fApB1.process(p + fbToB, lenB1 + mB, -0.70f);
            fDlB1.write(tb);
            tb = fDlB1.tap(dB1);
            fDampB += fDampCoef * (tb - fDampB);
            fHpB += fHpCoef * (fDampB - fHpB);
            tb = fApB2.processInt((fDampB - fHpB) * g, lenB2, 0.5f);
            fDlB2.write(tb + kAntiDenormal);

            const float wl = fDlB1.tap(TAP(266)) + fDlB1.tap(TAP(2974))
                           - fApB2.dl.tap(TAP(1913)) + fDlB2.tap(TAP(1996))
                           - fDlA1.tap(TAP(1990)) - fApA2.dl.tap(TAP(187))
                           - fDlA2.tap(TAP(1066));
            const float wr = fDlA1.tap(TAP(353)) + fDlA1.tap(TAP(3627))
                           - fApA2.dl.tap(TAP(1228)) + fDlA2.tap(TAP(2673))
                           - fDlB1.tap(TAP(2111)) - fApB2.dl.tap(TAP(335))
                           - fDlB2.tap(TAP(121));

            // narrow image: underwater, sound comes from everywhere (mostly mid)
            const float mid  = fBncG * mp + fRevG * 0.5f * (wl + wr);
            const float side = fRevG * 0.5f * (wl - wr) * kWidth;
            float sl = mid + side, sr2 = mid - side;

            // the surface: an inverted reflection that drifts with the swell, a little differently per side
            fSurf1 += sInc1; if (fSurf1 >= 1.0f) fSurf1 -= 1.0f;
            fSurf2 += sInc2; if (fSurf2 >= 1.0f) fSurf2 -= 1.0f;
            float ph1 = fSurf1 + 0.31f; if (ph1 >= 1.0f) ph1 -= 1.0f;
            float ph2 = fSurf2 + 0.5f;  if (ph2 >= 1.0f) ph2 -= 1.0f;
            fSurfL.write(sl); fSurfR.write(sr2);
            sl  -= kSurfG * fSurfL.tapFrac(sBase + sDep1 * fastSin(fSurf1) + sDep2 * fastSin(fSurf2));
            sr2 -= kSurfG * fSurfR.tapFrac(sBase + sDep1 * fastSin(ph1)    + sDep2 * fastSin(ph2));
            fFarPL = fFarL; fFarPR = fFarR; fFarL = sl; fFarR = sr2;
            }
            // back to full rate: linear interpolation between ocean samples
            const float fr = (float)(fPh + 1) * invM;
            // ...then two one-poles at 5 kHz per side to wash out the interpolation images
            fImL1 += cImg * (fFarPL + (fFarL - fFarPL) * fr - fImL1); fImL2 += cImg * (fImL1 - fImL2);
            fImR1 += cImg * (fFarPR + (fFarR - fFarPR) * fr - fImR1); fImR2 += cImg * (fImR1 - fImR2);
            const float farL = fImL2, farR = fImR2;

            // wet = near call + far ocean; soft-limited (the tank and the throat can peak)
            const float yl = softKnee(fWetG * (fCallG * call + fFarG * farL), 0.8f, 0.15f);
            const float yr = softKnee(fWetG * (fCallG * call + fFarG * farR), 0.8f, 0.15f);
            outL[i] = fDryG * x + yl;
            outR[i] = fDryG * x + yr;
        }
        #undef TAP

        // input level out (for the face), always on, whatever Mode or bypass: a peak follower
        // (instant rise, ~180 ms fall: long enough for MOD's few-times-a-second updates to catch
        // each pluck), mapped -48 dBFS -> 0 .. -12 dBFS -> 1, then ^1.5 so attacks read strong and
        // sustains fade sooner (v2.4; a guitar pluck at about -20 dBFS reads about 0.7)
        {
            const float rel = std::exp(-1.0f / (0.180f * sr));
            for (uint32_t i = 0; i < frames; ++i) {
                const float a = std::fabs(in[i]);
                fLevel = a > fLevel ? a : fLevel * rel;
            }
            fLevel += kAntiDenormal;
            const float dB = 20.0f * std::log10(fLevel + 1e-9f);
            const float lv = clampf((dB + 48.0f) / 36.0f, 0.0f, 1.0f);
            fParams[kInputLevel] = lv * std::sqrt(lv);
        }

        // land the smoothers on their targets
        if (std::fabs(fInG - inT) < 1e-4f) fInG = inT;
        if (std::fabs(fWetG - wetT) < 1e-4f) fWetG = wetT;
        if (std::fabs(fDryG - dryT) < 1e-4f) fDryG = dryT;
    }

    // Depth = distance: pre-delay 0..120 ms, bounces spread 0.5x..2x, wash RT60 2..12 s,
    // darkness 2.5 kHz .. 500 Hz (24 dB/oct), near/far balance
    // (wash RT60 2..8 s since v2.4)
    void updateDepth(float sr, float osr)
    {
        const float d = fDm;
        fPreTarget = 0.120f * d * osr;
        fScaleTarget = (0.5f + 1.5f * d) * 0.001f * osr;         // ocean samples per tap-ms
        const float rt60 = 2.0f * std::pow(5.0f, d);   // 2..10 s set point (v2.4: was 12)
        const float loopT = 21589.0f / (float)kRefRate;
        const float g = std::pow(10.0f, -3.0f * loopT / (4.0f * rt60));
        fLoopG = g > 0.97f ? 0.97f : g;
        const float hc = 2500.0f * std::pow(0.2f, d);
        fLp1.set(hc, 0.5412f, sr);
        fLp2.set(hc, 1.3066f, sr);
        for (int t = 0; t < kTaps; ++t) fTapC[t] = hzCoef(hc * 2.0f * std::pow(0.72f, (float)t), osr);
        fDampCoef = hzCoef(hc, osr);
        fHpCoef = hzCoef(kTankHp, osr);
        fCallG = 1.0f - 0.8f * d;
        fFarG  = 1.0f;
        fBncG  = 0.55f + 0.25f * d;
        fRevG  = 0.20f + 0.30f * d;
    }

private:
    static constexpr float kInLen[4] = { 142.0f, 107.0f, 379.0f, 277.0f };
    static constexpr float kMaxSwoop = 1.0f;        // seconds of swoop delay at most (v2.4: room for 2 octaves)
    static constexpr int   kClearStages = 8;
    static constexpr int   kApStages = 48;
    static constexpr int   kTaps = 6;
    static constexpr float kTapMs[6] = { 0.0f, 23.0f, 51.0f, 89.0f, 137.0f, 199.0f };   // x0.5..x2 with Depth
    static constexpr float kTapG[6]  = { 1.0f, -0.62f, 0.45f, -0.33f, 0.24f, -0.17f };  // surface bounces flip
    static constexpr float kWidth = 0.35f;
    static constexpr float kSurfG = 0.45f;
    static constexpr float kThroatOffG = 0.45f;      // full-range level with Throat Off (matched to Follow by RMS)
    static constexpr float kTankHp = 100.0f;        // Hz: high-pass inside the tank loop (v2.4, tail too resonant)

    float fParams[kParameterCount];

    DelayLine fSwoop, fPre, fBounce, fSurfL, fSurfR;
    Allpass   fIn[4];
    Allpass   fApA1, fApB1, fApA2, fApB2;
    DelayLine fDlA1, fDlB1, fDlA2, fDlB2;
    SvfLP     fLp1, fLp2;
    float     fAp[kApStages][8];
    uint32_t  fApPos = 0, fApK = 2, fM = 2, fPh = 0;
    float     fImL1 = 0.0f, fImL2 = 0.0f, fImR1 = 0.0f, fImR2 = 0.0f;
    float     fOsr = 24000.0f, fFarPL = 0.0f, fFarPR = 0.0f, fFarL = 0.0f, fFarR = 0.0f;
    float     fTapLp[kTaps] = {}, fTapC[kTaps] = {};

    float fSr = 48000.0f, fK = 1.0f;
    float fFast = 0.0f, fSlow = 0.0f, fP1 = 0.0f, fP2 = 0.0f;
    float fIc1 = 0.0f, fIc2 = 0.0f, fA1 = 1.0f, fA2 = 0.0f, fA3 = 0.0f;
    float fDepthS = 0.0f, fDm = 0.5f, fPreS = 0.0f, fPreTarget = 0.0f, fScaleS = 48.0f, fScaleTarget = 48.0f;
    float fLevel = 0.0f;
    float fApA = 0.0f, fThrMix = 1.0f, fThrPos = 0.0f;
    bool  fFirstPos = true;
    float fDampA = 0.0f, fDampB = 0.0f, fHpA = 0.0f, fHpB = 0.0f, fHpCoef = 0.01f;
    float fDampCoef = 0.5f, fLoopG = 0.8f, fCallG = 0.6f, fFarG = 1.0f, fBncG = 0.6f, fRevG = 0.3f;
    float fModA = 0.0f, fModB = 0.25f, fSurf1 = 0.0f, fSurf2 = 0.37f;
    float fInG = 1.0f, fWetG = 0.0f, fDryG = 1.0f;
    uint32_t fCtr = 0;
    int   fClearStage = -1;
    bool  fFirst = true;

    DISTRHO_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(TranceAtlanticPlugin)
};

constexpr float TranceAtlanticPlugin::kInLen[4];
constexpr float TranceAtlanticPlugin::kMaxSwoop;
constexpr int   TranceAtlanticPlugin::kClearStages;
constexpr int   TranceAtlanticPlugin::kApStages;
constexpr int   TranceAtlanticPlugin::kTaps;
constexpr float TranceAtlanticPlugin::kTapMs[6];
constexpr float TranceAtlanticPlugin::kTapG[6];
constexpr float TranceAtlanticPlugin::kWidth;
constexpr float TranceAtlanticPlugin::kSurfG;
constexpr float TranceAtlanticPlugin::kThroatOffG;
constexpr float TranceAtlanticPlugin::kTankHp;

Plugin* createPlugin() { return new TranceAtlanticPlugin(); }

END_NAMESPACE_DISTRHO
