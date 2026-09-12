"use client";

import { useState } from "react";
import type { Message } from "../app/types";
import { MAX_RRF } from "../app/types";
import SourceSnippets from "./SourceSnippets";

const BUBBLE: React.CSSProperties = {
  borderRadius: 10,
  padding: "10px 12px",
  maxWidth: 760,
  border: "1px solid #2c3446",
  background: "#111721",
  lineHeight: 1.5,
};

function Why({ reasoning }: { reasoning?: string }) {
  const [open, setOpen] = useState(false);
  if (!reasoning) return null;
  return (
    <div style={{ marginTop: 8, fontSize: 12 }}>
      <button
        onClick={() => setOpen(!open)}
        style={{ background: "none", border: "none", color: "#64748b", cursor: "pointer", padding: 0, fontSize: 12 }}
      >
        {open ? "▾" : "▸"} why this path
      </button>
      {open && <div style={{ color: "#94a3b8", marginTop: 4, fontStyle: "italic" }}>{reasoning}</div>}
    </div>
  );
}

export default function ChatMessage({ msg }: { msg: Message }) {
  if (msg.role === "user") {
    return (
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <div style={{ ...BUBBLE, background: "#1d4ed8", borderColor: "#1d4ed8", color: "#fff" }}>{msg.text}</div>
      </div>
    );
  }

  if (msg.type === "abstain") {
    return (
      <div>
        <div style={{ ...BUBBLE, opacity: 0.65, fontStyle: "italic", color: "#94a3b8" }}>
          Not covered in the documentation.
        </div>
        <Why reasoning={msg.reasoning} />
      </div>
    );
  }

  if (msg.type === "clarify") {
    return (
      <div>
        <div style={{ ...BUBBLE, border: "1px solid #f59e0b", background: "#221a08" }}>
          <div style={{ fontSize: 11, color: "#fbbf24", marginBottom: 4, letterSpacing: 0.5 }}>NEEDS DETAIL</div>
          {msg.clarifying_question}
        </div>
        <Why reasoning={msg.reasoning} />
      </div>
    );
  }

  if (msg.type === "tool_call") {
    return (
      <div>
        <div style={{ ...BUBBLE, border: "1px solid #22c55e", background: "#08210f" }}>
          <div style={{ fontSize: 11, color: "#4ade80", marginBottom: 6, letterSpacing: 0.5 }}>
            TOOL CALL · <code>{msg.tool}</code>
          </div>
          <div style={{ fontSize: 12, color: "#cbd5e1" }}>arguments</div>
          <pre style={{ margin: "2px 0 8px", fontSize: 12, color: "#a7f3d0", whiteSpace: "pre-wrap" }}>
            {JSON.stringify(msg.tool_args, null, 2)}
          </pre>
          <div style={{ fontSize: 12, color: "#cbd5e1" }}>result</div>
          <pre style={{ margin: "2px 0 0", fontSize: 12, color: "#a7f3d0", whiteSpace: "pre-wrap" }}>
            {JSON.stringify(msg.tool_result, null, 2)}
          </pre>
        </div>
        <Why reasoning={msg.reasoning} />
      </div>
    );
  }

  const confidence =
    msg.retrieval_confidence !== undefined
      ? Math.min(100, Math.round((msg.retrieval_confidence / MAX_RRF) * 100))
      : undefined;

  return (
    <div>
      <div style={BUBBLE}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
          {confidence !== undefined && (
            <span
              title={`Fused RRF score ${msg.retrieval_confidence} of a ${MAX_RRF.toFixed(4)} maximum`}
              style={{ fontSize: 10, background: "#1e293b", color: "#93c5fd", borderRadius: 4, padding: "1px 5px" }}
            >
              confidence {confidence}%
            </span>
          )}
          {msg.verified && (
            <span style={{ fontSize: 10, background: "#1e293b", color: "#86efac", borderRadius: 4, padding: "1px 5px" }}>
              groundedness verified
            </span>
          )}
        </div>
        <div>{msg.answer}</div>
        <SourceSnippets sources={msg.sources ?? []} />
      </div>
      <Why reasoning={msg.reasoning} />
    </div>
  );
}
