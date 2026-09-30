import { useState } from "react";
import { KeyModal } from "./components/KeyModal";
import { KeyStatusElement } from "./components/KeyStatusElement";
import { EntryScreen } from "./screens/EntryScreen";
import { QnAScreen } from "./screens/QnAScreen";
import { StoryScreen } from "./screens/StoryScreen";
import type { PendingInput } from "./state/ValidationStateContext";
import { ValidationStateProvider } from "./state/ValidationStateContext";
import { useSessionToken } from "./state/useSessionToken";
import "./App.css";

type Screen =
  | { name: "entry" }
  | { name: "qna"; input: PendingInput }
  | { name: "story"; input: PendingInput };

export default function App() {
  const [screen, setScreen] = useState<Screen>({ name: "entry" });

  // The handoff: once a Validated Key is available for a pending input
  // (immediately, if one already exists, or right after the Key Modal
  // succeeds), navigate to the matching screen. This is the real
  // replacement for the entry-screen spec's console-log ModeStub.
  function handleReady(input: PendingInput) {
    setScreen(input.mode === "story" ? { name: "story", input } : { name: "qna", input });
  }

  return (
    <ValidationStateProvider onReady={handleReady}>
      <AppShell screen={screen} setScreen={setScreen} />
    </ValidationStateProvider>
  );
}

function AppShell({ screen, setScreen }: { screen: Screen; setScreen: (s: Screen) => void }) {
  const { serverWakeState } = useSessionToken();

  return (
    <div className="app">
      <KeyStatusElement serverWakeState={serverWakeState} />
      <KeyModal />
      {screen.name === "entry" && <EntryScreen />}
      {screen.name === "qna" && (
        <QnAScreen
          initialInput={screen.input}
          onSwitchToStory={() => setScreen({ name: "story", input: { text: "", mode: "story" } })}
        />
      )}
      {screen.name === "story" && (
        <StoryScreen
          initialInput={screen.input}
          onSwitchToQnA={() => setScreen({ name: "qna", input: { text: "", mode: "qna" } })}
        />
      )}
    </div>
  );
}
