#!/usr/bin/env bash
# Render a proposal HTML file to PDF with headless Chrome.
#
# Requires Bash, Python 3, and a Chrome-compatible browser. Render to a fresh
# temporary file and replace the destination only after successful output.
#
# Usage:
#   html-to-pdf.sh proposal.html [proposal.pdf]
#   PAPER=A4 html-to-pdf.sh proposal.html
#   CHROME_BIN="/path/to/chrome" html-to-pdf.sh proposal.html
#
# The page's own @page rule owns size and margins. PAPER only sets a default
# for pages that declare none.

set -euo pipefail

src=${1:-}
out=${2:-}

if [[ -z $src ]]; then
  sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
fi

[[ -f $src ]] || { echo "no such file: $src" >&2; exit 2; }
[[ -n $out ]] || out="${src%.*}.pdf"
command -v python3 >/dev/null 2>&1 || { echo "Python 3 is required to encode the input file URL" >&2; exit 3; }
[[ ! -d $out ]] || { echo "output is a directory: $out" >&2; exit 2; }

browser=${CHROME_BIN:-}
if [[ -n $browser ]]; then
  browser=$(command -v "$browser") || { echo "CHROME_BIN is not executable: $CHROME_BIN" >&2; exit 3; }
else
  for candidate in google-chrome google-chrome-stable chromium chromium-browser chrome \
                 microsoft-edge microsoft-edge-stable \
                 "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
                 "/Applications/Chromium.app/Contents/MacOS/Chromium" \
                 "$HOME"/.agent-browser/browsers/chrome-*/chrome \
                 "${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"/chromium-*/chrome-linux*/chrome; do
    if command -v "$candidate" >/dev/null 2>&1; then browser=$(command -v "$candidate"); break; fi
  done
fi

if [[ -z $browser ]]; then
  cat >&2 <<'EOF'
No Chrome, Chromium, or Edge found, and this script needs one of them.

Alternatives, in rough order of fidelity:
  - Open the HTML in any browser and print to PDF (Cmd/Ctrl-P). Turn on
    "Background graphics", or the themed surfaces print white.
  - Set CHROME_BIN to an installed Chrome-compatible executable.
  - Install Chrome/Chromium, then re-run this script.
EOF
  exit 3
fi

# URI encoding preserves spaces, #, and non-ASCII characters in source names.
url=$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve().as_uri())' "$src")
out_dir=$(cd "$(dirname "$out")" && pwd)
render_dir=$(mktemp -d "$out_dir/.proposal-render.XXXXXX")
trap 'rm -rf "$render_dir"' EXIT
pdf="$render_dir/output.pdf"

echo "rendering with: $browser"

if "$browser" \
  --headless \
  --disable-gpu \
  --no-sandbox \
  --no-pdf-header-footer \
  --print-to-pdf-no-header \
  --user-data-dir="$render_dir/profile" \
  ${PAPER:+--print-to-pdf-paper-size="$PAPER"} \
  --virtual-time-budget=12000 \
  --run-all-compositor-stages-before-draw \
  --print-to-pdf="$pdf" \
  "$url" >"$render_dir/browser.log" 2>&1; then
  :
else
  status=$?
  echo "render failed (browser exit $status); destination unchanged: $out" >&2
  cat "$render_dir/browser.log" >&2
  exit "$status"
fi

if [[ ! -s $pdf ]] || [[ $(head -c 5 "$pdf") != '%PDF-' ]]; then
  echo "render produced no fresh PDF; destination unchanged: $out" >&2
  cat "$render_dir/browser.log" >&2
  exit 1
fi

bytes=$(wc -c <"$pdf" | tr -d ' ')
if (( bytes < 2000 )); then
  echo "warning: $out is only ${bytes} bytes, which usually means a blank page" >&2
fi
mv -f "$pdf" "$out"

echo "wrote: $out (${bytes} bytes)"
echo
echo "Open it and check the page breaks before sending — they are the one thing"
echo "you cannot verify by reading the source. Watch for a cost table clipped at"
echo "the right edge, which means a scroll container still has overflow set."
