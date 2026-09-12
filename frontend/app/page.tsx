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

  async function send(text: string) {
    if (!text.trim() || loading) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`${API}${agentMode ? "/agent" : "/ask"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(agentMode ? { message: text } : { question: text }),
      });
      if (!res.ok) throw new Error(`backend returned ${res.status}`);
      const data = await res.json();
      const reply: AssistantMessage = agentMode
        ? { role: "assistant", ...data }
        : { role: "assistant", type: data.abstained ? "abstain" : "answer", ...data };
      setMessages((m) => [...m, reply]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ maxWidth: 860, margin: "0 auto", padding: "32px 20px 80px" }}>
      <h1 style={{ fontSize: 22, marginBottom: 4 }}>Craftify Support Assistant</h1>
      <p style={{ color: "#64748b", fontSize: 13, marginTop: 0 }}>
        Retrieval over 13 docs + 7 support tickets, with a router that can also file tickets and flag generations.
      </p>

      <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, color: "#94a3b8", margin: "12px 0 18px" }}>
        <input type="checkbox" checked={agentMode} onChange={(e) => setAgentMode(e.target.checked)} />
        agent mode (<code>/agent</code> — routing + tools). Uncheck for plain RAG (<code>/ask</code>).
      </label>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 18 }}>
        {EXAMPLES.map((q) => (
          <button
            key={q}
            onClick={() => send(q)}
            style={{
              fontSize: 11,
              color: "#93c5fd",
              background: "#131a26",
              border: "1px solid #253046",
              borderRadius: 999,
              padding: "4px 10px",
              cursor: "pointer",
            }}
          >
            {q}
          </button>
        ))}
      </div>

      <div style={{ display: "grid", gap: 14 }}>
        {messages.map((m, i) => (
          <ChatMessage key={i} msg={m} />
        ))}
        {loading && <div style={{ color: "#64748b", fontSize: 13 }}>thinking…</div>}
        {error && <div style={{ color: "#f87171", fontSize: 13 }}>Backend error: {error}</div>}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        style={{ display: "flex", gap: 8, marginTop: 24 }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about exports, limits, tickets… or ask to file a ticket"
          style={{
            flex: 1,
            padding: "10px 12px",
            borderRadius: 8,
            border: "1px solid #253046",
            background: "#0f1420",
            color: "#e2e8f0",
          }}
        />
        <button
          type="submit"
          disabled={loading}
          style={{
            padding: "10px 18px",
            borderRadius: 8,
            border: "none",
            background: loading ? "#334155" : "#1d4ed8",
            color: "#fff",
            cursor: loading ? "default" : "pointer",
          }}
        >
          Send
        </button>
      </form>
    </main>
  );
}
