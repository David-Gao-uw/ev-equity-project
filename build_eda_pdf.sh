#!/usr/bin/env bash
# Rebuild eda.pdf from eda_report.md (pandoc -> Edge print -> page numbers).
set -euo pipefail
cd "$(dirname "$0")"
EDGE="/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"

# Fail before touching anything if the page-numbering step cannot run.
./.venv/bin/python -c "import pypdf, reportlab" || {
  echo "pypdf/reportlab missing: run .venv/bin/pip install -r requirements.txt" >&2
  exit 1
}

pandoc eda_report.md -f markdown -t html5 -s --css style_eda.css \
  --metadata title-prefix="CSE 163 EDA" -o eda_report.html

"$EDGE" --headless=new --no-sandbox --disable-gpu \
  --disable-software-rasterizer --no-pdf-header-footer \
  --user-data-dir=/tmp/edge-pdf-eda-build \
  --print-to-pdf="$PWD/eda_raw.pdf" "file://$PWD/eda_report.html" \
  2>&1 | grep -E "bytes written" || true

./.venv/bin/python - <<'PY'
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
import io

reader = PdfReader("eda_raw.pdf")
total = len(reader.pages)
writer = PdfWriter()
for index, page in enumerate(reader.pages, start=1):
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    buffer = io.BytesIO()
    overlay = canvas.Canvas(buffer, pagesize=(width, height))
    overlay.setFont("Times-Roman", 11)
    overlay.drawCentredString(width / 2, 0.42 * 72, f"Page {index} of {total}")
    overlay.save()
    buffer.seek(0)
    page.merge_page(PdfReader(buffer).pages[0])
    writer.add_page(page)
with open("eda.pdf", "wb") as out:
    writer.write(out)
print(f"eda.pdf written: {total} pages")
PY
rm -f eda_raw.pdf eda_report.html
