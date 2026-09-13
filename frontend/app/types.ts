export type Source = {
  doc_id: string;
  title: string;
  snippet: string;
  via_reference: boolean;
};

/** Summed OpenAI usage from the backend response.usage field. */
export type TokenUsage = {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  calls: number;
};

// gpt-4.1-mini list prices (USD / 1M tokens) — same as backend/eval/stress_pass.py
export const PRICE_IN_PER_1M = 0.4;
export const PRICE_OUT_PER_1M = 1.6;

export function estimateCostUsd(usage: TokenUsage): number {
  return (
    (usage.prompt_tokens * PRICE_IN_PER_1M + usage.completion_tokens * PRICE_OUT_PER_1M) /
    1_000_000
  );
}

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
  usage?: TokenUsage;
  /** Thread back as `previous_response_id`; "" means the conversation is over. */
  response_id?: string;
  /** Client-measured round-trip ms (send → response). */
  latencyMs?: number;
};

export type UserMessage = { role: "user"; text: string };
export type Message = UserMessage | AssistantMessage;

// Two retrievers at RRF k=60 top out at 2/60; the badge shows share of that maximum.
export const MAX_RRF = 2 / 60;
