import React, { useState, useEffect, useRef } from 'react';
import './App.css';

const API_BASE = "http://localhost:8000/api";

export default function App() {
  const [users, setUsers] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [sessionId, setSessionId] = useState("");
  const [activeScreen, setActiveScreen] = useState("login"); // 'login', 'home', 'upi', 'rd', 'mf', 'insurance'
  
  // Real-time states
  const [userProfile, setUserProfile] = useState(null);
  const [logs, setLogs] = useState([]);
  const [activeIntervention, setActiveIntervention] = useState(null);
  const [walkthroughStep, setWalkthroughStep] = useState(-1); // -1: none, 0: intro, 1: amount, 2: tenure, 3: confirm
  const [showEscalationModal, setShowEscalationModal] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");

  // RD Form State
  const [rdAmount, setRdAmount] = useState("");
  const [rdTenure, setRdTenure] = useState("1");
  const [rdAutoRenew, setRdAutoRenew] = useState(true);

  // UPI Form State
  const [upiId, setUpiId] = useState("");
  const [upiAmount, setUpiAmount] = useState("");
  const [upiPin, setUpiPin] = useState("");

  // Refs for tracking dwell times
  const dwellStartRef = useRef(null);
  const currentFeatureRef = useRef("");
  const logStreamEndRef = useRef(null);

  // Fetch users list on mount
  useEffect(() => {
    fetchUsers();
  }, []);

  // Scroll console to bottom when new logs arrive
  useEffect(() => {
    if (logStreamEndRef.current) {
      logStreamEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  // Track screen dwell time on navigation changes
  useEffect(() => {
    // End previous dwell tracking
    if (dwellStartRef.current && currentFeatureRef.current) {
      const dwellDuration = (Date.now() - dwellStartRef.current) / 1000;
      if (dwellDuration > 1) { // Only log if stayed more than 1 second
        logTelemetryEvent(currentFeatureRef.current, "dwell", dwellDuration);
      }
    }

    // Start new dwell tracking
    if (activeScreen !== 'login') {
      let feature = "home";
      if (activeScreen === 'upi') feature = "upi_transfer";
      else if (activeScreen === 'rd') feature = "recurring_deposit";
      else if (activeScreen === 'mf') feature = "mutual_funds";
      else if (activeScreen === 'insurance') feature = "insurance";
      
      currentFeatureRef.current = feature;
      dwellStartRef.current = Date.now();
      
      // Log visit event immediately
      logTelemetryEvent(feature, "visit");
    } else {
      dwellStartRef.current = null;
      currentFeatureRef.current = "";
    }
  }, [activeScreen]);

  const fetchUsers = async () => {
    try {
      const res = await fetch(`${API_BASE}/users`);
      if (res.ok) {
        const data = await res.json();
        setUsers(data);
      } else {
        addConsoleLog("Error fetching user list from backend.", "error");
      }
    } catch (err) {
      addConsoleLog("Could not connect to FastAPI backend. Make sure it is running.", "error");
    }
  };

  const fetchUserProfile = async (accNum) => {
    try {
      const res = await fetch(`${API_BASE}/users/${accNum}`);
      if (res.ok) {
        const data = await res.json();
        setUserProfile(data);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleLogin = (user) => {
    setSelectedUser(user);
    const newSession = Math.random().toString(36).substring(2, 15);
    setSessionId(newSession);
    setLogs([]);
    setActiveScreen("home");
    setWalkthroughStep(-1);
    setActiveIntervention(null);
    setShowEscalationModal(false);
    fetchUserProfile(user.account_number);
    
    // Reset inputs
    setRdAmount("");
    setRdTenure("1");
    setUpiId("");
    setUpiAmount("");
    setUpiPin("");

    addConsoleLog(`Session Started: ${newSession} for Customer ${user.name}`, "system");
    addConsoleLog(`Primary Language: ${user.primary_language.toUpperCase()} | Initial DCS: ${user.current_dcs} (${user.current_dcs_band})`, "system");
  };

  const handleLogout = () => {
    setSelectedUser(null);
    setUserProfile(null);
    setActiveScreen("login");
    setSessionId("");
    setWalkthroughStep(-1);
    setActiveIntervention(null);
    addConsoleLog("Session terminated by user.", "system");
  };

  const addConsoleLog = (message, type = "event") => {
    const time = new Date().toLocaleTimeString();
    setLogs(prev => [...prev, { time, message, type }]);
  };

  // Speaks guides using HTML5 SpeechSynthesis (multilingual simulation)
  const speakVoiceGuide = (text, lang) => {
    if (!('speechSynthesis' in window)) return;
    
    // Stop any ongoing speech
    window.speechSynthesis.cancel();
    
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.85; // Slow and clear instructions
    
    // Attempt to match voice language properties
    const voices = window.speechSynthesis.getVoices();
    let selectedVoice = null;
    
    if (lang === 'hi') {
      selectedVoice = voices.find(v => v.lang.includes('hi') || v.lang.includes('IN'));
    } else if (lang === 'ta') {
      selectedVoice = voices.find(v => v.lang.includes('ta') || v.lang.includes('IN'));
    } else {
      selectedVoice = voices.find(v => v.lang.includes('en-IN') || v.lang.includes('en'));
    }
    
    if (selectedVoice) {
      utterance.voice = selectedVoice;
    }
    
    window.speechSynthesis.speak(utterance);
  };

  // Dispatches telemetry to the backend BFI engine
  const logTelemetryEvent = async (featureName, action, dwellTime = 0, errorOccurred = false, errorMessage = "") => {
    if (!selectedUser) return;
    
    const payload = {
      account_number: selectedUser.account_number,
      session_id: sessionId,
      feature_name: featureName,
      action: action,
      dwell_time: parseFloat(dwellTime),
      error_occurred: errorOccurred,
      error_message: errorMessage || null
    };

    addConsoleLog(`>>> TELEMETRY OUT: [${action.toUpperCase()}] on ${featureName} ${dwellTime ? `(dwell: ${dwellTime.toFixed(1)}s)` : ''} ${errorOccurred ? `[ERROR: ${errorMessage}]` : ''}`, "event");

    try {
      const res = await fetch(`${API_BASE}/telemetry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        const result = await res.json();
        
        // Update user profile metrics dynamically from telemetry response
        setUserProfile(prev => prev ? { ...prev, current_dcs: result.dcs, current_dcs_band: result.current_dcs_band } : null);
        
        addConsoleLog(`<<< ENGINE IN: DCS=${result.dcs} (${result.current_dcs_band}) | Should Intervene=${result.should_intervene} | Mode=${result.mode}`, "engine");
        
        if (result.should_intervene) {
          addConsoleLog(`🔔 BFI Triggered Mode ${result.mode} [${result.gap_type}]: "${result.message}"`, "engine");
          setActiveIntervention(result);
          
          if (result.mode === 2) {
            // Initiate voice walkthrough
            setWalkthroughStep(0); // Intro screen
            speakVoiceGuide(result.message, selectedUser.primary_language);
          }
        } else if (result.mode === 4) {
          // Direct Mode 4 escalation (e.g., Access Gap)
          addConsoleLog(`🚨 Access Blockage Detected. Mode 4 Escalated automatically to Staff Queue!`, "engine");
          setShowEscalationModal(true);
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleInterventionOutcome = async (outcome) => {
    if (!selectedUser || !activeIntervention) return;
    
    const payload = {
      account_number: selectedUser.account_number,
      session_id: sessionId,
      feature_name: activeIntervention.target_feature,
      mode: activeIntervention.mode,
      outcome: outcome
    };

    addConsoleLog(`>>> OUTCOME SUBMIT: [${outcome.toUpperCase()}] for Mode ${activeIntervention.mode} on ${activeIntervention.target_feature}`, "event");

    try {
      const res = await fetch(`${API_BASE}/outcome`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        const result = await res.json();
        addConsoleLog(`<<< OUTCOME OK: New DCS = ${result.new_dcs} (${result.new_dcs_band})`, "engine");
        
        // Refresh local user profile
        fetchUserProfile(selectedUser.account_number);
        
        // Reset walkthrough states
        setActiveIntervention(null);
        setWalkthroughStep(-1);
        if ('speechSynthesis' in window) {
          window.speechSynthesis.cancel();
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

  // Staff escalation confirmation trigger (Mode 4)
  const triggerManualEscalation = () => {
    setShowEscalationModal(true);
    logTelemetryEvent(currentFeatureRef.current, "exit_without_action", 0, true, "User manually requested staff call support.");
  };

  const confirmEscalation = async () => {
    setShowEscalationModal(false);
    addConsoleLog("✅ Support Queue Escalation Confirmed. Callback Ticket Registered.", "system");
    setStatusMessage("Executive callback requested! A representative will call you shortly.");
    setTimeout(() => setStatusMessage(""), 5000);
  };

  // Mode 2 Voice walkthrough steps state management
  const advanceWalkthroughStep = () => {
    const nextStep = walkthroughStep + 1;
    setWalkthroughStep(nextStep);
    
    const lang = selectedUser.primary_language;
    
    if (nextStep === 1) {
      const txt = lang === 'ta' 
        ? "தயவுசெய்து நீங்கள் சேமிக்க விரும்பும் தொகையை உள்ளிடவும், குறைந்தது 500 ரூபாய்." 
        : lang === 'hi' 
        ? "कृपया अपनी बचत राशि दर्ज करें, कम से कम 500 रुपये।" 
        : "Please enter your monthly savings amount, starting from 500 Rupees.";
      speakVoiceGuide(txt, lang);
    } else if (nextStep === 2) {
      const txt = lang === 'ta'
        ? "இப்போது உங்கள் சேமிப்பு காலத்தைத் தேர்ந்தெடுக்கவும். உதாரணத்திற்கு, ஒரு வருடம்."
        : lang === 'hi'
        ? "अब अपनी बचत की अवधि चुनें। उदाहरण के लिए, 1 वर्ष।"
        : "Now choose your deposit tenure. For example, 1 year.";
      speakVoiceGuide(txt, lang);
    } else if (nextStep === 3) {
      const txt = lang === 'ta'
        ? `தொகை ${rdAmount} ரூபாய் என்பதை உறுதிசெய்து, சேமிப்பைத் தொடங்க 'Confirm' பட்டனை அழுத்தவும்.`
        : lang === 'hi'
        ? `कृपया जांचें कि राशि ${rdAmount} रुपये है, और जमा शुरू करने के लिए 'Confirm' दबाएं।`
        : `Verify your monthly savings amount is ${rdAmount} Rupees, and tap 'Confirm' to initiate your deposit.`;
      speakVoiceGuide(txt, lang);
    }
  };

  const handleRDSubmit = (e) => {
    e.preventDefault();
    if (!rdAmount) return;
    
    addConsoleLog(`RD Form Submitted: Amount=${rdAmount}, Tenure=${rdTenure} yrs`, "event");
    
    // Complete the transaction in telemetry
    logTelemetryEvent("recurring_deposit", "attempt");
    logTelemetryEvent("recurring_deposit", "complete");
    
    // Report intervention success if we were guided
    if (activeIntervention && activeIntervention.target_feature === "recurring_deposit") {
      handleInterventionOutcome("completed");
    } else {
      // Just refresh DCS
      fetchUserProfile(selectedUser.account_number);
    }
    
    setStatusMessage(`Recurring Deposit of ₹${rdAmount} setup successfully!`);
    setActiveScreen("home");
    setTimeout(() => setStatusMessage(""), 4000);
  };

  const handleUPISubmit = (e) => {
    e.preventDefault();
    if (!upiId || !upiAmount) return;

    addConsoleLog(`UPI Payment Submitted: To=${upiId}, Amt=${upiAmount}`, "event");
    
    logTelemetryEvent("upi_transfer", "attempt");
    logTelemetryEvent("upi_transfer", "complete");
    
    if (activeIntervention && activeIntervention.target_feature === "upi_transfer") {
      handleInterventionOutcome("completed");
    } else {
      fetchUserProfile(selectedUser.account_number);
    }

    setStatusMessage(`Payment of ₹${upiAmount} to ${upiId} successful!`);
    setActiveScreen("home");
    setTimeout(() => setStatusMessage(""), 4000);
  };

  return (
    <div className="app-container">
      {/* 1. Left Hand Side - Developer / Judge Console Panel */}
      <div className="console-panel">
        <div className="console-header">
          <h1 className="console-title">Saarthi BFI Sandbox</h1>
          <p className="console-subtitle">Interactive Telemetry Injector & Live DCS Viewer</p>
        </div>

        {/* User Selector Dropdown */}
        <div className="profile-selector-box">
          <div className="profile-select-label">Select Target Cohort User Profile:</div>
          <select 
            className="profile-dropdown" 
            value={selectedUser ? selectedUser.account_number : ""} 
            onChange={(e) => {
              const u = users.find(usr => usr.account_number === e.target.value);
              if (u) handleLogin(u);
              else handleLogout();
            }}
          >
            <option value="">-- Choose User Profile to Log In --</option>
            {users.map(u => (
              <option key={u.account_number} value={u.account_number}>
                {u.name} ({u.current_dcs_band} | DCS: {u.current_dcs} | Lang: {u.primary_language.toUpperCase()})
              </option>
            ))}
          </select>
        </div>

        {/* Live DCS Score Gauge */}
        {userProfile && (
          <div className="dcs-panel-box">
            <div className="dcs-gauge-row">
              <div>
                <strong style={{ fontSize: '0.8rem', color: '#a0aec0', textTransform: 'uppercase' }}>Customer Confidence Score</strong>
                <div style={{ color: '#ffffff', fontWeight: 600 }}>{userProfile.name}</div>
                <div style={{ fontSize: '0.8rem', color: '#cbd5e0' }}>Band: <strong>{userProfile.current_dcs_band}</strong></div>
              </div>
              <div className="dcs-gauge-val">{userProfile.current_dcs}</div>
            </div>
            
            <div className="dcs-gauge-bar-outer">
              <div 
                className="dcs-gauge-bar-inner" 
                style={{ 
                  width: `${userProfile.current_dcs}%`,
                  backgroundColor: 
                    userProfile.current_dcs_band === 'Dormant' ? '#ff6b6b' :
                    userProfile.current_dcs_band === 'Cautious' ? '#ecc94b' :
                    userProfile.current_dcs_band === 'Developing' ? '#4299e1' : '#48bb78'
                }}
              ></div>
            </div>

            {/* Components Breakdown */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px', marginTop: '15px', fontSize: '0.75rem', color: '#a0aec0' }}>
              <div>Breadth: <strong style={{ color: '#ffffff' }}>{userProfile.components?.feature_breadth}%</strong></div>
              <div>Completion: <strong style={{ color: '#ffffff' }}>{userProfile.components?.completion_rate}%</strong></div>
              <div>Hesitation: <strong style={{ color: '#ffffff' }}>{userProfile.components?.hesitation_decay}%</strong></div>
              <div>Return Rate: <strong style={{ color: '#ffffff' }}>{userProfile.components?.return_rate}%</strong></div>
            </div>
          </div>
        )}

        {/* Console Telemetry Logs */}
        <div className="log-panel-box">
          <div className="log-title">Live Telemetry & Engine Handshakes</div>
          <div className="log-stream">
            {logs.length === 0 ? (
              <div style={{ color: '#718096', fontStyle: 'italic' }}>Logs will stream here in real time as you tap around the app...</div>
            ) : (
              logs.map((log, i) => (
                <div key={i} className={`log-entry ${log.type}`}>
                  [{log.time}] {log.message}
                </div>
              ))
            )}
            <div ref={logStreamEndRef}></div>
          </div>
        </div>
      </div>

      {/* 2. Right Hand Side - Smartphone Container Mock */}
      <div className="phone-panel">
        {statusMessage && (
          <div style={{
            position: 'absolute',
            top: '30px',
            background: '#48bb78',
            color: 'white',
            padding: '10px 20px',
            borderRadius: '25px',
            fontSize: '0.9rem',
            fontWeight: 'bold',
            zIndex: 1000,
            boxShadow: '0 4px 10px rgba(0,0,0,0.2)'
          }}>
            {statusMessage}
          </div>
        )}

        <div className="smartphone-frame">
          <div className="smartphone-notch"></div>
          
          <div className="smartphone-screen">
            
            {/* Login Overlay Screen inside mobile frame */}
            {activeScreen === "login" && (
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', padding: '25px', backgroundColor: '#0a1530', color: 'white', textAlign: 'center' }}>
                <div className="sbi-circle" style={{ width: '45px', height: '45px', backgroundColor: '#00bfff', marginBottom: '15px' }}></div>
                <h3 style={{ margin: '0 0 5px 0', fontSize: '1.5rem', fontWeight: 700 }}>YONO 2.0</h3>
                <p style={{ margin: '0 0 30px 0', fontSize: '0.8rem', color: '#a0aec0' }}>State Bank of India Digital Gateway</p>
                
                <div style={{ width: '100%', background: 'rgba(255,255,255,0.05)', padding: '15px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.1)' }}>
                  <p style={{ fontSize: '0.85rem', margin: '0 0 10px 0', color: '#e2e8f0' }}>Quick Access Cohort Profiles:</p>
                  {users.slice(0, 5).map(u => (
                    <button 
                      key={u.account_number}
                      onClick={() => handleLogin(u)}
                      style={{
                        width: '100%',
                        padding: '10px',
                        marginBottom: '8px',
                        backgroundColor: '#16254f',
                        color: 'white',
                        border: '1px solid #1f366b',
                        borderRadius: '6px',
                        fontSize: '0.75rem',
                        fontWeight: 'bold',
                        textAlign: 'left',
                        cursor: 'pointer'
                      }}
                    >
                      👤 {u.name} ({u.current_dcs_band})
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* App screens (when logged in) */}
            {activeScreen !== "login" && selectedUser && (
              <>
                {/* Standard YONO Header */}
                <div className="yono-header">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center' }}>
                      <div className="sbi-symbol"></div>
                      <h2 style={{ fontSize: '1.1rem' }}>SBI</h2>
                    </div>
                    <span 
                      onClick={handleLogout}
                      style={{ fontSize: '0.75rem', backgroundColor: 'rgba(255,255,255,0.15)', padding: '4px 8px', borderRadius: '4px', cursor: 'pointer' }}
                    >
                      Logout
                    </span>
                  </div>
                  <p style={{ textAlign: 'left', marginTop: '10px', fontSize: '0.8rem' }}>Welcome, {selectedUser.name}</p>
                </div>

                <div className="yono-screen-content">
                  
                  {/* HOME SCREEN */}
                  {activeScreen === "home" && (
                    <>
                      {/* Check Balance box */}
                      <div className="balance-card">
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: '0.75rem', color: '#718096', fontWeight: 600 }}>Primary Account balance</span>
                          <button 
                            onClick={() => logTelemetryEvent("balance_check", "complete")}
                            style={{ padding: '3px 8px', fontSize: '0.7rem', backgroundColor: '#00529b', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
                          >
                            Show Balance
                          </button>
                        </div>
                        <div className="balance-value">₹ 47,820.50</div>
                        <div style={{ fontSize: '0.65rem', color: '#a0aec0' }}>A/c: {selectedUser.account_number}</div>
                      </div>

                      {/* Banking Grid Actions */}
                      <strong style={{ fontSize: '0.8rem', color: '#4a5568', display: 'block', margin: '10px 0 5px 0' }}>Quick Banking Services</strong>
                      
                      <div className="yono-grid">
                        <div className="yono-card" onClick={() => setActiveScreen("upi")}>
                          <div className="yono-card-icon">💸</div>
                          <div className="yono-card-title">UPI Pay</div>
                          <div className="yono-card-subtitle">Quick Transfers</div>
                        </div>

                        <div className="yono-card" onClick={() => setActiveScreen("rd")}>
                          <div className="yono-card-icon">📈</div>
                          <div className="yono-card-title">Recurring Deposit</div>
                          <div className="yono-card-subtitle">Safe Savings</div>
                        </div>

                        <div className="yono-card" onClick={() => setActiveScreen("mf")}>
                          <div className="yono-card-icon">📊</div>
                          <div className="yono-card-title">Mutual Funds</div>
                          <div className="yono-card-subtitle">Wealth Builder</div>
                        </div>

                        <div className="yono-card" onClick={() => setActiveScreen("insurance")}>
                          <div className="yono-card-icon">🛡️</div>
                          <div className="yono-card-title">Insurance</div>
                          <div className="yono-card-subtitle">Term / Health</div>
                        </div>
                      </div>

                      <button 
                        className="yono-btn-primary" 
                        style={{ marginTop: 'auto', background: '#ff6b6b' }}
                        onClick={triggerManualEscalation}
                      >
                        📞 Request Live Human Support
                      </button>
                    </>
                  )}

                  {/* UPI PAY SCREEN */}
                  {activeScreen === "upi" && (
                    <div>
                      <div className="yono-back-btn" onClick={() => setActiveScreen("home")}>← Back to Home</div>
                      <h3 style={{ margin: '0 0 15px 0', color: '#00529b' }}>UPI Fast Transfer</h3>
                      
                      <form onSubmit={handleUPISubmit}>
                        <div className="yono-input-group">
                          <label className="yono-input-label">Recipient UPI ID</label>
                          <input 
                            type="text" 
                            className="yono-input-field" 
                            placeholder="e.g. name@okhdfcbank" 
                            value={upiId}
                            onChange={(e) => setUpiId(e.target.value)}
                            required
                          />
                        </div>

                        <div className="yono-input-group">
                          <label className="yono-input-label">Transfer Amount (₹)</label>
                          <input 
                            type="number" 
                            className="yono-input-field" 
                            placeholder="Min ₹1" 
                            value={upiAmount}
                            onChange={(e) => setUpiAmount(e.target.value)}
                            required
                          />
                        </div>

                        <div className="yono-input-group">
                          <label className="yono-input-label">Enter 6-Digit UPI PIN</label>
                          <input 
                            type="password" 
                            className="yono-input-field" 
                            placeholder="••••••" 
                            value={upiPin}
                            onChange={(e) => setUpiPin(e.target.value)}
                            maxLength={6}
                            required
                          />
                        </div>

                        <button type="submit" className="yono-btn-primary">Proceed to Pay</button>
                      </form>
                    </div>
                  )}

                  {/* RECURRING DEPOSIT (RD) SCREEN */}
                  {activeScreen === "rd" && (
                    <div>
                      <div className="yono-back-btn" onClick={() => {
                        logTelemetryEvent("recurring_deposit", "exit_without_action", 0);
                        setActiveScreen("home");
                      }}>← Back to Home</div>
                      <h3 style={{ margin: '0 0 15px 0', color: '#00529b' }}>Open Savings Recurring Deposit</h3>
                      
                      <form onSubmit={handleRDSubmit}>
                        <div className="yono-input-group">
                          <label className="yono-input-label">Monthly Deposit Amount (₹)</label>
                          <input 
                            type="number" 
                            className={`yono-input-field ${walkthroughStep === 1 ? 'highlighted' : ''}`}
                            placeholder="Enter amount (min ₹500)" 
                            value={rdAmount}
                            onChange={(e) => {
                              setRdAmount(e.target.value);
                              if (walkthroughStep === 1 && e.target.value >= 500) {
                                advanceWalkthroughStep();
                              }
                            }}
                            required
                          />
                        </div>

                        <div className="yono-input-group">
                          <label className="yono-input-label">Savings Tenure (Years)</label>
                          <select 
                            className={`yono-input-field ${walkthroughStep === 2 ? 'highlighted' : ''}`}
                            value={rdTenure}
                            onChange={(e) => {
                              setRdTenure(e.target.value);
                              if (walkthroughStep === 2) {
                                advanceWalkthroughStep();
                              }
                            }}
                          >
                            <option value="1">1 Year (Interest 6.8%)</option>
                            <option value="3">3 Years (Interest 7.0%)</option>
                            <option value="5">5 Years (Interest 7.2%)</option>
                          </select>
                        </div>

                        <div className="yono-input-group" style={{ display: 'flex', alignItems: 'center', gap: '8px', margin: '15px 0' }}>
                          <input 
                            type="checkbox" 
                            id="auto_renew" 
                            checked={rdAutoRenew}
                            onChange={(e) => setRdAutoRenew(e.target.checked)}
                          />
                          <label htmlFor="auto_renew" style={{ fontSize: '0.8rem', color: '#4a5568', cursor: 'pointer' }}>
                            Auto-renew deposit on maturity
                          </label>
                        </div>

                        <button 
                          type="submit" 
                          className={`yono-btn-primary ${walkthroughStep === 3 ? 'highlighted' : ''}`}
                        >
                          Confirm & Open Deposit
                        </button>
                      </form>
                    </div>
                  )}

                  {/* MUTUAL FUNDS SCREEN */}
                  {activeScreen === "mf" && (
                    <div>
                      <div className="yono-back-btn" onClick={() => setActiveScreen("home")}>← Back to Home</div>
                      <h3 style={{ margin: '0 0 15px 0', color: '#00529b' }}>SBI Mutual Funds</h3>
                      <p style={{ fontSize: '0.75rem', color: '#718096' }}>Invest in top-performing equity and debt funds instantly.</p>
                      
                      <div style={{ background: '#edf2f7', padding: '12px', borderRadius: '8px', marginBottom: '12px' }}>
                        <div style={{ fontSize: '0.75rem', fontWeight: 'bold' }}>SBI Bluechip Fund (Direct-Growth)</div>
                        <div style={{ fontSize: '0.7rem', color: '#48bb78', marginTop: '2px' }}>★ ★ ★ ★ ☆ | 3yr Returns: 14.8%</div>
                      </div>

                      <div style={{ background: '#edf2f7', padding: '12px', borderRadius: '8px', marginBottom: '15px' }}>
                        <div style={{ fontSize: '0.75rem', fontWeight: 'bold' }}>SBI Nifty 50 Index Fund</div>
                        <div style={{ fontSize: '0.7rem', color: '#48bb78', marginTop: '2px' }}>★ ★ ★ ★ ★ | 3yr Returns: 16.2%</div>
                      </div>
                      
                      <button 
                        className="yono-btn-primary" 
                        onClick={() => {
                          logTelemetryEvent("mutual_funds", "attempt");
                          logTelemetryEvent("mutual_funds", "complete");
                          setActiveScreen("home");
                          setStatusMessage("Mutual Fund SIP activated!");
                          setTimeout(() => setStatusMessage(""), 3000);
                        }}
                      >
                        Invest Quick SIP (₹1,000)
                      </button>
                    </div>
                  )}

                  {/* INSURANCE SCREEN */}
                  {activeScreen === "insurance" && (
                    <div>
                      <div className="yono-back-btn" onClick={() => {
                        logTelemetryEvent("insurance", "exit_without_action", 0);
                        setActiveScreen("home");
                      }}>← Back to Home</div>
                      <h3 style={{ margin: '0 0 15px 0', color: '#00529b' }}>Term Life & Health Insurance</h3>
                      
                      <div style={{ padding: '10px', background: 'rgba(255, 107, 107, 0.1)', border: '1px solid #ff6b6b', borderRadius: '8px', marginBottom: '15px', fontSize: '0.75rem', color: '#c53030' }}>
                        ⚠️ PAN details or KYC Verification is required to activate Insurance policies online.
                      </div>

                      <button 
                        className="yono-btn-primary"
                        onClick={() => {
                          logTelemetryEvent("insurance", "attempt", 0, true, "KYC validation failed: PAN check timeout.");
                        }}
                      >
                        Check Eligibility & Verify KYC
                      </button>
                    </div>
                  )}

                </div>

                {/* BFI NUDGE MODAL: Mode 1 (Contextual Card Nudge) */}
                {activeIntervention && activeIntervention.mode === 1 && (
                  <div className="mode-1-overlay">
                    <div className="mode-1-title">
                      <span style={{ marginRight: '6px' }}>💡</span> 
                      {selectedUser.primary_language === 'ta' ? 'உதவிக்குறிப்பு' : selectedUser.primary_language === 'hi' ? 'सुझाव' : 'Contextual Tip'}
                    </div>
                    <p className="mode-1-desc">{activeIntervention.message}</p>
                    <div className="mode-1-actions">
                      <button 
                        className="mode-1-btn-accept" 
                        onClick={() => {
                          handleInterventionOutcome("completed");
                          if (activeIntervention.target_feature === "recurring_deposit") setActiveScreen("rd");
                          else if (activeIntervention.target_feature === "upi_transfer") setActiveScreen("upi");
                          else if (activeIntervention.target_feature === "mutual_funds") setActiveScreen("mf");
                          else if (activeIntervention.target_feature === "insurance") setActiveScreen("insurance");
                        }}
                      >
                        {selectedUser.primary_language === 'ta' ? 'முயற்சி செய்' : selectedUser.primary_language === 'hi' ? 'अभी प्रयास करें' : 'Try Now'}
                      </button>
                      <button 
                        className="mode-1-btn-reject" 
                        onClick={() => handleInterventionOutcome("dismissed")}
                      >
                        {selectedUser.primary_language === 'ta' ? 'தவிர்' : selectedUser.primary_language === 'hi' ? 'खारिज करें' : 'Dismiss'}
                      </button>
                    </div>
                  </div>
                )}

                {/* BFI NUDGE MODAL: Mode 2 (BHASHINI Voice Walkthrough) */}
                {activeIntervention && activeIntervention.mode === 2 && walkthroughStep >= 0 && (
                  <div className="mode-2-overlay">
                    <div className="mode-2-assistant">
                      <div className="mode-2-avatar">💁‍♀️</div>
                      <div>
                        <div className="mode-2-speaking-text">
                          {walkthroughStep === 0 && (selectedUser.primary_language === 'ta' ? 'வழிகாட்டியைத் தொடங்கலாமா?' : selectedUser.primary_language === 'hi' ? 'क्या हम वॉयस गाइड शुरू करें?' : 'Start guided walk through?')}
                          {walkthroughStep === 1 && (selectedUser.primary_language === 'ta' ? 'தொகையை உள்ளிடவும்.' : selectedUser.primary_language === 'hi' ? 'राशि दर्ज करें।' : 'Enter savings amount.')}
                          {walkthroughStep === 2 && (selectedUser.primary_language === 'ta' ? 'காலத்தைத் தேர்ந்தெடுக்கவும்.' : selectedUser.primary_language === 'hi' ? 'बचत की अवधि चुनें।' : 'Select savings tenure.')}
                          {walkthroughStep === 3 && (selectedUser.primary_language === 'ta' ? 'விவரங்களைச் சரிபார்த்து உறுதிப்படுத்தவும்.' : selectedUser.primary_language === 'hi' ? 'विवरण जांचें और पुष्टि करें।' : 'Review and confirm details.')}
                        </div>
                      </div>
                      <div className="voice-waves" style={{ marginLeft: 'auto' }}>
                        <div className="voice-wave"></div>
                        <div className="voice-wave"></div>
                        <div className="voice-wave"></div>
                        <div className="voice-wave"></div>
                      </div>
                    </div>
                    
                    <p className="mode-2-subtitle">
                      {walkthroughStep === 0 && activeIntervention.message}
                      {walkthroughStep === 1 && (selectedUser.primary_language === 'ta' ? 'வழிகாட்டி: தொகை பெட்டியில் குறைந்தபட்சம் 500 ரூபாயை உள்ளிடவும்.' : selectedUser.primary_language === 'hi' ? 'गाइड: राशि बॉक्स में कम से कम 500 रुपये दर्ज करें।' : 'Guide: Enter ₹500 or more in the monthly amount box.')}
                      {walkthroughStep === 2 && (selectedUser.primary_language === 'ta' ? 'வழிகாட்டி: வைப்பு காலத்தைத் தேர்ந்தெடுக்கவும் (1, 3 அல்லது 5 ஆண்டுகள்).' : selectedUser.primary_language === 'hi' ? 'गाइड: जमा अवधि चुनें (1, 3 या 5 वर्ष)।' : 'Guide: Choose your deposit tenure (1, 3, or 5 years).')}
                      {walkthroughStep === 3 && (selectedUser.primary_language === 'ta' ? 'வழிகாட்டி: தொகை சரியாக இருந்தால் Confirm பட்டனை அழுத்தவும்.' : selectedUser.primary_language === 'hi' ? 'गाइड: यदि राशि सही है तो Confirm दबाएं।' : 'Guide: Tap Confirm if the amount looks correct.')}
                    </p>

                    <div className="mode-2-actions">
                      {walkthroughStep === 0 ? (
                        <>
                          <button 
                            className="mode-1-btn-accept" 
                            style={{ backgroundColor: '#ecc94b', color: '#000' }}
                            onClick={advanceWalkthroughStep}
                          >
                            {selectedUser.primary_language === 'ta' ? 'ஆம், வழிகாட்டவும்' : selectedUser.primary_language === 'hi' ? 'हाँ, शुरू करें' : 'Yes, walk me through'}
                          </button>
                          <button 
                            className="mode-2-btn-skip" 
                            onClick={() => handleInterventionOutcome("dismissed")}
                          >
                            {selectedUser.primary_language === 'ta' ? 'இல்லை, பரவாயில்லை' : selectedUser.primary_language === 'hi' ? 'नहीं, धन्यवाद' : 'No thanks'}
                          </button>
                        </>
                      ) : (
                        <>
                          <button className="mode-2-btn-staff" onClick={triggerManualEscalation}>
                            {selectedUser.primary_language === 'ta' ? 'அதிகாரியிடம் பேசவும்' : selectedUser.primary_language === 'hi' ? 'अधिकारी से बात करें' : 'Talk to someone instead'}
                          </button>
                          <button 
                            className="mode-2-btn-skip" 
                            onClick={() => handleInterventionOutcome("dismissed")}
                          >
                            {selectedUser.primary_language === 'ta' ? 'விலகு' : selectedUser.primary_language === 'hi' ? 'छोड़ें' : 'Skip Guide'}
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                )}

                {/* BFI NUDGE MODAL: Mode 4 (Human staff call confirm popup) */}
                {showEscalationModal && (
                  <div style={{
                    position: 'absolute',
                    top: '0', left: '0', right: '0', bottom: '0',
                    backgroundColor: 'rgba(0,0,0,0.8)',
                    zIndex: 2000,
                    display: 'flex',
                    justifyContent: 'center',
                    alignItems: 'center',
                    padding: '20px'
                  }}>
                    <div style={{
                      backgroundColor: 'white',
                      padding: '25px',
                      borderRadius: '15px',
                      textAlign: 'center',
                      borderTop: '5px solid #ff6b6b'
                    }}>
                      <div style={{ fontSize: '2.5rem', marginBottom: '10px' }}>☎️</div>
                      <h4 style={{ margin: '0 0 10px 0', color: '#2d3748', fontSize: '1.1rem' }}>Connect with Support Agent?</h4>
                      <p style={{ fontSize: '0.8rem', color: '#4a5568', margin: '0 0 20px 0' }}>
                        We notice you are facing issues. A digital support agent from SBI can call you directly on your registered phone in Tamil/Hindi/English. Would you like a callback?
                      </p>
                      <div style={{ display: 'flex', gap: '10px' }}>
                        <button 
                          onClick={confirmEscalation}
                          style={{ flex: 1, padding: '10px', background: '#ff6b6b', color: 'white', border: 'none', borderRadius: '6px', fontWeight: 'bold', cursor: 'pointer' }}
                        >
                          Request Callback
                        </button>
                        <button 
                          onClick={() => {
                            setShowEscalationModal(false);
                            addConsoleLog("User rejected Support callback request.", "event");
                          }}
                          style={{ flex: 1, padding: '10px', background: '#edf2f7', color: '#4a5568', border: '1px solid #cbd5e0', borderRadius: '6px', cursor: 'pointer' }}
                        >
                          No, cancel
                        </button>
                      </div>
                    </div>
                  </div>
                )}

              </>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}
