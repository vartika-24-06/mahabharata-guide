# Requirements Document

## Introduction

Q&A mode lets a user ask a question about the Mahabharata and receive a short, cited answer drawn only from the Ganguli translation. Each question is treated as factual, philosophical or ambiguous, and the answer takes a different shape for each. This document covers entering Q&A mode, answering, citing sources, "tell me more", in-session follow-ups, and the cases where the app cannot or will not answer. It does not cover story mode, the entry screen or key handling (see the entry-screen spec), or the general refusal and tone rules (see the source-and-guardrails spec).

## Glossary

- **App**: The Mahabharata guide web application.
- **Q&A Mode**: The mode entered when the user picks "Ask a Question".
- **Source Text**: The Kisari Mohan Ganguli English translation of the Mahabharata.
- **Question**: The text the user submits in Q&A Mode.
- **Factual Question**: A question about what happened, who, when or where in the epic.
- **Philosophical Question**: A question about meaning, duty, consequence or dharma as the epic treats them.
- **Ambiguous Question**: A question that is both factual and philosophical, so neither answer alone would serve the user.
- **Short Answer**: The default answer of about 3 to 5 sentences.
- **Citation**: A reference showing the parva, the section and a short excerpt from the Source Text that supports an answer.
- **Tell Me More**: The control that expands an answer into fuller content from the Source Text.
- **Session**: One browser tab's lifetime, ending when the tab is closed.
- **Session Context**: The recent Questions and answers of the current Session.
- **Verdict**: A statement in the App's own voice that a person or action was right or wrong, a hero or a villain.

## Requirements

### Requirement 1: Entering Q&A Mode

**User Story:** As a user, I want my question answered as soon as I get here, so that I do not have to ask twice.

#### Acceptance Criteria

1. WHEN the entry screen hands a Question to Q&A Mode, THE App SHALL begin answering it without asking the user to resubmit.
2. WHEN Q&A Mode opens with no Question, THE App SHALL display a Question input.
3. THE App SHALL provide a control, visible throughout Q&A Mode, to switch to story mode.

### Requirement 2: Question Classification

**User Story:** As a user, I want the answer to suit the kind of question I asked, so that a plain fact is not buried in reflection.

#### Acceptance Criteria

1. WHEN the user submits a Question, THE App SHALL classify it as Factual, Philosophical or Ambiguous before answering.
2. WHEN the classification is not clearly Factual or clearly Philosophical, THE App SHALL treat the Question as Ambiguous.
3. THE App SHALL NOT ask the user to choose the classification.

### Requirement 3: Factual Answers

**User Story:** As a user asking about events and people, I want a direct answer from the text, so that I get the facts.

#### Acceptance Criteria

1. WHEN a Question is classified Factual, THE App SHALL present a Short Answer drawn from the Source Text.
2. THE App SHALL present at least one Citation with every Short Answer.
3. THE App SHALL present a Tell Me More control with every Short Answer.

### Requirement 4: Philosophical Answers

**User Story:** As a user asking about meaning and duty, I want the epic's own reasoning, so that I understand how it treated the question.

#### Acceptance Criteria

1. WHEN a Question is classified Philosophical, THE App SHALL present a Short Answer drawn from the Source Text.
2. THE App SHALL present at least one Citation with every Short Answer.
3. THE App SHALL present a Tell Me More control with every Short Answer.
4. WHEN a Question is Philosophical but does not use epic names, places or themes, THE App SHALL treat it as outside the App's scope (Requirement 9).

### Requirement 5: Ambiguous Answers

**User Story:** As a user asking a question with both a factual and a philosophical side, I want to see both, so that I can choose where to go deeper.

#### Acceptance Criteria

1. WHEN a Question is classified Ambiguous, THE App SHALL present two opening sentences, one giving the factual reading and one giving the philosophical reading.
2. THE App SHALL present a Citation with each of the two sentences.
3. THE App SHALL present a Tell Me More control with the two sentences.

### Requirement 6: Citations

**User Story:** As a user, I want to check where an answer comes from, so that I can trust it.

#### Acceptance Criteria

1. THE App SHALL present each Citation as a parva name, a section number and a short excerpt from the Source Text.
2. THE App SHALL base each Citation on passages from the Source Text that were retrieved for the current answer.
3. THE App SHALL NOT present a Citation that does not appear in the Source Text.

### Requirement 7: Tell Me More

**User Story:** As a user, I want to go deeper on an answer, so that I can read more of what the text says.

#### Acceptance Criteria

1. WHEN the user activates Tell Me More on a Short Answer, THE App SHALL present fuller content drawn from the Source Text on the same Question.
2. WHEN the user activates Tell Me More on an Ambiguous answer, THE App SHALL present the full relevant content covering both readings.
3. THE App SHALL present a Citation with all expanded content.
4. WHILE expanded content is being prepared, THE App SHALL display a loading indicator.

### Requirement 8: Follow-Up Questions

**User Story:** As a user, I want to ask a follow-up without repeating myself, so that the conversation flows.

#### Acceptance Criteria

1. WHEN the user submits a follow-up Question in the same Session, THE App SHALL interpret it using the Session Context.
2. THE App SHALL clear the Session Context when the tab is closed.
3. THE App SHALL NOT keep the Session Context across Sessions.
4. WHEN the user switches to story mode and returns to Q&A Mode within the same Session, THE App SHALL keep the Session Context.

### Requirement 9: Questions the Text Cannot Answer

**User Story:** As a user, I want to be told plainly when the text has nothing on my question, so that I am not given an invented answer.

#### Acceptance Criteria

1. WHEN the Source Text has no good answer to a Question, THE App SHALL say that the text does not cover it.
2. WHEN the App declines a Question for lack of an answer, THE App SHALL suggest two or three related topics the Source Text does cover.
3. THE App SHALL NOT present an answer that is not supported by the Source Text.
4. WHEN a Question is not about the Mahabharata, THE App SHALL decline in one or two sentences and invite a question about the epic.
5. WHEN a Question asks about the modern world using no epic names, places or themes, THE App SHALL treat it as outside the App's scope for this version.

### Requirement 10: Tone

**User Story:** As a user who wants a mature take, I want the epic reported, not moralised over, so that I can draw my own conclusions.

#### Acceptance Criteria

1. THE App SHALL NOT state a Verdict in its own voice in any answer.
2. WHEN the Source Text records a character or the narrator giving a judgement, THE App MAY report it, attributed to the speaker and cited.
3. WHEN a Question asks the App directly for a Verdict, THE App SHALL answer by presenting what the Source Text records, without taking a side.
4. THE App SHALL NOT tell the user how they should act.

### Requirement 11: Loading and Failure States

**User Story:** As a user, I want to know the App is working and to recover when it is not, so that I am not left waiting or guessing.

#### Acceptance Criteria

1. WHILE an answer is being prepared, THE App SHALL display a loading indicator.
2. THE loading indicator SHALL end whether the answer succeeds or fails.
3. WHEN a provider returns an auth error while answering, THE App SHALL follow the entry-screen handling for auth errors on a real request (invalidate the key, reopen the key window, keep the Question).
4. WHEN a provider returns a rate-limit error while answering, THE App SHALL follow the entry-screen handling for rate-limit errors on a real request (inline message, Retry with the same key, and Add / change key).
5. WHEN answering fails for any other reason, THE App SHALL display an inline error and offer Retry, keeping the Question.

### Requirement 12: Switching Modes

**User Story:** As a user, I want to move between asking and hearing stories, so that I can follow my curiosity.

#### Acceptance Criteria

1. WHEN the user activates the switch to story mode, THE App SHALL open story mode.
2. WHEN the user activates the switch to story mode, THE App SHALL keep the Session Context and the Validated Key.

## Assumptions and open items for design

- The tone rule follows Reading A: the App's own voice never issues a Verdict, but it may report what characters or the narrator say, attributed and cited. Confirm this is what you mean.
- The number of recent exchanges kept in the Session Context is a design decision.
- The method and accuracy target for classifying Questions is a design decision, backed by your labeled eval set of sample queries.
- The exact wording of declines and the number of suggested topics are content decisions to settle in design.
- How "not a good answer" is judged (retrieval quality) is a design decision.