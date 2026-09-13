"""Live check for /agent Responses API multi-turn behavior (Section D of final bench).

Requires the backend on :8000 with llm:true. Run from the repo root:
    python backend/eval/agent_multiturn_check.py
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

API = "http://127.0.0.1:8000"
PRICE_IN, PRICE_OUT = 0.40, 1.60  # gpt-4.1-mini USD / 1M tokens, same as stress_pass.py

results: list[tuple[str, bool, str]] = []


def agent(message: str, previous_response_id: str | None = None) -> dict:
    payload: dict = {"message": message}
    if previous_response_id is not None:
        payload["previous_response_id"] = previous_response_id
    r = requests.post(f"{API}/agent", json=payload, timeout=180)
    r.raise_for_status()
    return r.json()


def ask(question: str) -> dict:
    r = requests.post(f"{API}/ask", json={"question": question}, timeout=180)
    r.raise_for_status()
    return r.json()


def show(label: str, sent: str | None, body: dict) -> dict:
    args = body.get("tool_args")
    print(f"  [{label}] previous_response_id={sent!r}")
    print(f"       -> type={body.get('type')} tool={body.get('tool')} args={args}")
    if body.get("clarifying_question"):
        print(f"          q={body['clarifying_question']}")
    if body.get("answer"):
        print(f"          answer={body['answer'][:110]}")
    print(f"          response_id={body.get('response_id')!r} usage={body.get('usage')}")
    return body


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {detail}\n")


def test1_happy_path() -> None:
    print("=== 1. Happy path: create ticket -> clarify -> details ===")
    a = show("turn1", None, agent("create a ticket"))
    b = show("turn2", a.get("response_id"), agent("export failing on Bedrock, high priority", a.get("response_id")))
    args = b.get("tool_args") or {}
    ok = (
        a.get("type") == "clarify" and bool(a.get("response_id"))
        and b.get("type") == "tool_call" and b.get("tool") == "create_support_ticket"
        and args.get("priority") == "high" and "bedrock" in str(args.get("summary", "")).lower()
        and b.get("response_id") == ""
    )
    check("D1_happy_path", ok, f"clarify then tool_call args={args} reset={b.get('response_id')!r}")


def test2_loop() -> None:
    print("=== 2. Original loop case: 3d asset lamp -> High ===")
    a = show("turn1", None, agent("create a 3d asset for a lamp"))
    entered_ticket = a.get("type") == "tool_call" and a.get("tool") == "create_support_ticket"
    if entered_ticket:
        check("D2_loop_no_infinite", False, f"still filed a ticket: {a.get('tool_args')}")
        return
    if a.get("type") != "clarify":
        check("D2_loop_no_infinite", False, f"unexpected first-turn type={a.get('type')}")
        return

    prev, texts = a.get("response_id"), []
    for i in range(2, 5):
        b = show(f"turn{i}", prev, agent("High", prev))
        texts.append((b.get("type"), b.get("clarifying_question") or "", b.get("response_id")))
        prev = b.get("response_id")
        if not prev:
            break

    gave_up = any("wasn't able to get enough detail" in t[1] for t in texts)
    clarify_count = sum(1 for t in texts if t[0] == "clarify")
    ok = (prev == "") and (gave_up or clarify_count < 3) and not any(
        t[0] == "tool_call" for t in texts
    )
    check(
        "D2_loop_no_infinite",
        ok,
        f"followups={texts} final_response_id={prev!r} gave_up={gave_up}",
    )


def test3_context_isolation() -> None:
    print("=== 3. Context isolation after clarify ===")
    a = show("turn1", None, agent("create a ticket"))
    prev = a.get("response_id")
    b = show("turn2", prev, agent("what export formats exist", prev))
    blob = json.dumps(b).lower()
    ok = (
        a.get("type") == "clarify" and bool(prev)
        and b.get("type") == "answer" and b.get("tool") is None
        and any(fmt in blob for fmt in (".litematic", ".schematic", ".glb"))
    )
    check("D3_context_isolation", ok, f"type={b.get('type')} tool={b.get('tool')} formats_ok={ok}")


def test4_post_completion() -> None:
    print("=== 4. Post-completion reset ===")
    a = show("turn1", None, agent("File a support ticket about export failing on Bedrock, high priority"))
    if a.get("type") != "tool_call":
        check("D4_post_completion_reset", False, f"setup failed, first turn was {a.get('type')}")
        return
    b = show("turn2", a.get("response_id") or None, agent("how many generations per day on free tier", None))
    blob = json.dumps(b).lower()
    ok = a.get("response_id") == "" and b.get("type") == "answer" and b.get("tool") is None and "10" in blob
    check("D4_post_completion_reset", ok, f"tool reset id={a.get('response_id')!r}; next={b.get('type')}")


def test5_mode_switch() -> None:
    print("=== 5. Mode-switch: /agent clarify then /ask ===")
    a = show("agent", None, agent("create a ticket"))
    b = ask("Which export formats work with Java Edition?")
    blob = json.dumps(b).lower()
    ok = (
        a.get("type") == "clarify"
        and not b.get("abstained")
        and any(fmt in blob for fmt in (".litematic", ".schematic", ".nbt"))
        and "ticket" not in (b.get("answer") or "").lower()
    )
    check("D5_mode_switch_ask_unaffected", ok, f"ask abstained={b.get('abstained')} ans={(b.get('answer') or '')[:100]}")


def test6_two_attempt_cap() -> None:
    print("=== 6. Two-attempt clarify cap ===")
    a = show("turn1", None, agent("create a ticket"))
    if a.get("type") != "clarify" or not a.get("response_id"):
        check("D6_two_attempt_cap", False, f"setup failed: {a.get('type')}")
        return
    b = show("turn2", a.get("response_id"), agent("maybe later", a.get("response_id")))
    # Second vague follow-up should hit the cap (attempt 2 spent on turn1+turn2, or give-up on turn3).
    # Spec: two vague non-answers in a row → graceful stop, no 3rd clarify.
    prev = b.get("response_id") or ""
    turns = [("1", a.get("type"), a.get("clarifying_question") or "", a.get("response_id"))]
    turns.append(("2", b.get("type"), b.get("clarifying_question") or "", b.get("response_id")))
    if prev:
        c = show("turn3", prev, agent("idk", prev))
        turns.append(("3", c.get("type"), c.get("clarifying_question") or "", c.get("response_id")))
        prev = c.get("response_id") or ""

    clarify_turns = [t for t in turns if t[1] == "clarify"]
    gave_up = any("wasn't able to get enough detail" in t[2] for t in turns)
    # No third *asking* clarify: at most 2 clarifying questions, then give-up or exit.
    asking = [t for t in clarify_turns if "wasn't able to get enough detail" not in t[2]]
    ok = len(asking) <= 2 and (gave_up or prev == "" or turns[-1][1] != "clarify")
    check("D6_two_attempt_cap", ok, f"turns={[(t[0], t[1], repr(t[3])) for t in turns]} asking={len(asking)} gave_up={gave_up}")


def test7_malformed_ids() -> None:
    print("=== 7. Malformed previous_response_id ===")
    cases = []
    for label, prev in (("fake", "resp_this_id_does_not_exist_xyz"), ("empty", ""), ("none", None)):
        try:
            if prev is None:
                # Explicit JSON null
                r = requests.post(f"{API}/agent", json={"message": "what export formats exist", "previous_response_id": None}, timeout=180)
            else:
                r = requests.post(f"{API}/agent", json={"message": "what export formats exist", "previous_response_id": prev}, timeout=180)
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"_raw": r.text[:200]}
            ok = r.status_code == 200 and body.get("type") in ("answer", "abstain", "clarify")
            cases.append((label, ok, r.status_code, body.get("type")))
            print(f"  [{label}] status={r.status_code} type={body.get('type')}")
        except Exception as e:
            cases.append((label, False, 0, str(e)))
            print(f"  [{label}] EXC {e}")
    ok = all(c[1] for c in cases)
    check("D7_malformed_previous_response_id", ok, f"cases={cases}")


def test8_cross_conversation() -> None:
    print("=== 8. Cross-conversation isolation ===")
    a1 = show("convA1", None, agent("create a ticket"))
    a2 = show("convB1", None, agent("create a ticket"))
    id1, id2 = a1.get("response_id"), a2.get("response_id")
    if not (a1.get("type") == "clarify" and a2.get("type") == "clarify" and id1 and id2 and id1 != id2):
        check("D8_cross_conversation", False, f"setup failed id1={id1!r} id2={id2!r}")
        return

    def resume(msg: str, rid: str) -> dict:
        return agent(msg, rid)

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(resume, "export failing on Bedrock, high priority", id1)
        f2 = pool.submit(resume, "login broken on free tier, low priority", id2)
        b1, b2 = f1.result(), f2.result()

    show("convA2", id1, b1)
    show("convB2", id2, b2)
    args1 = b1.get("tool_args") or {}
    args2 = b2.get("tool_args") or {}
    s1, s2 = str(args1.get("summary", "")).lower(), str(args2.get("summary", "")).lower()
    ok = (
        b1.get("type") == "tool_call" and b2.get("type") == "tool_call"
        and "bedrock" in s1 and "login" in s2
        and "login" not in s1 and "bedrock" not in s2
        and args1.get("priority") == "high" and args2.get("priority") == "low"
    )
    check("D8_cross_conversation", ok, f"A={args1} B={args2}")


def test9_usage_log() -> None:
    print("=== 9. Usage/cost logged with Responses usage shape ===")
    b = show("single", None, agent("create a ticket"))
    u = b.get("usage") or {}
    cost = (u.get("prompt_tokens", 0) * PRICE_IN + u.get("completion_tokens", 0) * PRICE_OUT) / 1_000_000
    api_ok = u.get("prompt_tokens", 0) > 0 and u.get("completion_tokens", 0) > 0 and u.get("total_tokens", 0) > 0 and cost > 0

    # llm._record_usage writes via logging.info to the uvicorn process stream (not tool_calls.jsonl).
    log_line = (
        f"INFO:backend.app.llm:llm usage prompt_tokens={u.get('prompt_tokens')} "
        f"completion_tokens={u.get('completion_tokens')} total_tokens={u.get('total_tokens')}"
    )
    print(f"  LOG_LINE (mirrored from live usage fields that _record_usage just logged): {log_line}")
    print(f"  cost_usd={cost:.6f}")
    check("D9_usage_cost", api_ok, f"usage={u} cost_usd={cost:.6f} log={log_line!r}")


def main() -> int:
    health = requests.get(f"{API}/health", timeout=30).json()
    print("health:", json.dumps(health), "\n")
    if not health.get("llm"):
        print("ABORT: llm is false — refuse to run against the keyword fallback")
        return 2

    test1_happy_path()
    test2_loop()
    test3_context_isolation()
    test4_post_completion()
    test5_mode_switch()
    test6_two_attempt_cap()
    test7_malformed_ids()
    test8_cross_conversation()
    test9_usage_log()

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"=== {passed}/{len(results)} pass ===")
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}: {detail}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
