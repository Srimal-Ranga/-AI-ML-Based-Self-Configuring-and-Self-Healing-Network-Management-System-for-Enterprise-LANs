"""
Self-Healing Network Backend (Member 3)
- Central API for Member 1 (ZTP / dashboard) and Member 2 (anomaly + prediction)
- Self-healing engine: provisioning, error fixing, preventive actions
- Logs every action in the `action` table
"""

import os
import time

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, jsonify, request

app = Flask(__name__)

# ----------------------------------------------------------------------
# CONFIG  (change the password, or set the DB_PASSWORD environment variable)
# ----------------------------------------------------------------------
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "selfheal_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "YOUR_PASSWORD"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
}

# Self-healing rules: anomaly_type -> (action_type, minimum confidence)
# Tune these numbers during testing.
ANOMALY_RULES = {
    "service_crash":     ("restart", 0.0),    # safe fault: always auto-fix
    "link_congestion":   ("reroute", 0.85),   # riskier: needs high confidence
    "suspicious_device": ("isolate", 0.95),   # dangerous: needs very high confidence
}

# Prediction thresholds
PRED_ACT_PROBABILITY = 0.90     # act automatically at or above this ...
PRED_ACT_MAX_MINUTES = 30       # ... if failure is expected within this many minutes
PRED_ALERT_PROBABILITY = 0.70   # alert the admin at or above this

# Provisioning
AUTO_PROVISION = True           # False = unknown devices only raise an alert
MAX_PROVISION_RETRIES = 3

# Config templates sent to new devices, by device_type
CONFIG_TEMPLATES = {
    "router": "hostname {name}\nip routing\nsnmp-server community public RO\n",
    "switch": "hostname {name}\nvlan 10\nspanning-tree mode rapid-pvst\n",
    "host":   "dhcp enabled\ndns 8.8.8.8\n",
}
DEFAULT_TEMPLATE = "hostname {name}\n"

# Actions the admin has blocked: set of (device_id, action_type); device_id None = all devices
# (kept in memory, so it resets when the server restarts)
BLOCKED_ACTIONS = set()


# ----------------------------------------------------------------------
# DATABASE HELPERS
# ----------------------------------------------------------------------
def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def query(sql, params=None, fetch=False):
    """Run one SQL command. Returns a list of rows when fetch=True."""
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, params)
        rows = cur.fetchall() if fetch else None
        conn.commit()
        return rows
    finally:
        conn.close()


def log_action(device_id, action_type, triggered_by="auto", anomaly_id=None,
               prediction_id=None, result=None, notes=None):
    """Insert a row into the action table. Returns action_id.
    If result is given, the action is marked finished immediately."""
    rows = query(
        """
        INSERT INTO action
            (device_id, anomaly_id, prediction_id, action_type, triggered_by,
             result, notes, finished_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s,
                CASE WHEN %s IS NULL THEN NULL ELSE NOW() END)
        RETURNING action_id;
        """,
        (device_id, anomaly_id, prediction_id, action_type, triggered_by,
         result, notes, result),
        fetch=True,
    )
    return rows[0]["action_id"]


def finish_action(action_id, result, notes=None):
    query(
        """
        UPDATE action
        SET finished_at = NOW(), result = %s, notes = COALESCE(%s, notes)
        WHERE action_id = %s;
        """,
        (result, notes, action_id),
    )


def set_device_status(device_id, status, **extra):
    if status == "active" and extra.get("provisioned"):
        query(
            "UPDATE device SET status=%s, provisioned_at=NOW(), config_applied=%s WHERE device_id=%s;",
            (status, extra.get("config"), device_id),
        )
    else:
        query("UPDATE device SET status=%s WHERE device_id=%s;", (status, device_id))


def get_device(device_id):
    rows = query("SELECT * FROM device WHERE device_id=%s;", (device_id,), fetch=True)
    return rows[0] if rows else None


# ----------------------------------------------------------------------
# SELF-HEALING ACTIONS
# Each function returns True (success) or False (fail).
# They are SIMULATED for now. Replace the TODO parts with real commands
# once you know how the test network (Mininet / GNS3) is controlled.
# ----------------------------------------------------------------------
def restart_service(device_id):
    # TODO: real restart (e.g. SSH to the device and restart the service)
    print(f"[ACTION] restart service on device {device_id}")
    time.sleep(0.2)
    return True


def reroute_traffic(device_id):
    # TODO: update flow rules / routing so traffic avoids this device
    print(f"[ACTION] reroute traffic around device {device_id}")
    time.sleep(0.2)
    return True


def isolate_device(device_id):
    # TODO: block the device's switch port / add a drop rule
    print(f"[ACTION] isolate device {device_id}")
    time.sleep(0.2)
    set_device_status(device_id, "isolated")
    return True


def unisolate_device(device_id):
    # TODO: remove the block rule
    print(f"[ACTION] un-isolate device {device_id}")
    set_device_status(device_id, "active")
    return True


def push_config(device, config_text):
    # TODO: send the config to the device (DHCP / SSH / SDN controller)
    print(f"[ACTION] push config to device {device['device_id']}:\n{config_text}")
    time.sleep(0.2)
    return True


ACTION_FUNCTIONS = {
    "restart": restart_service,
    "reroute": reroute_traffic,
    "isolate": isolate_device,
}


def is_blocked(device_id, action_type):
    return ((device_id, action_type) in BLOCKED_ACTIONS
            or (None, action_type) in BLOCKED_ACTIONS)


def run_and_log(action_type, device_id, anomaly_id=None, prediction_id=None,
                triggered_by="auto"):
    """Run one corrective action and record it in the action table."""
    action_id = log_action(device_id, action_type, triggered_by,
                           anomaly_id=anomaly_id, prediction_id=prediction_id)
    try:
        ok = ACTION_FUNCTIONS[action_type](device_id)
    except Exception as e:
        finish_action(action_id, "fail", f"error: {e}")
        return action_id, False
    finish_action(action_id, "success" if ok else "fail")
    return action_id, ok


def send_alert_to_admin(device_id, message, anomaly_id=None, prediction_id=None):
    """For now the alert is printed and saved as an 'alert' action.
    The dashboard shows it through GET /api/actions."""
    print(f"[ALERT] device {device_id}: {message}")
    return log_action(device_id, "alert", "auto", anomaly_id=anomaly_id,
                      prediction_id=prediction_id, result="success", notes=message)


# ----------------------------------------------------------------------
# WORKFLOW A: NEW DEVICE AUTO-CONNECT (provisioning)
# ----------------------------------------------------------------------
def handle_new_device(device):
    device_id = device["device_id"]

    if device["status"] == "active":
        return {"provisioned": False, "reason": "already active"}

    if not AUTO_PROVISION or is_blocked(device_id, "provision"):
        send_alert_to_admin(device_id, "New device needs manual approval")
        return {"provisioned": False, "reason": "waiting for admin approval"}

    set_device_status(device_id, "provisioning")
    template = CONFIG_TEMPLATES.get(device.get("device_type"), DEFAULT_TEMPLATE)
    config_text = template.format(name=device.get("name") or f"device{device_id}")

    action_id = log_action(device_id, "provision", "auto")
    for attempt in range(1, MAX_PROVISION_RETRIES + 1):
        if push_config(device, config_text):
            set_device_status(device_id, "active", provisioned=True, config=config_text)
            finish_action(action_id, "success", f"provisioned on attempt {attempt}")
            return {"provisioned": True, "attempts": attempt}

    set_device_status(device_id, "failed")
    finish_action(action_id, "fail", f"failed after {MAX_PROVISION_RETRIES} attempts")
    send_alert_to_admin(device_id, "Auto-provisioning failed")
    return {"provisioned": False, "reason": "provisioning failed"}


# ----------------------------------------------------------------------
# WORKFLOW B: AUTO-CORRECT ERRORS
# ----------------------------------------------------------------------
def handle_anomaly(anomaly):
    """anomaly = {anomaly_id, device_id, anomaly_type, confidence}"""
    device_id = anomaly["device_id"]
    anomaly_id = anomaly["anomaly_id"]
    rule = ANOMALY_RULES.get(anomaly["anomaly_type"])

    if rule is None:
        send_alert_to_admin(device_id, f"Unknown anomaly type: {anomaly['anomaly_type']}",
                            anomaly_id=anomaly_id)
        query("UPDATE anomaly SET status='alerted' WHERE anomaly_id=%s;", (anomaly_id,))
        return {"decision": "alert", "reason": "unknown anomaly type"}

    action_type, min_conf = rule

    if is_blocked(device_id, action_type):
        log_action(device_id, action_type, "auto", anomaly_id=anomaly_id,
                   result="blocked", notes="Blocked by admin")
        send_alert_to_admin(device_id, f"Auto-{action_type} blocked by admin", anomaly_id=anomaly_id)
        query("UPDATE anomaly SET status='alerted' WHERE anomaly_id=%s;", (anomaly_id,))
        return {"decision": "alert", "reason": "action blocked by admin"}

    if anomaly["confidence"] >= min_conf:
        action_id, ok = run_and_log(action_type, device_id, anomaly_id=anomaly_id)
        query("UPDATE anomaly SET status=%s WHERE anomaly_id=%s;",
              ("handled" if ok else "alerted", anomaly_id))
        if not ok:
            send_alert_to_admin(device_id, f"Auto-{action_type} failed", anomaly_id=anomaly_id)
        return {"decision": "auto_fix", "action": action_type,
                "success": ok, "action_id": action_id}

    send_alert_to_admin(
        device_id,
        f"{anomaly['anomaly_type']} (confidence {anomaly['confidence']:.2f} "
        f"below {min_conf}), admin decision needed",
        anomaly_id=anomaly_id,
    )
    query("UPDATE anomaly SET status='alerted' WHERE anomaly_id=%s;", (anomaly_id,))
    return {"decision": "alert", "reason": "confidence too low"}


# ----------------------------------------------------------------------
# WORKFLOW C: ACT ON PREDICTED FAILURES
# ----------------------------------------------------------------------
def handle_prediction(pred):
    """pred = {prediction_id, device_id, predicted_issue,
               failure_probability, estimated_time_to_failure_min}"""
    device_id = pred["device_id"]
    pid = pred["prediction_id"]
    prob = pred["failure_probability"] or 0
    minutes = pred.get("estimated_time_to_failure_min")

    result = {"decision": "store_only"}

    if (prob >= PRED_ACT_PROBABILITY and minutes is not None
            and minutes <= PRED_ACT_MAX_MINUTES
            and not is_blocked(device_id, "reroute")):
        action_id, ok = run_and_log("reroute", device_id, prediction_id=pid)
        # label this action as preventive in the notes
        query("UPDATE action SET action_type='preventive', notes=%s WHERE action_id=%s;",
              ("preventive reroute before predicted failure", action_id))
        send_alert_to_admin(
            device_id,
            f"Predicted {pred['predicted_issue']} in ~{minutes} min "
            f"(p={prob:.2f}); traffic rerouted",
            prediction_id=pid,
        )
        result = {"decision": "preventive_action", "success": ok}
    elif prob >= PRED_ALERT_PROBABILITY:
        send_alert_to_admin(
            device_id,
            f"Predicted {pred['predicted_issue']} "
            f"(p={prob:.2f}, ~{minutes} min to failure)",
            prediction_id=pid,
        )
        result = {"decision": "alert"}

    query("UPDATE prediction SET handled=TRUE WHERE prediction_id=%s;", (pid,))
    return result


# ----------------------------------------------------------------------
# API ENDPOINTS
# ----------------------------------------------------------------------
@app.route("/")
def home():
    return jsonify({"message": "Self-Healing Network Backend is running"})


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


# ---- Devices (Goal 1: auto-connect) ----
@app.route("/api/device/discovered", methods=["POST"])
def device_discovered():
    data = request.get_json(silent=True)
    if not data or "mac_address" not in data:
        return jsonify({"error": "mac_address is required"}), 400

    rows = query(
        """
        INSERT INTO device (mac_address, name, ip_address, device_type)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (mac_address)
        DO UPDATE SET ip_address = COALESCE(EXCLUDED.ip_address, device.ip_address)
        RETURNING *;
        """,
        (data["mac_address"], data.get("name"), data.get("ip_address"),
         data.get("device_type")),
        fetch=True,
    )
    device = rows[0]

    outcome = {}
    if device["status"] in ("discovered", "failed"):
        outcome = handle_new_device(device)
        device = get_device(device["device_id"])

    return jsonify({"device_id": device["device_id"], "status": device["status"],
                    "provisioning": outcome}), 201


@app.route("/api/device/<int:device_id>/config")
def device_config(device_id):
    device = get_device(device_id)
    if not device:
        return jsonify({"error": "device not found"}), 404
    template = CONFIG_TEMPLATES.get(device["device_type"], DEFAULT_TEMPLATE)
    config_text = template.format(name=device["name"] or f"device{device_id}")
    return jsonify({"device_id": device_id, "config": config_text})


@app.route("/api/device/<int:device_id>/provisioned", methods=["POST"])
def device_provisioned(device_id):
    """The device (or Member 1's module) reports the result of the auto-connect."""
    data = request.get_json(silent=True) or {}
    if not get_device(device_id):
        return jsonify({"error": "device not found"}), 404
    if data.get("success", True):
        set_device_status(device_id, "active", provisioned=True, config=data.get("config"))
        log_action(device_id, "provision", "auto", result="success",
                   notes="confirmed by device")
    else:
        set_device_status(device_id, "failed")
        log_action(device_id, "provision", "auto", result="fail",
                   notes=data.get("error", "reported failed"))
        send_alert_to_admin(device_id, "Device reported provisioning failure")
    return jsonify({"device_id": device_id, "ok": True})


@app.route("/api/devices")
def list_devices():
    return jsonify(query("SELECT * FROM device ORDER BY device_id;", fetch=True))


# ---- Metrics (performance data for prediction) ----
@app.route("/api/metrics", methods=["POST"])
def receive_metrics():
    d = request.get_json(silent=True)
    if not d or "device_id" not in d:
        return jsonify({"error": "device_id is required"}), 400
    rows = query(
        """
        INSERT INTO traffic_log
            (device_id, bytes_in, bytes_out, packet_loss, latency_ms,
             cpu_usage, memory_usage, temperature)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING log_id;
        """,
        (d["device_id"], d.get("bytes_in"), d.get("bytes_out"), d.get("packet_loss"),
         d.get("latency_ms"), d.get("cpu_usage"), d.get("memory_usage"),
         d.get("temperature")),
        fetch=True,
    )
    return jsonify(rows[0]), 201


@app.route("/api/metrics/<int:device_id>")
def get_metrics(device_id):
    """Recent metrics for one device (Member 2 can use this for prediction)."""
    limit = min(int(request.args.get("limit", 100)), 1000)
    return jsonify(query(
        "SELECT * FROM traffic_log WHERE device_id=%s ORDER BY timestamp DESC LIMIT %s;",
        (device_id, limit), fetch=True))


# ---- Anomalies (Goal 2: auto-correct) ----
@app.route("/api/anomaly", methods=["POST"])
def receive_anomaly():
    d = request.get_json(silent=True)
    if not d or "device_id" not in d or "anomaly_type" not in d:
        return jsonify({"error": "device_id and anomaly_type are required"}), 400

    rows = query(
        """
        INSERT INTO anomaly (device_id, anomaly_type, confidence)
        VALUES (%s, %s, %s)
        RETURNING anomaly_id, device_id, anomaly_type, confidence;
        """,
        (d["device_id"], d["anomaly_type"], d.get("confidence", 0.0)),
        fetch=True,
    )
    outcome = handle_anomaly(rows[0])
    return jsonify({"anomaly_id": rows[0]["anomaly_id"], "result": outcome}), 201


@app.route("/api/anomalies")
def list_anomalies():
    return jsonify(query("SELECT * FROM anomaly ORDER BY detected_at DESC LIMIT 100;",
                         fetch=True))


# ---- Predictions (Goal 3: predict failures) ----
@app.route("/api/prediction", methods=["POST"])
def receive_prediction():
    d = request.get_json(silent=True)
    if not d or "device_id" not in d:
        return jsonify({"error": "device_id is required"}), 400

    rows = query(
        """
        INSERT INTO prediction
            (device_id, predicted_issue, failure_probability,
             estimated_time_to_failure_min)
        VALUES (%s, %s, %s, %s)
        RETURNING prediction_id, device_id, predicted_issue,
                  failure_probability, estimated_time_to_failure_min;
        """,
        (d["device_id"], d.get("predicted_issue", "unknown"),
         d.get("failure_probability", 0.0), d.get("estimated_time_to_failure_min")),
        fetch=True,
    )
    outcome = handle_prediction(rows[0])
    return jsonify({"prediction_id": rows[0]["prediction_id"], "result": outcome}), 201


@app.route("/api/predictions")
def list_predictions():
    return jsonify(query("SELECT * FROM prediction ORDER BY predicted_at DESC LIMIT 100;",
                         fetch=True))


# ---- Actions log + manual override (dashboard) ----
@app.route("/api/actions")
def list_actions():
    return jsonify(query("SELECT * FROM action ORDER BY started_at DESC LIMIT 100;",
                         fetch=True))


@app.route("/api/actions/<int:action_id>/undo", methods=["POST"])
def undo_action(action_id):
    rows = query("SELECT * FROM action WHERE action_id=%s;", (action_id,), fetch=True)
    if not rows:
        return jsonify({"error": "action not found"}), 404
    act = rows[0]

    if act["result"] != "success":
        return jsonify({"error": "only successful actions can be undone"}), 400

    t = act["action_type"]
    device_id = act["device_id"]

    if t == "isolate":
        unisolate_device(device_id)
    elif t in ("reroute", "preventive"):
        print(f"[ACTION] revert reroute for device {device_id}")  # TODO: real revert
    elif t == "provision":
        set_device_status(device_id, "discovered")
    else:
        return jsonify({"error": f"'{t}' actions cannot be undone"}), 400

    finish_action(action_id, "undone", "undone by admin")
    log_action(device_id, "undo", "admin", result="success",
               notes=f"undid action {action_id} ({t})")
    return jsonify({"action_id": action_id, "result": "undone"})


@app.route("/api/block-action", methods=["POST"])
def block_action():
    """Body: {"action_type": "isolate", "device_id": 5}  (device_id optional = all devices)"""
    d = request.get_json(silent=True)
    if not d or "action_type" not in d:
        return jsonify({"error": "action_type is required"}), 400
    BLOCKED_ACTIONS.add((d.get("device_id"), d["action_type"]))
    log_action(d.get("device_id"), d["action_type"], "admin", result="blocked",
               notes="auto-action blocked by admin")
    return jsonify({"blocked": sorted([[str(x), y] for x, y in BLOCKED_ACTIONS])})


@app.route("/api/unblock-action", methods=["POST"])
def unblock_action():
    d = request.get_json(silent=True)
    if not d or "action_type" not in d:
        return jsonify({"error": "action_type is required"}), 400
    BLOCKED_ACTIONS.discard((d.get("device_id"), d["action_type"]))
    return jsonify({"unblocked": True})


@app.route("/api/blocked-actions")
def list_blocked():
    return jsonify([{"device_id": x, "action_type": y} for x, y in BLOCKED_ACTIONS])


# ----------------------------------------------------------------------
# RUN
# ----------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)