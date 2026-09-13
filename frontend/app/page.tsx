"use client";

import { useState } from "react";
import ChatMessage from "../components/ChatMessage";
import type { AssistantMessage, Message } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

const EXAMPLES = [
  "Which export formats work with Java Edition?",
  "Which tickets resulted in a refund?",
  "What does the ticket that cites Known Issue #2 say about the resolution?",
  "Create a ticket",
  "Flag this generation for review because the castle has floating blocks",
];

export default function Page() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [agentMode, setAgentMode] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Responses API conversation the next /agent message resumes, so a clarifying question
  // and the answer to it are one conversation. The backend decides when it ends by sending
  // back an empty response_id; switching endpoint mode drops it here.
  const [prevResponseId, setPrevResponseId] = useState<string | null>(null);

  const empty = messages.length === 0;

  function switchMode(toAgent: boolean) {
    setAgentMode(toAgent);
    setPrevResponseId(null);
  }

  async function send(text: string) {
    if (!text.trim() || loading) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setError(null);
    setLoading(true);
    const t0 = performance.now();
    try {
      const res = await fetch(`${API}${agentMode ? "/agent" : "/ask"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          agentMode ? { message: text, previous_response_id: prevResponseId } : { question: text },
        ),
      });
      if (!res.ok) throw new Error(`backend returned ${res.status}`);
      const data = await res.json();
      if (agentMode) setPrevResponseId(data.response_id || null);
      const latencyMs = Math.round(performance.now() - t0);
      const reply: AssistantMessage = agentMode
        ? { role: "assistant", ...data, latencyMs }
        : {
            role: "assistant",
            type: data.abstained ? "abstain" : "answer",
            ...data,
            latencyMs,
          };
      setMessages((m) => [...m, reply]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className={empty ? "shell shell--empty" : "shell"}>
      <header className="masthead">
        <div className="brand-mark" aria-hidden="true" />
        <h1>Craftify Support Assistant</h1>
        <p>Answers from the docs and tickets — and can file tickets or flag generations.</p>

        <div className="segmented" role="group" aria-label="Endpoint mode">
          <input
            type="radio"
            name="mode"
            id="mode-agent"
            checked={agentMode}
            onChange={() => switchMode(true)}
          />
          <label htmlFor="mode-agent">/agent</label>
          <input
            type="radio"
            name="mode"
            id="mode-ask"
            checked={!agentMode}
            onChange={() => switchMode(false)}
          />
          <label htmlFor="mode-ask">/ask</label>
        </div>
      </header>

      <div className="stream">
        {messages.map((m, i) => (
          <ChatMessage key={i} msg={m} />
        ))}
        {loading && <div className="status">thinking…</div>}
        {error && <div className="status status--error">Backend error: {error}</div>}
      </div>

      <div className="composer">
        <div className="chips">
          {EXAMPLES.map((q) => (
            <button key={q} type="button" className="chip" onClick={() => send(q)}>
              {q}
            </button>
          ))}
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about exports, limits, tickets… or ask to file a ticket"
            aria-label="Message"
          />
          <button type="submit" className="send" disabled={loading}>
            Send
          </button>
        </form>
      </div>
    </main>
  );
}
