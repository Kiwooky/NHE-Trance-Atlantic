#!/usr/bin/env python3
"""Tests for NHE Trance Atlantic (traits: every, tail, feedback, buffer, level-sensitive,
modulated delay, stereo, mix). Guitar level: pluck_train peaks around -16 dBFS."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
for d in (os.environ.get('PB_TOOLS', ''), os.path.join(HERE, '..', 'tools')):
    if d and os.path.exists(os.path.join(d, 'lv2test.py')):
        sys.path.insert(0, d); break
import numpy as np
from lv2test import Plugin, check, done, db, rms, centroid, pluck_train, tick_count, max_step, rt60, warble_cents
sys.path.insert(0, HERE)
from gtr import gtr_train   # harmonic plucks: a wah needs harmonics to work on

ORDER = ['sense', 'song', 'swim', 'depth', 'scatter', 'throat', 'blend', 'travel', 'mode', 'tails', 'input_level', 'lv2_enabled']
DEF = dict(sense=50, song=5, swim=250, depth=35.83, scatter=80.71, throat=50, blend=76.77, travel=2, mode=2, tails=1, input_level=0, lv2_enabled=1)
p = Plugin(order=ORDER, defaults=DEF, n_in=1, n_out=2)
sr = 48000

def inst_freq(y, sr, win=0.02):
    """pitch track by zero crossings, one value per window"""
    n = int(win * sr); out = []
    for a in range(0, len(y) - n, n // 2):
        s = y[a:a + n]; z = np.where((s[:-1] <= 0) & (s[1:] > 0))[0]
        if len(z) >= 3 and np.abs(s).max() > 1e-4:   # skip silent windows
            fr = z + s[z] / (s[z] - s[z + 1])   # sub-sample crossing
            out.append(sr * (len(fr) - 1) / (fr[-1] - fr[0]))
        else:
            out.append(np.nan)
    return np.array(out)

def tone(sr, f=220.0, secs=1.5, on=0.1, hold=0.8, level=0.1):
    t = np.arange(int(secs * sr)) / sr
    env = np.clip((t - on) / 0.003, 0, 1) * np.clip((on + hold - t) / 0.02, 0, 1)
    return level * env * np.sin(2 * np.pi * f * t)

# ---- swoop: dry-free, reverb nearly off, throat open & broad, so the pitch reads clean
SW = dict(blend=100, depth=0, sense=100, scatter=0)   # dispersion turns any onset into a chirp; keep it out of the pitch read
def swoop_cents(srt, win=0.02, **kw):
    x = tone(srt)
    y = p.run(x, srt, **{**SW, **kw})[:, 0]
    # strip the reverb share by looking at the call only: run again with Song 0 as the reference
    f = inst_freq(y[int(0.12 * srt):int(0.85 * srt)], srt, win)
    c = 1200 * np.log2(f / 220.0)
    # median of 3 windows: the ocean's direct path sums with the call, and where the two nearly
    # cancel, zero crossings spike (a measurement artefact, not a pitch)
    c = np.array([np.median(c[j - 1:j + 2]) if 0 < j < len(c) - 1 and np.isfinite(c[j - 1:j + 2]).all() else np.nan for j in range(len(c))])
    return np.nanmax(c), np.nanmin(c)

for srt in (44100, 48000, 96000):
    up, dn = swoop_cents(srt, song=5, travel=0)
    check('Up: swoops up about 5 st on a full pluck (%d Hz)' % srt, 300 < up < 650 and dn > -250, 'max %+.0f c, min %+.0f c' % (up, dn))
up, dn = swoop_cents(sr, song=5, travel=1)
check('Down: swoops down about 5 st', -650 < dn < -350 and up < 250, 'max %+.0f c, min %+.0f c' % (up, dn))
up, dn = swoop_cents(sr, song=0)
check('Song 0: no swoop (only the reverb warble)', abs(up) < 100 and abs(dn) < 100, 'max %+.0f c, min %+.0f c' % (up, dn))
up12, _ = swoop_cents(sr, song=12, travel=0)
check('Song 12: about an octave', 1000 < up12 < 1350, 'max %+.0f c' % up12)
up24, _ = swoop_cents(sr, song=24, travel=0, swim=200)
# Up starts late and catches up; at big settings the top of the swoop happens before the
# read point reaches the note, so the audible peak is lower than Song (physics of a delay)
check('Song 24 Up: well beyond an octave, audible', 1400 < up24 < 2600, 'max %+.0f c' % up24)
_, dn24 = swoop_cents(sr, win=0.06, song=24, travel=1, swim=200)   # 55 Hz needs longer windows
check('Song 24 Down: dives about two octaves, never reverses', -2600 < dn24 < -1800, 'min %+.0f c' % dn24)

# Arc: up on the attack, down on the release
t = np.arange(int(2.0 * sr)) / sr
x = 0.15 * np.clip((t - 0.1) / 0.003, 0, 1) * np.exp(-np.clip(t - 0.1, 0, None) / 0.35) * np.sin(2 * np.pi * 220 * t)
y = p.run(x, sr, **{**SW, 'sense': 50}, song=5, travel=2)[:, 0]
f = inst_freq(y[int(0.1 * sr):int(1.2 * sr)], sr)
c = 1200 * np.log2(f / 220.0)
first, last = c[:30], c[30:]   # Arc idles ~114 ms late: the call starts behind and catches up
check('Arc: up on attack, down on release', np.nanmax(first) > 300 and np.nanmin(last) < -150,
      'attack max %+.0f c, release min %+.0f c' % (np.nanmax(first), np.nanmin(last)))

# ---- throat follows the envelope: harder picking = brighter call
xs = gtr_train(sr, 4.5)
soft = p.run(0.2 * xs, sr, blend=100, depth=0, song=0)[:, 0]
hard = p.run(xs, sr, blend=100, depth=0, song=0)[:, 0]
cs, ch = centroid(soft[int(0.3*sr):int(0.9*sr)], sr), centroid(hard[int(0.3*sr):int(0.9*sr)], sr)
check('harder picking opens the throat (guitar level)', ch > 1.3 * cs, '%.0f Hz vs %.0f Hz' % (ch, cs))

# ---- Throat switch (v2.5): Off = full range, Fixed = half open whatever you play, Follow = as above
def cents(mode, lvl):
    y = p.run(lvl * xs, sr, blend=100, depth=0, song=0, mode=mode)[:, 0]
    return centroid(y[int(0.3*sr):int(0.9*sr)], sr)
fs_, fh_ = cents(1, 0.2), cents(1, 1.0)
check('Throat Fixed: same colour soft or hard', abs(fh_ / fs_ - 1) < 0.15, '%.0f Hz vs %.0f Hz' % (fh_, fs_))
os_, oh_ = cents(0, 0.2), cents(0, 1.0)
check('Throat Off: same colour soft or hard', abs(oh_ / os_ - 1) < 0.15, '%.0f Hz vs %.0f Hz' % (oh_, os_))
xg = gtr_train(sr, 9.0)
for mode in (0, 1, 2):
    y = p.run(xg, sr, mode=mode)
    g = db(rms(y[:, 0]) / rms(xg))
    check('Throat %s: defaults within 3 dB of bypass' % ['Off', 'Fixed', 'Follow'][mode], abs(g) < 3, '%+.1f dB' % g)
# 5 ms attacks: with 2 ms ones the input itself reads as a tick at -90 dBFS, and Off passes it on
xg5 = gtr_train(sr, 9.0, attack=0.005)
y = p.run(xg5, sr, events=[(int(1.0*sr), 'mode', 0), (int(2.5*sr), 'mode', 1), (int(4.0*sr), 'mode', 2), (int(5.5*sr), 'mode', 0), (int(7.0*sr), 'throat', 0), (int(8.0*sr), 'throat', 100)])
check('switching Mode and sweeping Throat while playing: no ticks', tick_count(y[:, 0], sr) == 0, '%d' % tick_count(y[:, 0], sr))

# ---- Mode Off = no envelope anywhere (v2.7): no swoop, no bloom
up, dn = swoop_cents(sr, song=12, travel=0, mode=0)
check('Off: Song 12 does nothing', abs(up) < 100 and abs(dn) < 100, 'max %+.0f c, min %+.0f c' % (up, dn))
xo = tone(sr, f=1000.0, secs=1.2, hold=1.0)
def eo(sw, mode):
    y = p.run(xo, sr, blend=100, depth=0, song=0, swim=sw, mode=mode)[:, 0]
    return rms(y[int(0.13*sr):int(0.17*sr)])
b = db(eo(1500, 0) / eo(100, 0))
check('Off: Swim does nothing (no bloom)', abs(b) < 1.5, '%+.1f dB at 30-70 ms, Swim 1500 vs 100' % b)
b = db(eo(1500, 1) / eo(100, 1))
check('Fixed: Swim still blooms', b < -8, '%+.1f dB' % b)

# ---- Throat knob (v2.6): centred = as before; left darker/lower (bass), right brighter
xb = gtr_train(sr, 4.5, notes=(41, 55, 73, 49))   # bass notes
def thr_c(x, t):
    y = p.run(x, sr, blend=100, depth=0, song=0, throat=t)[:, 0]
    return centroid(y[int(0.3*sr):int(0.9*sr)], sr)
cl, cc, cr = thr_c(xs, 0), thr_c(xs, 50), thr_c(xs, 100)
check('Throat knob: left darker, right brighter (guitar)', cl < 0.8 * cc and cr > 1.25 * cc, '%.0f / %.0f / %.0f Hz' % (cl, cc, cr))
bl, bc = thr_c(xb, 0), thr_c(xb, 50)
check('Throat left on bass: the throat sits in the bass register', bl < 0.8 * bc, '%.0f Hz vs %.0f Hz at 12 o\'clock' % (bl, bc))
for t in (0, 100):
    y = p.run(xg, sr, throat=t)
    g = db(rms(y[:, 0]) / rms(xg))
    check('Throat %d: within 3 dB of bypass' % t, abs(g) < 3.5, '%+.1f dB' % g)

# ---- Swim: slow swim blooms (call level at 50 ms is lower than at 600 ms)
x = tone(sr, f=1000.0, secs=1.2, hold=1.0)   # near where the throat opens to
def early_late(sw):   # Throat 0 holds the filter still, so this measures the swell alone
    y = p.run(x, sr, blend=100, depth=0, song=0, swim=sw)[:, 0]
    return rms(y[int(0.13*sr):int(0.17*sr)]), rms(y[int(0.65*sr):int(0.75*sr)])
# compare Swim settings with each other: a steady sine sets up fixed call/reverb interference
e1, l1 = early_late(1500)
e0, l0 = early_late(100)
check('Swim 1500 ms blooms: much quieter than Swim 100 ms at first', db(e1 / e0) < -8, '%+.1f dB at 30-70 ms' % db(e1 / e0))
e2, l2 = early_late(250)
check('Swim 250 ms has arrived by 600 ms (sine + reverb interference: +-4 dB)', abs(db(l2 / l0)) < 4, '%+.1f dB vs Swim 100 at 550-650 ms' % db(l2 / l0))
check('Swim 1500 ms is still blooming at 600 ms', db(l1 / l0) < -4, '%+.1f dB' % db(l1 / l0))

# ---- Depth: decay grows with Depth, outputs decorrelated
x = np.zeros(int(14 * sr)); x[int(0.1*sr):int(0.1*sr)+int(0.03*sr)] = 0.3 * np.random.default_rng(3).standard_normal(int(0.03*sr))
prev = 0
for dep in (0, 50, 100):
    y = p.run(x, sr, blend=100, depth=dep, song=0, sense=100)
    t = rt60(y[int(0.3*sr):, 0], sr)
    check('Depth %d: tail decays (RT60, longer with Depth, at most ~8 s)' % dep, prev < t < 9.0, '%.1f s' % t)
    prev = t
corr = np.corrcoef(y[int(0.5*sr):int(3*sr), 0], y[int(0.5*sr):int(3*sr), 1])[0, 1]
check('narrow image (underwater: from everywhere), but not mono', 0.4 < corr < 0.97, 'corr %.2f' % corr)

# ---- dispersion: lows arrive after highs (a falling chirp); the dial sets how much
from scipy.signal import butter, sosfilt
def band_lag(disp, srt=sr):
    """ms the 150-300 Hz band arrives after the 1-2 kHz band, on the ocean's direct arrival
    (Depth 100: the ocean starts 120 ms after the near call, so the near call is out of the window)"""
    xi = np.zeros(int(1.0 * srt)); xi[int(0.1 * srt)] = 0.5
    y = p.run(xi, srt, blend=100, depth=100, song=0, sense=0, scatter=disp)[:, 0]
    def arrival(lo, hi):
        e = np.abs(sosfilt(butter(4, [lo, hi], 'bandpass', fs=srt, output='sos'), y))
        e = np.convolve(e, np.ones(int(0.002 * srt)) / int(0.002 * srt), 'same')
        a = int(0.2 * srt)
        return (a + int(np.argmax(e[a:int(0.3 * srt)]))) / srt
    return 1e3 * (arrival(150, 300) - arrival(1000, 2000))
base = band_lag(0)   # the darkness filters alone delay the lows a little
for srt in (44100, 48000, 96000):
    l40, l100 = band_lag(40, srt) - band_lag(0, srt), band_lag(100, srt) - band_lag(0, srt)
    check('Scatter dial grows the chirp (%d Hz)' % srt, 10 < l40 < l100 and 35 < l100 < 90,
          'lows extra-late by %+.1f ms at 40, %+.1f ms at 100' % (l40, l100))
check('Scatter 0: only the filters\' own lag', abs(base) < 20, '%+.1f ms' % base)


# ---- the far reverb: dark and warbly, not a cave (first hardware test)
t = np.arange(int(4 * sr)) / sr
x = 0.1 * np.clip(t / 0.01, 0, 1) * np.clip((2.0 - t) / 0.01, 0, 1) * np.sin(2 * np.pi * 440 * t)
y = p.run(x, sr, blend=100, depth=100, song=0, sense=100)[:, 0]
tail = y[int(2.3 * sr):int(3.5 * sr)]
wc = warble_cents(y[int(1.0 * sr):int(1.9 * sr)], sr, 440)   # tail-only reads ~20 c even unmodulated; during the note reads 3 c unmodulated (calibrated)
check('far ocean warbles slightly (Depth 100, held note)', 10 < wc < 40, '%.1f cents' % wc)
n = 0.05 * np.random.default_rng(5).standard_normal(int(4 * sr)) * (np.arange(int(4 * sr)) < 2 * sr)
y = p.run(n, sr, blend=100, depth=50, song=0, sense=100)[:, 0]
F = np.abs(np.fft.rfft(y[int(2.2 * sr):int(3.4 * sr)])) ** 2; fr = np.fft.rfftfreq(int(1.2 * sr), 1 / sr)
hi = db(np.sqrt(F[fr > 3000].sum() / F[(fr > 150) & (fr < 1000)].sum()))
check('Depth 50 tail: little above 3 kHz', hi < -30, '%.1f dB vs 150 Hz-1 kHz' % hi)

# ---- tail not resonant: lows drain inside the tank (v2.4)
n = 0.05 * np.random.default_rng(2).standard_normal(int(6 * sr)) * (np.arange(int(6 * sr)) < 2 * sr)
yn = p.run(n, sr, blend=100, depth=100)[:, 0]
seg = yn[int(2.1 * sr):int(3.1 * sr)]; F = np.abs(np.fft.rfft(seg)) ** 2; fr = np.fft.rfftfreq(len(seg), 1 / sr)
boom = db(np.sqrt(F[(fr > 40) & (fr < 160)].sum() / F[(fr > 160) & (fr < 800)].sum()))
check('Depth 100 tail: lows below 160 Hz well under the mids (no boom)', boom < -5, '%.1f dB' % boom)

# ---- Input Level output (face ripples): follows the input, in every Mode and in bypass
import subprocess, tempfile
def level_trace(x, **kw):
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, PB_TRACE_FILE=os.path.join(d, 't.raw'), PB_TRACE_PORT=str(3 + ORDER.index('input_level')))
        os.environ.update(env); p.run(x, sr, **kw)
        v = np.fromfile(env['PB_TRACE_FILE'], np.float32)
        del os.environ['PB_TRACE_FILE'], os.environ['PB_TRACE_PORT']
        return v
xl = gtr_train(sr, 3.0)
for kw in ({}, dict(mode=0), dict(lv2_enabled=0)):
    v = level_trace(xl, **kw)
    blk = 256 / sr
    peak = v[int(0.25 / blk):int(0.45 / blk)].max(); quiet = v[int(0.05 / blk):int(0.15 / blk)].max()
    check('Input Level %s: guitar pluck reads high, silence reads 0' % (kw or 'defaults'), 0.6 < peak <= 1.0 and quiet < 0.05, 'pluck %.2f, before %.2f' % (peak, quiet))
v = level_trace(0.2 * xl)
# v2.4: attacks strong, sustain fades sooner: 0.5 s into a pluck it has dropped well below the attack
vd = level_trace(xl); blk = 256 / sr
att, sus = vd[int(0.21 / blk):int(0.3 / blk)].max(), vd[int(0.85 / blk):int(0.95 / blk)].max()
check('Input Level: sustain (0.7 s in) well below the attack', sus < 0.6 * att, 'attack %.2f, sustain %.2f' % (att, sus))
check('Input Level: softer playing reads lower', 0.1 < v[int(0.25 / (256 / sr)):int(0.45 / (256 / sr))].max() < 0.6, '%.2f' % v[int(0.25 / (256 / sr)):int(0.45 / (256 / sr))].max())

# ---- [every] loudness at defaults within 3 dB of bypass (RMS, guitar level)
xp = gtr_train(sr, 9.0)
y = p.run(xp, sr)
g = db(rms(y[:, 0]) / rms(xp)), db(rms(y[:, 1]) / rms(xp))
check('defaults within 3 dB of bypass', all(abs(v) < 3 for v in g), 'L %+.1f dB, R %+.1f dB' % g)

# ---- [every][mix][tail] bypass: dry at unity whatever Blend, click-free; tails ring or fade
x = 0.1 * np.sin(2 * np.pi * 220 * np.arange(int(2.5 * sr)) / sr)
for tails in (1, 0):
    for bl in (50, 100):
        y = p.run(x, sr, tails=tails, blend=bl, events=[(sr, 'lv2_enabled', 0)])
        a, b = int(1.5 * sr), int(2.4 * sr)
        resid = np.abs(y[a:b, 0] - x[a:b]).max()
        stp = max_step(y[int(0.98*sr):int(1.05*sr), 0])
        ok = (resid < 1e-3) if not tails else (resid > 1e-3)   # tails: the wet still rings
        check('bypass tails=%d blend=%d: dry at unity, tail %s, no click' % (tails, bl, 'rings' if tails else 'gone'),
              ok and stp < 1.5 * max_step(x[:sr]) + 0.02, 'resid %.4f, step %.3f' % (resid, stp))

# re-engage after tails-off clear: comes back cleanly
y = p.run(x, sr, tails=0, events=[(int(0.5*sr), 'lv2_enabled', 0), (int(1.5*sr), 'lv2_enabled', 1)])
check('re-engage after Tails-off clear is finite and click-free', np.isfinite(y).all() and max_step(y[int(1.48*sr):int(1.6*sr), 0]) < 0.1)

# ---- [every] first run: bypassed from sample 0 = exactly dry
y = p.run(x, sr, lv2_enabled=0)
check('first run bypassed: dry from sample 0', np.abs(y[:, 0] - x).max() < 1e-5)

# ---- [every][feedback] torture: extremes, hot input, three rates: finite and under 0 dBFS
for srt in (44100, 48000, 96000):
    xt = 0.8 * np.random.default_rng(1).standard_normal(int(3 * srt))
    y = p.run(xt, srt, sense=100, song=24, swim=2000, depth=100, blend=100)
    check('torture %d Hz' % srt, np.isfinite(y).all() and np.abs(y).max() < 1.0, 'peak %.2f' % np.abs(y).max())
# knobs moving while playing
ev = [(int(t * sr), k, v) for t, k, v in [(1, 'song', 24), (1.5, 'swim', 100), (2, 'depth', 100), (2.5, 'travel', 1),
                                          (3.5, 'swim', 2000), (4, 'depth', 0), (4.5, 'song', 0)]]
y = p.run(xp, sr, events=ev)
check('knob moves while playing: finite', np.isfinite(y).all(), 'peak %.2f' % np.abs(y).max())

# ---- [every] no ticks with plucks, at defaults and at full song
# (song 12 uses sine plucks: an octave swoop lifts the harmonic plucks' real 8 kHz partials
#  to 16 kHz at -89 dBFS, which tick_count reads as a tick; checked by hand, not a click)
for kw in ({}, dict(song=12, swim=100, blend=100)):
    # 5 ms attacks: the 2 ms harmonic plucks read as a tick on their own (-90 dBFS treble)
    y = p.run(gtr_train(sr, 9.0, attack=0.005) if not kw else pluck_train(sr, 9.0), sr, **kw)
    n = tick_count(y[:, 0], sr)
    check('no ticks %s' % (kw or 'defaults'), n == 0, '%d' % n)
    check('under 0 dBFS %s' % (kw or 'defaults'), np.abs(y).max() < 1.0, '%.1f dBFS' % db(np.abs(y).max()))

# ---- [every] silence
y = p.run(np.zeros(sr), sr)
check('silence in, silence out', np.abs(y).max() < 1e-6)
done()
