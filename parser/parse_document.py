from __future__ import annotations
import json
import os
import re
import sys
import traceback
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from redactor import PresidioRedactor
from registry import RedactionRegistry
import pdfplumber
from groq import Groq

# --------------------------
# Config knobs
# --------------------------
X_ALIGN_TOL = 8.0
FONT_SIZE_TOL = 1.25
Y_CLUSTER_TOL = 3.0
INDENT_BUCKET = 36.0
WORD_X_TOL = 1.5 
HEADER_ZONE_PCT = 0.15
FOOTER_ZONE_PCT = 0.15
REPETITION_THRESHOLD = 0.30
MIN_TABLE_ROWS = 3         
MIN_COLUMNS_DETECTED = 2   
BANNER_TEXT_THRESHOLD = 30
MAX_DOC_CHARS = 80_000      # ~20k tokens, safe headroom for llama-3.3-70b-versatile (now openAI)

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
# Tables
# --------------------------
def format_table_to_markdown(table_data: List[List[Optional[str]]]) -> str:
    if not table_data: return ""
    lines = []
    for row in table_data:
        clean_row = [(cell or "").replace("\n", " ").strip() for cell in row]
        lines.append("| " + " | ".join(clean_row) + " |")
    return "\n".join(lines)

def fix_table_merges(table_data: List[List[Optional[str]]]) -> List[List[Optional[str]]]:
    if not table_data: return table_data
    rows, cols = len(table_data), len(table_data[0])
    for r in range(rows):
        for c in range(cols):
            if table_data[r][c] is None:
                if r > 0 and table_data[r-1][c] is not None:
                    table_data[r][c] = table_data[r-1][c]
                elif c > 0 and table_data[r][c-1] is not None:
                    prev_text = table_data[r][c-1]
                    table_data[r][c] = "" if len(prev_text) > BANNER_TEXT_THRESHOLD else prev_text
    return table_data

def is_inside_box(word_box, table_box) -> bool:
    wx0, wtop, wx1, wbottom = word_box
    tx0, ttop, tx1, tbottom = table_box
    wcx, wcy = (wx0 + wx1) / 2, (wtop + wbottom) / 2
    return (tx0 <= wcx <= tx1) and (ttop <= wcy <= tbottom)

def validate_table_structure(words_in_box: List[dict]) -> bool:
    if not words_in_box: return False
    rows = set(int(round(w["top"] / Y_CLUSTER_TOL)) for w in words_in_box)
    if len(rows) < MIN_TABLE_ROWS: return False
    x_starts = [round(w["x0"] / X_ALIGN_TOL) * X_ALIGN_TOL for w in words_in_box]
    counts = Counter(x_starts)
    valid_columns = sum(1 for count in counts.values() if count >= 3)
    return valid_columns >= MIN_COLUMNS_DETECTED

def assess_table_quality(data: List[List[str]]) -> bool:
    if not data or len(data[0]) < 2: return False
    total_cells = sum(len(row) for row in data)
    empty_cells = sum(1 for row in data for cell in row if not cell or not cell.strip())
    if total_cells > 0 and (empty_cells / total_cells) > 0.7: return False
    words = [len(cell.split()) for row in data for cell in row if cell]
    if words and (sum(words) / len(words)) > 15: return False
    return True

# --------------------------
# Extraction
# --------------------------
def extract_lines(pdf_path: str):
    lines = []
    page_sizes = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for pageno, page in enumerate(pdf.pages):
            page_sizes.append((page.width, page.height))
            
            words = page.extract_words(
                use_text_flow=True, 
                keep_blank_chars=False, 
                x_tolerance=WORD_X_TOL,
                extra_attrs=["fontname", "size"]
            )
            
            # --- Table Extraction ---
            candidates = page.find_tables()
            valid_bboxes = []
            for t in candidates:
                words_inside = [w for w in words if is_inside_box((w["x0"], w["top"], w["x1"], w["bottom"]), t.bbox)]
                if validate_table_structure(words_inside):
                    data = fix_table_merges(t.extract())
                    if assess_table_quality(data):
                        text_repr = format_table_to_markdown(data)
                        lines.append(Line(
                            page=pageno, text=text_repr, x0=t.bbox[0], x1=t.bbox[2], top=t.bbox[1], bottom=t.bbox[3],
                            font_size=0.0, is_bold=False, is_upper=False, text_clean=text_repr, is_table_placeholder=True
                        ))
                        valid_bboxes.append(t.bbox)

            # --- Word Merging into Lines ---
            valid_words = [w for w in words if not any(is_inside_box((w["x0"], w["top"], w["x1"], w["bottom"]), b) for b in valid_bboxes)]
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
                num, clean = detect_numbering_prefix(text)
                
                lines.append(Line(
                    page=pageno, text=text, x0=x0, x1=x1, top=top, bottom=bottom,
                    font_size=font_size, is_bold=is_bold, is_upper=is_upper,
                    numbering=num, text_clean=clean, is_table_placeholder=False
                ))
    
    lines.sort(key=lambda l: (l.page, l.top))
    return lines, page_sizes

def detect_and_mark_artifacts(lines: List[Line], page_sizes: List[Tuple[float, float]]) -> List[str]:
    if not lines: return []
    zone_texts = Counter()
    total_pages = len(page_sizes)
    if total_pages >= 2:
        for line in lines:
            if line.is_table_placeholder: continue
            ph = page_sizes[line.page][1]
            if line.top < (ph * HEADER_ZONE_PCT) or line.bottom > (ph * (1.0 - FOOTER_ZONE_PCT)):
                zone_texts[line.text.strip()] += 1
    threshold = max(2, total_pages * REPETITION_THRESHOLD)
    artifact_set = {t for t, count in zone_texts.items() if count >= threshold}
    unique_artifacts = []
    for line in lines:
        if line.is_table_placeholder: continue
        txt = line.text.strip()
        ph = page_sizes[line.page][1]
        is_in_zone = (line.top < ph * HEADER_ZONE_PCT) or (line.bottom > ph * (1.0 - FOOTER_ZONE_PCT))
        if (is_in_zone and txt in artifact_set) or (is_in_zone and PAGE_NUM_RE.search(txt)):
            line.is_header_footer = True
            if txt not in unique_artifacts: unique_artifacts.append(txt)
    return unique_artifacts

# --------------------------
# Merging & Hierarchy
# --------------------------
def classify_line(line: Line, ranks: Dict[float, int]) -> BlockType:
    if line.is_table_placeholder: return BlockType.TABLE
    clean = line.text_clean or ""
    has_num = bool(line.numbering)
    if _looks_run_in_leadin(line.numbering, clean) or (has_num and looks_like_lower_alpha_paren(line.numbering)):
        return BlockType.PARAGRAPH
    size_rank = ranks.get(round(line.font_size, 1), 99)
    if ((size_rank <= 2) or line.is_bold or line.is_upper) and _word_count(clean) <= 16 and not has_num:
        return BlockType.HEADING
    return BlockType.LIST_ITEM if has_num else BlockType.PARAGRAPH

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
        x0, x1 = min(l.x0 for l in cur._member_lines), max(l.x1 for l in cur._member_lines)
        top, bottom = min(l.top for l in cur._member_lines), max(l.bottom for l in cur._member_lines)
        pw, ph = page_sizes[page]
        cur.positions = {"page": page, "bbox_pdf": [x0, ph - bottom, x1 - x0, bottom - top], "reading_order": reading_order}
        reading_order += 1; blocks.append(cur); cur = None

    for ln in lines:
        if ln.is_header_footer: continue
        btype = classify_line(ln, ranks)
        if cur and (btype == BlockType.TABLE or cur.block_type == BlockType.TABLE or cur.block_type == BlockType.HEADING): flush()
        if cur is None:
            cur = Block(f"b{block_id_seq:06d}", btype, ln.text_clean, numbering=ln.numbering)
            cur._member_lines.append(ln); block_id_seq += 1
            if btype == BlockType.TABLE: flush()
            continue
        if cur.block_type == btype and abs(cur._member_lines[-1].x0 - ln.x0) <= X_ALIGN_TOL and abs(cur._member_lines[-1].font_size - ln.font_size) <= FONT_SIZE_TOL:
            cur.text = (cur.text + " " + (ln.text_clean or "")).strip(); cur._member_lines.append(ln)
        else:
            flush()
            cur = Block(f"b{block_id_seq:06d}", btype, ln.text_clean, numbering=ln.numbering)
            cur._member_lines.append(ln); block_id_seq += 1
    flush()
    return blocks

def assign_hierarchy(blocks: List[Block]) -> List[Block]:
    text_lines = [l for b in blocks if b.block_type != BlockType.TABLE for l in b._member_lines]
    if not text_lines: return blocks
    min_x0 = min((l.x0 for l in text_lines), default=0.0)
    ranks = font_size_rank_map(text_lines)
    stack = []
    for b in blocks:
        tok = b.numbering
        L = count_decimal_segments(tok) if tok and looks_like_decimal(tok) else (ranks.get(round(b._member_lines[0].font_size, 1), 3) if b.block_type == BlockType.HEADING else indent_to_level(b._member_lines[0].x0, min_x0))
        b.level = L
        if b.block_type == BlockType.HEADING:
            while stack and stack[-1][1] >= (L or 1): stack.pop()
            stack.append((b.numbering or b.text[:60], L or 1))
        b.section_path = [k for (k, _) in stack]
    return blocks

# --------------------------
# Export & Redact
# --------------------------
def build_doc_text(blocks: List[Block], artifacts: List[str]) -> str:
    buf, pos = [], 0
    for b in blocks:
        start = pos
        sep = "\n" if b.block_type == BlockType.TABLE else " "
        segment = f"[[ {b.block_id} | {b.block_type} ]]{sep}{b.text}"
        buf.append(segment); pos += len(segment); buf.append("\n\n"); pos += 2
        b.char_span_doc = {"start": start, "end": pos - 2}
    if artifacts:
        buf.append(f"[[ META | ARTIFACTS ]]\n")
        for art in artifacts: buf.append(f"- {art}\n")
    return "".join(buf)

def batch_redact_blocks(blocks: List[Block]) -> Tuple[List[Block], Dict]:
    redactor = PresidioRedactor(); registry = RedactionRegistry()
    print(f"🔒 Starting Redaction on {len(blocks)} blocks...")
    count = 0
    for block in blocks:
        cleaned = redactor.redact(block.text, registry)
        if cleaned != block.text: block.text = cleaned; count += 1
    print(f"✅ Replaced secrets in {count} blocks.")
    return blocks, registry.vault

# --------------------------
# AI Analysis (Groq)
# --------------------------
def analyze_legal_document(doc_text_path: str) -> List[Dict]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError("❌ GROQ_API_KEY is not set. Export it before running.")

    try:
        client = Groq(api_key=api_key)

        with open(doc_text_path, 'r', encoding='utf-8') as f:
            document_text = f.read()

        # Truncate if document exceeds safe token headroom
        if len(document_text) > MAX_DOC_CHARS:
            print(f"⚠️  Document truncated from {len(document_text)} to {MAX_DOC_CHARS} chars to fit context window.")
            document_text = document_text[:MAX_DOC_CHARS]

        print("🧠 Sending document to Groq...")
        chat_completion = client.chat.completions.create(
            messages = [
                {
                    "role": "system",
                    "content": """
                    You are a legal contract analysis AI.

                    The document is provided as a sequence of blocks.

                    Each block has the format:

                    [[ BLOCK_ID | BLOCK_TYPE ]] text

                    Example:
                    [[ b000123 | BlockType.PARAGRAPH ]] The employee shall not disclose confidential information.

                    Rules:
                    - BLOCK_ID uniquely identifies the text block.
                    - BLOCK_ID maps to the original PDF location and will be used for highlighting.

                    Your task:
                    Identify important clauses and potential risks in the contract.

                    For each finding:
                    - Determine the topic of the clause
                    - Assign a risk level
                    - Write a short summary (used as the card title)
                    - Write a detailed explanation of why this clause is significant
                    - List specific triggers: concrete reasons why this clause was flagged
                    - Return the BLOCK_IDs that support the finding

                    Risk levels allowed:
                    - high   → high risk or unusual clause
                    - medium → noteworthy but common clause
                    - low    → standard clause

                    CRITICAL RULES:
                    - Always reference clauses using BLOCK_IDs.
                    - NEVER invent BLOCK_IDs.
                    - NEVER quote large parts of the document.
                    - NEVER return text offsets.
                    - Only reference BLOCK_IDs that appear in the input.
                    - Multiple BLOCK_IDs may belong to the same finding.

                    Output strictly in JSON.

                    Schema:

                    {
                    "findings": [
                        {
                        "finding_id": 0,
                        "risk": "high | medium | low",
                        "summary": "short title describing the clause",
                        "explanation": "detailed explanation of why this clause is significant",
                        "triggers": [
                            "specific reason this was flagged",
                            "another specific reason"
                        ],
                        "block_ids": ["b000001", "b000002"]
                        }
                    ]
                    }
                    """
                },
                {
                    "role": "user",
                    "content": document_text
                }
            ],
            model="openai/gpt-oss-20b",
            temperature=0.1,
            max_tokens=4096,
            response_format={"type": "json_object"}
        )

        raw_response = chat_completion.choices[0].message.content
        finish_reason = chat_completion.choices[0].finish_reason

        print(f"🔍 finish_reason: {finish_reason}", flush=True)

        # content is None when finish_reason is "length" (hit token limit)
        if raw_response is None:
            print(f"❌ Groq returned None content. finish_reason='{finish_reason}'. "
                  f"The document likely exceeded the model's output token limit.", flush=True)
            return []

        parsed = json.loads(raw_response)

        findings = parsed.get("findings", [])
        if not findings:
            print("⚠️  Groq returned valid JSON but 'findings' is empty or missing.", flush=True)
        else:
            print(f"✅ Groq returned {len(findings)} finding(s).", flush=True)

        return findings

    except EnvironmentError:
        raise
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse Groq response as JSON: {e}")
        traceback.print_exc()
        return []
    except Exception as e:
        print(f"❌ Groq request failed: {e}")
        traceback.print_exc()
        return []

# --------------------------
# Main Entry Point
# --------------------------
def parse_pdf(pdf_path: str, out_dir: str):
    lines, page_sizes = extract_lines(pdf_path)

    os.makedirs(out_dir, exist_ok=True)

    if not lines:
        print("❌ CRITICAL: No lines extracted. Marking as UNSUPPORTED.")
        with open(os.path.join(out_dir, "document.json"), "w", encoding="utf-8") as f:
            json.dump({"error": "UNSUPPORTED_DOCUMENT", "blocks": [], "findings": []}, f)
        return

    artifacts = detect_and_mark_artifacts(lines, page_sizes)
    blocks = merge_lines_to_blocks(lines, page_sizes)

    blocks, redaction_map = batch_redact_blocks(blocks)
    blocks = assign_hierarchy(blocks)
    
    doc_text = build_doc_text(blocks, artifacts)

    #If string is empty, DO NOT call AI
    if not doc_text.strip():
        print("❌ CRITICAL: Resulting text is empty. Aborting API call.")
        with open(os.path.join(out_dir, "document.json"), "w", encoding="utf-8") as f:
            json.dump({"error": "UNSUPPORTED_DOCUMENT", "blocks": [], "findings": []}, f)
        return

    # Save files
    doc_text_path = os.path.join(out_dir, "document.txt")
    with open(doc_text_path, "w", encoding="utf-8") as f: f.write(doc_text)
    with open(os.path.join(out_dir, "redaction_map.json"), "w", encoding="utf-8") as f: json.dump(redaction_map, f)

    # Call AI
    llm_findings = analyze_legal_document(doc_text_path)

    # Save final JSON
    with open(os.path.join(out_dir, "document.json"), "w", encoding="utf-8") as f:
        json.dump({
            "pages": len(page_sizes),
            "blocks": [asdict(b) for b in blocks],
            "findings": llm_findings
        }, f, ensure_ascii=False, indent=2)

    print(f"✅ DONE: {out_dir}")

if __name__ == "__main__":
    PDF_PATH = sys.argv[1] if len(sys.argv) > 1 else "sample/pii_test_document.pdf"
    parse_pdf(PDF_PATH, "output/")