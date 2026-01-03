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
#   python main.py
#
# Notes:
# - pdfplumber "size" attr availability can vary; we request it explicitly via extra_attrs.
# - If your PDF has weird fonts or no sizes, the font-rank fallback still works (rank uniques).

from __future__ import annotations
import json
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
    char_span_doc: Dict[str, int] = field(default_factory=dict)
    # internal
    _member_lines: List[Line] = field(default_factory=list, repr=False)

# --------------------------
# Utilities
# --------------------------
def _normalize_inline_spacing(t: str) -> str:
    # collapse spaces before punctuation and multiple spaces
    t = re.sub(r"\s+([,.;:])", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()

def detect_numbering_prefix(s: str):
    t = s.lstrip()
    for rx in (DECIMAL_RE, UPPER_ALPHA_RE, LOWER_ALPHA_PAREN_RE, ROMAN_RE, BULLET_RE):
        m = rx.match(t)
        if m:
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
    cleaned = token.rstrip(").").strip()
    return len(cleaned.split("."))

def indent_to_level(x0: float, min_x0: float) -> int:
    return max(1, int(round((x0 - min_x0) / INDENT_BUCKET)) + 1)

def _word_count(s: str) -> int:
    return len(re.findall(r"\w+", s))

def _looks_run_in_leadin(numbering: Optional[str], clean: str) -> bool:
    if not numbering:
        return False
    m = re.match(r"^([^\.]{1,60})\.\s+\S", clean)
    if not m:
        return False
    return _word_count(m.group(1)) <= 6

# --------------------------
# Extraction
# --------------------------
def extract_lines(pdf_path: str):
    lines, page_sizes = [], []
    with pdfplumber.open(pdf_path) as pdf:
        for pageno, page in enumerate(pdf.pages):
            page_sizes.append((page.width, page.height))
            words = page.extract_words(
                use_text_flow=True,
                keep_blank_chars=False,
                extra_attrs=["fontname", "size"],
            )
            rows = {}
            for w in words:
                key = int(round(w["top"] / max(1.0, Y_CLUSTER_TOL)))
                rows.setdefault(key, []).append(w)
            for _, ws in sorted(rows.items(), key=lambda kv: min(w["top"] for w in kv[1])):
                ws_sorted = sorted(ws, key=lambda w: w["x0"])
                text = _normalize_inline_spacing(" ".join(w["text"] for w in ws_sorted).strip())
                x0, x1 = min(w["x0"] for w in ws_sorted), max(w["x1"] for w in ws_sorted)
                top, bottom = min(w["top"] for w in ws_sorted), max(w["bottom"] for w in ws_sorted)
                sizes = [w.get("size") or 0.0 for w in ws_sorted]
                font_size = sum(sizes) / len(sizes) if sizes else 0.0
                fontnames = {w.get("fontname", "").lower() for w in ws_sorted}
                is_bold = any("bold" in fn for fn in fontnames)
                is_upper = text.isupper() and len(text) >= 3
                numbering, clean = detect_numbering_prefix(text)
                lines.append(Line(
                    page=pageno,
                    text=text,
                    x0=x0, x1=x1, top=top, bottom=bottom,
                    font_size=font_size,
                    is_bold=is_bold, is_upper=is_upper,
                    numbering=numbering,
                    text_clean=clean,
                ))
    return lines, page_sizes

# --------------------------
# Classification (rule-based)
# --------------------------
def classify_line(line: Line, ranks: Dict[float, int]) -> BlockType:
    clean = line.text_clean or ""
    has_num = bool(line.numbering)
    if _looks_run_in_leadin(line.numbering, clean):
        return BlockType.PARAGRAPH
    if has_num and looks_like_lower_alpha_paren(line.numbering):
        return BlockType.PARAGRAPH
    size_rank = ranks.get(round(line.font_size, 1), 99)
    heading_visual = (size_rank <= 2) or line.is_bold or line.is_upper
    if heading_visual and _word_count(clean) <= 16 and not has_num:
        return BlockType.HEADING
    if has_num:
        return BlockType.LIST_ITEM
    return BlockType.PARAGRAPH

# --------------------------
# Merging lines → blocks
# --------------------------
def font_size_rank_map(lines: List[Line]) -> Dict[float, int]:
    uniq = sorted({round(l.font_size, 1) for l in lines}, reverse=True)
    return {size: i + 1 for i, size in enumerate(uniq)}

def merge_lines_to_blocks(lines: List[Line], page_sizes: List[Tuple[float, float]]) -> List[Block]:
    ranks = font_size_rank_map(lines)
    blocks, cur = [], None
    block_id_seq, reading_order = 1, 0

    def flush():
        nonlocal cur, reading_order
        if not cur: return
        page = cur._member_lines[0].page
        x0, x1 = min(l.x0 for l in cur._member_lines), max(l.x1 for l in cur._member_lines)
        top, bottom = min(l.top for l in cur._member_lines), max(l.bottom for l in cur._member_lines)
        pw, ph = page_sizes[page]

        bbox_pdf = [
            x0,
            ph - bottom,
            x1 - x0,
            bottom - top,
        ]
        cur.positions = {
            "page": page,
            "bbox_pdf": bbox_pdf,
            # "bbox_norm": bbox_norm,
            "line_spans": [
                {
                    "page": l.page,
                    "bbox_pdf": [
                        l.x0,
                        ph - l.bottom,
                        l.x1 - l.x0,
                        l.bottom - l.top,
                    ],
                }
                for l in cur._member_lines
            ],
            "reading_order": reading_order,
        }
        reading_order += 1
        blocks.append(cur)
        cur = None

    for ln in lines:
        btype = classify_line(ln, ranks)
        if cur is not None and cur.block_type == BlockType.HEADING:
            flush()
        if cur is None:
            cur = Block(f"b{block_id_seq:06d}", btype, ln.text_clean, numbering=ln.numbering)
            cur._member_lines.append(ln); block_id_seq += 1; continue
        same_type = (cur.block_type == btype)
        aligned = abs(cur._member_lines[-1].x0 - ln.x0) <= X_ALIGN_TOL
        similar_size = abs(cur._member_lines[-1].font_size - ln.font_size) <= FONT_SIZE_TOL
        if same_type and aligned and similar_size:
            cur.text = (cur.text + " " + (ln.text_clean or "")).strip()
            if not cur.numbering: cur.numbering = ln.numbering
            cur._member_lines.append(ln)
        else:
            flush()
            cur = Block(f"b{block_id_seq:06d}", btype, ln.text_clean, numbering=ln.numbering)
            cur._member_lines.append(ln); block_id_seq += 1
    flush()
    return blocks

# --------------------------
# Level inference + section paths
# --------------------------
def infer_level(block: Block, min_x0: float, ranks: Dict[float, int]) -> Optional[int]:
    tok = block.numbering
    if tok:
        if looks_like_decimal(tok): return count_decimal_segments(tok)
        if looks_like_lower_alpha_paren(tok): return 1
        if looks_like_roman(tok): return 2
        if looks_like_upper_alpha(tok) or looks_like_bullet(tok): return 1
    if block.block_type == BlockType.HEADING and block._member_lines:
        size = round(block._member_lines[0].font_size, 1)
        return ranks.get(size, 3)
    if block.block_type == BlockType.LIST_ITEM and block._member_lines:
        return indent_to_level(block._member_lines[0].x0, min_x0)
    return None

def assign_hierarchy(blocks: List[Block]) -> List[Block]:
    if not blocks: return blocks
    min_x0 = min((l.x0 for b in blocks for l in b._member_lines), default=0.0)
    ranks = font_size_rank_map([l for b in blocks for l in b._member_lines])
    stack = []
    def key_for(b: Block): return b.numbering or normalize_heading_key(b.text)
    for b in blocks:
        L = infer_level(b, min_x0, ranks); b.level = L
        if b.block_type == BlockType.HEADING:
            while stack and stack[-1][1] >= (L or 1): stack.pop()
            stack.append((key_for(b), L or 1)); b.section_path = [k for (k, _) in stack]
        elif b.block_type == BlockType.LIST_ITEM:
            b.section_path = [k for (k, _) in stack] + ([key_for(b)] if key_for(b) else [])
        else:
            b.section_path = [k for (k, _) in stack]
    return blocks

# --------------------------
# Export JSON + document.txt with enriched metadata
# --------------------------
def build_doc_text(blocks: List[Block]) -> str:
    buf, pos = [], 0
    for b in blocks:
        start = pos
        path_str = ".".join(b.section_path) if b.section_path else "-"
        level_str = f"level={b.level}" if b.level else ""
        # metadata inline for LLM
        segment = f"[[ {b.block_id} | {b.block_type} ]] {b.text}"
        buf.append(segment)
        pos += len(segment)
        buf.append("\n\n"); pos += 2
        b.char_span_doc = {"start": start, "end": pos - 2}
    return "".join(buf)

def export_document(pdf_path: str, out_dir: str, blocks: List[Block], page_count: int) -> None:
    os.makedirs(out_dir, exist_ok=True)
    doc_id = os.path.basename(pdf_path)
    doc_text = build_doc_text(blocks)
    payload = {
        "document_id": doc_id,
        "pages": page_count,
        "blocks": [asdict(b) for b in blocks],
    }
    with open(os.path.join(out_dir, "document.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "document.txt"), "w", encoding="utf-8") as f:
        f.write(doc_text)

# --------------------------
# Helpers
# --------------------------
def normalize_heading_key(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
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
    PDF_PATH = "sample/exhibit101.pdf"
    OUT_DIR = "output/"
    if not os.path.exists(PDF_PATH):
        print(f"❌ Error: Input file not found at '{PDF_PATH}'")
        sys.exit(1)
    main(PDF_PATH, OUT_DIR)
