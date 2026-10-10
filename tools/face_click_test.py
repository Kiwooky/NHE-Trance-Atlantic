#!/usr/bin/env python3
"""Click every control on a modgui face, using mod-ui's own widget code, and
report what each click does. Catches faces that look right but play wrong:
toggles that drop clicks when the mouse moves slightly (the film widget treats
a 2 px wobble as a drag), multi-position switches that only step forward and
wrap, controls driven by a face script that don't respond, and face scripts that
throw.

    python3 tools/face_click_test.py <bundle>.lv2 [--mod-ui <mod-ui checkout>]

Needs: pip install playwright rdflib; python3 -m playwright install chromium.
mod-ui is cloned to $PB_CACHE/mod-ui (default ~/.cache/mod-playbook) if not given.

How it works: the page loads mod-ui's html/js/lib/jquery-1.9.1.min.js and
html/js/modgui.js, renders the face template with its stylesheet, and binds each
mod-role="input-control-port" element with $(el).controlWidget({port, change})
exactly as mod-ui does (port data from the TTL). The face script, if any, is
evaluated the way mod-ui does ('method = ' + code) and started with a jQuery
icon and funcs.set_port_value, behaving as mod-ui does: event.data is one
object kept for the face's lifetime, and a value the script sets with
set_port_value is NOT reported back to it as a 'change' (mod-ui's "from-js"
source). Then each control is clicked at its centre twice cleanly and twice with
a 2 px mouse wobble between press and release, starting from its TTL default,
and every toggle is tapped four times on a touch screen.

Controls drawn by the face script instead of a mod-role widget are found by
any attribute whose value is the port symbol (e.g. <div my-switch="tails">):
script toggles get the same click and tap checks; other script-driven ports
(button banks, click zones) are clicked one element at a time, cleanly and then
with a wobble.

Result per control:
  toggles       FAIL if any click (clean or wobbly) leaves the value unchanged;
                momentary ports must go on at press and off at release
  enumerations  clicked at three spots (top/middle/bottom, or left/middle/right):
                FAIL if a wobbly click is dropped or picks a different value;
                NOTE if clicks only step forward and wrap (a position can't be picked)
  knobs         info only (a click on a film knob steps it by one)
  script-driven FAIL if a toggle doesn't change on every click and tap, if a
                wobbly click gives a different value from a clean one, or if no
                element of the port ever sets a value
The bypass (lv2:enabled) port is skipped: mod-ui's bypass widget handles it.
Exit code 1 on any FAIL or a script error.
"""
import argparse, json, os, re, subprocess, sys, tempfile, asyncio
import rdflib

L = rdflib.Namespace('http://lv2plug.in/ns/lv2core#')
MG = rdflib.Namespace('http://moddevices.com/ns/modgui#')
RDF = rdflib.RDF
RDFS = rdflib.RDFS


def load_bundle(bundle):
    g = rdflib.Graph()
    for fn in os.listdir(bundle):
        if fn.endswith('.ttl'):
            g.parse(os.path.join(bundle, fn), format='turtle')
    gui = next(g.objects(None, MG['gui']))

    def rel(k):
        v = g.value(gui, MG[k])
        if v is None:
            return None
        p = str(v).replace('file://', '')
        return p if os.path.isabs(p) else os.path.join(bundle, p)

    ports = {}
    for p in g.objects(None, L['port']):
        sym = g.value(p, L['symbol'])
        if sym is None or (p, RDF.type, L['ControlPort']) not in g or (p, RDF.type, L['InputPort']) not in g:
            continue
        if g.value(p, L['designation']) is not None:   # lv2:enabled = the bypass widget, tested by mod-ui itself
            continue
        props = [str(o).split('#')[-1] for o in g.objects(p, L['portProperty'])]
        sps = sorted(({'value': float(g.value(s, RDF.value)), 'label': str(g.value(s, RDFS.label))}
                      for s in g.objects(p, L['scalePoint'])), key=lambda d: d['value'])
        ports[str(sym)] = {
            'symbol': str(sym),
            'ranges': {'minimum': float(g.value(p, L['minimum'])), 'maximum': float(g.value(p, L['maximum'])),
                       'default': float(g.value(p, L['default']))},
            'properties': props, 'scalePoints': sps,
        }
    return {'res': rel('resourcesDirectory'), 'html': rel('iconTemplate'), 'css': rel('stylesheet'),
            'js': rel('javascript'), 'ports': ports}


def mod_ui_path(arg):
    if arg:
        return arg
    cache = os.environ.get('PB_CACHE', os.path.expanduser('~/.cache/mod-playbook'))
    path = os.path.join(cache, 'mod-ui')
    if not os.path.isdir(path):
        os.makedirs(cache, exist_ok=True)
        subprocess.run(['git', 'clone', '-q', '--depth', '1', 'https://github.com/mod-audio/mod-ui.git', path], check=True)
    return path


PAGE = r'''<html><head><meta charset="utf-8">
<script src="file://%(modui)s/html/js/lib/jquery-1.9.1.min.js"></script>
<script>var isSDK = true, desktop = null, VERSION = 'test';</script>
<script src="file://%(modui)s/html/js/modgui.js"></script>
<style>body{margin:0}%(css)s</style></head><body>%(html)s
<script>
window.log = []; window.errors = [];
var PORTS = %(ports)s;
var root = $('[class*="mod-pedal"]').first();
function bind(el, port) {
  $(el).controlWidget({ port: port, dummy: false,
    change: function (e, v) { log.push([port.symbol, v]); fire({ type: 'change', symbol: port.symbol, value: v }); } });
}
$('[mod-role="input-control-port"]').each(function () {
  var p = PORTS[this.getAttribute('mod-port-symbol')]; if (p) bind(this, p);
});
var method = null, code = %(script)s;
if (code) { try { eval('method = ' + code); } catch (e) { errors.push('script does not parse: ' + e); } }
var VALUES = {}; Object.keys(PORTS).forEach(function (k) { VALUES[k] = PORTS[k].ranges['default']; });
var DATA = {};   // mod-ui keeps one event.data per face (this.jsData)
var funcs = { set_port_value: function (s, v) {
  // as mod-ui's setPortValue(symbol, value, "from-js"): clamp, skip if unchanged,
  // update widgets, and do NOT send a 'change' event back to the script
  var p = PORTS[s]; if (!p) return;
  v = Math.min(p.ranges.maximum, Math.max(p.ranges.minimum, v));
  if (VALUES[s] === v) return;
  VALUES[s] = v; log.push([s, v]);
  $('[mod-role="input-control-port"][mod-port-symbol="' + s + '"]').controlWidget('setValue', v, true); } };
function fire(ev) {
  if (ev.type === 'change') VALUES[ev.symbol] = ev.value;
  if (!method) return;
  ev.icon = root; ev.data = DATA; ev.api_version = 3;
  try { method(ev, funcs); } catch (e) { errors.push('script threw on ' + ev.type + ': ' + e); method = null; }
}
setTimeout(function () {
  var ports = Object.keys(PORTS).map(function (k) { return { symbol: k, value: PORTS[k].ranges['default'] }; });
  fire({ type: 'start', ports: ports, parameters: [] });
  window.ready = true;
}, 300);
</script></body></html>'''


async def run(info, modui):
    from playwright.async_api import async_playwright
    res = os.path.abspath(info['res'])
    css = open(info['css']).read().replace('{{{cns}}}', '').replace('{{{ns}}}', '')
    css = re.sub(r'url\(/resources/([^)]+)\)', lambda m: 'url(file://%s/%s)' % (res, m.group(1)), css)
    html = open(info['html']).read()
    html = re.sub(r'\{\{#.*?\}\}.*?\{\{/.*?\}\}', '', html, flags=re.S).replace('{{{cns}}}', '').replace('{{{ns}}}', '')
    script = open(info['js']).read() if info['js'] and os.path.exists(info['js']) else ''
    page_html = PAGE % {'modui': os.path.abspath(modui), 'css': css, 'html': html,
                        'ports': json.dumps(info['ports']), 'script': json.dumps(script)}
    fails, notes = [], []
    with tempfile.TemporaryDirectory() as td:
        fn = os.path.join(td, 'face.html')
        open(fn, 'w').write(page_html)
        async with async_playwright() as p:
            b = await p.chromium.launch()
            ctx = await b.new_context(viewport={'width': 1400, 'height': 1000}, has_touch=True)
            pg = await ctx.new_page()
            pageerr = []
            pg.on('pageerror', lambda e: pageerr.append(str(e)))
            await pg.goto('file://' + fn)
            await pg.wait_for_function('window.ready === true', timeout=5000)
            await pg.wait_for_timeout(300)
            cur = {s: p['ranges']['default'] for s, p in info['ports'].items()}

            async def script_elements(sym):
                # elements with any attribute (other than mod-port-symbol) whose value is the symbol
                return await pg.query_selector_all('xpath=//*[@*[name()!="mod-port-symbol" and .="%s"]]' % sym)

            async def press(sym, x, y, wobble=0, touch=False):
                await pg.evaluate('log = []')
                if touch:
                    await pg.touchscreen.tap(x, y)
                    held = []
                else:
                    await pg.mouse.move(x, y)
                    await pg.mouse.down()
                    held = [v for s, v in await pg.evaluate('log.slice()') if s == sym]
                    if wobble:
                        await pg.mouse.move(x + 1, y - wobble)
                    await pg.mouse.up()
                await pg.wait_for_timeout(60)
                after = [v for s, v in await pg.evaluate('log') if s == sym]
                if after:
                    cur[sym] = after[-1]
                return held, after, cur[sym]

            for sym, port in info['ports'].items():
                el = await pg.query_selector('[mod-role="input-control-port"][mod-port-symbol="%s"]' % sym)
                if el is None:
                    els = await script_elements(sym)
                    if not els:
                        notes.append('%-14s not on the face (settings only)' % sym)
                        continue
                    props = port['properties']
                    steppers = [e for e in els if await e.evaluate('el => Array.prototype.some.call(el.attributes, a => /step/.test(a.name))')]
                    if steppers:
                        # a step button (attribute name contains "step", e.g. ta-step="mode"): every
                        # press, clean, wobbly or tapped, must move to a new value
                        box = await steppers[0].bounding_box()
                        cx, cy = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
                        seq, ok = [], True
                        for w, t in ((0, 0), (0, 0), (2, 0), (2, 0), (0, 1), (0, 1)):
                            before = cur[sym]
                            _, _, v = await press(sym, cx, cy, w, bool(t))
                            seq.append('%s%g' % ('~' if w else '^' if t else '', v))
                            ok &= v != before
                        await pg.wait_for_timeout(1200)
                        line = '%-14s script step   after each press (~ = wobble, ^ = touch tap): %s' % (sym, ', '.join(seq))
                        (notes if ok else fails).append(line if ok else 'FAIL ' + line)
                        els = [e for e in els if e not in steppers]
                        if not els:
                            continue
                    if 'toggled' in props or (len(els) == 1 and len(port['scalePoints']) == 2):
                        box = await els[0].bounding_box()
                        cx, cy = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
                        seq, ok = [], True
                        for w, t in ((0, 0), (0, 0), (2, 0), (2, 0), (0, 1), (0, 1), (0, 1), (0, 1)):
                            before = cur[sym]
                            _, _, v = await press(sym, cx, cy, w, bool(t))
                            seq.append('%s%g' % ('~' if w else '^' if t else '', v))
                            ok &= v != before
                        await pg.wait_for_timeout(1200)   # scripts often ignore emulated mouse events for ~1 s after a touch
                        line = '%-14s script toggle  after each press (~ = wobble, ^ = touch tap): %s' % (sym, ', '.join(seq))
                        (notes if ok else fails).append(line if ok else 'FAIL ' + line)
                    else:
                        clean, ok, any_set = [], True, False
                        for e in els:
                            box = await e.bounding_box()
                            x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
                            _, after, v = await press(sym, x, y, 0)
                            any_set |= bool(after)
                            clean.append(v)
                        for e, want in reversed(list(zip(els, clean))):
                            box = await e.bounding_box()
                            x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
                            _, after, v = await press(sym, x, y, 2)
                            ok &= v == want
                        ok &= any_set
                        line = '%-14s script control %d elements; a clean click on each gave %s; wobbly clicks %s' % (
                            sym, len(els), ', '.join('%g' % v for v in clean),
                            'agree' if ok else ('never set a value' if not any_set else 'gave different values'))
                        (notes if ok else fails).append(line if ok else 'FAIL ' + line)
                    continue
                box = await el.bounding_box()
                cx, cy = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
                props = port['properties']
                kind = 'toggle' if 'toggled' in props else 'enum' if 'enumeration' in props else 'knob'
                momentary = 'preferMomentaryOnByDefault' in props or 'preferMomentaryOffByDefault' in props

                async def click(x, y, wobble, sym=sym):
                    return await press(sym, x, y, wobble)

                if kind == 'enum' and await el.get_attribute('mod-widget') == 'custom-select':
                    # mod-ui's dropdown (stock boxy selector): click to open, click an option
                    opts = await el.query_selector_all('[mod-role="enumeration-option"]')
                    seq, ok = [], bool(opts)
                    for w in (0, 2):
                        for o in reversed(opts):
                            want = float(await o.get_attribute('mod-port-value'))
                            await click(cx, cy, 0)
                            await pg.wait_for_timeout(80)
                            ob = await o.bounding_box()
                            if not ob or not await o.is_visible():
                                ok = False; seq.append('%s(list did not open)' % ('~' if w else '')); continue
                            _, _, v = await click(ob['x'] + ob['width'] / 2, ob['y'] + ob['height'] / 2, w)
                            seq.append('%s%g' % ('~' if w else '', v))
                            ok &= v == want
                    line = '%-14s dropdown    open + pick each option (~ = 2 px wobble): %s' % (sym, ', '.join(seq))
                    (notes if ok else fails).append(line if ok else 'FAIL ' + line)
                elif kind == 'toggle':
                    if momentary:
                        ok = True
                        for w in (0, 0, 2, 2):
                            held, after, _ = await click(cx, cy, w)
                            ok &= bool(held) and held[-1] == port['ranges']['maximum'] and bool(after) and after[-1] == port['ranges']['minimum']
                        line = '%-14s momentary   press = on, release = off on every click: %s' % (sym, 'yes' if ok else 'NO')
                    else:
                        seq, ok = [], True
                        for w, t in ((0, 0), (0, 0), (2, 0), (2, 0), (0, 1), (0, 1), (0, 1), (0, 1)):
                            before = cur[sym]
                            _, _, v = await press(sym, cx, cy, w, bool(t))
                            seq.append('%s%g' % ('~' if w else '^' if t else '', v))
                            ok &= v != before
                        await pg.wait_for_timeout(1200)
                        line = '%-14s toggle      value after each press (~ = 2 px wobble, ^ = touch tap): %s' % (sym, ', '.join(seq))
                    (notes if ok else fails).append(line if ok else 'FAIL ' + line)
                elif kind == 'enum':
                    pts = [sp['value'] for sp in port['scalePoints']]
                    spots = [(cx, box['y'] + box['height'] * f) for f in (0.15, 0.5, 0.85)] if box['height'] >= box['width'] \
                        else [(box['x'] + box['width'] * f, cy) for f in (0.15, 0.5, 0.85)]
                    picks = []
                    for x, y in spots:
                        _, _, v = await click(x, y, 0)
                        picks.append(v)
                    again = {}
                    for i in (2, 0, 1):          # same spots in another order
                        _, _, v = await click(*spots[i], 0)
                        again[i] = v
                    consistent = all(again[i] == picks[i] for i in range(3))
                    if consistent and len(set(picks)) == len(picks):
                        mode = 'position'   # each spot selects its own value
                        ok = True
                        for (x, y), want in zip(spots, picks):
                            _, _, v = await click(x, y, 2)
                            ok &= v == want
                    else:
                        mode = 'cycle'      # every click steps to the next value
                        ok = True
                        for _ in range(2):
                            before = cur[sym]
                            _, _, v = await click(cx, cy, 2)
                            ok &= v != before
                    line = '%-14s switch      clicks at three spots gave %s; with a 2 px wobble %s' % (
                        sym, ', '.join('%g' % v for v in picks), 'it still works' if ok else 'the click is dropped')
                    (notes if ok else fails).append(line if ok else 'FAIL ' + line)
                    if mode == 'cycle' and len(pts) > 2:
                        notes.append('NOTE %-9s clicks only step forward and wrap: clicking a position cannot select it '
                                     '(fix: click zones calling funcs.set_port_value, docs/modgui.md)' % sym)
                else:
                    seq = []
                    for w in (0, 2):
                        _, _, v = await click(cx, cy, w)
                        seq.append('%s%g' % ('~' if w else '', v))
                    notes.append('%-14s knob        a click steps it: %s (info)' % (sym, ', '.join(seq)))
            errs = await pg.evaluate('errors') + pageerr
            await b.close()
    for e in errs:
        fails.append('FAIL script: ' + e)
    return fails, notes


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('bundle')
    ap.add_argument('--mod-ui')
    a = ap.parse_args()
    info = load_bundle(a.bundle.rstrip('/'))
    fails, notes = asyncio.run(run(info, mod_ui_path(a.mod_ui)))
    for n in notes:
        print(n)
    for f in fails:
        print(f)
    print('\n%d failures' % len(fails))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
