# Minimal, readable starter you can run today
# - Extracts lines (with bbox) from PDF using pdfplumber
# - Detects numbering prefixes
# - Infers levels from numbering or font-size buckets
# - Merges lines into blocks (HEADING / PARAGRAPH / LIST_ITEM)
# - Builds section_path via a heading/list stack
# - Exports compact JSON + document.txt with char spans for highlightability
#
# Usage:
#   pip install pdfplumber==0.11.0 rapidfuzz==3.9.6
#   python legal_parser_minimal.py input.pdf out_dir/
#
# Notes:
# - This is intentionally simple and well-commented. Tighten heuristics as you go.
# - pdfplumber "size" attr availability can vary; we request it explicitly via extra_attrs.
# - If your PDF has weird fonts or no sizes, the font-rank fallback still works (rank uniques).

from __future__ import annotations
import json
import math
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import pdfplumber

# --------------------------
# Config knobs (tweak here)
# --------------------------
X_ALIGN_TOL = 8.0       # px tolerance for considering lines aligned (same paragraph)
FONT_SIZE_TOL = 1.25    # pt tolerance when merging lines
Y_CLUSTER_TOL = 3.0     # px tolerance to cluster words into a single line
INDENT_BUCKET = 36.0    # px per indent level for lists

# --------------------------
# Regexes for numbering
# --------------------------
DECIMAL_RE = re.compile(r"^(\d+(?:\.\d+)*[\.)]?)\s+")
UPPER_ALPHA_RE = re.compile(r"^([A-Z][\.)])\s+")
LOWER_ALPHA_PAREN_RE = re.compile(r"^(\([a-z]\))\s+")
ROMAN_RE = re.compile(r"^(?:\(?([ivxlcdm]+)\)?[\.)]?)\s+", re.IGNORECASE)
BULLET_RE = re.compile(r"^([-•●○▪︎])\s+")

class BlockType(str, Enum):
    META = "META"
    HEADING = "HEADING"
    PARAGRAPH = "PARAGRAPH"
    LIST_ITEM = "LIST_ITEM"
    TABLE = "TABLE"
    FOOTNOTE = "FOOTNOTE"
    SIGNATURE = "SIGNATURE"
    EXHIBIT = "EXHIBIT"

@dataclass
class Line:
    page: int
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    font_size: float
    is_bold: bool
    is_upper: bool
    numbering: Optional[str] = None
    text_clean: Optional[str] = None

@dataclass
class Block:
    block_id: str
    block_type: BlockType
    text: str
    level: Optional[int] = None
    numbering: Optional[str] = None
    section_path: List[str] = field(default_factory=list)
    role: Optional[str] = None
    positions: Dict[str, Any] = field(default_factory=dict)
    # internal
    _member_lines: List[Line] = field(default_factory=list, repr=False)

# --------------------------
# Utilities
# --------------------------

def detect_numbering_prefix(s: str) -> Tuple[Optional[str], str]:
    t = s.lstrip()
    for rx in (DECIMAL_RE, UPPER_ALPHA_RE, LOWER_ALPHA_PAREN_RE, ROMAN_RE, BULLET_RE):
        m = rx.match(t)
        if m:
            # prefer the full matched token (group 1 if exists, else full)
            token = m.group(1) if m.lastindex else m.group(0).strip()
            stripped = t[m.end():]
            return token, stripped
    return None, t


def looks_like_decimal(token: str) -> bool:
    return bool(re.match(r"^\d+(?:\.\d+)*[\.)]?$", token))


def looks_like_lower_alpha_paren(token: str) -> bool:
    return bool(re.match(r"^\([a-z]\)$", token))


def looks_like_upper_alpha(token: str) -> bool:
    return bool(re.match(r"^[A-Z][\.)]$", token))


def looks_like_roman(token: str) -> bool:
    return bool(re.match(r"^[ivxlcdm]+$", token, re.IGNORECASE))


def looks_like_bullet(token: str) -> bool:
    return token in {"-", "•", "●", "○", "▪︎"}


def count_decimal_segments(token: str) -> int:
    # "4.2.1" -> 3; strip trailing ")" or "." if any
    cleaned = token.rstrip(").").strip()
    return len(cleaned.split("."))


def indent_to_level(x0: float, min_x0: float) -> int:
    # Simple indent bucketing from the minimum left edge
    return max(1, int(round((x0 - min_x0) / INDENT_BUCKET)) + 1)

# --------------------------
# Extraction
# --------------------------

def extract_lines(pdf_path: str) -> Tuple[List[Line], List[Tuple[float,float]]]:
    lines: List[Line] = []
    page_sizes: List[Tuple[float, float]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for pageno, page in enumerate(pdf.pages):
            page_sizes.append((page.width, page.height))
            # request extra attrs so we can get font size
            words = page.extract_words(
                use_text_flow=True,
                keep_blank_chars=False,
                extra_attrs=["fontname", "size"],
            )
            # cluster words into lines by close 'top' values
            rows: Dict[int, List[dict]] = {}
            for w in words:
                key = int(round(w["top"] / max(1.0, Y_CLUSTER_TOL)))
                rows.setdefault(key, []).append(w)
            for _, ws in sorted(rows.items(), key=lambda kv: min(w["top"] for w in kv[1])):
                ws_sorted = sorted(ws, key=lambda w: w["x0"])  # left-to-right
                text = " ".join(w["text"] for w in ws_sorted).strip()
                x0 = min(w["x0"] for w in ws_sorted)
                x1 = max(w["x1"] for w in ws_sorted)
                top = min(w["top"] for w in ws_sorted)
                bottom = max(w["bottom"] for w in ws_sorted)
                sizes = [w.get("size") or 0.0 for w in ws_sorted]
                font_size = sum(sizes) / len(sizes) if sizes else 0.0
                fontnames = {w.get("fontname", "").lower() for w in ws_sorted}
                is_bold = any("bold" in fn for fn in fontnames)
                is_upper = text.isupper() and len(text) >= 3
                numbering, clean = detect_numbering_prefix(text)
                lines.append(Line(
                    page=pageno,
                    text=text,
                    x0=x0,
                    x1=x1,
                    top=top,
                    bottom=bottom,
                    font_size=font_size,
                    is_bold=is_bold,
                    is_upper=is_upper,
                    numbering=numbering,
                    text_clean=clean,
                ))
    return lines, page_sizes

# --------------------------
# Classification (rule-based)
# --------------------------

def classify_line(line: Line, doc_font_ranks: Dict[float, int]) -> BlockType:
    # Heading if: bold/upper OR font jump OR ends with ':' and short
    size_rank = doc_font_ranks.get(round(line.font_size, 1), 99)
    heading_hint = (
        (line.is_bold or line.is_upper) or
        (size_rank <= 2) or
        (line.text_clean.endswith(":") and len(line.text_clean) < 80)
    )
    if heading_hint and len(line.text_clean) <= 140:
        return BlockType.HEADING

    # List item if numbering exists or clear bullet
    if line.numbering and (looks_like_bullet(line.numbering) or True):
        return BlockType.LIST_ITEM

    return BlockType.PARAGRAPH

# --------------------------
# Merging lines → blocks
# --------------------------

def font_size_rank_map(lines: List[Line]) -> Dict[float, int]:
    # rank unique sizes (desc): largest=1, next=2, ...
    uniq = sorted({round(l.font_size, 1) for l in lines}, reverse=True)
    return {size: i + 1 for i, size in enumerate(uniq)}


def merge_lines_to_blocks(lines: List[Line], page_sizes: List[Tuple[float,float]]) -> List[Block]:
    ranks = font_size_rank_map(lines)
    blocks: List[Block] = []
    cur: Optional[Block] = None

    def flush():
        nonlocal cur
        if cur is None:
            return
        # aggregate bbox + positions
        page = cur._member_lines[0].page
        x0 = min(l.x0 for l in cur._member_lines)
        x1 = max(l.x1 for l in cur._member_lines)
        top = min(l.top for l in cur._member_lines)
        bottom = max(l.bottom for l in cur._member_lines)
        pw, ph = page_sizes[page]
        cur.positions = {
            "page": page,
            "bbox_pdf": [x0, top, x1, bottom],
            "bbox_norm": [x0 / pw, top / ph, x1 / pw, bottom / ph],
            "line_spans": [
                {
                    "page": l.page,
                    "bbox_pdf": [l.x0, l.top, l.x1, l.bottom],
                    "text": l.text_clean,
                }
                for l in cur._member_lines
            ],
        }
        blocks.append(cur)
        cur = None

    block_id_seq = 1
    for ln in lines:
        btype = classify_line(ln, ranks)
        if cur is None:
            cur = Block(
                block_id=f"b{block_id_seq:06d}",
                block_type=btype,
                text=ln.text_clean,
                numbering=ln.numbering,
            )
            cur._member_lines.append(ln)
            block_id_seq += 1
            continue
        # try to merge with current block when type and layout match
        same_type = (cur.block_type == btype)
        aligned = abs(cur._member_lines[-1].x0 - ln.x0) <= X_ALIGN_TOL
        similar_size = abs(cur._member_lines[-1].font_size - ln.font_size) <= FONT_SIZE_TOL
        if same_type and aligned and similar_size:
            # concatenate with space; caller can refine punctuation logic later
            cur.text = (cur.text + " " + ln.text_clean).strip()
            if cur.numbering is None:
                cur.numbering = ln.numbering
            cur._member_lines.append(ln)
        else:
            flush()
            cur = Block(
                block_id=f"b{block_id_seq:06d}",
                block_type=btype,
                text=ln.text_clean,
                numbering=ln.numbering,
            )
            cur._member_lines.append(ln)
            block_id_seq += 1

    flush()
    return blocks

# --------------------------
# Level inference + section paths
# --------------------------

def infer_level(block: Block, min_x0_in_doc: float, doc_font_ranks: Dict[float, int]) -> Optional[int]:
    tok = block.numbering
    if tok:
        if looks_like_decimal(tok):
            return count_decimal_segments(tok)
        if looks_like_lower_alpha_paren(tok):
            return 1
        if looks_like_roman(tok):
            # assume nested roman under letters if any prior letter list exists (simplify)
            return 2
        if looks_like_upper_alpha(tok) or looks_like_bullet(tok):
            # list top-level under current heading
            return 1
    # No numbering: headings by font rank, lists by indent, paragraphs null
    if block.block_type == BlockType.HEADING:
        # use first member line font size
        if block._member_lines:
            size = round(block._member_lines[0].font_size, 1)
            return doc_font_ranks.get(size, 3)
        return 3
    if block.block_type == BlockType.LIST_ITEM and block._member_lines:
        x0 = block._member_lines[0].x0
        return indent_to_level(x0, min_x0_in_doc)
    return None


def assign_hierarchy(blocks: List[Block]) -> List[Block]:
    if not blocks:
        return blocks
    min_x0 = min((l.x0 for b in blocks for l in b._member_lines), default=0.0)
    ranks = font_size_rank_map([l for b in blocks for l in b._member_lines])

    stack: List[Tuple[str, int]] = []  # (key, level)

    def key_for(block: Block) -> str:
        return block.numbering or normalize_heading_key(block.text)

    for b in blocks:
        L = infer_level(b, min_x0, ranks)
        b.level = L
        if b.block_type == BlockType.HEADING:
            # pop same or deeper
            while stack and stack[-1][1] >= (L or 1):
                stack.pop()
            stack.append((key_for(b), L or 1))
            b.section_path = [k for (k, _) in stack]
        elif b.block_type == BlockType.LIST_ITEM:
            # list lives under current heading path; extend by its own key
            base = [k for (k, _) in stack]
            b.section_path = base + ([key_for(b)] if key_for(b) else [])
        else:
            # paragraph/table/footnote inherit current heading path
            b.section_path = [k for (k, _) in stack]
    return blocks

# --------------------------
# Export JSON + document.txt with char spans
# --------------------------

def build_doc_text_and_spans(blocks: List[Block]) -> Tuple[str, Dict[str, Dict[str,int]]]:
    buf = []
    spans = {}
    pos = 0
    for b in blocks:
        start = pos
        buf.append(b.text)
        pos += len(b.text)
        # two newlines between blocks
        buf.append("\n\n")
        pos += 2
        spans[b.block_id] = {"start": start, "end": pos - 2}
        # also attach into positions for convenience
        b.positions["char_span_doc"] = {"start": start, "end": pos - 2}
    return "".join(buf), spans


def export_document(pdf_path: str, out_dir: str, blocks: List[Block], page_count: int) -> None:
    os.makedirs(out_dir, exist_ok=True)
    doc_id = os.path.basename(pdf_path)
    doc_text, _ = build_doc_text_and_spans(blocks)

    payload = {
        "document_id": doc_id,
        "pages": page_count,
        "blocks": [
            {
                **{k: v for k, v in asdict(b).items() if k != "_member_lines"},
            }
            for b in blocks
        ],
    }

    with open(os.path.join(out_dir, "document.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    with open(os.path.join(out_dir, "document.txt"), "w", encoding="utf-8") as f:
        f.write(doc_text)

# --------------------------
# Helpers
# --------------------------

def normalize_heading_key(text: str) -> str:
    # Short, stable key for unnumbered headings
    t = re.sub(r"\s+", " ", text.strip())
    t = re.sub(r"[^A-Za-z0-9 ()\.-]", "", t)
    return t[:60]


# --------------------------
# CLI
# --------------------------

def main(pdf_path: str, out_dir: str):
    print(f"Processing {pdf_path}...")
    lines, page_sizes = extract_lines(pdf_path)
    blocks = merge_lines_to_blocks(lines, page_sizes)
    blocks = assign_hierarchy(blocks)
    export_document(pdf_path, out_dir, blocks, page_count=len(page_sizes))
    print(f"✅ Done. Output saved to '{out_dir}'")

if __name__ == "__main__":
    # Hardcoded file path and output directory
    PDF_PATH = "sample/exhibit101.pdf"
    OUT_DIR = "output/"
    
    if not os.path.exists(PDF_PATH):
        print(f"❌ Error: Input file not found at '{PDF_PATH}'")
        sys.exit(1)
        
    main(PDF_PATH, OUT_DIR)
