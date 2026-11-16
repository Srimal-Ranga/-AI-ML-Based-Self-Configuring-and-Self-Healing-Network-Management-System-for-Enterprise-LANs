import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import './App.css';

// Backend (Member 3) and classifier (Member 2) addresses.
// To change them without editing code, create a file called .env in the React
// project folder with:  REACT_APP_API_URL=http://192.168.1.205:5000
const API = process.env.REACT_APP_API_URL || 'http://127.0.0.1:5000';
const CLASSIFIER = process.env.REACT_APP_CLASSIFIER_URL || 'http://127.0.0.1:5001';

// Actions the backend can undo (only when they succeeded)
const UNDOABLE = ['isolate', 'reroute', 'preventive', 'provision'];

const fmtTime = (v) => {
  if (!v) return '-';
  const d = new Date(v);
  return isNaN(d.getTime()) ? '-' : d.toLocaleTimeString();
};

const randomMac = () => {
  const byte = () => Math.floor(Math.random() * 256).toString(16).padStart(2, '0').toUpperCase();
  return `AA:BB:CC:${byte()}:${byte()}:${byte()}`;
};

function App() {
  const [devices, setDevices] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [actions, setActions] = useState([]);
  const [summary, setSummary] = useState(null);
  const [tab, setTab] = useState('devices');
  const [backendOk, setBackendOk] = useState(true);

  // Admin login (needed for Override and Approve)
  const [token, setToken] = useState(null);
  const [adminName, setAdminName] = useState('');
  const [user, setUser] = useState('');
  const [pass, setPass] = useState('');
  const [message, setMessage] = useState('');

  // AI classifier test
  const [aiResult, setAiResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      const [d, a, x, s] = await Promise.all([
        axios.get(`${API}/api/devices`),
        axios.get(`${API}/api/alerts`),
        axios.get(`${API}/api/actions`),
        axios.get(`${API}/api/summary`),
      ]);
      const names = {};
      d.data.forEach((dev) => { names[dev.device_id] = dev.name || dev.mac_address; });
      setDevices(d.data.map((dev) => ({
        id: dev.device_id, name: dev.name, mac: dev.mac_address,
        ip: dev.ip_address || '-', type: dev.device_type || 'unknown', status: dev.status,
      })));
      setAlerts(a.data.map((al) => ({
        id: al.action_id, device: names[al.device_id] || `device ${al.device_id}`,
        type: al.notes || 'alert', time: fmtTime(al.started_at),
      })));
      setActions(x.data.map((ac) => ({
        id: ac.action_id, action: ac.action_type, by: ac.triggered_by,
        target: names[ac.device_id] || `device ${ac.device_id}`,
        status: ac.result, time: fmtTime(ac.started_at),
        canUndo: UNDOABLE.includes(ac.action_type) && ac.result === 'success',
      })));
      setSummary(s.data);
      setBackendOk(true);
    } catch (e) {
      console.error('Backend not reachable', e);
      setBackendOk(false);
    }
  }, []);

  // Load now, then refresh every 5 seconds
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  const authConfig = () => ({ headers: { Authorization: `Bearer ${token}` } });

  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      const r = await axios.post(`${API}/api/login`, { username: user, password: pass });
      setToken(r.data.token);
      setAdminName(r.data.username);
      setPass('');
      setMessage('');
    } catch (err) {
      setMessage(err.response?.data?.error || 'Login failed (is the backend running?)');
    }
  };

  const handleLogout = () => { setToken(null); setAdminName(''); };

  const handleOverride = async (id) => {
    if (!token) { setMessage('Log in as admin first to use Override.'); return; }
    try {
      await axios.post(`${API}/api/actions/${id}/undo`, {}, authConfig());
      setMessage('');
      load();
    } catch (err) {
      setMessage(err.response?.data?.error || 'Override failed');
    }
  };

  const handleApprove = async (id) => {
    if (!token) { setMessage('Log in as admin first to approve a device.'); return; }
    try {
      await axios.post(`${API}/api/device/${id}/approve`, {}, authConfig());
      setMessage('');
      load();
    } catch (err) {
      setMessage(err.response?.data?.error || 'Approve failed');
    }
  };

  // Ask the AI classifier, then register the result with the backend (zero-touch flow)
  const testAI = async () => {
    setLoading(true);
    setAiResult(null);
    try {
      // A fake IoT traffic signature
      const payload = {
        avg_packet_size: 98, max_packet_size: 98, min_packet_size: 98,
        packet_count: 10, packets_per_second: 10,
        tcp_count: 0, udp_count: 0, icmp_count: 10,
      };
      const response = await axios.post(`${CLASSIFIER}/classify`, payload);
      const ai = response.data;
      try {
        const reg = await axios.post(`${API}/api/device/discovered`, {
          mac_address: randomMac(), name: 'ai-test',
          device_type: ai.device_type, confidence: ai.confidence,
        });
        setAiResult({ ...ai, backend: reg.data.status });
        load();
      } catch (err) {
        setAiResult({ ...ai, backend: 'backend error' });
      }
    } catch (error) {
      console.error('Error connecting to classifier', error);
      setAiResult({ error: 'Is the classifier API running on port 5001?' });
    }
    setLoading(false);
  };

  return (
    <div className="App">
      <header>
        <h1>Enterprise LAN - ZTP Dashboard</h1>
        <div style={{ fontSize: '14px', marginTop: '6px' }}>
          Backend: {backendOk ? 'connected' : 'NOT reachable'} ({API})
        </div>
      </header>

      {/* Admin login */}
      <div style={{ margin: '10px 0' }}>
        {token ? (
          <span>
            Logged in as <strong>{adminName}</strong>{' '}
            <button onClick={handleLogout}>Log out</button>
          </span>
        ) : (
          <form onSubmit={handleLogin} style={{ display: 'inline-flex', gap: '8px' }}>
            <input placeholder="admin username" value={user} onChange={(e) => setUser(e.target.value)} />
            <input type="password" placeholder="password" value={pass} onChange={(e) => setPass(e.target.value)} />
            <button type="submit">Admin login</button>
          </form>
        )}
        {message && <span style={{ color: '#b91c1c', marginLeft: '12px' }}>{message}</span>}
      </div>

      {/* Summary cards */}
      {summary && (
        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', margin: '10px 0 20px' }}>
          {[
            ['Devices', summary.devices.total],
            ['Waiting for approval', summary.devices.waiting_for_approval],
            ['Alerts (24h)', summary.last_24_hours.alerts],
            ['Anomalies (24h)', summary.last_24_hours.anomalies],
            ['Predictions (24h)', summary.last_24_hours.predictions],
            ['Self-healing success', `${summary.self_healing.success_rate_percent ?? 0}%`],
          ].map(([label, value]) => (
            <div key={label} style={{ padding: '10px 16px', background: '#f1f5f9', borderRadius: '8px', minWidth: '130px' }}>
              <div style={{ fontSize: '12px', color: '#475569' }}>{label}</div>
              <div style={{ fontSize: '22px', fontWeight: 'bold' }}>{value}</div>
            </div>
          ))}
        </div>
      )}

      <nav>
        <button onClick={() => setTab('devices')} className={tab === 'devices' ? 'active' : ''}>Devices</button>
        <button onClick={() => setTab('alerts')} className={tab === 'alerts' ? 'active' : ''}>Alerts</button>
        <button onClick={() => setTab('actions')} className={tab === 'actions' ? 'active' : ''}>Actions & Override</button>
      </nav>

      {tab === 'devices' && (
        <>
          <div style={{ marginBottom: '20px', padding: '15px', background: '#e0f2fe', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '20px' }}>
            <button onClick={testAI} disabled={loading} style={{ padding: '10px 15px', background: '#0284c7', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold' }}>
              {loading ? 'Testing...' : 'Test AI API (Simulate IoT)'}
            </button>
            {aiResult && (
              <div>
                {aiResult.error ? aiResult.error : (
                  <>
                    <strong>AI Result:</strong> {aiResult.device_type} (Confidence: {aiResult.confidence})
                    {' '}→ backend: <strong>{aiResult.backend}</strong>
                  </>
                )}
              </div>
            )}
          </div>

          <table>
            <thead>
              <tr><th>Name</th><th>MAC Address</th><th>IP Address</th><th>Device Type (AI)</th><th>Status</th><th>Approval</th></tr>
            </thead>
            <tbody>
              {devices.map((d) => (
                <tr key={d.id} style={d.status === 'quarantined' ? { background: '#fef3c7' } : undefined}>
                  <td>{d.name || '-'}</td><td>{d.mac}</td><td>{d.ip}</td>
                  <td><span className={`badge ${d.type}`}>{d.type}</span></td>
                  <td>{d.status}</td>
                  <td>
                    {d.status === 'quarantined' && (
                      <button onClick={() => handleApprove(d.id)}>Approve</button>
                    )}
                  </td>
                </tr>
              ))}
              {devices.length === 0 && <tr><td colSpan="6">No devices yet.</td></tr>}
            </tbody>
          </table>
        </>
      )}

      {tab === 'alerts' && (
        <table>
          <thead><tr><th>Device</th><th>Alert</th><th>Time</th></tr></thead>
          <tbody>
            {alerts.map((a) => (
              <tr key={a.id}><td>{a.device}</td><td>{a.type}</td><td>{a.time}</td></tr>
            ))}
            {alerts.length === 0 && <tr><td colSpan="3">No alerts.</td></tr>}
          </tbody>
        </table>
      )}

      {tab === 'actions' && (
        <table>
          <thead><tr><th>Action</th><th>Target</th><th>By</th><th>Status</th><th>Time</th><th>Manual Override</th></tr></thead>
          <tbody>
            {actions.map((a) => (
              <tr key={a.id}>
                <td>{a.action}</td><td>{a.target}</td><td>{a.by}</td><td>{a.status}</td><td>{a.time}</td>
                <td>
                  {a.canUndo && (
                    <button onClick={() => handleOverride(a.id)} className="override-btn">Override</button>
                  )}
                  {a.status === 'undone' && 'Overridden'}
                </td>
              </tr>
            ))}
            {actions.length === 0 && <tr><td colSpan="6">No actions yet.</td></tr>}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default App;