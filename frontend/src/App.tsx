import { useState } from "react";
import { KeyModal } from "./components/KeyModal";
import { KeyStatusElement } from "./components/KeyStatusElement";
import { QnAScreen } from "./screens/QnAScreen";
import { StoryScreen } from "./screens/StoryScreen";
import type { PendingInput, RunRequest } from "./state/ValidationStateContext";
import { ValidationStateProvider } from "./state/ValidationStateContext";
import { SessionContextProvider } from "./state/SessionContextProvider";
import { useSessionToken } from "./state/useSessionToken";
import "./App.css";

type Tab = "qna" | "story";

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>("qna");
  const [runRequest, setRunRequest] = useState<RunRequest | null>(null);

  // The handoff: once a Validated Key is available for a pending input
  // (immediately, if one already exists, or right after the Key Modal
  // succeeds), switch to the matching tab and tell that tab's screen to
  // run the request. Both screens stay mounted the whole time, so this
  // never clears whatever the other tab was already showing.
  function handleReady(input: PendingInput) {
    setActiveTab(input.mode);
    setRunRequest({ mode: input.mode, nonce: Date.now(), input });
  }

  return (
    <ValidationStateProvider onReady={handleReady}>
      <SessionContextProvider>
        <AppShell activeTab={activeTab} setActiveTab={setActiveTab} runRequest={runRequest} />
      </SessionContextProvider>
    </ValidationStateProvider>
  );
}

function AppShell({
  activeTab,
  setActiveTab,
  runRequest,
}: {
  activeTab: Tab;
  setActiveTab: (t: Tab) => void;
  runRequest: RunRequest | null;
}) {
  const { serverWakeState } = useSessionToken();

  return (
    <div className="app">
      <header className="site-header">
        <h1>The Mahabharata Guide</h1>
        <KeyStatusElement serverWakeState={serverWakeState} />
      </header>

      <div className="tabs" role="tablist" aria-label="Choose how to explore the epic">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "qna"}
          className={activeTab === "qna" ? "tab tab-active" : "tab"}
          onClick={() => setActiveTab("qna")}
        >
          Ask a Question
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "story"}
          className={activeTab === "story" ? "tab tab-active" : "tab"}
          onClick={() => setActiveTab("story")}
        >
          Hear a Story
        </button>
      </div>

      <KeyModal />

      <div hidden={activeTab !== "qna"}>
        <QnAScreen runRequest={runRequest?.mode === "qna" ? runRequest : null} />
      </div>
      <div hidden={activeTab !== "story"}>
        <StoryScreen runRequest={runRequest?.mode === "story" ? runRequest : null} />
      </div>
    </div>
  );
}
