# Requirements Document

## Introduction

The Mahabharata Entry Screen is the first screen a user encounters in the Mahabharata-based guide web app. The user selects a path ("Hear a Story" or "Ask a Question"), enters a request, and provides an AI provider API key on demand. The key is validated per session and never persisted beyond the current tab. This document covers the Entry Screen, Path Selection, Key Modal, Key Status Element, and all API key handling. It does not cover story mode or Q&A mode internals.

## Glossary

- **App**: The Mahabharata guide web application.
- **Entry Screen**: The first screen the user sees; contains Path Selection and request submission.
- **Path Selection**: The control that lets the user choose between "Hear a Story" and "Ask a Question".
- **Pending Input**: The user's request in any form — typed text, a chosen character or parva selection, or a "surprise me" action — preserved until a Validated Key exists and the App hands it to the selected mode.
- **Key Modal**: The dialog that collects Provider selection, API Key, and optional model name.
- **Provider**: One of the three supported AI service providers: OpenAI, Anthropic, or Gemini.
- **API Key**: A secret credential string supplied by the user to authenticate with a Provider.
- **Key Field**: The masked API Key input field inside the Key Modal, with a show/hide toggle.
- **Model Field**: An optional free-text field in the Key Modal where the user may specify a model name.
- **Default Model**: The per-Provider model the App uses when the Model Field is left blank.
- **Ping Call**: A lightweight, low-cost request sent to a Provider's endpoint to validate both the API Key and the model together.
- **Validated Key**: An API Key (with its associated Provider and model) that has passed a successful Ping Call within the current Session.
- **Session**: A single browser tab's lifetime from page load until tab close. A page refresh does not end the Session.
- **SessionStorage**: The browser's `sessionStorage` API, scoped to a single tab and persisted across page refreshes within that tab; cleared when the tab is closed.
- **Key Status Element**: The element reachable from every screen that displays the current key validation state and provides the "Add / change key" control.
- **Loading State**: The period during which a Ping Call is in flight; the Key Modal shows a loading indicator and the "Save key" button is disabled.
- **Cooldown Period**: A time-limited lockout entered after a threshold number of consecutive failed validation attempts in a Session, during which the "Save key" button is disabled.
- **Auth Error**: An error returned by a Provider indicating the API Key is invalid or unauthorised.
- **Rate-Limit Error**: An error returned by a Provider indicating the API Key has exceeded its request quota.
- **Unrecognised Model Error**: An error returned by a Provider indicating the supplied model name is not known.
- **Network Failure**: A failure to reach a Provider's endpoint due to a network-level error.
- **Timeout**: A Ping Call that does not receive a response within 10 seconds.

---

## Requirements

### Requirement 1: Entry Screen Path Selection

**User Story:** As a user, I want to see path options on the Entry Screen without needing an API key first, so that I can choose my experience before providing credentials.

#### Acceptance Criteria

1. THE App SHALL display Path Selection on the Entry Screen when the user first loads the App.
2. THE Path Selection SHALL offer exactly two options: "Hear a Story" and "Ask a Question".
3. THE App SHALL allow the user to select a path and enter a request without requiring a Validated Key.

---

### Requirement 2: Deferred Key Collection

**User Story:** As a user, I want to provide my API key only when I submit a request, so that I can explore the App before committing credentials.

#### Acceptance Criteria

1. WHEN the user submits a request without a Validated Key, THE App SHALL open the Key Modal.
2. WHEN the Key Modal opens, THE App SHALL preserve the Pending Input.
3. THE App SHALL NOT run any retrieval or generation before a Validated Key exists.

---

### Requirement 3: Key Modal Contents

**User Story:** As a user, I want a single place to configure my provider and key, so that I can start using the App quickly.

#### Acceptance Criteria

1. THE Key Modal SHALL contain a Provider selector that lists OpenAI, Anthropic, and Gemini.
2. THE Key Modal SHALL present the Provider selector with no default selection.
3. THE Key Modal SHALL contain a Key Field.
4. THE Key Modal SHALL contain a show/hide toggle for the Key Field.
5. THE Key Modal SHALL contain a Model Field for free-text model name entry.
6. THE Key Modal SHALL contain a "Save key" button.
7. THE Key Modal SHALL display the statement: "Your key is held in this tab only and is never stored on our servers or written to logs."

---

### Requirement 4: Provider Change Clears Key Field

**User Story:** As a user, I want the Key Field to clear when I switch providers, so that I do not accidentally submit a key intended for a different provider.

#### Acceptance Criteria

1. WHEN the user changes the selected Provider, THE Key Modal SHALL clear the Key Field.

---

### Requirement 5: Validation on Save Key

**User Story:** As a user, I want my key and model validated immediately when I save, so that I know they work before my request runs.

#### Acceptance Criteria

1. WHEN the user presses "Save key", THE App SHALL send a Ping Call to the selected Provider's endpoint to validate the API Key and the model together.
2. WHEN the Model Field is blank and the user presses "Save key", THE App SHALL use the Default Model for the selected Provider in the Ping Call.
3. WHEN the Ping Call succeeds, THE App SHALL mark the key as a Validated Key.
4. WHEN a Validated Key is established, THE App SHALL hand the Pending Input to the selected mode without requiring the user to resubmit.

---

### Requirement 6: Loading State During Ping

**User Story:** As a user, I want clear feedback while my key is being validated, so that I know the App is working and do not submit twice.

#### Acceptance Criteria

1. WHILE a Ping Call is in progress, THE Key Modal SHALL display a loading indicator.
2. WHILE a Ping Call is in progress, THE Key Modal SHALL disable the "Save key" button.
3. WHEN the Ping Call succeeds, THE Loading State SHALL terminate.
4. WHEN the Ping Call returns any error, THE Loading State SHALL terminate.
5. WHEN a Network Failure occurs during the Ping Call, THE Loading State SHALL terminate.
6. WHEN a Timeout occurs, THE Loading State SHALL terminate.

---

### Requirement 7: Default Model Behaviour

**User Story:** As a user, I want the App to work without me specifying a model name, so that I do not need to know provider-specific model identifiers.

#### Acceptance Criteria

1. WHEN the Model Field is left blank, THE App SHALL use the Default Model for the selected Provider.

---

### Requirement 8: Session Storage of Validated Key

**User Story:** As a user, I want my key available throughout my session but not accessible from other tabs or after I close the tab, so that my credentials remain scoped and temporary.

#### Acceptance Criteria

1. THE App SHALL store the Validated Key exclusively in SessionStorage.
2. THE Validated Key SHALL survive a page refresh within the same tab.
3. THE Validated Key SHALL NOT persist when the tab is closed.
4. THE Validated Key SHALL NOT be accessible from a new tab.
5. THE App SHALL NOT store the Validated Key in localStorage.
6. THE App SHALL NOT store the Validated Key in a cookie.
7. THE App SHALL NOT store the Validated Key in any server-side storage.
8. THE App SHALL NOT include the Validated Key in any server-side logs.

---

### Requirement 9: Previous Key Preservation on Failed Validation

**User Story:** As a user, I want my existing key to remain active if a new key fails validation, so that I can continue using the App while I fix the new entry.

#### Acceptance Criteria

1. IF a new Ping Call fails for any reason, THE App SHALL retain the previously established Validated Key as active.

---

### Requirement 10: Key Status Element Display

**User Story:** As a user, I want to always see my current key status at a glance, so that I know whether I am set up to make requests.

#### Acceptance Criteria

1. THE Key Status Element SHALL be reachable from every screen of the App during a Session.
2. WHEN no Validated Key exists, THE Key Status Element SHALL display "No key added yet".
3. WHEN a Validated Key exists, THE Key Status Element SHALL display the name of the active Provider.

---

### Requirement 11: Add / Change Key Control

**User Story:** As a user, I want to be able to change my provider or key at any point in my session, so that I can switch providers or fix an expired key without reloading.

#### Acceptance Criteria

1. THE Key Status Element SHALL provide an "Add / change key" control at all times during a Session.
2. WHEN the user activates the "Add / change key" control, THE App SHALL open the Key Modal.

---

### Requirement 12: Validation Attempt Throttling

**User Story:** As a user, I want the App to prevent rapid repeated validation attempts, so that my provider account is protected from accidental rate exhaustion.

#### Acceptance Criteria

1. WHEN the number of consecutive failed validation attempts in a Session reaches the throttle threshold, THE App SHALL enter a Cooldown Period.
2. WHILE a Cooldown Period is active, THE Key Modal SHALL disable the "Save key" button.
3. WHILE a Cooldown Period is active, THE Key Modal SHALL display the remaining wait time.
4. WHEN the Cooldown Period ends, THE App SHALL re-enable the "Save key" button.
5. WHILE a Cooldown Period is active, THE App SHALL allow the previously Validated Key to remain usable.

---

### Requirement 13: Missing Provider Error

**User Story:** As a user, I want an immediate error if I forget to select a provider, so that I know exactly what is missing.

#### Acceptance Criteria

1. WHEN the user presses "Save key" without selecting a Provider, THE Key Modal SHALL display an inline error indicating that a Provider must be selected.
2. WHEN no Provider is selected, THE App SHALL NOT send a Ping Call.

---

### Requirement 14: Missing Key Input Error

**User Story:** As a user, I want an immediate error if I forget to enter a key, so that I know exactly what is missing.

#### Acceptance Criteria

1. WHEN the user presses "Save key" without entering an API Key, THE Key Modal SHALL display an inline error indicating that an API Key must be entered.
2. WHEN the Key Field is empty, THE App SHALL NOT send a Ping Call.

---

### Requirement 15: Auth Error During Ping

**User Story:** As a user, I want a clear error when my key is rejected, so that I can correct it and try again.

#### Acceptance Criteria

1. WHEN the Ping Call returns an Auth Error, THE Key Modal SHALL display an inline error indicating the API Key is invalid.
2. WHEN an Auth Error is displayed, THE Key Modal SHALL allow the user to correct the Key Field and retry.

---

### Requirement 16: Unrecognised Model Error During Ping

**User Story:** As a user, I want a specific error when I enter an unknown model name, so that I can distinguish it from a key problem and fix the right field.

#### Acceptance Criteria

1. WHEN the Ping Call returns an Unrecognised Model Error, THE Key Modal SHALL display an inline error that is distinct from the Auth Error and Rate-Limit Error messages.
2. WHEN an Unrecognised Model Error is displayed, THE Key Modal SHALL allow the user to correct the Model Field and retry.

---

### Requirement 17: Rate-Limit Error During Ping

**User Story:** As a user, I want a clear error when my key hits a rate limit during validation, so that I can retry without being forced to change my key.

#### Acceptance Criteria

1. WHEN the Ping Call returns a Rate-Limit Error, THE Key Modal SHALL display an inline error indicating the rate limit has been reached.
2. WHEN a Rate-Limit Error is displayed during a Ping Call, THE Key Modal SHALL allow the user to retry with the same API Key.

---

### Requirement 18: Generic Provider Error During Ping

**User Story:** As a user, I want a clear error for any unexpected provider failure during validation, so that I am not left without feedback.

#### Acceptance Criteria

1. WHEN the Ping Call returns an error that is not an Auth Error, Unrecognised Model Error, Rate-Limit Error, Network Failure, or Timeout, THE Key Modal SHALL display a generic inline error.
2. WHEN a generic inline error is displayed, THE Key Modal SHALL provide a retry option.

---

### Requirement 19: Network Failure During Ping

**User Story:** As a user, I want a clear error when the network fails, so that I can retry once connectivity is restored.

#### Acceptance Criteria

1. WHEN a Network Failure occurs during a Ping Call, THE Key Modal SHALL display an inline error indicating a network problem.
2. WHEN a Network Failure error is displayed, THE Key Modal SHALL allow the user to retry.

---

### Requirement 20: Timeout During Ping

**User Story:** As a user, I want a clear error when validation takes too long, so that the App never leaves me with a frozen indicator.

#### Acceptance Criteria

1. WHEN a Ping Call does not respond within 10 seconds, THE App SHALL treat it as a Timeout.
2. WHEN a Timeout occurs, THE Key Modal SHALL display an inline timeout error.
3. WHEN a timeout error is displayed, THE Key Modal SHALL allow the user to retry.

---

### Requirement 21: Auth Error During a Real Request

**User Story:** As a user, I want to be prompted to re-enter my key when it becomes invalid mid-session, so that I can continue without losing my place.

#### Acceptance Criteria

1. WHEN a Provider returns an Auth Error during a real request, THE App SHALL mark the current Validated Key as invalid.
2. WHEN the current Validated Key is marked invalid, THE App SHALL open the Key Modal.
3. WHEN the Key Modal opens following an Auth Error on a real request, THE App SHALL preserve the Pending Input.

---

### Requirement 22: Rate-Limit Error During a Real Request

**User Story:** As a user, I want options when my key hits a rate limit mid-session, so that I can retry or switch to a different provider without losing my place.

#### Acceptance Criteria

1. WHEN a Provider returns a Rate-Limit Error during a real request, THE App SHALL display an inline error on the current screen.
2. WHEN a Rate-Limit Error is displayed on the current screen, THE App SHALL provide a "Retry" option that resubmits the request using the same Validated Key.
3. WHEN a Rate-Limit Error is displayed on the current screen, THE App SHALL provide an "Add / change key" option that opens the Key Modal.

---

### Requirement 23: Key Modal Dismissed Without Saving

**User Story:** As a user, I want to be able to close the Key Modal without losing my request, so that I can change my mind about providing a key without starting over.

#### Acceptance Criteria

1. WHEN the user dismisses the Key Modal without pressing "Save key", THE App SHALL preserve the Pending Input.
2. WHEN the user dismisses the Key Modal without pressing "Save key", THE App SHALL NOT run any retrieval or generation.
