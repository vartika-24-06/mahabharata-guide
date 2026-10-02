import { useState } from "react";
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

  return (
    <div className="app">
      <header className="site-header">
        <div className="site-title">
          <span className="site-title-devanagari" lang="hi" aria-hidden="true">
            महाभारत
          </span>
          <h1>The Mahabharata Guide</h1>
        </div>
        <KeyStatusElement serverWakeState={serverWakeState} />
      </header>

      <KeyModal />

      <QnAScreen runRequest={runRequest} />
    </div>
  );
}
