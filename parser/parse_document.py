from __future__ import annotations
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from redactor import PresidioRedactor
from registry import RedactionRegistry
import pdfplumber

# --------------------------
# Config knobs
# --------------------------
# Alignment & Layout
X_ALIGN_TOL = 8.0
FONT_SIZE_TOL = 1.25
Y_CLUSTER_TOL = 3.0
INDENT_BUCKET = 36.0

# Text Extraction
WORD_X_TOL = 1.5  # Stricter tolerance to prevent "TheHeadoftheDept" artifacts

# Header/Footer Detection
HEADER_ZONE_PCT = 0.15
FOOTER_ZONE_PCT = 0.15
REPETITION_THRESHOLD = 0.30

# Table Detection
MIN_TABLE_ROWS = 3         # Invariant: Must have at least 3 rows to be a "Table"
MIN_COLUMNS_DETECTED = 2   # Invariant: Must have at least 2 aligned columns
BANNER_TEXT_THRESHOLD = 30 # Chars: If a merged cell text > 30 chars, don't repeat it (Banner Heuristic)

# --------------------------
# Regexes
# --------------------------
DECIMAL_RE = re.compile(r"^(\d+(?:\.\d+)*[\.)]?)\s+")
UPPER_ALPHA_RE = re.compile(r"^([A-Z][\.)])\s+")
LOWER_ALPHA_PAREN_RE = re.compile(r"^(\([a-z]\))\s+")
ROMAN_RE = re.compile(r"^(?:\(?([ivxlcdm]+)\)?[\.)]?)\s+", re.IGNORECASE)
BULLET_RE = re.compile(r"^([-•●○▪︎])\s+")
PAGE_NUM_RE = re.compile(r"Page\s+\d+\s+of\s+\d+", re.IGNORECASE)

class BlockType(str, Enum):
    META = "META"
    HEADING = "HEADING"
    PARAGRAPH = "PARAGRAPH"
    LIST_ITEM = "LIST_ITEM"
    TABLE = "TABLE"
    FOOTNOTE = "FOOTNOTE"

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
    is_table_placeholder: bool = False
    is_header_footer: bool = False

@dataclass
class Block:
    block_id: str
    block_type: BlockType
    text: str
    level: Optional[int] = None
    numbering: Optional[str] = None
    section_path: List[str] = field(default_factory=list)
    positions: Dict[str, Any] = field(default_factory=dict)
    char_span_doc: Dict[str, int] = field(default_factory=dict)
    _member_lines: List[Line] = field(default_factory=list, repr=False)

# --------------------------
# Utilities
# --------------------------
def _normalize_inline_spacing(t: str) -> str:
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

def indent_to_level(x0: float, min_x0: float) -> int:
    return max(1, int(round((x0 - min_x0) / INDENT_BUCKET)) + 1)

def _word_count(s: str) -> int:
    return len(re.findall(r"\w+", s))

def looks_like_decimal(token: str) -> bool: return bool(re.match(r"^\d+(?:\.\d+)*[\.)]?$", token))
def looks_like_lower_alpha_paren(token: str) -> bool: return bool(re.match(r"^\([a-z]\)$", token))
def looks_like_upper_alpha(token: str) -> bool: return bool(re.match(r"^[A-Z][\.)]$", token))
def looks_like_roman(token: str) -> bool: return bool(re.match(r"^[ivxlcdm]+$", token, re.IGNORECASE))
def looks_like_bullet(token: str) -> bool: return token in {"-", "•", "●", "○", "▪︎"}
def count_decimal_segments(token: str) -> int: return len(token.rstrip(").").strip().split("."))

def _looks_run_in_leadin(numbering: Optional[str], clean: str) -> bool:
    if not numbering: return False
    m = re.match(r"^([^\.]{1,60})\.\s+\S", clean)
    return bool(m) and _word_count(m.group(1)) <= 6

# --------------------------
# Table: 1. Repair / Formatting (Downstream)
# --------------------------
def format_table_to_markdown(table_data: List[List[Optional[str]]]) -> str:
    if not table_data: return ""
    lines = []
    for row in table_data:
        clean_row = [(cell or "").replace("\n", " ").strip() for cell in row]
        lines.append("| " + " | ".join(clean_row) + " |")
    return "\n".join(lines)

def fix_table_merges(table_data: List[List[Optional[str]]]) -> List[List[Optional[str]]]:
    """
    Repair logic with Banner Detection.
    Priority: Vertical (Top-down) > Horizontal (Left-right).
    """
    if not table_data: 
        return table_data
    
    rows = len(table_data)
    cols = len(table_data[0])

    for r in range(rows):
        for c in range(cols):
            if table_data[r][c] is None:
                # 1. Try Vertical Fill (Look Up)
                if r > 0 and table_data[r-1][c] is not None:
                    table_data[r][c] = table_data[r-1][c]
                # 2. Fallback to Horizontal Fill (Look Left)
                elif c > 0 and table_data[r][c-1] is not None:
                    # --- NEW: Banner Heuristic ---
                    prev_text = table_data[r][c-1]
                    # If text is long (> 30 chars), assume it's a banner spanning the row.
                    # Don't repeat it to save tokens.
                    if len(prev_text) > BANNER_TEXT_THRESHOLD:
                        table_data[r][c] = "" 
                    else:
                        table_data[r][c] = prev_text
    return table_data

# --------------------------
# Table: 2. Geometry & Detection (Upstream)
# --------------------------
def is_inside_box(word_box: Tuple[float, float, float, float], table_box: Tuple[float, float, float, float]) -> bool:
    wx0, wtop, wx1, wbottom = word_box
    tx0, ttop, tx1, tbottom = table_box
    wcx, wcy = (wx0 + wx1) / 2, (wtop + wbottom) / 2
    return (tx0 <= wcx <= tx1) and (ttop <= wcy <= tbottom)

def validate_table_structure(words_in_box: List[dict]) -> bool:
    """
    Phase 2: Geometric Validation.
    Invariant: "A TABLE exists only if column alignment is observable across >= 3 rows."
    """
    if not words_in_box: return False

    # 1. Check Row Invariant
    rows = set()
    for w in words_in_box:
        rows.add(int(round(w["top"] / Y_CLUSTER_TOL)))
    
    if len(rows) < MIN_TABLE_ROWS:
        return False

    # 2. Check Column Invariant
    x_starts = []
    for w in words_in_box:
        x_starts.append(round(w["x0"] / X_ALIGN_TOL) * X_ALIGN_TOL)
    
    counts = Counter(x_starts)
    valid_columns = sum(1 for count in counts.values() if count >= 3)
    
    return valid_columns >= MIN_COLUMNS_DETECTED

def assess_table_quality(data: List[List[str]]) -> bool:
    """
    Phase 3: Semantic Filtering.
    """
    if not data: return False
    
    # 1. Reject 1-column tables
    if len(data[0]) < 2: return False

    # 2. Reject empty/sparse tables
    total_cells = sum(len(row) for row in data)
    empty_cells = sum(1 for row in data for cell in row if not cell or not cell.strip())
    if total_cells > 0 and (empty_cells / total_cells) > 0.7:
        return False

    # 3. Reject "Layout Tables" (high word count per cell)
    words = [len(cell.split()) for row in data for cell in row if cell]
    if words:
        avg_words = sum(words) / len(words)
        if avg_words > 15: 
            return False

    return True

# --------------------------
# Extraction & Artifact Detection
# --------------------------
def extract_lines(pdf_path: str):
    lines = []
    page_sizes = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for pageno, page in enumerate(pdf.pages):
            page_sizes.append((page.width, page.height))
            
            # --- Step 0: Extract ALL words first (Ground Truth) ---
            words = page.extract_words(
                use_text_flow=True, 
                keep_blank_chars=False, 
                x_tolerance=WORD_X_TOL,
                extra_attrs=["fontname", "size"]
            )
            
            # --- Step 1: Candidate Generation ---
            candidates = page.find_tables()
            
            valid_tables = []
            valid_bboxes = []

            for t in candidates:
                t_bbox = t.bbox
                words_inside = [w for w in words if is_inside_box(
                    (w["x0"], w["top"], w["x1"], w["bottom"]), t_bbox
                )]

                # --- Step 2: Geometric Validation ---
                if not validate_table_structure(words_inside):
                    continue

                # --- Step 3: Semantic Filtering ---
                data = t.extract()
                if not assess_table_quality(data):
                    continue

                # --- Step 4: Repair & Store ---
                data = fix_table_merges(data)
                valid_tables.append((t, data))
                valid_bboxes.append(t_bbox)
            
            # --- Step 5: Integration ---
            for t, data in valid_tables:
                text_repr = format_table_to_markdown(data)
                lines.append(Line(
                    page=pageno, text=text_repr,
                    x0=t.bbox[0], x1=t.bbox[2], top=t.bbox[1], bottom=t.bbox[3],
                    font_size=0.0, is_bold=False, is_upper=False,
                    text_clean=text_repr, is_table_placeholder=True
                ))

            # Add Word Lines
            valid_words = []
            for w in words:
                w_box = (w["x0"], w["top"], w["x1"], w["bottom"])
                if not any(is_inside_box(w_box, t_box) for t_box in valid_bboxes):
                    valid_words.append(w)
            
            rows = {}
            for w in valid_words:
                key = int(round(w["top"] / max(1.0, Y_CLUSTER_TOL)))
                rows.setdefault(key, []).append(w)
            
            for _, ws in sorted(rows.items(), key=lambda kv: min(w["top"] for w in kv[1])):
                ws_sorted = sorted(ws, key=lambda w: w["x0"])
                text = _normalize_inline_spacing(" ".join(w["text"] for w in ws_sorted).strip())
                if not text: continue
                x0, x1 = min(w["x0"] for w in ws_sorted), max(w["x1"] for w in ws_sorted)
                top, bottom = min(w["top"] for w in ws_sorted), max(w["bottom"] for w in ws_sorted)
                sizes = [w.get("size") or 0.0 for w in ws_sorted]
                font_size = sum(sizes) / len(sizes) if sizes else 0.0
                fontnames = {w.get("fontname", "").lower() for w in ws_sorted}
                is_bold = any("bold" in fn for fn in fontnames)
                is_upper = text.isupper() and len(text) >= 3
                numbering, clean = detect_numbering_prefix(text)
                
                lines.append(Line(
                    page=pageno, text=text, x0=x0, x1=x1, top=top, bottom=bottom,
                    font_size=font_size, is_bold=is_bold, is_upper=is_upper,
                    numbering=numbering, text_clean=clean, is_table_placeholder=False
                ))
    
    lines.sort(key=lambda l: (l.page, l.top))
    return lines, page_sizes

def detect_and_mark_artifacts(lines: List[Line], page_sizes: List[Tuple[float, float]]) -> List[str]:
    """
    Identifies headers and footers that repeat across pages and marks them.
    """
    if not lines: return []
    
    zone_texts = Counter()
    total_pages = len(page_sizes)
    
    if total_pages >= 2:
        for line in lines:
            if line.is_table_placeholder: continue
            ph = page_sizes[line.page][1]
            is_top = line.top < (ph * HEADER_ZONE_PCT)
            is_bottom = line.bottom > (ph * (1.0 - FOOTER_ZONE_PCT))
            if is_top or is_bottom:
                zone_texts[line.text.strip()] += 1

    threshold = max(2, total_pages * REPETITION_THRESHOLD)
    artifact_set = {t for t, count in zone_texts.items() if count >= threshold}
    unique_artifacts = []

    for line in lines:
        if line.is_table_placeholder: continue
        txt = line.text.strip()
        ph = page_sizes[line.page][1]
        is_in_zone = (line.top < ph * HEADER_ZONE_PCT) or (line.bottom > ph * (1.0 - FOOTER_ZONE_PCT))
        
        if is_in_zone and txt in artifact_set:
            line.is_header_footer = True
            if txt not in unique_artifacts: unique_artifacts.append(txt)
        elif is_in_zone and PAGE_NUM_RE.search(txt):
            line.is_header_footer = True
            if txt not in unique_artifacts: unique_artifacts.append(txt)

    return unique_artifacts

# --------------------------
# Classification & Merging
# --------------------------
def classify_line(line: Line, ranks: Dict[float, int]) -> BlockType:
    if line.is_table_placeholder: return BlockType.TABLE
    clean = line.text_clean or ""
    has_num = bool(line.numbering)
    if _looks_run_in_leadin(line.numbering, clean): return BlockType.PARAGRAPH
    if has_num and looks_like_lower_alpha_paren(line.numbering): return BlockType.PARAGRAPH
    size_rank = ranks.get(round(line.font_size, 1), 99)
    if ((size_rank <= 2) or line.is_bold or line.is_upper) and _word_count(clean) <= 16 and not has_num:
        return BlockType.HEADING
    if has_num: return BlockType.LIST_ITEM
    return BlockType.PARAGRAPH

def font_size_rank_map(lines: List[Line]) -> Dict[float, int]:
    valid = [l for l in lines if not l.is_table_placeholder and not l.is_header_footer]
    uniq = sorted({round(l.font_size, 1) for l in valid}, reverse=True)
    return {size: i + 1 for i, size in enumerate(uniq)}

def merge_lines_to_blocks(lines: List[Line], page_sizes: List[Tuple[float, float]]) -> List[Block]:
    ranks = font_size_rank_map(lines)
    blocks, cur = [], None
    block_id_seq, reading_order = 1, 0

    def flush():
        nonlocal cur, reading_order
        if not cur: return
        page = cur._member_lines[0].page
        x0 = min(l.x0 for l in cur._member_lines)
        x1 = max(l.x1 for l in cur._member_lines)
        top = min(l.top for l in cur._member_lines)
        bottom = max(l.bottom for l in cur._member_lines)
        pw, ph = page_sizes[page]
        cur.positions = {
            "page": page,
            "bbox_pdf": [x0, ph - bottom, x1 - x0, bottom - top],
            "reading_order": reading_order,
        }
        reading_order += 1
        blocks.append(cur)
        cur = None

    for ln in lines:
        if ln.is_header_footer:
            continue

        btype = classify_line(ln, ranks)
        is_table = (btype == BlockType.TABLE)
        
        if cur and (is_table or cur.block_type == BlockType.TABLE or cur.block_type == BlockType.HEADING):
            flush()

        if cur is None:
            cur = Block(f"b{block_id_seq:06d}", btype, ln.text_clean, numbering=ln.numbering)
            cur._member_lines.append(ln); block_id_seq += 1
            if is_table: flush()
            continue

        same_type = (cur.block_type == btype)
        aligned = abs(cur._member_lines[-1].x0 - ln.x0) <= X_ALIGN_TOL
        similar_size = abs(cur._member_lines[-1].font_size - ln.font_size) <= FONT_SIZE_TOL
        
        if same_type and aligned and similar_size:
            cur.text = (cur.text + " " + (ln.text_clean or "")).strip()
            cur._member_lines.append(ln)
        else:
            flush()
            cur = Block(f"b{block_id_seq:06d}", btype, ln.text_clean, numbering=ln.numbering)
            cur._member_lines.append(ln); block_id_seq += 1
    flush()
    return blocks

# --------------------------
# Hierarchy
# --------------------------
def normalize_heading_key(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(r"[^A-Za-z0-9 ()\.-]", "", t)
    return t[:60]

def infer_level(block: Block, min_x0: float, ranks: Dict[float, int]) -> Optional[int]:
    if block.block_type == BlockType.TABLE: return None
    tok = block.numbering
    if tok:
        if looks_like_decimal(tok): return count_decimal_segments(tok)
        if looks_like_lower_alpha_paren(tok): return 1
        if looks_like_roman(tok): return 2
        if looks_like_upper_alpha(tok) or looks_like_bullet(tok): return 1
    if block.block_type == BlockType.HEADING and block._member_lines:
        return ranks.get(round(block._member_lines[0].font_size, 1), 3)
    if block.block_type == BlockType.LIST_ITEM and block._member_lines:
        return indent_to_level(block._member_lines[0].x0, min_x0)
    return None

def assign_hierarchy(blocks: List[Block]) -> List[Block]:
    text_lines = [l for b in blocks if b.block_type != BlockType.TABLE for l in b._member_lines]
    if not text_lines: return blocks
    min_x0 = min((l.x0 for l in text_lines), default=0.0)
    ranks = font_size_rank_map(text_lines)
    stack = []
    
    def key_for(b: Block): return b.numbering or normalize_heading_key(b.text)
    
    for b in blocks:
        L = infer_level(b, min_x0, ranks); b.level = L
        if b.block_type == BlockType.TABLE:
            b.section_path = [k for (k, _) in stack]
            continue
        if b.block_type == BlockType.HEADING:
            while stack and stack[-1][1] >= (L or 1): stack.pop()
            stack.append((key_for(b), L or 1)); b.section_path = [k for (k, _) in stack]
        elif b.block_type == BlockType.LIST_ITEM:
            b.section_path = [k for (k, _) in stack] + ([key_for(b)] if key_for(b) else [])
        else:
            b.section_path = [k for (k, _) in stack]
    return blocks

# --------------------------
# Export
# --------------------------
def build_doc_text(blocks: List[Block], artifacts: List[str]) -> str:
    buf, pos = [], 0
    for b in blocks:
        start = pos
        sep = "\n" if b.block_type == BlockType.TABLE else " "
        segment = f"[[ {b.block_id} | {b.block_type} ]]{sep}{b.text}"
        buf.append(segment)
        pos += len(segment)
        buf.append("\n\n"); pos += 2
        b.char_span_doc = {"start": start, "end": pos - 2}
        
    if artifacts:
        buf.append(f"[[ META | ARTIFACTS ]]\n")
        for art in artifacts:
            buf.append(f"- {art}\n")
            
    return "".join(buf)

# --------------------------
# Redact
# --------------------------
def batch_redact_blocks(blocks: List[Block]) -> Tuple[List[Block], Dict]:
    redactor = PresidioRedactor()
    
    # Initialize a fresh Registry for this document
    # This ensures PERSON_1 resets for every new PDF uploaded
    registry = RedactionRegistry()
    
    print(f"🔒 Starting Consistent PII Redaction on {len(blocks)} blocks...")
    count = 0
    
    for block in blocks:
        if block.block_type == BlockType.META:
            continue
            
        # Pass the registry to the redactor
        cleaned_text = redactor.redact(block.text, registry)
        
        if cleaned_text != block.text:
            block.text = cleaned_text
            count += 1
            
    print(f"✅ Redaction Complete. Replaced secrets in {count} blocks.")
    
    # Return the Vault from the registry
    return blocks, registry.vault


# Main Entry Point
def parse_pdf(pdf_path: str, out_dir: str):
    print(f"Processing {pdf_path}...")
    lines, page_sizes = extract_lines(pdf_path)
    
    artifacts = detect_and_mark_artifacts(lines, page_sizes)
    print(f"👻 Detected {len(artifacts)} repetitive header/footer artifacts.")
    
    blocks = merge_lines_to_blocks(lines, page_sizes)

    # --- FIX IS HERE: Unpack the tuple ---
    blocks, redaction_map = batch_redact_blocks(blocks)
    # -------------------------------------

    blocks = assign_hierarchy(blocks)
    
    os.makedirs(out_dir, exist_ok=True)
    
    # 1. Save the Document Structure (Sanitized)
    with open(os.path.join(out_dir, "document.json"), "w", encoding="utf-8") as f:
        json.dump({
            "document_id": os.path.basename(pdf_path),
            "pages": len(page_sizes),
            "layout_artifacts": artifacts,
            "blocks": [asdict(b) for b in blocks]
        }, f, ensure_ascii=False, indent=2)
    
    # 2. Save the Text (Sanitized)
    with open(os.path.join(out_dir, "document.txt"), "w", encoding="utf-8") as f:
        f.write(build_doc_text(blocks, artifacts))
        
    # 3. Save the Vault (The Redaction Map)
    map_path = os.path.join(out_dir, "redaction_map.json")
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(redaction_map, f, indent=2, ensure_ascii=False)

    print(f"✅ Done. Output saved to '{out_dir}'")


if __name__ == "__main__":
    PDF_PATH = sys.argv[1] if len(sys.argv) > 1 else "sample/pii_test_document.pdf"
    OUT_DIR = "output/"
    if not os.path.exists(PDF_PATH):
        print(f"❌ Error: {PDF_PATH} not found"); sys.exit(1)
    parse_pdf(PDF_PATH, OUT_DIR)