# Trance Atlantic: design

**URI** `https://github.com/Kiwooky/NHE-Trance-Atlantic` · **Maker** New Horizon Electronics · **Licence** GPL-3.0-or-later
**Traits** every plugin, tail, feedback (reverb tank), buffer, level-sensitive, modulated delay, stereo, mix.
Mono in, stereo out. Duo, Duo X, Dwarf.

## Signal flow

```
in --+-------------------------------------------------- dry ----------------(+)--> out L/R
     +-> envelopes (fast 1/120 ms, slow = Swim, 2-pole pitch env)                ^
     +-> throat SVF -> swoop delay -> swell = call --+--- near call -------------+ wet (soft-limited)
                                                     +-> the ocean --------------+
```

The ocean (runs at half the sample rate, a quarter at 96 kHz): pre-delay -> 24 dB/oct low-pass ->
48 stretched first-order all-passes (dispersion) -> six multipath taps (alternating polarity,
each darker) -> Dattorro tank fed by the late taps (high-pass in the loop) -> narrow stereo
(side x 0.35) -> per-side inverted surface reflection drifting 2..10 ms.

## Controls

| Port | Range | Default | Mapping |
| --- | --- | --- | --- |
| sense | 0..100 % | 50 | detector gain 10 x 10^((s - 50)/50) |
| song | 0..24 st | 5 | peak swoop at a full pluck; Up/Arc: depth = (r - 1) Swim / 0.736, Down: (1 - 1/r) Swim / 0.736, capped at 1 s |
| swim | 100..2000 ms (log) | 250 | slow-env rise; fall 2x (at least 150 ms); pitch env 2 x one-pole at Swim/2 |
| depth | 0..100 % | 35.83 | pre-delay 0..120 ms; taps x0.5..x2; wash RT60 set point 2..10 s (measured about 2 / 3.9 / 5.7 s); darkness 2.5 kHz..500 Hz |
| scatter | 0..100 % | 80.71 | all-pass delay per stage D = 1 + 15 s; a = (1 - D)/(1 + D) |
| throat | 0..100 % | 50 | +-1.5 octave shift, Q 3.3 x 2^(0.8 t); level match below centre, +2 dB at full right |
| blend | 0..100 % | 76.77 | wet = min(1, 2b), dry = min(1, 2(1 - b)) |
| travel | Up / Down / Arc | Arc | Arc falls as fast as it rises; Up/Down fall 4x slower |
| mode | Off / Fix / Env | Env | Off: no throat, swoop or bloom; Fix: throat at mid position |
| tails | toggle | on | bypass lets the ocean ring out |
| input_level (out) | 0..1 | | peak follower, 180 ms fall, (dB + 48)/36 then ^1.5; drives the face's ripples |
| lv2_enabled | bypass | 1 | ~10 ms crossfade, dry at unity |

## Measured (tests/test_nhe_trance_atlantic.py)

- Swoop: Song 5 Up = +5 st at 44.1, 48, 96 kHz; Song 24 Down dives about 21 st.
- Scatter: lows arrive 17 ms (40 %) / 36 ms (100 %) after highs, same at all rates.
- Defaults within 0.5 dB of bypass (RMS, guitar level).
- CPU on the Duo build: about 1.4 to 1.5 x NHE Taj Mahal (relative, under emulation).
