"""Extract text lines from a PDF into JSONL.

Produces two files derived from the input PDF path:
  <name>.jsonl          — full records (id, page, bbox, text, language)
  <name>-filtered.jsonl — only id and text fields
"""

import fitz  # pip install pymupdf
import json
import re

# characters to strip out
INVISIBLE_CHARS = re.compile(
    r'[\u200b\u200c\u200d\u200e\u200f'   # zero-width spaces & directional marks
    r'\u00ad'                              # soft hyphen
    r'\u2060\u2061\u2062\u2063\u2064'      # invisible operators
    r'\ufeff'                              # BOM / zero-width no-break space
    r'\u00a0'                              # non-breaking space → replace with normal space
    r'\x00-\x08\x0b\x0c\x0e-\x1f]',       # control characters
    flags=re.UNICODE
)

def clean_text(text):
    """Strip invisible characters, normalize whitespace, and trim."""
    text = text.replace('\u00a0', ' ')           # NBSP → normal space
    text = INVISIBLE_CHARS.sub('', text)          # remove all invisible chars
    text = re.sub(r' {2,}', ' ', text).strip()    # collapse multiple spaces
    return text


def extract_lines_to_jsonl(pdf_path, lang=None):
    """Extract text lines from a PDF and write two JSONL files.

    Outputs:
      <name>.jsonl          — one record per line with id, page, bbox, text, language.
      <name>-filtered.jsonl — same records reduced to id and text only.
    """
    base = pdf_path.rsplit(".", 1)[0]
    output_path = base + ".jsonl"
    filtered_path = base + "-filtered.jsonl"

    doc = fitz.open(pdf_path)
    line_id = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for page_num, page in enumerate(doc, start=1):
            page_dict = page.get_text("dict")

            for block in page_dict["blocks"]:
                if block["type"] != 0:
                    continue
                for line in block["lines"]:
                    text = "".join(span["text"] for span in line["spans"]).strip()
                    text = clean_text(text)
                    if not text:
                        continue

                    line_id += 1
                    bbox = line["bbox"]

                    record = {
                        "id": str(line_id),
                        "p": page_num,
                        "b": [round(bbox[0], 2), round(bbox[1], 2), round(bbox[2], 2), round(bbox[3], 2)],
                        "t": text,
                        "language": lang,
                    }

                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

    doc.close()
    print(f"Done: {line_id} lines written to {output_path}")

    # Write a second JSONL with only id and t fields
    with open(output_path, "r", encoding="utf-8") as fin, \
         open(filtered_path, "w", encoding="utf-8") as fout:
        for line in fin:
            record = json.loads(line)
            fout.write(json.dumps({"id": record["id"], "t": record["t"]}, ensure_ascii=False) + "\n")
    print(f"Done: filtered file written to {filtered_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extract text lines from PDF to JSONL")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("--lang", default=None, help="Language code (e.g., fr, en)")
    args = parser.parse_args()
    extract_lines_to_jsonl(args.pdf_path, lang=args.lang)
