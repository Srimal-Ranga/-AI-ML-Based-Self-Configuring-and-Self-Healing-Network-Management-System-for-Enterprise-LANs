import React, { useEffect, useState } from 'react';
import axios from 'axios'; // <-- Import Axios
import './App.css';

function App() {
  const [devices, setDevices] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [actions, setActions] = useState([]);
  const [tab, setTab] = useState('devices');
  
  // State for the AI test
  const [aiResult, setAiResult] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setDevices([
      { id: 1, mac: 'AA:BB:CC:11:22:33', ip: '192.168.1.10', type: 'laptop', status: 'active' },
      { id: 2, mac: 'AA:BB:CC:44:55:66', ip: '192.168.1.11', type: 'iot',    status: 'active' },
      { id: 3, mac: 'AA:BB:CC:77:88:99', ip: '192.168.1.12', type: 'server', status: 'active' },
    ]);
    setAlerts([
      { id: 1, device: 'IoT Device', type: 'Anomaly Detected', confidence: 0.92, time: '10:32:15' },
    ]);
    setActions([
      { id: 1, action: 'isolate_device', target: 'IoT Device', status: 'success', time: '10:32:16', override: false },
    ]);
  }, []);

  const handleOverride = (id) => {
    setActions(actions.map(a =>
      a.id === id ? { ...a, status: 'overridden', override: true } : a
    ));
  };

  // Function to test the AI API
  const testAI = async () => {
    setLoading(true);
    try {
      // Sending a fake IoT traffic signature to the API
      const payload = {
        avg_packet_size: 98, max_packet_size: 98, min_packet_size: 98,
        packet_count: 10, packets_per_second: 10,
        tcp_count: 0, udp_count: 0, icmp_count: 10
      };
      
      const response = await axios.post('http://127.0.0.1:5001/classify', payload);
      setAiResult(response.data);
    } catch (error) {
      console.error("Error connecting to API", error);
      setAiResult({ status: "error", message: "Is the Flask API running?" });
    }
    setLoading(false);
  };

  return (
    <div className="App">
      <header>
        <h1>Enterprise LAN - ZTP Dashboard</h1>
      </header>

      <nav>
        <button onClick={() => setTab('devices')} className={tab==='devices'?'active':''}>Devices</button>
        <button onClick={() => setTab('alerts')}  className={tab==='alerts' ?'active':''}>Alerts</button>
        <button onClick={() => setTab('actions')} className={tab==='actions'?'active':''}>Actions & Override</button>
      </nav>

      {tab === 'devices' && (
        <>
          <div style={{ marginBottom: '20px', padding: '15px', background: '#e0f2fe', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '20px' }}>
            <button onClick={testAI} disabled={loading} style={{ padding: '10px 15px', background: '#0284c7', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold' }}>
              {loading ? 'Testing...' : 'Test AI API (Simulate IoT)'}
            </button>
            
            {aiResult && (
              <div>
                <strong>AI Result:</strong> {aiResult.device_type} (Confidence: {aiResult.confidence})
              </div>
            )}
          </div>

          <table>
            <thead><tr><th>MAC Address</th><th>IP Address</th><th>Device Type (AI)</th><th>Status</th></tr></thead>
            <tbody>
              {devices.map(d => (
                <tr key={d.id}>
                  <td>{d.mac}</td><td>{d.ip}</td>
                  <td><span className={`badge ${d.type}`}>{d.type}</span></td>
                  <td>{d.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {tab === 'alerts' && (
        <table>
          <thead><tr><th>Device</th><th>Alert Type</th><th>Confidence</th><th>Time</th></tr></thead>
          <tbody>
            {alerts.map(a => (
              <tr key={a.id}>
                <td>{a.device}</td><td>{a.type}</td><td>{a.confidence}</td><td>{a.time}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {tab === 'actions' && (
        <table>
          <thead><tr><th>Action</th><th>Target</th><th>Status</th><th>Time</th><th>Manual Override</th></tr></thead>
          <tbody>
            {actions.map(a => (
              <tr key={a.id}>
                <td>{a.action}</td><td>{a.target}</td><td>{a.status}</td><td>{a.time}</td>
                <td>
                  <button onClick={() => handleOverride(a.id)} disabled={a.override} className="override-btn">
                    {a.override ? 'Overridden' : 'Override'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default App;