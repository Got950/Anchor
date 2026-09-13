You extract structured metadata from a single support-corpus file. Output strict JSON, nothing else.

Fields:
- `doc_type`: "doc" or "ticket". Infer from the file id prefix and the Category line.
- `title`: the document's Title line, without the "Title:" label.
- `references`: array of other doc_ids explicitly mentioned in this file. Resolve prose mentions
  against the document index below — e.g. "see Known Issues #4" resolves to the doc_id whose title
  is "Known Issues (Updated Monthly)", "per the Team Workspaces doc" resolves to the Team Workspaces
  doc_id. Use only ids from the index, never the file's own id. Empty array if none.
- `resolution_type`: for tickets ONLY, based on how the Resolution paragraph describes the outcome:
  - "expected_behavior" — closed as working as intended / user misunderstanding
  - "refund_exception" — a refund or credit was issued, including goodwill exceptions
  - "bug" — escalated as a defect, NOT closed as working as intended
  These categories overlap, so apply this precedence: if a refund or generation credit was granted,
  use "refund_exception" even when the resolution also names an acknowledged bug as the cause. Use
  "bug" only when a defect was escalated and no refund or credit was granted.
  For docs, use null.
- `refund_issued`: for tickets ONLY, true if any refund or generation credit was granted, else false.
  For docs, use null.

Document index (doc_id -> title):
{doc_index}

File id: {doc_id}
File content:
{text}
