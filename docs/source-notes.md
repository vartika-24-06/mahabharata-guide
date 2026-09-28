# Source Notes: Sacred-Texts.com Ganguli Mahabharata

## 1. Source Acquisition & Download Method
* **Source Archive**: The Kisari Mohan Ganguli translation of the Mahabharata is downloaded as a single compressed zip file, `mahatxt.zip`, directly from the sacred-texts.com archive.
* **Download Strategy**: Obtained via a single archive download rather than page-by-page web scraping.

## 2. Site Usage Guidelines & Copyright Terms
* **Robots Policy (`robots.txt`)**: The site's `robots.txt` allows one text per day for automated access and strictly forbids repeated high-speed requests.
* **Licensing & Reuse**: Texts produced by the Internet Sacred Text Archive (ISTA) may be copied for non-commercial use, provided full attribution is retained.

## 3. File & Text Structure
* **Parva Files**: Each of the 18 parvas is stored as one `.txt` file inside the `mahatxt.zip` archive.
* **Standard Header**: Each file includes a standard header with:
  * Book number
  * Parva name
  * Translator credit
  * `"Scanned/Proofed at sacred-texts.com"` header line
* **Section Headings**: Sections inside each parva are marked with "Section" headings accompanied by Roman numerals (e.g., `SECTION I`, `SECTION II`).
* **Footnotes**:
  * Body text contains footnote markers formatted like `[1]`, `[2]`, which restart numbering per section.
  * All footnotes for that parva are collected under a single `"Footnotes"` heading placed at the end of the file.

## 4. Published Errata (from the site's own errata page)
The site documents the following known errata:
* **Book 1**: Sections 176 and 177 are swapped.
* **Book 2**: Misplaced section 67.
* **Book 7**: Missing section breaks at sections 54, 55, and 189.
* **Book 13**: Two sections labeled 168 (the first occurrence should be section 163).

## 5. Verified against the real files (this goes further than the site's errata page)

Running the actual parser against all 18 files in `mahatxt.zip` turned up two things the site's own errata page doesn't mention, plus confirmation the documented errata undersell how irregular the numbering really is.

**Two different section-marker formats, not one.** The design originally assumed every file uses `SECTION <ROMAN NUMERAL>`. In fact:
* **Books 1–7 and 12–15** (11 of 18) use `SECTION <ROMAN NUMERAL>` on its own line.
* **Books 8, 9, 10, 11, 16, 17, 18** (7 of 18 — Karna, Shalya, Sauptika, Stri, Mausala, Mahaprasthanika, Svargarohanika parvas) use a bare arabic number alone on its own line instead, with the word "Section" appearing only occasionally. The parser now detects which style a file uses (no file mixes both) and handles either.

**Footnotes only exist in 11 of the 18 books.** The 7 arabic-style books above have no "Footnotes" heading at all — confirmed genuine (no footnote content anywhere in those files), not a parse miss. The design's assumption that every parva ends in a Footnotes section only holds for the roman-numeral-style books.

**Parva name header casing differs too.** Roman-style books use all-caps ("ADI PARVA", "SANTI PARVA"). Arabic-style books use title case with a hyphen ("Karna-parva", "Mausala-parva"). Both are handled now. This also confirms, empirically, the site's own spelling for the four parvas already adopted for citations: **SANTI, ANUSASANA, ASWAMEDHA, ASRAMAVASIKA** (matches `answering-engine/design.md`'s citation convention exactly).

**The real numbering gaps go well beyond the documented errata**, confirmed by parsing every section number in every file and checking for gaps/duplicates against the min–max range:

| Book | Parva | Missing sections | Duplicate sections |
|---|---|---|---|
| 1 | Adi | 64, **177** | — |
| 2 | Sabha | 67 | — |
| 4 | Virata | 23 | 22 |
| 7 | Drona | 54, 55, 105, 123, 137, 150, 151, 182, 189 | 101, 122 |
| 12 | Santi | 34, 35, 157, 165, 174, 189, 240, 302, 364 | — |
| 13 | Anusasana | 8, 36, 69, **163** | **168** |
| 14 | Aswamedha | 10 | 5 |
| 15 | Asramavasika | 31 | — |

Bolded entries line up with the documented errata (Book 1's 177, Book 13's 163/168 pair). Everything else — Book 1's section 64, all of Book 4's and Book 7's gaps, all of Book 12's and Book 14's and Book 15's gaps — is new, found only by parsing the real files, not mentioned on the site's errata page.

**What this means for the build:** the completeness report (design.md, "Text preparation") can't just check against the four documented corrections and fail on anything else — the real data has far more irregularities than that. It now works two ways instead: confirm no whole parva is missing (hard fail if so), and log every gap/duplicate found per book as an informational finding rather than a blocking error, since these gaps are a property of the original 1883-1896 translation/scan, not something a build step can "fix" — they just need to be known and accounted for in section numbering.
