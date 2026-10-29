import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, jsonify

app = Flask(__name__)

def get_conn():
    return psycopg2.connect(
        dbname="selfheal_db",
        user="postgres",
        password="YOUR_PASSWORD",   # the password you set when installing PostgreSQL
        host="localhost",
        port=5432,
    )

@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/api/devices")
def devices():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM device;")
    rows = cur.fetchall()
    conn.close()
    return jsonify(rows)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)