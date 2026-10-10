"""Reusable offline audio tests for MOD plugins (via tools/lv2host).

In a plugin's test script:

    from lv2test import Plugin, check, done, db, rms, centroid, tick_count, warble_cents, pluck_train, rt60, onset_ms
    p = Plugin(order=['time', 'feedback', 'mix', 'tails', 'lv2_enabled'],
               defaults=dict(time=350, feedback=40, mix=35, tails=1, lv2_enabled=1),
               n_in=1, n_out=1)
    y = p.run(x, sr=48000, feedback=0)              # returns (frames, n_out)
    check('first echo at 350 ms', ..., 'info')
    done()                                          # prints the summary, exits 1 on failure

Which build is tested comes from the environment (tools/check.sh sets these):
    PB_SO   path to <bundle>_dsp.so
    PB_HOST host command, e.g. "tools/lv2host" or "qemu-arm -L /usr/arm-linux-gnueabihf tools/lv2host-arm"

Lessons baked in (see docs/testing.md):
  - test at guitar level (about -20 dBFS peaks), not just hot signals
  - test signals need smooth envelopes, or you will find your own edges
  - a hardware report becomes a failing test first, then the fix
"""
import os, subprocess, sys, tempfile
import numpy as np

_fails = 0
_passes = 0


class Plugin:
    def __init__(self, order, defaults, n_in=1, n_out=1, so=None, host=None):
        self.order = list(order)
        self.defaults = dict(defaults)
        self.port = {k: n_in + n_out + i for i, k in enumerate(self.order)}
        self.n_in, self.n_out = n_in, n_out
        self.so = so or os.environ.get('PB_SO')
        self.host = (host or os.environ.get('PB_HOST', 'tools/lv2host')).split()
        if not self.so:
            sys.exit('set PB_SO to the plugin .so (tools/check.sh does this)')

    def run(self, x, sr=48000, events=(), **controls):
        """x: (frames,) or (frames, n_in). events: [(sample, symbol, value), ...]"""
        unknown = set(controls) - set(self.order)
        if unknown:
            raise KeyError('unknown control(s): %s' % ', '.join(sorted(unknown)))
        c = dict(self.defaults); c.update(controls)
        x = np.asarray(x, np.float32)
        if x.ndim == 1:
            x = x[:, None].repeat(self.n_in, 1)
        with tempfile.TemporaryDirectory() as d:
            fi, fo = os.path.join(d, 'i.raw'), os.path.join(d, 'o.raw')
            x.tofile(fi)
            args = self.host + [self.so, fi, fo, str(sr), str(self.n_in), str(self.n_out)]
            args += ['%g' % c[k] for k in self.order]
            args += ['@%d:%d=%g' % (s, self.port[k], v) for s, k, v in events]
            subprocess.run(args, check=True, stdout=subprocess.DEVNULL)
            return np.fromfile(fo, np.float32).reshape(-1, self.n_out)


def check(name, ok, info=''):
    global _fails, _passes
    print('%s  %s  %s' % ('PASS' if ok else 'FAIL', name, info), flush=True)
    if ok:
        _passes += 1
    else:
        _fails += 1


def done():
    print('\n%d passed, %d failure(s)' % (_passes, _fails))
    sys.exit(1 if _fails else 0)


def db(v):
    return 20 * np.log10(max(float(v), 1e-12))


def rms(v):
    return float(np.sqrt(np.mean(np.square(np.asarray(v, np.float64)))))


def centroid(seg, sr):
    """Spectral centroid (Hz): a quick brightness measure."""
    s = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    f = np.fft.rfftfreq(len(seg), 1 / sr)
    return float((s * f).sum() / max(s.sum(), 1e-12))


def pluck_train(sr, seconds=10.0, level=0.15, notes=(196, 247, 147, 330, 220, 165), every=1.5):
    """Guitar-ish plucks with smooth envelopes (2 ms attack, 50 ms release).
    level 0.15 peaks around -16 dBFS, roughly a guitar into a MOD input."""
    t = np.arange(int(seconds * sr))
    x = np.zeros(len(t))
    for k, f in enumerate(notes):
        n = int((0.2 + every * k) * sr)
        L = min(int(1.2 * sr), len(x) - n)
        if L <= 0:
            break
        a = np.arange(L)
        env = np.exp(-a / (0.3 * sr)) * np.minimum(1, a / (0.002 * sr)) * np.minimum(1, (L - a) / (0.05 * sr))
        x[n:n + L] += level * env * np.sin(2 * np.pi * f * a / sr)
    return x


def tick_count(w, sr=48000, threshold=10.0):
    """Count ticks: moments where >12 kHz energy is out of all proportion to the
    signal around it. Clicks, hard-clip corners and aliasing edges are almost
    all treble; a bright pluck or cymbal is not. A burst counts when the local
    treble share (HF / total energy) jumps above `threshold` times its typical
    value nearby and the treble is above -90 dBFS. Edges excluded."""
    from scipy.signal import butter, sosfilt
    w = np.asarray(w, np.float64)
    hp = butter(4, 12000, 'highpass', fs=sr, output='sos')
    h = sosfilt(hp, w)
    L = max(int(0.002 * sr), 8)
    k = np.ones(L) / L
    e_hf = np.convolve(h ** 2, k, 'same')
    e_all = np.convolve(w ** 2, k, 'same')
    share = e_hf / (e_all + 1e-12)
    B = int(0.1 * sr)
    typical = np.convolve(share, np.ones(B) / B, 'same') + 1e-6
    hit = (share / typical > threshold) & (e_hf > 1e-9)
    idx = np.nonzero(hit[B:-B])[0]
    gap = int(0.05 * sr)
    return len([i for j, i in enumerate(idx) if j == 0 or i - idx[j - 1] > gap])


def warble_cents(w, sr, f0, skip=0.0):
    """RMS pitch deviation (cents) of a steady sine at f0, e.g. a delay's wow/flutter."""
    from scipy.signal import hilbert
    from scipy.ndimage import uniform_filter1d
    seg = np.asarray(w[int(skip * sr):], np.float64)
    f = np.diff(np.unwrap(np.angle(hilbert(seg)))) * sr / 2 / np.pi
    c = 1200 * np.log2(np.abs(uniform_filter1d(f, int(0.01 * sr))[2000:-2000]) / f0)
    return float(c.std())


def rt60(w, sr):
    """Reverb time from an impulse response (Schroeder backward integration, T30 x 2).

    w: (frames,) or (frames, channels); channels are summed in energy. Needs at least
    35 dB of clean decay in the render (render long enough, test with Vintage/noise off).
    Reference (a hall reverb): 5.63 / 5.58 / 5.72 s at 44.1 / 48 / 96 kHz for one setting.
    """
    e = np.asarray(w, dtype=float) ** 2
    if e.ndim > 1:
        e = e.sum(axis=1)
    edc = np.cumsum(e[::-1])[::-1]
    edc = 10 * np.log10(edc / edc[0] + 1e-30)
    i5, i35 = np.argmax(edc < -5), np.argmax(edc < -35)
    return (i35 - i5) / sr * 2


def onset_ms(w, sr, frac=0.01):
    """First sample above frac x the peak, in ms: pre-delay and latency checks."""
    a = np.abs(np.asarray(w, dtype=float))
    if a.ndim > 1:
        a = a.sum(axis=1)
    return float(np.argmax(a > a.max() * frac)) / sr * 1000


def max_step(w):
    """Largest sample-to-sample jump: compare against the signal's own steps for click checks."""
    return float(np.abs(np.diff(np.asarray(w, np.float64))).max())
