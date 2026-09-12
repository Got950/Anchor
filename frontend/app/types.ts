export type Source = {
  doc_id: string;
  title: string;
  snippet: string;
  via_reference: boolean;
};

export type AssistantMessage = {
  role: "assistant";
  type: "answer" | "abstain" | "tool_call" | "clarify";
  reasoning?: string;
  answer?: string;
  sources?: Source[];
  tool?: string;
  tool_args?: Record<string, unknown>;
  tool_result?: Record<string, unknown>;
  clarifying_question?: string;
  retrieval_confidence?: number;
  verified?: boolean;
};

export type UserMessage = { role: "user"; text: string };
export type Message = UserMessage | AssistantMessage;

// Two retrievers at RRF k=60 top out at 2/60; the badge shows share of that maximum.
export const MAX_RRF = 2 / 60;
