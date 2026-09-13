import type { Source } from "../app/types";

export default function SourceSnippets({ sources }: { sources: Source[] }) {
  if (!sources?.length) return null;
  return (
    <details className="disclosure">
      <summary>sources ({sources.length})</summary>
      <div className="sources">
        {sources.map((s) => (
          <div key={s.doc_id}>
            <div className="source-head">
              <span className="source-id mono">{s.doc_id}</span>
              <span className="source-title">{s.title}</span>
              {s.via_reference && (
                <span
                  className="source-ref"
                  title="Pulled in by single-hop reference expansion, not ranked directly"
                >
                  referenced
                </span>
              )}
            </div>
            <div className="source-snippet">{s.snippet}</div>
          </div>
        ))}
      </div>
    </details>
  );
}
