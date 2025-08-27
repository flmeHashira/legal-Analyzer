# -*- coding: utf-8 -*-
import pdfplumber
import joblib
from itertools import groupby
from operator import itemgetter
import json
import re
import os
from pathlib import Path

# ========= CONFIG =========
PDF_PATH = "sample/exhibit101.pdf"         # <-- your input PDF
MODEL_PATH = "line_classifier_v2.pkl"       # <-- trained (model, label_encoder)
TOLERANCE = 3                            # vertical grouping tolerance
SAVE_STRUCTURED = True                   # also save hierarchical JSON for debugging
STRUCTURED_OUT = "structured_output.json"
COMPACT_OUT = "compact_output.json"
# ==========================

# ---------- Helpers: noise filtering + continuation detection ----------
SENT_END = (".", "?", "!")
CONNECTOR_RE = re.compile(
    r"^(and|or|but|to|of|for|with|as|by|under|in|on|at|from|that|which|who|whom|whose|because|since|so|if|then)\b",
    re.IGNORECASE,
)

def _is_noise_clause(text: str) -> bool:
    """
    Filter obvious page/footnote crumbs that bloat counts.
    """
    s = (text or "").strip()
    if not s:
        return True
    if s.lower() in {"st", "nd", "rd", "th"}:
        return True
    if re.fullmatch(r"\d{1,3}", s):                      # bare small number (likely page/footnote)
        return True
    if re.fullmatch(r"[ivxlcdm]+\)?", s.lower()):        # lone roman numeral
        return True
    if len(s) <= 5 and re.fullmatch(r"\*?\d+\.?.*", s):  # "*1.", "1.", "2)"
        return True
    return False

def _looks_like_continuation(prev: str, cur: str) -> bool:
    """
    Decide if current line is a continuation of the previous one (join them).
    """
    if not prev:
        return False
    if prev.rstrip().endswith(SENT_END):
        return False

    c = (cur or "").lstrip()
    # punctuation/closing bracket/semicolon/colon starts → continuation
    if re.match(r"^[,;:)\]]", c):
        return True
    # lowercase start → continuation
    if c[:1].islower():
        return True
    # connector words at start → continuation
    if CONNECTOR_RE.match(c):
        return True
    return False

# ---------- PDF word → line grouping ----------
def extract_words(page):
    return page.extract_words(extra_attrs=["fontname", "size"])

def group_words_into_lines(words, tolerance, page_num):
    words_sorted = sorted(words, key=lambda w: (round(w["top"] / tolerance), w["x0"]))
    grouped_lines = []

    for _, line_group in groupby(words_sorted, key=lambda w: round(w["top"] / tolerance)):
        line_words = list(line_group)
        line_words.sort(key=itemgetter("x0"))

        text = " ".join(w["text"] for w in line_words).strip()
        if not text:
            continue

        # Early filter for tiny non-words (prevents junk upstream)
        if len(text) < 3 and not re.search(r"\w", text):
            continue

        font_sizes = [w.get("size", 0.0) for w in line_words]
        font_names = [str(w.get("fontname", "")) for w in line_words]
        avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 0.0
        is_bold = any(("Bold" in f) or ("BoldMT" in f) or ("Black" in f) for f in font_names)
        is_upper = text.isupper()

        grouped_lines.append({
            "page_num": page_num,
            "text": text,
            "avg_font_size": round(float(avg_font_size), 2),
            "is_bold": int(bool(is_bold)),
            "is_upper": int(bool(is_upper)),
            "text_length": int(len(text)),
        })

    return grouped_lines

def extract_all_lines(pdf_path):
    all_lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            words = extract_words(page) or []
            if words:
                lines = group_words_into_lines(words, TOLERANCE, page_num)
                all_lines.extend(lines)
    return all_lines

# ---------- Load classifier ----------
def load_classifier(model_path):
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"❌ Model not found: {model_path}")
    model, label_encoder = joblib.load(model_path)
    return model, label_encoder

def classify_lines(lines, model, label_encoder):
    feature_cols = ["avg_font_size", "is_bold", "is_upper", "text_length"]
    X = [[line[f] for f in feature_cols] for line in lines]
    y_pred = model.predict(X)
    labels = label_encoder.inverse_transform(y_pred)
    for line, label in zip(lines, labels):
        line["label"] = label
    return lines

# ---------- Build hierarchical structure (HEADING/CHAPTER/TOPIC/BODY) ----------
def build_structure(lines):
    """
    Builds the same structure you already had but with BODY paragraph merging and noise filtering.
    """
    structured = []
    current_heading = None
    current_chapter = None
    current_topic = None

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        label = line.get("label")
        text = (line.get("text") or "").strip()

        if label == "CHAPTER":
            # Merge two-line chapter titles like "CHAPTER II" + "PRELIMINARY"
            next_line = lines[i + 1] if (i + 1) < n else None
            if next_line:
                next_text = (next_line.get("text") or "").strip()
                # short, often ALL CAPS second line → join
                if len(next_text) < 60 and (next_line.get("is_upper", 0) == 1):
                    text = f"{text} – {next_text}"
                    i += 1  # consume next line

            current_chapter = {"chapter": text, "topics": []}
            if current_heading is None:
                current_heading = {"heading": None, "chapters": []}
                structured.append(current_heading)
            current_heading["chapters"].append(current_chapter)
            current_topic = None

        elif label == "HEADING":
            current_heading = {"heading": text, "chapters": []}
            structured.append(current_heading)
            current_chapter = None
            current_topic = None

        elif label in ("TOPIC", "SECTION"):  # treat SECTION like TOPIC (title for a body block)
            # Try to split inline topic/body if " – ", " — ", ":" present
            if re.search(r"\s[–—:]\s", text):
                topic_part, body_part = re.split(r"\s[–—:]\s", text, maxsplit=1)
                current_topic = {"topic": topic_part.strip(), "body": []}
                # seed first body paragraph with body_part (after filtering noise)
                if body_part.strip() and not _is_noise_clause(body_part):
                    current_topic["body"].append(body_part.strip())
            else:
                # Fallback: try a structure-based split if it starts with a number/keyword and is long
                words = text.split()
                if len(words) > 4 and (words[0][:1].isdigit() or words[0].lower().startswith("section")):
                    split_point = min(4, len(words) - 1)
                    topic_part = " ".join(words[:split_point])
                    body_part = " ".join(words[split_point:])
                    current_topic = {"topic": topic_part.strip(), "body": []}
                    if body_part.strip() and not _is_noise_clause(body_part):
                        current_topic["body"].append(body_part.strip())
                else:
                    current_topic = {"topic": text, "body": []}

            if current_chapter is None:
                if current_heading is None:
                    current_heading = {"heading": None, "chapters": []}
                    structured.append(current_heading)
                current_chapter = {"chapter": None, "topics": []}
                current_heading["chapters"].append(current_chapter)

            current_chapter["topics"].append(current_topic)

        elif label == "BODY":
            if current_topic is None:
                # Orphaned BODY → create a dummy topic
                if current_chapter is None:
                    if current_heading is None:
                        current_heading = {"heading": None, "chapters": []}
                        structured.append(current_heading)
                    current_chapter = {"chapter": None, "topics": []}
                    current_heading["chapters"].append(current_chapter)
                current_topic = {"topic": None, "body": []}
                current_chapter["topics"].append(current_topic)

            # Drop noise crumbs
            if _is_noise_clause(text):
                i += 1
                continue

            # Merge with previous line if it looks like a continuation
            if current_topic["body"]:
                prev = current_topic["body"][-1]
                if _looks_like_continuation(prev, text):
                    current_topic["body"][-1] = (prev.rstrip() + " " + text.lstrip()).strip()
                else:
                    current_topic["body"].append(text)
            else:
                current_topic["body"].append(text)

        # OTHER labels → ignore or treat as BODY (your dataset mainly uses above)
        i += 1

    return structured

# ---------- Compact for LLM (paragraph-level) ----------
def flatten_and_merge_paragraphs(structured):
    """
    Produce paragraph-level records:
      { "context": "Heading | Chapter", "topic": "<topic>", "text": "<merged paragraph>" }
    Also merges consecutive rows with same context when previous paragraph doesn't end a sentence.
    """
    compact = []
    for heading in structured:
        heading_title = heading.get("heading")
        for chapter in heading.get("chapters", []):
            chapter_title = chapter.get("chapter")
            context = None
            if heading_title and chapter_title:
                context = f"{heading_title} | {chapter_title}"
            else:
                context = heading_title or chapter_title

            for topic in chapter.get("topics", []):
                topic_title = topic.get("topic")
                # Filter + join body lines into a paragraph
                body_lines = [b.strip() for b in topic.get("body", []) if b and not _is_noise_clause(b)]
                if not body_lines:
                    continue
                paragraph = " ".join(body_lines).strip()

                row = {"context": context, "topic": topic_title, "text": paragraph}

                # Merge with previous if same context and previous doesn't end a sentence
                if compact and compact[-1]["context"] == row["context"]:
                    if not compact[-1]["text"].rstrip().endswith(SENT_END):
                        compact[-1]["text"] = (compact[-1]["text"].rstrip() + " " + row["text"].lstrip()).strip()
                        continue
                compact.append(row)
    return compact

# ---------- Main ----------
def main():
    if not os.path.exists(PDF_PATH):
        raise FileNotFoundError(f"❌ File not found: {PDF_PATH}")

    # Load model
    model, label_encoder = load_classifier(MODEL_PATH)

    # Extract + classify
    lines = extract_all_lines(PDF_PATH)
    classified = classify_lines(lines, model, label_encoder)

    # Build structure with BODY merging
    structured = build_structure(classified)

    # Save full structure (optional, for debugging)
    if SAVE_STRUCTURED:
        with open(STRUCTURED_OUT, "w", encoding="utf-8") as f:
            json.dump(structured, f, indent=2, ensure_ascii=False)

    # Build compact paragraph-level output
    compact = flatten_and_merge_paragraphs(structured)
    with open(COMPACT_OUT, "w", encoding="utf-8") as f:
        json.dump(compact, f, indent=2, ensure_ascii=False)

    print(f"✅ Done.\n- Structured: {STRUCTURED_OUT if SAVE_STRUCTURED else '(skipped)'}\n- Compact: {COMPACT_OUT}\n"
          f"Lines in: {len(lines)}  → Records out (compact): {len(compact)}")

if __name__ == "__main__":
    main()
