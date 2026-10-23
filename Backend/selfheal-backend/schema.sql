-- schema.sql : Self-Healing Network project database

CREATE TABLE device (
    device_id SERIAL PRIMARY KEY,
    mac_address VARCHAR(17) UNIQUE NOT NULL,
    name VARCHAR(100),
    ip_address VARCHAR(45),
    device_type VARCHAR(30),
    status VARCHAR(20) DEFAULT 'discovered',
    first_seen TIMESTAMP DEFAULT NOW(),
    provisioned_at TIMESTAMP,
    config_applied TEXT
);

CREATE TABLE traffic_log (
    log_id SERIAL PRIMARY KEY,
    device_id INT REFERENCES device(device_id),
    timestamp TIMESTAMP DEFAULT NOW(),
    bytes_in BIGINT,
    bytes_out BIGINT,
    packet_loss FLOAT,
    latency_ms FLOAT,
    cpu_usage FLOAT,
    memory_usage FLOAT,
    temperature FLOAT
);

CREATE TABLE anomaly (
    anomaly_id SERIAL PRIMARY KEY,
    device_id INT REFERENCES device(device_id),
    detected_at TIMESTAMP DEFAULT NOW(),
    anomaly_type VARCHAR(50),
    confidence FLOAT,
    status VARCHAR(20) DEFAULT 'new'
);

CREATE TABLE prediction (
    prediction_id SERIAL PRIMARY KEY,
    device_id INT REFERENCES device(device_id),
    predicted_at TIMESTAMP DEFAULT NOW(),
    predicted_issue VARCHAR(50),
    failure_probability FLOAT,
    estimated_time_to_failure_min INT,
    handled BOOLEAN DEFAULT FALSE
);

CREATE TABLE action (
    action_id SERIAL PRIMARY KEY,
    device_id INT REFERENCES device(device_id),
    anomaly_id INT REFERENCES anomaly(anomaly_id),
    prediction_id INT REFERENCES prediction(prediction_id),
    action_type VARCHAR(30),
    triggered_by VARCHAR(20),
    started_at TIMESTAMP DEFAULT NOW(),
    finished_at TIMESTAMP,
    result VARCHAR(20),
    notes TEXT
);

CREATE TABLE admin_user (
    admin_id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(20) DEFAULT 'admin'
);