"""
Task 8: scope check.

A request passes if it matches the curated list of epic names, places,
themes and spelling variants, OR if it's a follow-up in an ongoing
conversation (has_context=True). Everything else gets a fixed one-line
decline (design.md "Scope check and guardrails").

The curated list is deliberately simple keyword matching, not NER or a
model call - this is a fast, free, offline gate that runs before any paid
API call, and design.md says it's "tuned against the eval set," implying
a plain list is the intended v1 approach, not a classifier of its own.

Hard cases from docs/qna-eval-set (design.md calls these out explicitly):
- Row 15 ("Is fate stronger than effort in the epic?"): no character
  names, but says "the epic." Expected label is Philosophical, not
  Decline - so generic epic-referencing words ("epic", "mahabharata")
  are included in the curated list below, not just character/place names.
- Row 25 ("The war led to so many deaths. What was the point?"):
  expected label is Follow-up, and is marked Settle specifically because
  it depends on context or on "the war" alone. Resolved here by NOT
  adding a bare word like "war" to the curated list (too broad - it'd
  match any war, not just this epic's) and relying on has_context
  instead: this passes when there's a prior turn to follow up on, and
  declines standalone, same as row 24. This matches the row's own
  expected label (Follow-up, not a keyword-matched Factual/Philosophical).
- Rows 29-31 (modern dilemmas: firing an employee, buying plants,
  overeating): already resolved by an earlier decision (see
  docs/decision-log.md) - the modern-dilemma classifier is deferred to
  v2, so these correctly decline in v1 simply because they contain no
  curated term and have no conversation context.
- Row 24 ("Tell me more about her." with no earlier question): declines
  for the same reason as an unresolved row 25 - no curated term, no
  context.
"""
import re

# The 18 parva names, spelled exactly as the source site spells them
# (design.md: "Citations name each parva as the source site spells it").
PARVA_NAMES = [
    "adi parva", "sabha parva", "vana parva", "virata parva",
    "udyoga parva", "bhishma parva", "drona parva", "karna-parva",
    "shalya-parva", "sauptika-parva", "stri-parva", "santi parva",
    "anusasana parva", "aswamedha parva", "asramavasika parva",
    "mausala-parva", "mahaprasthanika-parva", "svargarohanika-parva",
]

# Major characters and common alternative spellings (design.md examples:
# "Yudisthir", "Arjun"). Not exhaustive - tune against the eval set as
# more gaps turn up.
CHARACTER_NAMES = [
    "arjuna", "arjun", "krishna", "kunti", "yudhishthira", "yudhisthir",
    "yudisthir", "bhima", "bhimasena", "nakula", "sahadeva",
    "duryodhana", "dushasana", "shakuni", "karna", "bhishma", "drona",
    "kripa", "ashwatthama", "vidura", "dhritarashtra", "gandhari",
    "draupadi", "abhimanyu", "drishtadyumna", "dhrishtadyumna",
    "subhadra", "ekalavya", "jayadratha", "shalya", "kripacharya",
    "ghatotkacha", "pandu", "satyavati", "shantanu", "vyasa", "sanjaya",
    "pandavas", "kauravas", "pandava", "kaurava",
]

# Places specific to the epic.
PLACE_NAMES = [
    "kurukshetra", "hastinapura", "hastinapur", "indraprastha",
    "panchala", "matsya", "dwaraka", "dwarka",
]

# Generic epic-referencing and theme words. Covers row 15's "the epic"
# case - a question can be clearly in-scope without naming any specific
# character.
THEME_WORDS = [
    "mahabharata", "mahabharat", "the epic", "bhagavad gita", "gita",
    "dharma", "karma", "kurukshetra war", "the great war",
    "dice game", "game of dice", "vastraharan", "cheerharan",
]

ALL_TERMS = PARVA_NAMES + CHARACTER_NAMES + PLACE_NAMES + THEME_WORDS

# Longest terms first, so e.g. "kurukshetra war" matches as a phrase
# before "kurukshetra" alone would short-circuit anything.
_TERM_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(t) for t in sorted(ALL_TERMS, key=len, reverse=True)) + r')\b',
    re.IGNORECASE,
)

DECLINE_MESSAGE = (
    "I can only help with questions about the Mahabharata - its "
    "characters, events and themes. Try asking about a character, "
    "place or moment from the epic instead."
)


def matches_curated_list(query: str) -> bool:
    return bool(_TERM_PATTERN.search(query))


def check_scope(query: str, has_context: bool = False) -> tuple[bool, str | None]:
    """Returns (in_scope, decline_message). decline_message is None when
    in_scope is True. has_context=True means this is a follow-up in an
    ongoing conversation - see the row 25 reasoning above for why that
    matters independently of keyword matching."""
    if matches_curated_list(query):
        return True, None
    if has_context:
        return True, None
    return False, DECLINE_MESSAGE
