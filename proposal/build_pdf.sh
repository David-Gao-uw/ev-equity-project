#!/usr/bin/env bash
# Rebuild proposal.pdf from proposal.md.
# Requires: pandoc, and Microsoft Edge (used headless to print HTML -> PDF).
set -euo pipefail
cd "$(dirname "$0")"

EDGE="/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"

pandoc proposal.md -f markdown -t html5 -s --css style.css \
  --metadata title-prefix="CSE 163 Proposal" -o proposal.html

"$EDGE" --headless=new --no-sandbox --disable-gpu --disable-software-rasterizer \
  --no-pdf-header-footer --user-data-dir=/tmp/edge-pdf-profile \
  --print-to-pdf="$PWD/proposal.pdf" "file://$PWD/proposal.html" 2>&1 \
  | grep -E "bytes written" || true

echo "Wrote $PWD/proposal.pdf"
