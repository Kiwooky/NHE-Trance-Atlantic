#!/usr/bin/env python3
"""Render a modgui face's screenshot and thumbnail, with every control at its
TTL default, using headless Chromium (pip install playwright rdflib pillow;
python3 -m playwright install chromium).

    python3 tools/render_face.py <bundle>.lv2

Reads modgui.ttl (template, stylesheet, screenshot/thumbnail names) and the
plugin TTL (defaults, ranges). Knob frames are worked out the way mod-ui does:
frames = strip width / element width, frame = round((v - min)/(max - min) * steps),
on a log scale for ports marked pprops:logarithmic.
mod-widget="switch" elements get class on/off; the bypass widget is drawn active.
Faces that @import mod-ui's /fonts render with them when PB_FONTS_DIR points at a copy.
Writes the screenshot at face size and a thumbnail that fits 256x64.
"""
import os, re, sys, tempfile
import rdflib
from PIL import Image

L = rdflib.Namespace('http://lv2plug.in/ns/lv2core#')
MG = rdflib.Namespace('http://moddevices.com/ns/modgui#')


def main():
    bundle = sys.argv[1].rstrip('/')
    g = rdflib.Graph()
    for fn in os.listdir(bundle):
        if fn.endswith('.ttl'):
            g.parse(os.path.join(bundle, fn), format='turtle')
    gui = next(g.objects(None, MG['gui']))
    path = lambda k: str(g.value(gui, MG[k])).replace('file://', '')
    rel = lambda k: os.path.join(bundle, os.path.relpath(path(k), os.path.abspath(bundle))) if os.path.isabs(path(k)) else os.path.join(bundle, path(k))
    res = rel('resourcesDirectory')
    html = open(rel('iconTemplate')).read()
    css = open(rel('stylesheet')).read()
    shot, thumb = rel('screenshot'), rel('thumbnail')

    ports = {}
    for p in g.objects(None, L['port']):
        sym = g.value(p, L['symbol'])
        if sym is None or g.value(p, L['default']) is None:
            continue
        log = any(str(o).endswith('#logarithmic') for o in g.objects(p, L['portProperty']))
        ports[str(sym)] = (float(g.value(p, L['default'])), float(g.value(p, L['minimum'])), float(g.value(p, L['maximum'])), log)

    html = re.sub(r'\{\{#.*?\}\}.*?\{\{/.*?\}\}', '', html, flags=re.S)
    css = css.replace('{{{cns}}}', '').replace('{{{ns}}}', '')
    css = re.sub(r'url\(/resources/([^)]+)\)', lambda m: 'url(file://%s/%s)' % (os.path.abspath(res), m.group(1)), css)
    fonts = os.environ.get('PB_FONTS_DIR')        # mod-ui's /fonts, for faces that @import them (tools/stock_face.py sets this)
    if fonts:
        css = re.sub(r'url\(/fonts/([^)]+)\)', lambda m: 'url(file://%s/%s)' % (os.path.abspath(fonts), m.group(1)), css)
    html = html.replace('{{{cns}}}', '').replace('{{{ns}}}', '')
    js = '''
const ports = %s;
async function go() {
  const els = document.querySelectorAll('[mod-port-symbol]');
  for (const el of els) {
    const sym = el.getAttribute('mod-port-symbol'); const p = ports[sym];
    if (!p) continue;
    const [v, lo, hi, log] = p;
    if (el.getAttribute('mod-widget') === 'switch') { el.classList.add(v > lo ? 'on' : 'off'); continue; }
    const cs = getComputedStyle(el); const url = cs.backgroundImage.slice(5, -2);
    if (!url) continue;
    const img = new Image(); img.src = url; await img.decode();
    const h = el.clientHeight, w = el.clientWidth;
    const bh = parseFloat(cs.backgroundSize.split(' ')[1]) || img.naturalHeight;
    const stripW = img.naturalWidth * bh / img.naturalHeight;
    const steps = Math.round(stripW / w) - 1;
    const pos = (log && lo > 0) ? Math.log(v / lo) / Math.log(hi / lo) : (v - lo) / (hi - lo);   // logarithmic ports, as mod-ui
    const f = Math.round(pos * steps);
    el.style.backgroundPosition = (-f * w) + 'px 0px';
  }
  document.querySelectorAll('[mod-role=bypass]').forEach(e => e.classList.add('off'));
  document.title = 'ready';
}
go();
''' % __import__('json').dumps(ports)
    imports = ''.join(re.findall(r'@import[^;]+;', css))      # @import only works at the top of a stylesheet
    if fonts:                                                    # and mod-ui's page-wide fonts
        imports += ''.join('@import url(file://%s/%s/stylesheet.css);' % (os.path.abspath(fonts), d)
                           for d in sorted(os.listdir(fonts)) if os.path.exists(os.path.join(fonts, d, 'stylesheet.css')))
    css = re.sub(r'@import[^;]+;', '', css)
    page = '<html><head><style>%sbody{margin:0;background:transparent;font-family:sans-serif}%s</style></head><body>%s<script>%s</script></body></html>' % (imports, css, html, js)
    from playwright.sync_api import sync_playwright
    with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False) as f:
        f.write(page); tmp = f.name
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=['--allow-file-access-from-files'])
        pg = b.new_page(viewport={'width': 1400, 'height': 1000})
        pg.goto('file://' + tmp)
        pg.wait_for_function('document.title === "ready"', timeout=10000)
        pg.evaluate('document.fonts.ready')
        el = pg.query_selector('.mod-pedal')
        el.screenshot(path=shot, omit_background=True)
        b.close()
    os.unlink(tmp)
    im = Image.open(shot)
    t = im.copy(); t.thumbnail((256, 64), Image.LANCZOS); t.save(thumb, optimize=True)
    print('wrote %s (%dx%d) and %s (%dx%d)' % (shot, im.width, im.height, thumb, t.width, t.height))


if __name__ == '__main__':
    main()
