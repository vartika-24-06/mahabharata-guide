"""
Ingestion pipeline for the Ganguli Mahabharata text (Tasks 3-5 of answering-engine-tasks.md).

Reads the 18 parva-wise .txt files from mahatxt.zip, extracts the header
(book number, parva name, credit line), splits each file at "SECTION <roman>"
markers, converts to plain section numbers, cuts off everything from the
"FOOTNOTES" heading onward, strips [N]-style inline footnote markers from
body text, and splits each section into passages of roughly a few hundred
words. Produces a completeness report alongside the parsed passages.
"""
import re
import json
from dataclasses import dataclass, asdict
from pathlib import Path

ROMAN_VALUES = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}

# filename -> (book number, expected parva name as we'll display it; the
# real parva name is read from each file's own header, this is just for
# cross-checking the header parse succeeded)
FILENAME_BOOK_MAP = {
    "maha01.txt": 1, "maha02.txt": 2, "maha03.txt": 3, "maha04.txt": 4,
    "maha05.txt": 5, "maha06.txt": 6, "maha07.txt": 7, "maha08.txt": 8,
    "maha09.txt": 9, "maha10.txt": 10, "maha11.txt": 11, "maha12.txt": 12,
    "maha13.txt": 13, "maha14.txt": 14, "maha15.txt": 15, "maha16.txt": 16,
    "maha17.txt": 17, "maha18.txt": 18,
}


def roman_to_int(s: str) -> int:
    total = 0
    prev = 0
    for ch in reversed(s):
        v = ROMAN_VALUES[ch]
        if v < prev:
            total -= v
        else:
            total += v
            prev = v
    return total


@dataclass
class Passage:
    parva_file: str
    book_number: int
    parva_name: str
    section: int
    passage_index: int
    text: str
    word_count: int


@dataclass
class ParvaReport:
    filename: str
    book_number: int
    parva_name_header: str
    credit_line: str
    has_footnotes_heading: bool
    section_style: str
    section_count: int
    section_min: int
    section_max: int
    missing_sections: list
    duplicate_sections: list
    passage_count: int
    total_words: int


def extract_header(text: str, filename: str) -> tuple[str, str]:
    """Returns (parva_name, credit_line) from the file's opening header block.

    Two header styles exist across the 18 files: all-caps ("ADI PARVA") in
    most books, and title-case with a hyphen ("Karna-parva") in others
    (books 8, 9, 10, 11, 16, 17, 18)."""
    head = "\n".join(text.splitlines()[:40])
    parva_match = re.search(r'^([A-Za-z][A-Za-z \-]*parva)\s*$', head, re.MULTILINE | re.IGNORECASE)
    parva_name = parva_match.group(1).strip() if parva_match else ""

    # Credit line: the "Scanned...sacred-texts.com..." line (wording varies slightly per file)
    credit_match = re.search(
        r'^(Scanned.*sacred-texts\.com.*(?:\n.*)?)', head, re.MULTILINE | re.IGNORECASE
    )
    # Take just the first line of the credit block for the report (full line kept in real use)
    credit_line = credit_match.group(1).splitlines()[0].strip() if credit_match else ""

    return parva_name, credit_line


def split_footnotes(text: str) -> tuple[str, str]:
    """Returns (body_before_footnotes, footnotes_block). If no FOOTNOTES
    heading exists, footnotes_block is empty and the flag is caller's job."""
    match = re.search(r'^FOOTNOTES\s*$', text, re.MULTILINE)
    if not match:
        return text, ""
    return text[:match.start()], text[match.start():]


ROMAN_HEADING = re.compile(r'^SECTION ([IVXLCDM]+)\s*$', re.MULTILINE)
ARABIC_HEADING = re.compile(r'^(?:Section )?([0-9]{1,4})\s*$', re.MULTILINE)


def detect_section_style(body: str) -> str:
    """Two conventions exist across the 18 files: 'SECTION <ROMAN>' headings
    (books 1-7, 12-15) and a bare arabic number alone on its own line, with
    the word 'Section' present only occasionally (books 8-11, 16-18).
    Detected per file since no file mixes the two."""
    if len(ROMAN_HEADING.findall(body)) > 0:
        return "roman"
    return "arabic"


def split_sections(body: str) -> tuple[list[tuple[int, str]], str]:
    """Returns (list of (section_number, section_text) in file order, style used)."""
    style = detect_section_style(body)
    pattern = ROMAN_HEADING if style == "roman" else ARABIC_HEADING
    matches = list(pattern.finditer(body))
    sections = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        section_text = body[start:end].strip()
        section_num = roman_to_int(m.group(1)) if style == "roman" else int(m.group(1))
        sections.append((section_num, section_text))
    return sections, style


def strip_footnote_markers(text: str) -> str:
    return re.sub(r'\[\d+\]', '', text)


def _split_oversized_paragraph(para: str, target_words: int) -> list[str]:
    """A handful of source sections (e.g. two in ANUSASANA PARVA) have no
    paragraph breaks at all - the whole section is one giant block of text.
    Without this, such a paragraph would pass straight through
    chunk_into_passages untouched and become a single 50,000+ character
    "passage", which is both a bad citation to show someone and too long
    for the OpenAI embeddings API's 8,192-token input limit. Splits on
    sentence boundaries instead, so it degrades to the same target size
    as normal passages rather than becoming an outlier."""
    sentences = re.split(r'(?<=[.!?])\s+', para)
    chunks = []
    current: list[str] = []
    current_words = 0
    for sent in sentences:
        wc = len(sent.split())
        if current_words + wc > target_words and current:
            chunks.append(" ".join(current))
            current = [sent]
            current_words = wc
        else:
            current.append(sent)
            current_words += wc
    if current:
        chunks.append(" ".join(current))
    return chunks


def chunk_into_passages(text: str, target_words: int = 300) -> list[str]:
    """Splits section text into passages of roughly target_words words,
    breaking on paragraph boundaries so we don't cut mid-sentence where avoidable."""
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    passages = []
    current: list[str] = []
    current_words = 0
    for para in paragraphs:
        wc = len(para.split())
        if wc > target_words * 3:
            # A single paragraph far bigger than our target - almost always
            # means the source had no paragraph breaks in this section at
            # all. Flush whatever's pending, split this paragraph on its
            # own, then continue.
            if current:
                passages.append(" ".join(current))
                current = []
                current_words = 0
            passages.extend(_split_oversized_paragraph(para, target_words))
        elif current_words + wc > target_words and current:
            passages.append(" ".join(current))
            current = [para]
            current_words = wc
        else:
            current.append(para)
            current_words += wc
    if current:
        passages.append(" ".join(current))
    return passages


def process_file(path: Path) -> tuple[ParvaReport, list[Passage]]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    parva_name, credit_line = extract_header(raw, path.name)
    body, footnotes_block = split_footnotes(raw)
    has_footnotes = bool(footnotes_block)

    sections, style = split_sections(body)
    nums = [n for n, _ in sections]
    dupes = sorted({n for n in nums if nums.count(n) > 1})

    passages: list[Passage] = []
    if nums:
        expected = set(range(min(nums), max(nums) + 1))
        missing = sorted(expected - set(nums))
    else:
        missing = []

    for sec_num, sec_text in sections:
        clean = strip_footnote_markers(sec_text)
        for idx, chunk in enumerate(chunk_into_passages(clean)):
            wc = len(chunk.split())
            passages.append(Passage(
                parva_file=path.name,
                book_number=FILENAME_BOOK_MAP[path.name],
                parva_name=parva_name,
                section=sec_num,
                passage_index=idx,
                text=chunk,
                word_count=wc,
            ))

    report = ParvaReport(
        filename=path.name,
        book_number=FILENAME_BOOK_MAP[path.name],
        parva_name_header=parva_name,
        credit_line=credit_line,
        has_footnotes_heading=has_footnotes,
        section_style=style,
        section_count=len(sections),
        section_min=min(nums) if nums else 0,
        section_max=max(nums) if nums else 0,
        missing_sections=missing,
        duplicate_sections=dupes,
        passage_count=len(passages),
        total_words=sum(p.word_count for p in passages),
    )
    return report, passages


def main():
    raw_dir = Path(__file__).parent.parent / "data_raw"
    if not raw_dir.exists():
        raw_dir = Path("/home/claude/mahabharata-guide/data_raw")

    all_reports = []
    all_passages = []
    for filename in sorted(FILENAME_BOOK_MAP, key=lambda f: FILENAME_BOOK_MAP[f]):
        path = raw_dir / filename
        report, passages = process_file(path)
        all_reports.append(report)
        all_passages.extend(passages)

    print(f"{'Book':<5}{'Parva (header)':<26}{'Style':<8}{'Sections':<10}{'Range':<10}{'Missing':<24}{'Dupes':<10}{'FN?':<5}{'Passages':<10}{'Words'}")
    for r in all_reports:
        missing_str = ",".join(map(str, r.missing_sections)) if r.missing_sections else "-"
        dupe_str = ",".join(map(str, r.duplicate_sections)) if r.duplicate_sections else "-"
        print(f"{r.book_number:<5}{r.parva_name_header:<26}{r.section_style:<8}{r.section_count:<10}"
              f"{str(r.section_min)+'-'+str(r.section_max):<10}{missing_str:<24}{dupe_str:<10}"
              f"{str(r.has_footnotes_heading):<5}{r.passage_count:<10}{r.total_words}")

    total_passages = len(all_passages)
    total_words = sum(p.word_count for p in all_passages)
    total_books = len(all_reports)
    print(f"\nTOTAL: {total_books} books, {total_passages} passages, {total_words} words")

    missing_books = set(FILENAME_BOOK_MAP.values()) - {r.book_number for r in all_reports}
    print(f"Missing books entirely: {sorted(missing_books) if missing_books else 'none'}")

    out_dir = raw_dir.parent / "data_processed"
    out_dir.mkdir(exist_ok=True)
    with open(out_dir / "completeness_report.json", "w") as f:
        json.dump([asdict(r) for r in all_reports], f, indent=2)
    with open(out_dir / "passages.jsonl", "w") as f:
        for p in all_passages:
            f.write(json.dumps(asdict(p)) + "\n")

    print(f"\nWrote {out_dir / 'completeness_report.json'} and {out_dir / 'passages.jsonl'}")


if __name__ == "__main__":
    main()
