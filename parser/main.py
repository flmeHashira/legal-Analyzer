import pdfplumber
import joblib
from itertools import groupby
from operator import itemgetter
import json
import re

PDF_PATH = "sample/A2013-18.pdf"
TOLERANCE = 3

# Load trained model and label encoder
model, label_encoder = joblib.load("line_classifier.pkl")

def extract_words(page):
    return page.extract_words(extra_attrs=["fontname", "size"])

def group_words_into_lines(words, tolerance, page_num):
    words_sorted = sorted(words, key=lambda w: (round(w["top"] / tolerance), w["x0"]))
    grouped_lines = []

    for _, line_group in groupby(words_sorted, key=lambda w: round(w["top"] / tolerance)):
        line_words = list(line_group)
        line_words.sort(key=itemgetter("x0"))

        text = " ".join(w["text"] for w in line_words)
        font_sizes = [w["size"] for w in line_words]
        font_names = [w["fontname"] for w in line_words]
        avg_font_size = sum(font_sizes) / len(font_sizes)
        is_bold = any("Bold" in f for f in font_names)
        is_upper = text.isupper()

        grouped_lines.append({
            "page_num": page_num,
            "text": text,
            "avg_font_size": round(avg_font_size, 2),
            "is_bold": int(is_bold),
            "is_upper": int(is_upper),
            "text_length": len(text)
        })

    return grouped_lines

def extract_all_lines(pdf_path):
    all_lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            words = extract_words(page)
            lines = group_words_into_lines(words, TOLERANCE, page_num)
            all_lines.extend(lines)
    return all_lines

def classify_lines(lines):
    feature_cols = ["avg_font_size", "is_bold", "is_upper", "text_length"]
    X = [[line[f] for f in feature_cols] for line in lines]
    y_pred = model.predict(X)
    labels = label_encoder.inverse_transform(y_pred)
    for line, label in zip(lines, labels):
        line["label"] = label
    return lines

def build_structure(lines):
    structured = []
    current_heading = None
    current_chapter = None
    current_topic = None

    i = 0
    while i < len(lines):
        line = lines[i]
        label = line["label"]
        text = line["text"]

        # Handle CHAPTER across two lines
        if label == "CHAPTER":
            next_line = lines[i + 1] if i + 1 < len(lines) else None
            if next_line and len(next_line["text"]) < 60 and next_line["is_upper"]:
                text = text + " – " + next_line["text"]
                i += 1  # Skip next line

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

        elif label == "TOPIC":
            # Try to split topic-body using punctuation
            if re.search(r"\s[–—:]\s", text):
                topic_part, body_part = re.split(r"\s[–—:]\s", text, maxsplit=1)
                current_topic = {"topic": topic_part.strip(), "body": [body_part.strip()]}
            else:
                # Try structure-based split (e.g., starts with number + short chunk)
                words = text.split()
                if len(words) > 4 and (words[0][0].isdigit() or words[0].lower().startswith("section")):
                    split_point = min(4, len(words) - 1)
                    topic_part = " ".join(words[:split_point])
                    body_part = " ".join(words[split_point:])
                    current_topic = {"topic": topic_part.strip(), "body": [body_part.strip()]}
                else:
                    current_topic = {"topic": text.strip(), "body": []}

            if current_chapter is None:
                if current_heading is None:
                    current_heading = {"heading": None, "chapters": []}
                    structured.append(current_heading)
                current_chapter = {"chapter": None, "topics": []}
                current_heading["chapters"].append(current_chapter)

            current_chapter["topics"].append(current_topic)

        elif label == "BODY":
            if current_topic is None:
                # Orphaned BODY line → make dummy topic
                if current_chapter is None:
                    if current_heading is None:
                        current_heading = {"heading": None, "chapters": []}
                        structured.append(current_heading)
                    current_chapter = {"chapter": None, "topics": []}
                    current_heading["chapters"].append(current_chapter)
                current_topic = {"topic": None, "body": []}
                current_chapter["topics"].append(current_topic)

            current_topic["body"].append(text)

        i += 1

    return structured

def flatten_and_merge_paragraphs(structured):
    compact = []
    for heading in structured:
        heading_title = heading["heading"]
        for chapter in heading["chapters"]:
            chapter_title = chapter["chapter"]
            for topic in chapter["topics"]:
                topic_title = topic["topic"]
                body_text = " ".join(topic["body"]).strip()
                if body_text:
                    compact.append({
                        "context": f"{heading_title} | {chapter_title}",
                        "topic": topic_title,
                        "text": body_text
                    })
    return compact


def main():
    print(f"📄 Parsing {PDF_PATH}")
    lines = extract_all_lines(PDF_PATH)
    classified = classify_lines(lines)
    structured = build_structure(classified)
    compact = flatten_and_merge_paragraphs(structured)

    with open("compact_output.json", "w", encoding="utf-8") as f:
        json.dump(compact, f, indent=2, ensure_ascii=False)

    print("✅ Compact output saved to compact_output.json")

if __name__ == "__main__":
    main()
