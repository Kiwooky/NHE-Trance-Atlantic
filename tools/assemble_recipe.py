#!/usr/bin/env python3
"""Assemble a single-file MOD Online Builder recipe (.mk) from plugin sources.

    python3 tools/assemble_recipe.py <plugin_src_dir> <bundle_dir> <out.mk> [--header header.txt]

  plugin_src_dir : the DPF plugin folder (*.cpp, *.h, Makefile)
  bundle_dir     : the <bundle>.lv2 folder (manifest.ttl, <bundle>.ttl, optional
                   modgui.ttl and modgui/ with html, css, js, png, jpg)
  out.mk         : must be named <bundle>.mk; the builder requires the filename
                   to match the variable prefix (simple-echo.mk -> SIMPLE_ECHO_)

The same folders also build as a normal repo (path B), so a plugin can start
as a single .mk and move to GitHub later without rewriting anything.

How things are embedded (patterns proven on builder.mod.audio):
  - small text sources: define + export + printf (the cookbook pattern)
  - anything over ~100 KB, and every bundle file: make's $(file >path,...),
    because Linux refuses environment variables over 128 KB
  - binary files: base64 inside a define, decoded with base64 -d at install
  - a literal $ is escaped to $$ automatically
  - if modgui/FETCH.txt exists (tools/stock_face.py --fetch-at-build), the files it
    lists are downloaded with wget at install time instead of being embedded, so a
    stock face costs a few lines (verified on builder.mod.audio, 2026-10-07)
"""
import argparse, base64, os, re, sys

DPF_SHA = '61d38eb638449647fb8395a35c5b8dab7e981ba7'
DPF_URL = 'https://github.com/DISTRHO/DPF.git'
TEXT_EXT = {'.cpp', '.hpp', '.h', '.c', '.ttl', '.html', '.css', '.js', '.txt', ''}
SMALL = 100 * 1024


def esc(text):
    return text.replace('$', '$$')


def b64lines(data):
    s = base64.b64encode(data).decode()
    return '\n'.join(s[i:i + 76] for i in range(0, len(s), 76))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('bundle'); ap.add_argument('out')
    ap.add_argument('--header', help='text file with the comment header (without # marks)')
    a = ap.parse_args()

    bundle_dir = a.bundle.rstrip('/')
    bname = os.path.basename(bundle_dir)
    if not bname.endswith('.lv2'):
        sys.exit('bundle dir must be <bundle>.lv2')
    bundle = bname[:-4]
    if os.path.basename(a.out) != bundle + '.mk':
        sys.exit('output must be named %s.mk (the builder matches filename and prefix)' % bundle)
    P = re.sub(r'[^A-Z0-9]', '_', bundle.upper())

    blocks, exports, configure, install = [], [], [], []
    n = 0

    # --- plugin sources -> $(@D)/examples/<bundle>/
    for fn in sorted(os.listdir(a.src)):
        path = os.path.join(a.src, fn)
        if not os.path.isfile(path):
            continue
        text = open(path).read()
        if fn == 'Makefile':
            # in the repo the plugin sits at plugins/<name>/ next to dpf/;
            # in the builder it sits at <dpf>/examples/<bundle>/
            text = text.replace('../../dpf/Makefile.plugins.mk', '../../Makefile.plugins.mk')
        n += 1
        var = '%s_SRC%d' % (P, n)
        blocks.append('define %s\n%s\nendef\n' % (var, esc(text.rstrip('\n'))))
        dest = '$(@D)/examples/%s/%s' % (bundle, fn)
        if len(text) < SMALL:
            exports.append('export %s' % var)
            configure.append("\tprintf '%%s\\n' \"$$%s\" > %s" % (var, dest))
        else:
            configure.append('\t$(file >%s,$(%s))' % (dest, var))

    # --- bundle files -> $($(PKG)_PKGDIR)/<bundle>.lv2/
    pkg = '$($(PKG)_PKGDIR)/%s.lv2' % bundle
    install.append('\tmkdir -p %s' % pkg)
    install.append('\tcp $(@D)/bin/%s.lv2/%s_dsp.so %s/' % (bundle, bundle, pkg))
    tmp = 0
    for root, dirs, files in os.walk(bundle_dir):
        dirs.sort()
        rel = os.path.relpath(root, bundle_dir)
        for fn in sorted(files):
            if fn.endswith('_dsp.so') or (rel == 'modgui' and fn == 'FETCH.txt'):
                continue
            src = os.path.join(root, fn)
            relp = fn if rel == '.' else os.path.join(rel, fn)
            n += 1; tmp += 1
            var = '%s_FILE%d' % (P, n)
            ext = os.path.splitext(fn)[1].lower()
            t = '$(@D)/.pb-%d' % tmp
            dest = '%s/%s' % (pkg, relp)
            if rel != '.':
                install.append('\tmkdir -p %s/%s' % (pkg, rel))
            if ext in TEXT_EXT:
                blocks.append('define %s\n%s\nendef\n' % (var, esc(open(src).read().rstrip('\n'))))
                install.append('\t$(file >%s,$(%s))' % (t, var))
                install.append('\tcp %s %s' % (t, dest))
            else:
                blocks.append('define %s\n%s\nendef\n' % (var, b64lines(open(src, 'rb').read())))
                install.append('\t$(file >%s,$(%s))' % (t, var))
                install.append('\tbase64 -d %s > %s' % (t, dest))

    fetch = os.path.join(bundle_dir, 'modgui', 'FETCH.txt')
    if os.path.exists(fetch):
        for line in open(fetch):
            parts = line.split()
            if not parts or parts[0].startswith('#'):
                continue
            dest, urls = '%s/modgui/%s' % (pkg, parts[0]), parts[1:]
            install.append('\tmkdir -p %s' % os.path.dirname(dest))
            install.append('\twget -q -O %s %s && test -s %s || (echo "face: could not download %s"; exit 1)'
                           % (dest, ' '.join(urls), dest, ' '.join(urls)))
            n += 1

    header = ''
    if a.header:
        header = ''.join('# ' + l if l.strip() else '#\n' for l in open(a.header).read().splitlines(True))
        header = header.rstrip('\n') + '\n#\n'
    header += ('# Upload this file at https://builder.mod.audio/buildroot with a MOD unit\n'
               '# connected over USB. Assembled by tools/assemble_recipe.py (MOD plugin playbook).\n')

    out = [header, '',
           '%s_VERSION = %s' % (P, DPF_SHA),
           '%s_SITE = %s' % (P, DPF_URL),
           '%s_SITE_METHOD = git' % P,
           '%s_BUNDLES = %s.lv2' % (P, bundle), '']
    out += blocks
    out += exports + ['']
    out.append('define %s_CONFIGURE_CMDS\n\tmkdir -p $(@D)/examples/%s\n%s\nendef\n' % (P, bundle, '\n'.join(configure)))
    out.append('define %s_BUILD_CMDS\n\t$(TARGET_MAKE_ENV) $(TARGET_CONFIGURE_OPTS) $(MAKE) NOOPT=true -C $(@D)/examples/%s lv2_dsp\nendef\n'
               % (P, bundle))
    out.append('define %s_INSTALL_TARGET_CMDS\n%s\nendef\n' % (P, '\n'.join(install)))
    out.append('$(eval $(generic-package))\n')
    open(a.out, 'w').write('\n'.join(out))
    print('wrote %s (prefix %s_, %d embedded files, %.0f KB)' % (a.out, P, n, os.path.getsize(a.out) / 1024))


if __name__ == '__main__':
    main()
