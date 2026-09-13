"""Hallucination-stability test (cross-request contamination + verifier spot-check).

Not a load/throughput test. Writes raw JSON under docs/testing/; markdown report
is assembled after manual Part B spot-checks.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parents[2] / "docs" / "testing" / "hallucination_stability_raw.json"

# Part A: 30 distinct known-answer questions (cycled/extended from golden + corpus facts).
# topic_keys are unique fingerprints used to detect cross-request contamination.
PART_A: list[dict] = [
    {
        "id": 1,
        "question": "What formats can a finished structure be exported as?",
        "topic": "export_formats",
        "expect_answer_any": [".litematic", ".schematic", ".glb", ".nbt"],
        "expect_sources_any": ["doc_04"],
        "foreign_markers": ["0.62", "PayPal", "Kubernetes", "floating coral", "30 bonus"],
    },
    {
        "id": 2,
        "question": "How many generations per day does the Free tier allow and what is its maximum structure size?",
        "topic": "free_tier_limits",
        "expect_answer_any": ["10", "64"],
        "expect_sources_any": ["doc_05", "doc_01"],
        "foreign_markers": [".litematic", "0.62", "PayPal", "floating coral", "Build of the Week"],
    },
    {
        "id": 3,
        "question": "What confidence score causes a build to be tagged review recommended?",
        "topic": "review_confidence",
        "expect_answer_any": ["0.62"],
        "expect_sources_any": ["doc_07"],
        "foreign_markers": [".litematic", "PayPal", "Kubernetes", "Studio", "30 bonus"],
    },
    {
        "id": 4,
        "question": "How do I get an API key and which tier is required?",
        "topic": "api_key_studio",
        "expect_answer_any": ["Studio", "Developer"],
        "expect_sources_any": ["doc_09"],
        "foreign_markers": ["0.62", "PayPal", "floating coral", "Build of the Week"],
    },
    {
        "id": 5,
        "question": "How many reference builds do I need to upload for a custom style preset?",
        "topic": "custom_preset_refs",
        "expect_answer_any": ["5"],
        "expect_sources_any": ["doc_03"],
        "foreign_markers": ["0.62", "PayPal", "Kubernetes", "floating coral"],
    },
    {
        "id": 6,
        "question": "Which known issue caused the ticket about a generation stuck on queued, and what does that known issue say?",
        "topic": "stuck_queued_issue",
        "expect_answer_any": ["30 seconds", "30-second", "Known Issue #4", "queued"],
        "expect_sources_any": ["ticket_101", "doc_12"],
        "foreign_markers": ["PayPal", "Kubernetes", "Build of the Week", ".litematic"],
    },
    {
        "id": 7,
        "question": "The ticket about floating coral chunks matches which known issue, and what workaround does that issue give?",
        "topic": "floating_coral",
        "expect_answer_any": ["128", "Known Issue #2", "underwater"],
        "expect_sources_any": ["ticket_105", "doc_12"],
        "foreign_markers": ["PayPal", "Kubernetes", "API key", "0.62"],
    },
    {
        "id": 8,
        "question": "Which failures are eligible for a generation-credit refund?",
        "topic": "refund_eligible_failures",
        "expect_answer_any": ["GPU", "transient", "category (3)", "category 3"],
        "expect_sources_any": ["doc_06"],
        "foreign_markers": ["PayPal", "Kubernetes", "Build of the Week", "0.62"],
    },
    {
        "id": 9,
        "question": "Within how many days of the initial charge can I get a refund, and are renewals eligible?",
        "topic": "billing_refund_window",
        "expect_answer_any": ["7 days", "7-day", "first billing", "renewals"],
        "expect_sources_any": ["doc_11"],
        "foreign_markers": ["Kubernetes", "floating coral", "0.62", ".litematic"],
    },
    {
        "id": 10,
        "question": "How many seats can a Studio Team Workspace have?",
        "topic": "workspace_seats",
        "expect_answer_any": ["10"],
        "expect_sources_any": ["doc_08", "doc_05"],
        "foreign_markers": ["PayPal", "Kubernetes", "0.62", "floating coral"],
    },
    {
        "id": 11,
        "question": "What happens to prompts longer than 400 characters?",
        "topic": "prompt_truncation",
        "expect_answer_any": ["400", "truncat"],
        "expect_sources_any": ["doc_02"],
        "foreign_markers": ["PayPal", "Kubernetes", "0.62", "floating coral"],
    },
    {
        "id": 12,
        "question": "How many bonus generation credits does Build of the Week award, and how long are they valid?",
        "topic": "botw_credits",
        "expect_answer_any": ["30", "60"],
        "expect_sources_any": ["doc_13"],
        "foreign_markers": ["PayPal", "Kubernetes", "0.62", ".litematic", "floating coral"],
    },
    {
        "id": 13,
        "question": "Are prompts that reference copyrighted characters allowed?",
        "topic": "content_policy_ip",
        "expect_answer_any": ["reject", "not", "copyright"],
        "expect_sources_any": ["doc_10"],
        "foreign_markers": ["PayPal", "Kubernetes", "0.62", "floating coral"],
    },
    {
        "id": 14,
        "question": "How long does a typical generation take?",
        "topic": "generation_time",
        "expect_answer_any": ["15", "45"],
        "expect_sources_any": ["doc_01"],
        "foreign_markers": ["PayPal", "Kubernetes", "0.62", "floating coral"],
    },
    {
        "id": 15,
        "question": "What is the Pro tier monthly price and daily generation limit?",
        "topic": "pro_tier",
        "expect_answer_any": ["15", "100"],
        "expect_sources_any": ["doc_05"],
        "foreign_markers": ["PayPal", "Kubernetes", "floating coral", "Build of the Week"],
    },
    {
        "id": 16,
        "question": "Does Craftify offer a native Bedrock add-on export format?",
        "topic": "no_bedrock_addon",
        "expect_answer_any": ["no", "not", "does not", "roadmap"],
        "expect_sources_any": ["doc_04", "ticket_103"],
        "foreign_markers": ["PayPal", "Kubernetes", "0.62", "Build of the Week"],
    },
    {
        "id": 17,
        "question": "When do unused generation credits reset, and do they roll over?",
        "topic": "credits_rollover",
        "expect_answer_any": ["do not roll", "don't roll", "00:00", "UTC", "not roll"],
        "expect_sources_any": ["doc_05", "doc_11"],
        "foreign_markers": ["Kubernetes", "floating coral", "0.62"],
    },
    {
        "id": 18,
        "question": "What is the API job polling rate limit?",
        "topic": "api_poll_rate",
        "expect_answer_any": ["2", "poll"],
        "expect_sources_any": ["doc_09"],
        "foreign_markers": ["PayPal", "Kubernetes", "floating coral", "0.62"],
    },
    {
        "id": 19,
        "question": "After a member is removed from a workspace, can other members still access builds generated in that workspace?",
        "topic": "workspace_build_ownership",
        "expect_answer_any": ["remain", "accessible", "workspace", "owned"],
        "expect_sources_any": ["doc_08"],
        "foreign_markers": ["PayPal", "Kubernetes", "0.62", "floating coral"],
    },
    {
        "id": 20,
        "question": "Roughly what fraction of the time are negative constraints like 'without X' honored?",
        "topic": "negative_constraint_rate",
        "expect_answer_any": ["80"],
        "expect_sources_any": ["doc_02"],
        "foreign_markers": ["PayPal", "Kubernetes", "0.62", "floating coral"],
    },
    {
        "id": 21,
        "question": "What is the Studio tier price and maximum structure size?",
        "topic": "studio_tier",
        "expect_answer_any": ["60", "512"],
        "expect_sources_any": ["doc_05"],
        "foreign_markers": ["PayPal", "Kubernetes", "floating coral", "Build of the Week"],
    },
    {
        "id": 22,
        "question": "How much extra generation time do borderline policy-flagged prompts add?",
        "topic": "policy_recheck_delay",
        "expect_answer_any": ["5", "10"],
        "expect_sources_any": ["doc_10"],
        "foreign_markers": ["PayPal", "Kubernetes", "floating coral", ".litematic"],
    },
    {
        "id": 23,
        "question": "Can I transfer a personal-account build into a workspace after the fact?",
        "topic": "no_posthoc_transfer",
        "expect_answer_any": ["no", "not", "regenerat"],
        "expect_sources_any": ["doc_08"],
        "foreign_markers": ["PayPal", "Kubernetes", "0.62", "floating coral"],
    },
    {
        "id": 24,
        "question": "Which export formats are available on the Free tier?",
        "topic": "free_export_formats",
        "expect_answer_any": [".schematic", ".glb"],
        "expect_sources_any": ["doc_05"],
        "foreign_markers": ["PayPal", "Kubernetes", "0.62", "floating coral"],
    },
    {
        "id": 25,
        "question": "Does downgrading from Pro take effect immediately or at period end?",
        "topic": "downgrade_timing",
        "expect_answer_any": ["end", "period", "billing"],
        "expect_sources_any": ["doc_11"],
        "foreign_markers": ["Kubernetes", "floating coral", "0.62", "Build of the Week"],
    },
    {
        "id": 26,
        "question": "What known issue affects Bedrock .nbt glass color?",
        "topic": "bedrock_glass_bug",
        "expect_answer_any": ["glass", "Bedrock", "color", "Known Issue"],
        "expect_sources_any": ["doc_12"],
        "foreign_markers": ["PayPal", "Kubernetes", "Build of the Week", "0.62"],
    },
    {
        "id": 27,
        "question": "How long can workspace sync lag, and is that considered a bug?",
        "topic": "workspace_sync_lag",
        "expect_answer_any": ["10", "expected", "not a bug", "sync"],
        "expect_sources_any": ["doc_12"],
        "foreign_markers": ["PayPal", "Kubernetes", "0.62", "Build of the Week"],
    },
    {
        "id": 28,
        "question": "Ticket #1058 about negative prompts not being respected — was a refund issued?",
        "topic": "ticket_102_no_refund",
        "expect_answer_any": ["no", "not", "expected", "limitation"],
        "expect_sources_any": ["ticket_102"],
        "foreign_markers": ["PayPal", "Kubernetes", "Build of the Week", "0.62"],
    },
    {
        "id": 29,
        "question": "What custom style preset tier is required, and how long does fine-tuning take?",
        "topic": "preset_tier_finetune",
        "expect_answer_any": ["Pro", "2", "6"],
        "expect_sources_any": ["doc_03"],
        "foreign_markers": ["PayPal", "Kubernetes", "floating coral", "0.62"],
    },
    {
        "id": 30,
        "question": "When a Free-tier user exceeds the daily generation cap, what HTTP status is returned?",
        "topic": "cap_exceed_429",
        "expect_answer_any": ["429", "reset_at"],
        "expect_sources_any": ["doc_05"],
        "foreign_markers": ["PayPal", "Kubernetes", "floating coral", "Build of the Week"],
    },
]

# Part B: 20 diverse queries — golden, paraphrases, and new-but-corpus-answerable.
PART_B: list[dict] = [
    {
        "id": 1,
        "kind": "golden",
        "question": "What formats can a finished structure be exported as?",
        "ground_notes": "doc_04: .schematic, .litematic, .glb, .nbt",
    },
    {
        "id": 2,
        "kind": "golden",
        "question": "What confidence score causes a build to be tagged review recommended?",
        "ground_notes": "doc_07: below 0.62",
    },
    {
        "id": 3,
        "kind": "golden",
        "question": "How do I get an API key and which tier is required?",
        "ground_notes": "doc_09: Studio, Account Settings > Developer",
    },
    {
        "id": 4,
        "kind": "golden_abstain",
        "question": "What uptime SLA does Craftify guarantee on the Studio tier?",
        "ground_notes": "Not in corpus — must abstain",
    },
    {
        "id": 5,
        "kind": "golden_abstain",
        "question": "Can I pay for my Craftify subscription with PayPal?",
        "ground_notes": "Not in corpus — must abstain",
    },
    {
        "id": 6,
        "kind": "paraphrase",
        "question": "List every file extension Craftify can export a finished build to.",
        "ground_notes": "doc_04 paraphrase of export formats",
    },
    {
        "id": 7,
        "kind": "paraphrase",
        "question": "On Free, what's my daily gen cap and the biggest build I can make?",
        "ground_notes": "doc_05 paraphrase: 10/day, 64^3",
    },
    {
        "id": 8,
        "kind": "paraphrase",
        "question": "Where do Studio users request developer API credentials?",
        "ground_notes": "doc_09 paraphrase",
    },
    {
        "id": 9,
        "kind": "paraphrase",
        "question": "If the model is unsure about geometry quality, what score threshold triggers the review badge?",
        "ground_notes": "doc_07 paraphrase: < 0.62",
    },
    {
        "id": 10,
        "kind": "paraphrase",
        "question": "For a refund after signup, what's the window and does it apply to renewals?",
        "ground_notes": "doc_11: 7 days, first cycle only",
    },
    {
        "id": 11,
        "kind": "new",
        "question": "Which category of generation failure gets a credit refund?",
        "ground_notes": "doc_06: only transient GPU (3)",
    },
    {
        "id": 12,
        "kind": "new",
        "question": "How many seats does a Team Workspace support?",
        "ground_notes": "doc_08: up to 10",
    },
    {
        "id": 13,
        "kind": "new",
        "question": "What happens if my prompt exceeds 400 characters?",
        "ground_notes": "doc_02: truncated",
    },
    {
        "id": 14,
        "kind": "new",
        "question": "How many bonus credits does Build of the Week give, and for how long are they valid?",
        "ground_notes": "doc_13: 30 credits, 60 days",
    },
    {
        "id": 15,
        "kind": "new",
        "question": "Are hate symbols or explicit sexual content allowed in prompts?",
        "ground_notes": "doc_10: rejected",
    },
    {
        "id": 16,
        "kind": "new",
        "question": "What is the Pro plan price and its daily generation limit?",
        "ground_notes": "doc_05: $15/mo, 100/day",
    },
    {
        "id": 17,
        "kind": "new",
        "question": "Is there a way to export as a native Bedrock add-on?",
        "ground_notes": "doc_04: no native Bedrock add-on",
    },
    {
        "id": 18,
        "kind": "new",
        "question": "How long can API polling keep showing queued after a job actually finished?",
        "ground_notes": "doc_12 Known Issue #4: up to 30 seconds",
    },
    {
        "id": 19,
        "kind": "new_hard",
        "question": "Does Craftify support paying with cryptocurrency or Apple Pay?",
        "ground_notes": "Not in corpus — should abstain (like PayPal)",
    },
    {
        "id": 20,
        "kind": "new_hard",
        "question": "What is Craftify's SOC 2 compliance status?",
        "ground_notes": "Not in corpus — should abstain",
    },
]


def post_ask(question: str) -> dict:
    data = json.dumps({"question": question}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/ask",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"error": f"HTTP {e.code}", "body": body}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def source_ids(resp: dict) -> list[str]:
    return [s.get("doc_id", "") for s in resp.get("sources") or []]


def verifier_label(resp: dict) -> str:
    if resp.get("error"):
        return "ERROR"
    if resp.get("override_reason") == "verifier returned UNSUPPORTED":
        return "UNSUPPORTED"
    if resp.get("verified") is True:
        return "SUPPORTED"
    if resp.get("abstained"):
        return "ABSTAINED_NO_VERIFIER_VETO"
    return "UNCLEAR"


def score_part_a(item: dict, resp: dict) -> dict:
    """Pass if response matches THIS request's topic; fail on foreign-topic leak."""
    answer = (resp.get("answer") or "").lower()
    srcs = source_ids(resp)
    err = resp.get("error")

    if err:
        return {
            "pass": False,
            "contamination": False,
            "reason": f"request error: {err}",
            "answer": resp.get("answer"),
            "sources": srcs,
            "verified": resp.get("verified"),
            "abstained": resp.get("abstained"),
            "override_reason": resp.get("override_reason"),
        }

    foreign_hits = [m for m in item["foreign_markers"] if m.lower() in answer]
    # Source contamination: cited a doc that is clearly for a different concurrent topic
    # only flag if answer also lacks expected content AND cites nothing expected.
    expect_ans = item["expect_answer_any"]
    expect_src = item["expect_sources_any"]
    ans_ok = any(e.lower() in answer for e in expect_ans)
    src_ok = any(s in srcs for s in expect_src) if srcs else False

    # Contaminated: answer discusses a foreign topic fingerprint without answering own question
    contamination = bool(foreign_hits) and not ans_ok

    # Also: sources entirely from unrelated docs while answer misses expected facts
    # (weaker signal — abstain with empty sources is OK)
    if not ans_ok and srcs and not src_ok and not resp.get("abstained"):
        contamination = True

    passed = ans_ok or (resp.get("abstained") and not contamination)
    # For known-answer questions, abstain without contamination is a soft fail (wrong) but
    # not contamination. Mark pass=False, contamination=False.
    if resp.get("abstained") and not contamination:
        passed = False
        reason = "abstained on known-answer question (not contamination)"
    elif contamination:
        passed = False
        reason = f"contamination: foreign markers {foreign_hits}; ans_ok={ans_ok} src_ok={src_ok}"
    elif ans_ok:
        passed = True
        reason = "answer matches expected topic"
    else:
        passed = False
        reason = f"answer missing expected markers {expect_ans}; src_ok={src_ok}"

    return {
        "pass": passed,
        "contamination": contamination,
        "reason": reason,
        "answer": resp.get("answer"),
        "sources": srcs,
        "verified": resp.get("verified"),
        "abstained": resp.get("abstained"),
        "override_reason": resp.get("override_reason"),
        "retrieval_confidence": resp.get("retrieval_confidence"),
        "foreign_hits": foreign_hits,
        "ans_ok": ans_ok,
        "src_ok": src_ok,
    }


def run_part_a() -> dict:
    print(f"Part A: firing {len(PART_A)} concurrent /ask requests...")
    t0 = time.perf_counter()
    results = []

    def one(item: dict) -> dict:
        resp = post_ask(item["question"])
        scored = score_part_a(item, resp)
        return {
            "id": item["id"],
            "topic": item["topic"],
            "question": item["question"],
            **scored,
            "raw": resp,
        }

    with ThreadPoolExecutor(max_workers=30) as pool:
        futs = {pool.submit(one, item): item["id"] for item in PART_A}
        for fut in as_completed(futs):
            row = fut.result()
            results.append(row)
            status = "PASS" if row["pass"] else ("CONTAM" if row["contamination"] else "FAIL")
            print(f"  A#{row['id']:02d} {status}: {row['topic']} — {row['reason'][:80]}")

    results.sort(key=lambda r: r["id"])
    elapsed = time.perf_counter() - t0
    contaminations = [r for r in results if r["contamination"]]
    fails = [r for r in results if not r["pass"]]
    return {
        "elapsed_sec": round(elapsed, 2),
        "n": len(results),
        "n_pass": sum(1 for r in results if r["pass"]),
        "n_fail": len(fails),
        "n_contamination": len(contaminations),
        "results": results,
    }


def run_part_b() -> dict:
    print(f"Part B: {len(PART_B)} sequential /ask requests...")
    t0 = time.perf_counter()
    results = []
    for item in PART_B:
        resp = post_ask(item["question"])
        label = verifier_label(resp)
        row = {
            "id": item["id"],
            "kind": item["kind"],
            "question": item["question"],
            "ground_notes": item["ground_notes"],
            "verifier": label,
            "verified": resp.get("verified"),
            "abstained": resp.get("abstained"),
            "override_reason": resp.get("override_reason"),
            "answer": resp.get("answer"),
            "sources": source_ids(resp),
            "retrieval_confidence": resp.get("retrieval_confidence"),
            "raw": resp,
        }
        results.append(row)
        print(f"  B#{item['id']:02d} {label}: {item['question'][:60]}")
        time.sleep(0.15)  # gentle pacing; sequential sampling, not load
    elapsed = time.perf_counter() - t0
    return {
        "elapsed_sec": round(elapsed, 2),
        "n": len(results),
        "results": results,
    }


def main() -> None:
    health = json.loads(urllib.request.urlopen(f"{BASE}/health", timeout=10).read())
    print("health:", health)
    if not health.get("llm"):
        raise SystemExit("llm:false — abort (verifier would be a no-op)")

    part_a = run_part_a()
    part_b = run_part_b()
    payload = {"health": health, "part_a": part_a, "part_b": part_b}
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT}")
    print(
        f"Part A: {part_a['n_pass']}/{part_a['n']} pass, "
        f"{part_a['n_contamination']} contamination, {part_a['elapsed_sec']}s"
    )
    print(f"Part B: {part_b['n']} responses in {part_b['elapsed_sec']}s")


if __name__ == "__main__":
    main()
