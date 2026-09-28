# tech.md

## Stack
- Frontend: React + TypeScript on Vite, deployed to Vercel.
- Backend: Python + FastAPI, deployed to Render (free tier, single uvicorn
  worker, in-memory state).
- Providers (BYOK): OpenAI, Anthropic, Gemini. All provider calls go through
  the backend, never directly from the browser.

## Non-negotiable rules
- The user's API key is never stored server-side and never written to logs
  (including URLs, headers, error messages and analytics).
- The key lives in the browser's sessionStorage only. Nothing goes in
  localStorage or cookies.
- No retrieval or generation runs before a validated key exists.
- Answers come only from the Mahabharata source text (Ganguli translation),
  with citations. The app's own voice never issues verdicts on right and
  wrong.
- Secrets (SESSION_TOKEN_SECRET etc.) live in host environment variables,
  never in the repo.

## Conventions
- Specs in .kiro/specs/. Where a spec has a "Revisions" section, it
  overrides earlier text.
- One task per commit, message starting with the task number.