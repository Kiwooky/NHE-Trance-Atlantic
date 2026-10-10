import numpy as np
def gtr_train(sr, seconds=9.0, level=0.15, notes=(196, 247, 147, 330, 220, 165), every=1.5, decay=0.6, attack=0.002):
    """Harmonic guitar-ish plucks: 24 harmonics at 1/n, higher ones dying faster;
    peaks at `level` (0.15 = about -16 dBFS, a guitar into a MOD). A wah needs harmonics
    to work on; the playbook's pluck_train is pure sines."""
    x = np.zeros(int(seconds * sr))
    for k, f in enumerate(notes):
        n = int((0.2 + every * k) * sr)
        L = min(int(1.4 * sr), len(x) - n)
        if L <= 0: break
        t = np.arange(L) / sr
        s = np.zeros(L)
        for h in range(1, 25):
            if h * f > 0.45 * sr: break
            s += np.sin(2 * np.pi * h * f * t + 0.3 * h) / h * np.exp(-t / (decay / h ** 0.6))
        env = np.minimum(1, t / attack) * np.minimum(1, (t[-1] - t) / 0.05)
        s *= env
        x[n:n + L] += s / np.abs(s).max() * level
    return x
