"""Diagnose resource growth under sustained /ask+/agent load. Not a fix."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import psutil
import requests

API = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parents[2] / "docs" / "testing" / "leak_diag.json"


def wait_health(timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            h = requests.get(f"{API}/health", timeout=10).json()
            if h.get("status") == "ok" and h.get("documents", 0) > 0:
                return h
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("backend not healthy")


def snapshot(proc: psutil.Process) -> dict:
    with proc.oneshot():
        return {
            "rss_mb": round(proc.memory_info().rss / 1e6, 1),
            "vms_mb": round(proc.memory_info().vms / 1e6, 1),
            "threads": proc.num_threads(),
            "fds_or_handles": proc.num_handles() if hasattr(proc, "num_handles") else None,
            "connections": len(proc.net_connections()),
            "tcp_established": sum(1 for c in proc.net_connections() if c.status == "ESTABLISHED"),
        }


def main():
    health = wait_health()
    print("health", health)

    # Find uvicorn pid via listen on 8000
    proc = None
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            for c in p.net_connections():
                if c.laddr and c.laddr.port == 8000 and c.status == "LISTEN":
                    proc = psutil.Process(p.pid)
                    break
        except (psutil.Error, Exception):
            continue
        if proc:
            break
    if proc is None:
        raise RuntimeError("could not find pid on :8000")

    print("target pid", proc.pid)
    rows = []
    base = snapshot(proc)
    print("BASE", base)
    rows.append({"n": 0, **base, "note": "baseline after health"})

    questions = [
        "Which export formats work with Java Edition?",
        "How many generations per day on free tier?",
        "Which tickets resulted in a refund?",
        "What is the Studio SLA?",
        "create a ticket",
        "Flag this generation for review because floating blocks",
        "Can I pay with PayPal?",
        "What confidence score means?",
        "export formats for Bedrock",
        "create a 3d asset for a lamp",
    ]

    first_fail = None
    for i in range(1, 31):
        q = questions[(i - 1) % len(questions)]
        ep = "/ask" if i % 2 else "/agent"
        payload = {"question": q} if ep == "/ask" else {"message": q}
        t0 = time.perf_counter()
        try:
            r = requests.post(f"{API}{ep}", json=payload, timeout=180)
            ms = (time.perf_counter() - t0) * 1000
            try:
                body = r.json()
            except Exception:
                body = {"_raw": r.text[:300]}
            ok = 200 <= r.status_code < 300
        except Exception as e:
            ms = (time.perf_counter() - t0) * 1000
            r = None
            body = {"error": str(e)}
            ok = False

        snap = snapshot(proc)
        row = {
            "n": i,
            "ep": ep,
            "status": None if r is None else r.status_code,
            "ok": ok,
            "ms": round(ms, 1),
            "body_keys": list(body)[:8] if isinstance(body, dict) else [],
            "type_or_abstain": body.get("type") if isinstance(body, dict) else None
            if ep == "/agent"
            else (body.get("abstained") if isinstance(body, dict) else None),
            "ans_len": len((body.get("answer") or "")) if isinstance(body, dict) else 0,
            **snap,
            "d_threads": snap["threads"] - base["threads"],
            "d_handles": (snap["fds_or_handles"] or 0) - (base["fds_or_handles"] or 0),
            "d_rss_mb": round(snap["rss_mb"] - base["rss_mb"], 1),
        }
        rows.append(row)
        print(
            f"n={i:02d} {ep:6s} status={row['status']} ok={ok} threads={snap['threads']} "
            f"(+{row['d_threads']}) handles={snap['fds_or_handles']} (+{row['d_handles']}) "
            f"rss={snap['rss_mb']}MB conn={snap['connections']}"
        )
        if not ok and first_fail is None:
            first_fail = {"n": i, "ep": ep, "status": row["status"], "body": body, "snap": snap}
            print("FIRST FAIL BODY:", json.dumps(body)[:500])

    OUT.write_text(json.dumps({"base": base, "first_fail": first_fail, "rows": rows}, indent=2), encoding="utf-8")
    print("wrote", OUT)
    print(
        "DELTA end-start threads",
        rows[-1]["threads"] - base["threads"],
        "handles",
        (rows[-1]["fds_or_handles"] or 0) - (base["fds_or_handles"] or 0),
        "rss_mb",
        round(rows[-1]["rss_mb"] - base["rss_mb"], 1),
    )


if __name__ == "__main__":
    main()
