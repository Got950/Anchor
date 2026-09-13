import type { AssistantMessage, Message } from "../app/types";
import { estimateCostUsd, MAX_RRF } from "../app/types";
import SourceSnippets from "./SourceSnippets";

function Why({ reasoning }: { reasoning?: string }) {
  if (!reasoning) return null;
  return (
    <details className="disclosure">
      <summary>why this path</summary>
      <div className="reasoning">{reasoning}</div>
    </details>
  );
}

/** Latency/cost line for answer + tool_call only (abstain/clarify omit it by design). */
function UsageLine({ msg }: { msg: AssistantMessage }) {
  if (msg.type !== "answer" && msg.type !== "tool_call") return null;
  const { usage, latencyMs } = msg;
  if (!usage || usage.total_tokens <= 0) return null;

  const secs = latencyMs !== undefined ? `~${(latencyMs / 1000).toFixed(1)}s` : null;
  const tokens = `${usage.total_tokens.toLocaleString("en-US")} tokens`;
  const cost = `$${estimateCostUsd(usage).toFixed(4)}`;
  const parts = [secs, tokens, cost].filter(Boolean);

  return (
    <div className="usage-line" title="Client round-trip · summed prompt+completion tokens · gpt-4.1-mini estimate">
      {parts.join(" · ")}
    </div>
  );
}

export default function ChatMessage({ msg }: { msg: Message }) {
  if (msg.role === "user") {
    return (
      <div className="turn">
        <div className="turn-label">you</div>
        <div className="turn-body">{msg.text}</div>
      </div>
    );
  }

  if (msg.type === "abstain") {
    return (
      <div className="turn turn--abstain">
        <div className="turn-label">not covered</div>
        <div className="turn-body">Not covered in the documentation.</div>
        <Why reasoning={msg.reasoning} />
      </div>
    );
  }

  if (msg.type === "clarify") {
    return (
      <div className="turn turn--clarify">
        <div className="turn-label">needs detail</div>
        <div className="turn-body">{msg.clarifying_question}</div>
        <Why reasoning={msg.reasoning} />
      </div>
    );
  }

  if (msg.type === "tool_call") {
    return (
      <div className="turn turn--tool_call">
        <div className="turn-label">
          tool call <span className="tool-name mono">{msg.tool}</span>
        </div>
        <div className="io-label">arguments</div>
        <pre className="io mono">{JSON.stringify(msg.tool_args, null, 2)}</pre>
        <div className="io-label">result</div>
        <pre className="io mono">{JSON.stringify(msg.tool_result, null, 2)}</pre>
        <UsageLine msg={msg} />
        <Why reasoning={msg.reasoning} />
      </div>
    );
  }

  const confidence =
    msg.retrieval_confidence !== undefined
      ? Math.min(100, Math.round((msg.retrieval_confidence / MAX_RRF) * 100))
      : undefined;

  return (
    <div className="turn turn--answer">
      <div className="turn-label">answer</div>
      {(confidence !== undefined || msg.verified) && (
        <div className="meta-row">
          {confidence !== undefined && (
            <span
              className="meta"
              title={`Fused RRF score ${msg.retrieval_confidence} of a ${MAX_RRF.toFixed(4)} maximum`}
            >
              confidence {confidence}%
            </span>
          )}
          {msg.verified && <span className="meta">groundedness verified</span>}
        </div>
      )}
      <div className="turn-body">{msg.answer}</div>
      <SourceSnippets sources={msg.sources ?? []} />
      <UsageLine msg={msg} />
      <Why reasoning={msg.reasoning} />
    </div>
  );
}
