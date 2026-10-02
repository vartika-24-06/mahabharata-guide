import { useState } from "react";
import { HowItWorksModal } from "./components/HowItWorksModal";
import { KeyModal } from "./components/KeyModal";
import { KeyStatusElement } from "./components/KeyStatusElement";
import { QnAScreen } from "./screens/QnAScreen";
import type { PendingInput, RunRequest } from "./state/ValidationStateContext";
import { ValidationStateProvider } from "./state/ValidationStateContext";
import { SessionContextProvider } from "./state/SessionContextProvider";
import { useSessionToken } from "./state/useSessionToken";
import "./App.css";

export default function App() {
  const [runRequest, setRunRequest] = useState<RunRequest | null>(null);

  // The handoff: once a Validated Key is available for a pending
  // question (immediately, if one already exists, or right after the
  // Key Modal succeeds), tell the Q&A screen to actually run it.
  function handleReady(input: PendingInput) {
    setRunRequest({ nonce: Date.now(), input });
  }

  return (
    <ValidationStateProvider onReady={handleReady}>
      <SessionContextProvider>
        <AppShell runRequest={runRequest} />
      </SessionContextProvider>
    </ValidationStateProvider>
  );
}

function AppShell({ runRequest }: { runRequest: RunRequest | null }) {
  const { serverWakeState } = useSessionToken();
  const [howItWorksOpen, setHowItWorksOpen] = useState(false);

  return (
    <div className="app">
      <header className="site-header">
        <div className="site-title">
          <span className="site-title-devanagari" lang="hi" aria-hidden="true">
            महाभारत
          </span>
          <h1>The Mahabharata Guide</h1>
        </div>
        <nav className="header-links">
          <button type="button" className="link-button" onClick={() => setHowItWorksOpen(true)}>
            How this works
          </button>
          <a href="https://github.com/vartika-24-06/mahabharata-guide" target="_blank" rel="noreferrer">
            View the code
          </a>
        </nav>
      </header>

      <p className="about-brief">
        Ask a question about the Mahabharata and get an answer grounded in the real text -
        Kisari Mohan Ganguli's English prose translation (
        <a href="https://archive.sacred-texts.com/hin/maha/index.htm" target="_blank" rel="noreferrer">
          read the original
        </a>
        ) - with citations back to the passages it's drawn from.
      </p>

      <KeyStatusElement serverWakeState={serverWakeState} />

      {howItWorksOpen && <HowItWorksModal onClose={() => setHowItWorksOpen(false)} />}

      <KeyModal />

      <QnAScreen runRequest={runRequest} />
    </div>
  );
}
