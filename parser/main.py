import pdfplumber
from itertools import groupby
import os

PDF_PATH = "sample/A2013-18.pdf"     
def extract_words(page):
    return page.extract_words(extra_attrs=["fontname", "size"])

def group_words_into_lines(words, tolerance):
    words_sorted = sorted(words, key=lambda w: (round(w["top"] / tolerance), w["x0"]))
    grouped_lines = []

    for _, line_group in groupby(words_sorted, key=lambda w: round(w["top"]/tolerance)):
        line_words = list(line_group)
        line_words.sort(key=itemgetter("x0"))
        grouped_lines.append(line_words)

    return grouped_lines

def main():
    if not os.path.exists(PDF_PATH):
        print(f"❌ File not found: {PDF_PATH}")
        return

    with pdfplumber.open(PDF_PATH) as pdf:
        page = pdf.pages[38]
        words = extract_words(page)



if __name__ == "__main__":
    main()