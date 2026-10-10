#!/usr/bin/env bash
# The gate every change passes before it goes to the builder.
#
#   tools/check.sh --src <plugin dir> --bundle <bundle>.lv2 --test <test script>   (sources in folders; path A or B)
#   tools/check.sh --recipe <name>.mk --test <test script>                        (a hand-written single-file recipe)
#
# Runs:  assemble (if --src) -> build native, Duo (arm32), Duo X/Dwarf (arm64) through the
#        builder's own hooks (tools/harness.mk) -> TTL vs DPF's generator -> lv2info load check
#        -> your test script natively -> the same tests on the Duo build under qemu.
# Exit code 0 only if every step passes. Compiler warnings count as failures.
#
# Needs: g++ g++-arm-linux-gnueabihf g++-aarch64-linux-gnu qemu-user lilv-utils git make
#        python3 with numpy scipy rdflib.   Cache: $PB_CACHE (default ~/.cache/mod-playbook)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DPF_SHA=61d38eb638449647fb8395a35c5b8dab7e981ba7
CACHE="${PB_CACHE:-$HOME/.cache/mod-playbook}"
SRC= BUNDLE= RECIPE= TEST= SKIP_QEMU=0
while [ $# -gt 0 ]; do
  case "$1" in
    --src) SRC="$2"; shift 2;;
    --bundle) BUNDLE="$2"; shift 2;;
    --recipe) RECIPE="$2"; shift 2;;
    --test) TEST="$2"; shift 2;;
    --no-qemu) SKIP_QEMU=1; shift;;
    *) echo "unknown argument $1"; exit 2;;
  esac
done
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
step() { printf '\n== %s\n' "$*"; }

step "DPF at $DPF_SHA"
mkdir -p "$CACHE"
if [ ! -d "$CACHE/dpf" ]; then
  git clone -q https://github.com/DISTRHO/DPF.git "$CACHE/dpf"
  (cd "$CACHE/dpf" && git checkout -q "$DPF_SHA" && git submodule update -q --init)
fi
if [ ! -x "$CACHE/dpf/utils/lv2_ttl_generator" ]; then
  make -s -C "$CACHE/dpf/utils/lv2-ttl-generator" >/dev/null
fi
echo ok

if [ -n "$SRC" ]; then
  step "assemble recipe from $SRC + $BUNDLE"
  B="$(basename "${BUNDLE%/}" .lv2)"
  RECIPE="$WORK/$B.mk"
  python3 "$HERE/assemble_recipe.py" "$SRC" "$BUNDLE" "$RECIPE"
fi
[ -n "$RECIPE" ] || { echo "need --src/--bundle or --recipe"; exit 2; }
B="$(basename "$RECIPE" .mk)"
PREFIX="$(echo "$B" | tr 'a-z-' 'A-Z_' | tr -c 'A-Z0-9_\n' '_')"

for T in native arm32 arm64; do
  step "build $T"
  rm -rf "$WORK/dpf-$T"; cp -r "$CACHE/dpf" "$WORK/dpf-$T"
  (cd "$WORK/dpf-$T" && git clean -qfdx -e utils/lv2_ttl_generator >/dev/null 2>&1 || true)
  C=""; [ "$T" != native ] && C="CROSS=$T"
  LOG="$WORK/build-$T.log"
  if ! make -s -f "$HERE/harness.mk" RECIPE="$RECIPE" PREFIX="$PREFIX" SRC="$WORK/dpf-$T" OUT="$WORK/out-$T" $C >"$LOG" 2>&1; then
    cat "$LOG"; echo "FAIL build $T"; exit 1
  fi
  if grep -qi "warning" "$LOG"; then grep -i -A3 "warning" "$LOG"; echo "FAIL: compiler warnings ($T)"; exit 1; fi
  file "$WORK/out-$T/$B.lv2/${B}_dsp.so" | cut -d, -f1-2
done

step "TTL vs DPF generator"
mkdir -p "$WORK/gen" && cp "$WORK/out-native/$B.lv2/${B}_dsp.so" "$WORK/gen/"
(cd "$WORK/gen" && "$CACHE/dpf/utils/lv2_ttl_generator" "./${B}_dsp.so" >/dev/null)
python3 "$HERE/ttlcmp.py" "$WORK/gen/${B}_dsp.ttl" "$WORK/out-native/$B.lv2/$B.ttl"

step "load check (lv2info)"
URI="$(grep -o '<[^>]*>' "$WORK/out-native/$B.lv2/manifest.ttl" | grep -v 'lv2plug\|w3.org\|\.so>\|\.ttl>' | head -1 | tr -d '<>')"
LV2_PATH="$WORK/out-native" lv2info "$URI" | grep -E "^\s*Name:" | head -1

if [ -n "$TEST" ]; then
  step "tests (native)"
  gcc -O2 -I"$CACHE/dpf/distrho/src" -I"$CACHE/dpf/distrho/src/lv2" "$HERE/lv2host.c" -o "$WORK/lv2host" -ldl
  PB_TOOLS="$HERE" PB_SO="$WORK/out-native/$B.lv2/${B}_dsp.so" PB_HOST="$WORK/lv2host" python3 "$TEST"
  if [ "$SKIP_QEMU" = 0 ]; then
    step "tests (Duo build under qemu)"
    arm-linux-gnueabihf-gcc -O2 -I"$CACHE/dpf/distrho/src" -I"$CACHE/dpf/distrho/src/lv2" "$HERE/lv2host.c" -o "$WORK/lv2host-arm" -ldl
    PB_TOOLS="$HERE" PB_SO="$WORK/out-arm32/$B.lv2/${B}_dsp.so" PB_HOST="qemu-arm -L /usr/arm-linux-gnueabihf $WORK/lv2host-arm" python3 "$TEST"
  fi
fi
step "ALL CHECKS PASSED"
if [ -n "$SRC" ]; then
  mkdir -p dist && cp "$RECIPE" "dist/$B.mk" && echo "recipe for the Online Builder: dist/$B.mk"
fi
