# Trance Atlantic: developer notes

Not needed to play it; for anyone building, testing or debugging.

## Testing

```sh
tools/check.sh --src plugins/nhe-trance-atlantic --bundle bundle/nhe-trance-atlantic.lv2 --test tests/test_nhe_trance_atlantic.py
python3 tools/face_click_test.py bundle/nhe-trance-atlantic.lv2
```

`check.sh` builds native, Duo (arm32) and Duo X/Dwarf (arm64) through the builder's own hooks, compares the TTL with DPF's generator, and runs the 58 audio tests natively and on the Duo build under qemu. It also writes `dist/nhe-trance-atlantic.mk`, a single-file recipe for builder.mod.audio that needs no commit hash. `face_click_test.py` clicks every control with mod-ui's own widget code (mouse, wobbly mouse, touch). Packages needed: `g++ g++-arm-linux-gnueabihf g++-aarch64-linux-gnu qemu-user lilv-utils`, Python `numpy scipy rdflib` (plus `playwright pillow` for the face tests).

## Performance

- **CPU:** on the Duo build, about 1.4 to 1.5 times NHE Taj Mahal (relative benchmark under emulation; the unit's own CPU meter is the real number). The ocean runs at half the sample rate (a quarter at 96 kHz): everything in it sits below 2.5 kHz.

## Known issues

- **Frozen ripples on MOD OS 1.14:** if the orb's ripples stop moving, the web interface has missed a `data_ready` handshake and is no longer receiving output values from the unit. The sound is not affected. Reload with every other MOD tab closed, reboot, or release it from the browser console:
  ```
  for (var n = 0; n <= 5000; n++) ws.send('data_ready ' + n)
  ```
- **Checking the ripples' data path:** in the browser console, `ws.addEventListener('message', function (e) { if (e.data.indexOf('input_level') > 0) console.log(e.data) })` prints the Input Level values as they arrive. The plugin only sends a value when it changes, so silence prints nothing.

## Face

- Readouts are pre-rendered image strips (Song #00 to #24; OFF / FIX / ENV), not a web font, so they work in every browser.
- The orb's top layer follows the plugin's **Input Level** output (port `input_level`, listed in `modgui:monitoredOutputs`): a peak follower with instant rise and about 180 ms fall, mapped −48 to −12 dBFS, then raised to the power 1.5 so attacks read strong and sustains fade sooner.
- Images are 2x, drawn at 1x size (650 x 400). Knobs: 128-frame horizontal strip.

## Recipe size

- The builder at builder.mod.audio silently refused a 998 KB recipe (status went from "preparing" straight to "ready"); 888 KB and below built. Keep the `.mk` well under 1 MB; save PNGs as 256-colour (palette) images.
