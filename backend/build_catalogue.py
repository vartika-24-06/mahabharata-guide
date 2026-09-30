"""
Task 14: story catalogue (design.md "Story mode" - "A catalogue file
lists the Featured Characters and the 18 parvas. Each entry points to
the sections that support stories about it. It is built with the
ingestion script and reviewed by hand, so no story is offered that the
text cannot support.").

Featured Characters starter list is story-mode requirements.md's own
"for example" list (well-known: Arjuna, Karna, Draupadi, Bhishma,
Krishna, Yudhishthira; lesser-known: Vidura, Shikhandi, Ghatotkacha,
Sanjaya) - checked here against the real corpus rather than assumed, per
that same requirement ("Each name must be checked against the Ganguli
text, because stories can only be told from what the text contains").

A character "has enough material" if there are at least MIN_SECTIONS
distinct sections where the name is mentioned at least MIN_MENTIONS_PER_
SECTION times - a single passing mention isn't enough to hang a story
on. These thresholds, and the final list, are a content decision (see
docs/decision-log.md for what the run below actually found and what was
kept/dropped).

For a Parva-level entry, section_refs is every section in that parva -
"a story from that Parva" can draw from anywhere in it, unlike a
character entry where only sections that actually mention the character
qualify.

Run with: python build_catalogue.py
"""
import json
import re
from collections import defaultdict
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
PASSAGES_PATH = BACKEND_DIR.parent / "data_processed" / "passages.jsonl"
OUT_PATH = BACKEND_DIR.parent / "data_processed" / "catalogue.json"

MIN_SECTIONS = 3
MIN_MENTIONS_PER_SECTION = 2

# name -> regex alternatives actually seen in the corpus (verified by a
# one-off grep against data_processed/passages.jsonl before writing this
# list - see docs/decision-log.md).
FEATURED_CHARACTERS = {
    "Arjuna": ["Arjuna", "Arjun"],
    "Karna": ["Karna"],
    "Draupadi": ["Draupadi"],
    "Bhishma": ["Bhishma"],
    "Krishna": ["Krishna"],
    "Yudhishthira": ["Yudhishthira", "Yudhisthira", "Yudisthir"],
    "Vidura": ["Vidura"],
    "Shikhandi": ["Shikhandi", "Sikhandin"],
    "Ghatotkacha": ["Ghatotkacha"],
    "Sanjaya": ["Sanjaya"],
}


def load_passages():
    passages = []
    with open(PASSAGES_PATH) as f:
        for line in f:
            passages.append(json.loads(line))
    return passages


def build_character_entry(name, variants, passages):
    # Keyed by (book_number, section), NOT (parva_name, section) - the 18
    # parvas are not in alphabetical order in the epic (Adi, Sabha, Vana,
    # Virata, Udyoga, Bhishma, ...), so sorting by parva_name would give
    # "Tell me more" and "the next part" a nonsensical reading order.
    # book_number is the corpus's own canonical book order (ingest.py).
    pattern = re.compile(r"\b(" + "|".join(re.escape(v) for v in variants) + r")\b", re.I)
    section_mentions = defaultdict(int)  # (book_number, parva_name, section) -> count
    for p in passages:
        count = len(pattern.findall(p["text"]))
        if count:
            section_mentions[(p["book_number"], p["parva_name"], p["section"])] += count

    qualifying = {
        key: count for key, count in section_mentions.items()
        if count >= MIN_MENTIONS_PER_SECTION
    }
    return {
        "subject": name,
        "type": "character",
        "total_mentions": sum(section_mentions.values()),
        "sections_mentioned_in": len(section_mentions),
        "qualifying_sections": len(qualifying),
        "section_refs": [
            {"parva_name": parva, "section": section}
            for (_book, parva, section) in sorted(qualifying.keys())
        ],
    }


def build_parva_entries(passages):
    sections_by_parva = defaultdict(set)
    book_number_by_parva = {}
    for p in passages:
        sections_by_parva[p["parva_name"]].add(p["section"])
        book_number_by_parva[p["parva_name"]] = p["book_number"]

    entries = []
    for parva_name in sorted(sections_by_parva, key=lambda name: book_number_by_parva[name]):
        sections = sorted(sections_by_parva[parva_name])
        entries.append({
            "subject": parva_name,
            "type": "parva",
            "book_number": book_number_by_parva[parva_name],
            "section_refs": [
                {"parva_name": parva_name, "section": s} for s in sections
            ],
        })
    return entries


def main():
    passages = load_passages()
    print(f"Loaded {len(passages)} passages.\n")

    character_entries = [
        build_character_entry(name, variants, passages)
        for name, variants in FEATURED_CHARACTERS.items()
    ]

    print(f"{'Character':<14}{'Total mentions':<16}{'Sections (any)':<16}"
          f"{'Sections (>=2 mentions)':<24}{'Meets threshold?'}")
    kept, dropped = [], []
    for entry in character_entries:
        meets = entry["qualifying_sections"] >= MIN_SECTIONS
        (kept if meets else dropped).append(entry["subject"])
        print(f"{entry['subject']:<14}{entry['total_mentions']:<16}"
              f"{entry['sections_mentioned_in']:<16}{entry['qualifying_sections']:<24}"
              f"{'yes' if meets else 'NO - below threshold'}")

    print(f"\nKept: {kept}")
    print(f"Dropped (below {MIN_SECTIONS}-section threshold): {dropped}")

    final_characters = [e for e in character_entries if e["qualifying_sections"] >= MIN_SECTIONS]
    parva_entries = build_parva_entries(passages)

    catalogue = {
        "characters": final_characters,
        "parvas": parva_entries,
        "thresholds": {
            "min_sections": MIN_SECTIONS,
            "min_mentions_per_section": MIN_MENTIONS_PER_SECTION,
        },
    }

    with open(OUT_PATH, "w") as f:
        json.dump(catalogue, f, indent=2)

    print(f"\nWrote {OUT_PATH}: {len(final_characters)} characters, {len(parva_entries)} parvas.")


if __name__ == "__main__":
    main()
