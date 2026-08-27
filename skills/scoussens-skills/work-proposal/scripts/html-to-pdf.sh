#!/usr/bin/env bash
# Render a proposal HTML file to PDF with headless Chrome.
#
# Chrome prints without backgrounds by default, which strips every themed
# surface from the page, and it fails quietly enough to leave a zero-byte file
# behind. This turns both on and checks the result.
#
# Usage:
#   html-to-pdf.sh proposal.html [proposal.pdf]
#   PAPER=A4 html-to-pdf.sh proposal.html
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

browser=""
for candidate in google-chrome google-chrome-stable chromium chromium-browser \
                 microsoft-edge microsoft-edge-stable \
                 "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
                 "/Applications/Chromium.app/Contents/MacOS/Chromium"; do
  if command -v "$candidate" >/dev/null 2>&1; then browser=$candidate; break; fi
  if [[ -x $candidate ]]; then browser=$candidate; break; fi
done

if [[ -z $browser ]]; then
  cat >&2 <<'EOF'
No Chrome, Chromium, or Edge found, and this script needs one of them.

Alternatives, in rough order of fidelity:
  - Open the HTML in any browser and print to PDF (Cmd/Ctrl-P). Turn on
    "Background graphics", or the themed surfaces print white.
  - npx playwright install chromium, then re-run this script.
EOF
  exit 3
fi

# Chrome needs an absolute URL; a bare relative path silently renders blank.
abs=$(cd "$(dirname "$src")" && printf '%s/%s' "$(pwd)" "$(basename "$src")")
profile=$(mktemp -d)
trap 'rm -rf "$profile"' EXIT

echo "rendering with: $browser"

"$browser" \
  --headless \
  --disable-gpu \
  --no-sandbox \
  --no-pdf-header-footer \
  --print-to-pdf-no-header \
  --user-data-dir="$profile" \
  ${PAPER:+--print-to-pdf-paper-size="$PAPER"} \
  --virtual-time-budget=12000 \
  --run-all-compositor-stages-before-draw \
  --print-to-pdf="$out" \
  "file://$abs" 2>/dev/null || true

if [[ ! -s $out ]]; then
  echo "render produced no output — the file may reference assets it cannot reach" >&2
  exit 1
fi

bytes=$(wc -c <"$out" | tr -d ' ')
if (( bytes < 2000 )); then
  echo "warning: $out is only ${bytes} bytes, which usually means a blank page" >&2
fi

echo "wrote: $out (${bytes} bytes)"
echo
echo "Open it and check the page breaks before sending — they are the one thing"
echo "you cannot verify by reading the source. Watch for a cost table clipped at"
echo "the right edge, which means a scroll container still has overflow set."
