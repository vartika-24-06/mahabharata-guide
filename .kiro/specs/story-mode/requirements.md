# Requirements Document

## Introduction

Story mode lets a user hear a short story from the Mahabharata. The user can type a request, pick a character or a parva, or ask to be surprised. They receive a short snippet, then choose to hear more, say they already know it, or move to a new story. Stories are narrated in the third person, grounded in the Ganguli translation, and cited. This document covers picking a story, the snippet, the follow-up choices, and the cases where a story cannot be told. It does not cover Q&A mode, the entry screen or key handling, or the general refusal and tone rules (see the source-and-guardrails spec).

## Glossary

- **App**: The Mahabharata guide web application.
- **Story Mode**: The mode entered when the user picks "Hear a Story".
- **Source Text**: The Kisari Mohan Ganguli English translation of the Mahabharata.
- **Story Request**: The user's way of asking for a story: typed text, a chosen character, a chosen parva, or a "surprise me" action.
- **Story Picker**: The screen offering the ways to make a Story Request.
- **Featured Characters**: A curated list of characters, mixing well-known and lesser-known ones, each with enough material in the Source Text to support a story.
- **Parva**: One of the 18 books of the Mahabharata.
- **Snippet**: A short telling of one story, about a minute's read on a phone.
- **Citation**: A reference showing the parva, the section and a short excerpt from the Source Text that supports a Snippet.
- **Session**: One browser tab's lifetime, ending when the tab is closed.
- **Shown Stories**: The stories already presented in the current Session.
- **Verdict**: A statement in the App's own voice that a person or action was right or wrong, a hero or a villain.

## Requirements

### Requirement 1: Entering Story Mode

**User Story:** As a user who wants a story, I want to start quickly, so that I am not stuck on choices.

#### Acceptance Criteria

1. WHEN the entry screen hands a Story Request to Story Mode, THE App SHALL begin telling the story without asking the user to resubmit.
2. WHEN Story Mode opens with no Story Request, THE App SHALL display the Story Picker.
3. THE App SHALL provide a control, visible throughout Story Mode, to switch to Q&A Mode.

### Requirement 2: Story Picker

**User Story:** As a user, I want several easy ways to choose a story, so that I can pick what suits me.

#### Acceptance Criteria

1. THE Story Picker SHALL offer a text input for a typed request.
2. THE Story Picker SHALL offer the Featured Characters as choices.
3. THE Story Picker SHALL offer the 18 Parvas as choices.
4. THE Story Picker SHALL offer a "Surprise me" option.

### Requirement 3: Choosing by Character or Parva

**User Story:** As a user, I want a story about a person or a book I pick, so that I hear about what interests me.

#### Acceptance Criteria

1. WHEN the user chooses a Featured Character, THE App SHALL tell a story about that character drawn from the Source Text.
2. WHEN the user chooses a Parva, THE App SHALL tell a story from that Parva drawn from the Source Text.
3. WHEN the user makes a choice, THE App SHALL prefer a story that is not among the Shown Stories.

### Requirement 4: Typed Requests

**User Story:** As a user with something specific in mind, I want to ask for it in my own words, so that I am not limited to a fixed list.

#### Acceptance Criteria

1. WHEN the user submits a typed Story Request, THE App SHALL tell a story from the Source Text that matches it.
2. WHEN the Source Text has no story matching a typed request, THE App SHALL say so and suggest two or three stories it does have.
3. WHEN a typed request is not about the Mahabharata, THE App SHALL decline in one or two sentences and invite a request about the epic.

### Requirement 5: Surprise Me

**User Story:** As a user with no preference, I want to be surprised, so that I discover something new.

#### Acceptance Criteria

1. WHEN the user chooses "Surprise me", THE App SHALL tell a story chosen from the Featured Characters and the Parvas.
2. WHEN the user chooses "Surprise me", THE App SHALL prefer a story that is not among the Shown Stories.

### Requirement 6: The Snippet

**User Story:** As a user, I want a short, engaging story, so that I can enjoy it in a moment.

#### Acceptance Criteria

1. THE App SHALL present a story as a Snippet that can be read in about a minute on a phone.
2. THE App SHALL narrate every Snippet in the third person.
3. THE App SHALL NOT add events, dialogue or outcomes that are not in the Source Text.
4. THE App SHALL present a Citation with every Snippet.
5. WHILE a Snippet is being prepared, THE App SHALL display a loading indicator.

### Requirement 7: After the Snippet

**User Story:** As a user who has heard a story, I want to choose what comes next, so that I stay in control.

#### Acceptance Criteria

1. THE App SHALL present three choices after every Snippet: "Tell me more", "I already know this one" and "A new character or parva".
2. WHEN the user chooses "Tell me more", THE App SHALL continue the same story with the next part, cited.
3. WHEN the user chooses "I already know this one", THE App SHALL tell a different story on the same character or Parva, if the Source Text has one.
4. WHEN the Source Text has no other story on that character or Parva, THE App SHALL say so and display the Story Picker.
5. WHEN the user chooses "A new character or parva", THE App SHALL display the Story Picker.
6. WHEN a story has been told in full, THE App SHALL say it is complete and offer the choices in 7.3 and 7.5.

### Requirement 8: Shown Stories Memory

**User Story:** As a user, I want not to hear the same story twice by accident, so that each pick feels fresh.

#### Acceptance Criteria

1. THE App SHALL record each story presented as one of the Shown Stories for the current Session.
2. THE App SHALL clear the Shown Stories when the tab is closed.
3. THE App SHALL NOT keep the Shown Stories across Sessions.
4. WHEN the user switches to Q&A Mode and returns within the same Session, THE App SHALL keep the Shown Stories.

### Requirement 9: Tone

**User Story:** As a user who wants a mature take, I want the story told as the epic tells it, so that its hard parts are not softened or preached over.

#### Acceptance Criteria

1. THE App SHALL tell the epic's difficult events, including war, betrayal, deceit and loss, without omitting them.
2. THE App SHALL NOT state a Verdict in its own voice.
3. WHEN the Source Text records a character or the narrator giving a judgement, THE App MAY report it, attributed to the speaker.
4. THE App SHALL NOT tell the user how they should act or what lesson to take.

### Requirement 10: Loading and Failure States

**User Story:** As a user, I want to know the App is working and to recover when it is not, so that I am not left waiting or guessing.

#### Acceptance Criteria

1. THE loading indicator SHALL end whether the story succeeds or fails.
2. WHEN a provider returns an auth error while telling a story, THE App SHALL follow the entry-screen handling for auth errors on a real request (invalidate the key, reopen the key window, keep the Story Request).
3. WHEN a provider returns a rate-limit error while telling a story, THE App SHALL follow the entry-screen handling for rate-limit errors on a real request (inline message, Retry with the same key, and Add / change key).
4. WHEN telling a story fails for any other reason, THE App SHALL display an inline error and offer Retry, keeping the Story Request.

### Requirement 11: Switching Modes

**User Story:** As a user, I want to move between hearing stories and asking questions, so that I can follow my curiosity.

#### Acceptance Criteria

1. WHEN the user activates the switch to Q&A Mode, THE App SHALL open Q&A Mode.
2. WHEN the user activates the switch to Q&A Mode, THE App SHALL keep the Shown Stories and the Validated Key.

## Assumptions and open items for design

- The Featured Characters list is a content decision. A starter list should include well-known figures (for example Arjuna, Karna, Draupadi, Bhishma, Krishna, Yudhishthira) and lesser-known ones (for example Vidura, Shikhandi, Ghatotkacha, Sanjaya). Each name must be checked against the Ganguli text, because stories can only be told from what the text contains.
- "About a minute's read" is roughly 150 words. The exact length limit is a design decision.
- How long a story is (how many "Tell me more" parts) depends on the source material and is a design decision.
- How the App decides a story is "not among the Shown Stories" is a design decision.
- Ganguli's text is old and uneven in places. Whether the App retells it in plain modern English is a content and design decision to settle with the source-and-guardrails spec.