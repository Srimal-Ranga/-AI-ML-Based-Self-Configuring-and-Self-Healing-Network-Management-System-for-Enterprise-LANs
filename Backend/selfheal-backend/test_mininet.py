#!/usr/bin/env python3
"""
Mininet -> backend test (Member 3).

Builds a small Mininet network (1 switch + 4 hosts), reports each host to the
backend as a newly discovered device (using the host's REAL Mininet MAC and IP),
then sends a fault, an attack and a failure prediction, and prints what the
backend decided.

Run inside the Mininet VM:
    sudo python3 test_mininet.py                      (backend at http://10.0.2.2:5000)
    sudo python3 test_mininet.py http://192.168.1.20:5000   (another address)

Note: the backend actions are still simulated, so nothing changes inside Mininet.
"""
import json
import sys
import urllib.error
import urllib.request

from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.topo import SingleSwitchTopo

API = (sys.argv[1] if len(sys.argv) > 1 else "http://10.0.2.2:5000").rstrip("/")


def post(path, body):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except ValueError:
            return e.code, {}


def get(path):
    with urllib.request.urlopen(API + path, timeout=15) as r:
        return json.loads(r.read().decode())


def main():
    try:
        print("Backend health:", get("/api/health"))
    except Exception as e:
        print("Cannot reach the backend at", API, "->", e)
        print("Is 'python app.py' running on the PC? Try:  curl", API + "/api/health")
        return

    setLogLevel("warning")
    net = Mininet(topo=SingleSwitchTopo(4))
    net.start()
    try:
        # (host, device type the classifier would report, confidence)
        plan = [("h1", "laptop", 0.99), ("h2", "iot", 0.97), ("h3", "server", 0.95), ("h4", "iot", 0.40)]
        ids = {}
        print("\n--- 1. New devices join the network ---")
        for name, dtype, conf in plan:
            h = net.get(name)
            code, resp = post("/api/device/discovered", {
                "mac_address": h.MAC(), "ip_address": h.IP(), "name": name,
                "device_type": dtype, "confidence": conf})
            ids[name] = resp.get("device_id")
            print(f"{name}  mac={h.MAC()} ip={h.IP()} type={dtype} conf={conf}"
                  f"  ->  HTTP {code}, status={resp.get('status')}, device_id={ids[name]}")
        print("Expected: h1-h3 active, h4 quarantined (low confidence).")

        print("\n--- 2. Traffic metrics ---")
        code, resp = post("/api/metrics", {"device_id": ids["h2"], "cpu_usage": 91, "memory_usage": 70,
                                           "bandwidth_in": 800, "bandwidth_out": 120})
        print("metrics for h2 -> HTTP", code)

        print("\n--- 3. Self-healing decisions ---")
        tests = [
            ("service crash on h1 (conf 0.90)", "/api/anomaly",
             {"device_id": ids["h1"], "anomaly_type": "service_crash", "confidence": 0.90}, "auto_fix"),
            ("suspicious h2 (conf 0.97)", "/api/anomaly",
             {"device_id": ids["h2"], "anomaly_type": "suspicious_device", "confidence": 0.97}, "auto_fix"),
            ("congestion on h3 (conf 0.50)", "/api/anomaly",
             {"device_id": ids["h3"], "anomaly_type": "link_congestion", "confidence": 0.50}, "alert"),
            ("prediction h3 (0.95, 20 min)", "/api/prediction",
             {"device_id": ids["h3"], "predicted_issue": "overheating", "failure_probability": 0.95,
              "estimated_time_to_failure_min": 20}, "preventive_action"),
        ]
        ok = 0
        for label, path, body, expected in tests:
            code, resp = post(path, body)
            decision = resp.get("result", {}).get("decision")
            good = decision == expected
            ok += good
            print(f"{'PASS' if good else 'FAIL'}  {label}: decision={decision} (expected {expected})")

        print("\n--- 4. What the dashboard will show ---")
        print("summary:", json.dumps(get("/api/summary")))
        print(f"\nDecisions correct: {ok}/{len(tests)}")
        print("Now open the dashboard and check the devices, alerts and actions tabs.")
    finally:
        net.stop()


if __name__ == "__main__":
    main()