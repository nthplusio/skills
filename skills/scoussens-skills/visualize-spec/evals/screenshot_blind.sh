#!/usr/bin/env bash
# Screenshot every blinded page so a grader can judge diagrams as pictures.
#
# Usage: evals/screenshot_blind.sh ITERATION_DIR
# Writes ITERATION_DIR/blind/<eval>/{A,B}.png next to the blinded HTML.
#
# Graders that read HTML score diagrams by imagining them: in iteration 6 they
# rated hand-written SVG above the template's diagram kit (4.44 vs 4.00), while
# graders shown these screenshots reversed it (legibility 4.78 vs 3.44), because
# on screen the SVG had crossing arrows and clipped labels. Judge visuals visually.
set -euo pipefail
dir="${1:?usage: screenshot_blind.sh ITERATION_DIR}"
chrome="$(command -v google-chrome || command -v chromium || true)"
[ -n "$chrome" ] || { echo "no Chrome or Chromium on PATH" >&2; exit 1; }
for page in "$dir"/blind/*/[AB].html; do
  timeout 90 "$chrome" --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
    --window-size=1000,6000 --screenshot="${page%.html}.png" "file://$page" >/dev/null 2>&1
done
ls "$dir"/blind/*/*.png | wc -l | xargs echo "screenshots:"
