"""
TC-05: Self-healing engine test (Member 3)

Sends many faults and predictions to the running API and measures:
  - decision accuracy   (did the engine choose the right response?)
  - recovery success rate (auto-fixes that succeeded / auto-fixes attempted)
  - recovery time       (milliseconds from sending the fault to the fix finishing)

Uses only the Python standard library (no pip install needed).

Before running:
  1. Start the server:  python app.py
  2. Restart the server first if you used /api/block-action (clears blocked actions)
Run:
  python tc05_test.py            (20 trials per case)
  python tc05_test.py 30         (30 trials per case)
"""
import csv
import json
import statistics
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:5000"
TRIALS = int(sys.argv[1]) if len(sys.argv) > 1 else 20

# (label, anomaly_type, confidence, expected decision)
ANOMALY_CASES = [
    ("service_crash, high confidence",     "service_crash",     0.90, "auto_fix"),
    ("link_congestion, high confidence",   "link_congestion",   0.90, "auto_fix"),
    ("suspicious_device, high confidence", "suspicious_device", 0.97, "auto_fix"),
    ("link_congestion, low confidence",    "link_congestion",   0.50, "alert"),
    ("suspicious_device, low confidence",  "suspicious_device", 0.50, "alert"),
    ("unknown fault type",                 "weird_fault",       0.99, "alert"),
]

# (label, probability, minutes to failure, expected decision)
PREDICTION_CASES = [
    ("prediction: high prob, soon",  0.95, 20,  "preventive_action"),
    ("prediction: medium prob",      0.80, 40,  "alert"),
    ("prediction: high prob, late",  0.95, 120, "alert"),
    ("prediction: low prob",         0.40, 20,  "store_only"),
]


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode() or "{}"
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"error": raw[:200]}


def main():
    # --- Pre-checks -------------------------------------------------------
    try:
        status, _ = call("GET", "/api/health")
    except Exception as e:
        print(f"Cannot reach the server at {BASE}. Is 'python app.py' running?\n{e}")
        return
    if status != 200:
        print("Health check failed.")
        return

    _, blocked = call("GET", "/api/blocked-actions")
    if blocked:
        print("Some actions are blocked, which would spoil the test:", blocked)
        print("Restart the server (Ctrl+C, then python app.py) and run this again.")
        return

    # --- Test device --------------------------------------------------------
    status, dev = call("POST", "/api/device/discovered", {
        "mac_address": "TC:05:00:00:00:01",
        "name": "tc05-router",
        "device_type": "router",
    })
    if status not in (200, 201):
        print("Could not create the test device:", dev)
        return
    device_id = dev["device_id"]
    print(f"Test device id: {device_id}  |  trials per case: {TRIALS}\n")

    rows = []  # one dict per trial, saved to CSV

    # --- Anomaly trials -----------------------------------------------------
    for label, a_type, conf, expected in ANOMALY_CASES:
        for i in range(TRIALS):
            t0 = time.perf_counter()
            status, resp = call("POST", "/api/anomaly", {
                "device_id": device_id, "anomaly_type": a_type, "confidence": conf,
            })
            ms = (time.perf_counter() - t0) * 1000

            result = resp.get("result", {}) if status in (200, 201) else {}
            decision = result.get("decision", "error")
            fixed = bool(result.get("success")) if decision == "auto_fix" else None
            correct = decision == expected and (fixed is not False)

            rows.append({"case": label, "kind": "anomaly", "expected": expected,
                         "decision": decision, "fix_succeeded": fixed,
                         "correct": correct, "time_ms": round(ms, 1)})

            # Put an isolated device back so the next trial starts clean
            if result.get("action") == "isolate" and result.get("action_id"):
                call("POST", f"/api/actions/{result['action_id']}/undo")

    # --- Prediction trials --------------------------------------------------
    for label, prob, minutes, expected in PREDICTION_CASES:
        for i in range(TRIALS):
            t0 = time.perf_counter()
            status, resp = call("POST", "/api/prediction", {
                "device_id": device_id, "predicted_issue": "overheating",
                "failure_probability": prob, "estimated_time_to_failure_min": minutes,
            })
            ms = (time.perf_counter() - t0) * 1000

            result = resp.get("result", {}) if status in (200, 201) else {}
            decision = result.get("decision", "error")
            fixed = bool(result.get("success")) if decision == "preventive_action" else None
            correct = decision == expected and (fixed is not False)

            rows.append({"case": label, "kind": "prediction", "expected": expected,
                         "decision": decision, "fix_succeeded": fixed,
                         "correct": correct, "time_ms": round(ms, 1)})

    # --- Summary table ------------------------------------------------------
    print(f"{'Case':<38}{'Trials':>7}{'Correct':>9}{'Accuracy':>10}{'Avg ms':>9}{'Max ms':>9}")
    print("-" * 82)
    for label in dict.fromkeys(r["case"] for r in rows):
        group = [r for r in rows if r["case"] == label]
        ok = sum(r["correct"] for r in group)
        times = [r["time_ms"] for r in group]
        print(f"{label:<38}{len(group):>7}{ok:>9}{100 * ok / len(group):>9.1f}%"
              f"{statistics.mean(times):>9.1f}{max(times):>9.1f}")
    print("-" * 82)

    total_ok = sum(r["correct"] for r in rows)
    print(f"Overall decision accuracy: {total_ok}/{len(rows)} "
          f"= {100 * total_ok / len(rows):.1f}%")

    fixes = [r for r in rows if r["fix_succeeded"] is not None]
    if fixes:
        good = sum(1 for r in fixes if r["fix_succeeded"])
        times = [r["time_ms"] for r in fixes]
        print(f"Recovery success rate:     {good}/{len(fixes)} "
              f"= {100 * good / len(fixes):.1f}%")
        print(f"Recovery time (avg / max): {statistics.mean(times):.1f} ms / "
              f"{max(times):.1f} ms")

    # --- Save every trial to CSV (for the report) ----------------------------
    with open("tc05_results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print("\nAll trials saved to tc05_results.csv (open it in Excel for your report).")
    print("Note: the actions are still simulated, so times are small. "
          "Re-run after real network commands are added.")


if __name__ == "__main__":
    main()