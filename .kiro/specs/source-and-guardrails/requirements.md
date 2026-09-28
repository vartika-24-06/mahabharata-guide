# Requirements Document

## Introduction

This spec sets the rules that apply to every answer and every story: where the content comes from, how it is written, what the App will not do, and how it protects itself from misuse. The Q&A mode and story mode specs describe what each mode does. This spec describes the boundaries around both. It does not cover the entry screen or key handling (see the entry-screen spec).

## Glossary

- **App**: The Mahabharata guide web application.
- **Source Text**: The Kisari Mohan Ganguli English translation of the Mahabharata.
- **Parva**: One of the 18 books of the Mahabharata.
- **Section**: A numbered division within a Parva in the Source Text.
- **Retelling**: Text the App writes in plain modern English that conveys what the Source Text says.
- **Excerpt**: A short quotation taken word for word from the Source Text.
- **Citation**: A reference showing a Parva, a Section and an Excerpt.
- **Request**: A Question in Q&A Mode or a Story Request in Story Mode.
- **Session**: One browser tab's lifetime, ending when the tab is closed.
- **Session Context**: The recent Requests and responses of the current Session.
- **Epic Vocabulary**: The names, places and themes of the Mahabharata.
- **Decline**: A one-line, polite refusal that invites the user to ask about the epic.
- **Visitor**: A person using the App, identified only for the purpose of limiting request rates.

## Requirements

### Requirement 1: Source and Attribution

**User Story:** As a user, I want to know where the content comes from, so that I can judge and check it.

#### Acceptance Criteria

1. THE App SHALL base every answer and every story only on the Source Text.
2. THE App SHALL make a notice available from every screen that states the Source Text and its translator, and that answers are written by an AI from the Source Text and can contain mistakes.
3. THE notice SHALL tell the user where the Source Text can be read in full.

### Requirement 2: Coverage and Citable Structure

**User Story:** As a user, I want the whole epic available and every reference checkable, so that no part is missing and nothing is vague.

#### Acceptance Criteria

1. THE App SHALL draw on all 18 Parvas of the Source Text.
2. THE App SHALL keep the Parva and Section of every passage it uses.
3. THE App SHALL present every Citation with a Parva and Section that exist in the Source Text.

### Requirement 3: Plain Modern English

**User Story:** As a user who finds older English hard to read, I want answers and stories in plain modern English, so that I can follow them easily.

#### Acceptance Criteria

1. THE App SHALL write every answer and every story as a Retelling in plain modern English.
2. THE App SHALL take every Excerpt word for word from the Source Text.
3. THE Retelling SHALL preserve the meaning of the passages it draws on.
4. THE App SHALL NOT state anything about the epic as fact that is not supported by the passages it drew on.

### Requirement 4: Name Variants

**User Story:** As a user who spells names differently, I want to be understood, so that a spelling difference does not block my request.

#### Acceptance Criteria

1. WHEN a Request contains a common alternative spelling of a character or place name, THE App SHALL treat it as that character or place.
2. THE App SHALL use one consistent spelling for each name in its own text.

### Requirement 5: Scope

**User Story:** As a user, I want a focused guide, so that it does one thing well.

#### Acceptance Criteria

1. WHEN a Request is not about the Mahabharata, THE App SHALL Decline.
2. WHEN a Request asks about the modern world and uses no Epic Vocabulary, THE App SHALL Decline.
3. WHEN a Request is a follow-up that depends on the Session Context, THE App SHALL NOT Decline it for lacking Epic Vocabulary.
4. THE App SHALL check whether a Request is in scope before retrieving any passages from the Source Text.

### Requirement 6: Protecting the App's Rules

**User Story:** As the owner of the App, I want it to keep to its purpose, so that it cannot be turned into something else.

#### Acceptance Criteria

1. WHEN a Request asks the App to reveal its instructions, THE App SHALL Decline.
2. WHEN a Request asks the App to ignore, change or override its rules, THE App SHALL Decline.
3. WHEN a Request asks the App to speak as a character in the first person, THE App SHALL Decline.
4. THE App SHALL Decline without revealing any part of its instructions.

### Requirement 7: Wording of Declines

**User Story:** As a user who has asked for something out of scope, I want a short, polite reply, so that I know what to do next.

#### Acceptance Criteria

1. THE App SHALL word every Decline as a single polite line.
2. THE App SHALL invite the user to ask a question or hear a story from the epic in every Decline.
3. THE App SHALL NOT explain its internal rules in a Decline.

### Requirement 8: Difficult Scenes

**User Story:** As a user who wants a mature take, I want the hard scenes told as the epic tells them, so that nothing is hidden.

#### Acceptance Criteria

1. THE App SHALL tell difficult scenes, including violence, humiliation and sexual violence, plainly, as the Source Text records them.
2. THE App SHALL NOT omit or soften a difficult scene the user asked about.
3. THE App SHALL NOT add graphic or sexual detail beyond what the Source Text records.
4. THE App SHALL NOT add warnings or moral commentary to difficult scenes.

### Requirement 9: Request Rate Limiting

**User Story:** As the owner of the App, I want to stop one Visitor from overloading it, so that it stays available for everyone.

#### Acceptance Criteria

1. THE App SHALL limit how many Requests a single Visitor can make in a period of time.
2. WHEN a Visitor reaches the limit, THE App SHALL tell them in one polite line how long to wait.
3. THE limit SHALL apply whether or not the Visitor has a Validated Key.
4. WHEN a Visitor has reached the limit, THE App SHALL NOT retrieve passages or generate a response for that Visitor's Requests.

### Requirement 10: Privacy of Requests

**User Story:** As a user, I want what I ask to stay private, so that I can ask freely.

#### Acceptance Criteria

1. THE App SHALL NOT keep the text of a Request or the Session Context on the server after the Request has been answered.
2. THE App SHALL NOT write the text of a Request to server logs.
3. THE App SHALL NOT keep the Session Context across Sessions.

## Assumptions and open items for design

- "Plainly" in Requirement 8 is read as told at the level of detail and restraint of the Source Text: nothing hidden or softened, nothing made more explicit. This keeps to the product.md line of mature themes, not explicit.
- Requirement 10 (request privacy) is a product assumption that fits the "never stored" stance of the key handling. Remove it if you want to keep request text for improving the App, and if so it needs a notice to users.
- How the App judges "Epic Vocabulary" is a design decision. Queries like "was the war necessary?" have no names in them, so the eval set of sample queries must include cases like this to test the rule.
- The request limit (how many, over what period) is a design decision.
- The Retelling must not drift from the Source Text. How that is checked (for example spot-checking answers against their cited Sections) is a design and testing decision.
- Whether all 18 Parvas of the chosen copy of the Source Text are complete and clean enough to divide by Section must be checked before design starts.

## Example Declines (content, for design to refine)

- Off-topic: "I can only help with the Mahabharata. Ask me a question or hear a story from the epic."
- Asking for instructions or rule changes: "I can't help with that, but I'd be glad to answer a question or tell a story from the Mahabharata."
- Rate limit: "You're asking quickly. Please wait about a minute, then ask again."