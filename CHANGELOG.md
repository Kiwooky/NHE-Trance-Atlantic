# Changelog

Versions are MOD's plugin versions (lv2:minorVersion.microVersion).

## 2.7 (2026-10-17)

- Five new factory presets: A Million Miles, Whale Call, Just drifting aimlessly, Converging streams, Bouncing of the Floor.
- Settings panel: controls grouped as Envelope (Sense, Swim, Throat, Mode), Pitch (Song, Travel), Reverb (Depth, Scatter) and Mix (Blend, Tails). The ports are renumbered in that order, so the order holds on MOD OS versions without group support too; saved pedalboards and presets are unaffected (MOD saves controls by symbol).
- Footswitch latches: the rest art while the effect runs, the pressed art while bypassed.
- Pedal face: the orb layers stay on their own GPU layers, so the ripples no longer make the whole face flicker in brightness.

## 2.5 (2026-10-10): first repository release

- Three factory presets: Trance Atlantic (the default settings), Choral Reef, Deep sea detune.
- Throat: up to +2 dB make-up at the right-hand end, so Throat 100 stays within 3 dB of bypass at the new defaults.

## 2.4

- Ripples favour the attack: input level falls in about 180 ms, mapped −48 to −12 dBFS, then ^1.5.

## 2.3

- Category: Reverb (the ocean is the part that's always on). New ripples artwork.

## 2.2

- Readouts are pre-rendered image strips instead of a web font, which didn't load on the unit.
- The orb's ripples follow a new always-on Input Level output (replaces the Envelope output).
- Sense knob moved 1 px.

## 2.1

- First pedal face (650 x 400, 2x artwork): status lights, dot-matrix readouts, five-layer orb.

## 2.0

- Renamed from the "Moby Wah" prototype (new URI). Controls renamed: Scatter, Travel, Mode (Off / Fix / Env).

## Moby Wah prototype (2.1 to 2.7, single-file recipes)

- Envelope throat filter, envelope pitch swoop (moving delay), slow-gear bloom.
- The ocean: steep darkness, dispersion, multipath bounces, a soft Dattorro wash, narrow stereo, a moving inverted surface reflection.
- Song up to 24 semitones; Down never reverses. Mode Off disables every envelope-driven part.
