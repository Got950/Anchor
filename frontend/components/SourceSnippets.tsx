import type { Source } from "../app/types";

export default function SourceSnippets({ sources }: { sources: Source[] }) {
  if (!sources?.length) return null;
  return (
    <div style={{ marginTop: 10, display: "grid", gap: 6 }}>
      {sources.map((s) => (
        <div
          key={s.doc_id}
          style={{
            fontSize: 12,
            border: "1px solid #2c3446",
            borderLeft: `3px solid ${s.via_reference ? "#a855f7" : "#3b82f6"}`,
            borderRadius: 6,
            padding: "6px 8px",
            background: "#151a24",
          }}
        >
          <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 2 }}>
            <code style={{ color: "#7dd3fc" }}>{s.doc_id}</code>
            <strong style={{ color: "#cbd5e1" }}>{s.title}</strong>
            {s.via_reference && (
              <span
                title="Pulled in by single-hop reference expansion, not ranked directly"
                style={{ color: "#e9d5ff", background: "#4c1d95", borderRadius: 4, padding: "1px 5px", fontSize: 10 }}
              >
                referenced
              </span>
            )}
          </div>
          <div style={{ color: "#94a3b8", lineHeight: 1.4 }}>{s.snippet}</div>
        </div>
      ))}
    </div>
  );
}
