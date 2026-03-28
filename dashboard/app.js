/* ═══════════════════════════════════════════════════════════════
   AXIOM OBSERVE — Frontend Application
   SSE-driven real-time AI Observability Dashboard
   ═══════════════════════════════════════════════════════════════ */

const API_BASE = window.location.protocol === 'file:'
  ? 'http://localhost:8050'
  : window.location.origin;

/* ── Service Topology Definition ── */
const SERVICES = [
  { id: 'gateway',      label: 'API Gateway',   x: 320, y: 50,  depth: 0 },
  { id: 'auth',         label: 'Auth',          x: 140, y: 140, depth: 1 },
  { id: 'catalog',      label: 'Catalog',       x: 320, y: 140, depth: 1 },
  { id: 'order',        label: 'Orders',        x: 500, y: 140, depth: 1 },
  { id: 'payment',      label: 'Payment',       x: 500, y: 260, depth: 2 },
  { id: 'redis',        label: 'Redis',         x: 140, y: 340, depth: 3, isDb: true },
  { id: 'postgres',     label: 'Postgres',      x: 360, y: 380, depth: 3, isDb: true },
];
const EDGES = [
  ['gateway','auth'],['gateway','catalog'],['gateway','order'],
  ['order','payment'],['auth','redis'],['catalog','redis'],
  ['order','postgres'],['payment','postgres'],['catalog','postgres'],
];

/* ── Application State ── */
const state = {
  mode: 'idle', // 'idle' | 'incident'
  currentIncident: null,
  slaStart: null,
  slaTimerInterval: null,
  serviceHealth: {},
  incidentsResolved: 0,
  avgResolution: 0,
  totalResolutionTime: 0,
  rlEpisodes: 0,
  uptimeStart: Date.now(),
  lastEvidence: null,
  recoveryChartInstance: null,
  milestoneLineEl: null,
};

/* ── DOM References ── */
const $ = id => document.getElementById(id);

/* ══════════════════════════════════════════
   HEX MAP RENDERER (SVG)
   ══════════════════════════════════════════ */
function hexPoints(cx, cy, r) {
  const pts = [];
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i - Math.PI / 6;
    pts.push(`${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`);
  }
  return pts.join(' ');
}

function renderHexMap() {
  const svg = $('hex-svg');
  svg.innerHTML = '';
  const ns = 'http://www.w3.org/2000/svg';
  // Defs for filters
  const defs = document.createElementNS(ns, 'defs');
  ['cyan','red','amber','purple','green'].forEach(color => {
    const val = getComputedStyle(document.documentElement).getPropertyValue(`--neon-${color}`).trim();
    const filter = document.createElementNS(ns, 'filter');
    filter.setAttribute('id', `glow-${color}`);
    filter.setAttribute('x', '-50%'); filter.setAttribute('y', '-50%');
    filter.setAttribute('width', '200%'); filter.setAttribute('height', '200%');
    const blur = document.createElementNS(ns, 'feGaussianBlur');
    blur.setAttribute('stdDeviation', '4'); blur.setAttribute('result', 'blur');
    const merge = document.createElementNS(ns, 'feMerge');
    const m1 = document.createElementNS(ns, 'feMergeNode'); m1.setAttribute('in', 'blur');
    const m2 = document.createElementNS(ns, 'feMergeNode'); m2.setAttribute('in', 'SourceGraphic');
    merge.append(m1, m2); filter.append(blur, merge); defs.append(filter);
  });
  svg.append(defs);

  // Draw edges
  EDGES.forEach(([a, b]) => {
    const sa = SERVICES.find(s => s.id === a), sb = SERVICES.find(s => s.id === b);
    const line = document.createElementNS(ns, 'line');
    line.setAttribute('x1', sa.x); line.setAttribute('y1', sa.y);
    line.setAttribute('x2', sb.x); line.setAttribute('y2', sb.y);
    line.setAttribute('stroke', '#1a2535'); line.setAttribute('stroke-width', '1.5');
    line.setAttribute('data-edge', `${a}-${b}`);
    line.classList.add('hex-edge');
    svg.append(line);
  });

  // Draw nodes
  SERVICES.forEach(svc => {
    const g = document.createElementNS(ns, 'g');
    g.classList.add('hex-node'); g.setAttribute('data-service', svc.id);
    // Sonar rings container
    const sonarG = document.createElementNS(ns, 'g');
    sonarG.classList.add('sonar-container'); sonarG.setAttribute('data-sonar', svc.id);
    g.append(sonarG);
    // Hex shape
    const poly = document.createElementNS(ns, 'polygon');
    poly.setAttribute('points', hexPoints(svc.x, svc.y, 34));
    poly.setAttribute('fill', 'rgba(12,16,24,0.9)');
    poly.setAttribute('stroke', '#00f5ff'); poly.setAttribute('stroke-width', '1.5');
    poly.setAttribute('filter', 'url(#glow-cyan)');
    poly.classList.add('hex-shape');
    g.append(poly);
    // Pulse animation (idle healthy)
    poly.style.animation = 'hexPulse 3s ease-in-out infinite';
    // Label
    const text = document.createElementNS(ns, 'text');
    text.setAttribute('x', svc.x); text.setAttribute('y', svc.y - 2);
    text.setAttribute('text-anchor', 'middle'); text.setAttribute('fill', '#e2eeff');
    text.setAttribute('font-family', "'Space Grotesk',sans-serif");
    text.setAttribute('font-size', '10'); text.setAttribute('font-weight', '500');
    text.textContent = svc.label;
    g.append(text);
    // Severity label
    const sevText = document.createElementNS(ns, 'text');
    sevText.setAttribute('x', svc.x); sevText.setAttribute('y', svc.y + 16);
    sevText.setAttribute('text-anchor', 'middle'); sevText.setAttribute('fill', '#6b7fa3');
    sevText.setAttribute('font-family', "'JetBrains Mono',monospace");
    sevText.setAttribute('font-size', '10');
    sevText.classList.add('hex-severity');
    sevText.textContent = '0.00';
    g.append(sevText);
    svg.append(g);
  });

  // Inject hex pulse keyframes
  if (!document.querySelector('#hex-pulse-style')) {
    const style = document.createElement('style'); style.id = 'hex-pulse-style';
    style.textContent = `
      @keyframes hexPulse { 0%,100%{stroke-opacity:0.7} 50%{stroke-opacity:1} }
      @keyframes hexCritical { 0%,100%{stroke-opacity:0.6;stroke-width:1.5px} 50%{stroke-opacity:1;stroke-width:2.5px} }
    `;
    document.head.append(style);
  }
}

function updateHexNode(serviceId, severity) {
  const svg = $('hex-svg');
  const node = svg.querySelector(`[data-service="${serviceId}"]`);
  if (!node) return;
  const poly = node.querySelector('.hex-shape');
  const sevText = node.querySelector('.hex-severity');
  if (sevText) sevText.textContent = severity.toFixed(2);

  const ns = 'http://www.w3.org/2000/svg';
  const sonarG = svg.querySelector(`[data-sonar="${serviceId}"]`);

  if (severity >= 0.7) {
    poly.setAttribute('stroke', '#ff2d55');
    poly.setAttribute('filter', 'url(#glow-red)');
    poly.style.animation = 'hexCritical 0.8s ease-in-out infinite';
    if (sevText) sevText.setAttribute('fill', '#ff2d55');
    // Sonar rings
    if (sonarG && sonarG.childElementCount === 0) {
      for (let i = 0; i < 3; i++) {
        const circ = document.createElementNS(ns, 'circle');
        const svc = SERVICES.find(s => s.id === serviceId);
        circ.setAttribute('cx', svc.x); circ.setAttribute('cy', svc.y);
        circ.setAttribute('r', '32'); circ.setAttribute('fill', 'none');
        circ.setAttribute('stroke', '#ff2d55'); circ.setAttribute('stroke-width', '1');
        circ.style.animation = `sonarRing 1.5s ${i * 0.5}s ease-out infinite`;
        sonarG.append(circ);
      }
    }
    // Animate edges red
    EDGES.forEach(([a, b]) => {
      if (a === serviceId || b === serviceId) {
        const edge = svg.querySelector(`[data-edge="${a}-${b}"]`);
        if (edge) { edge.setAttribute('stroke', '#ff2d55'); edge.setAttribute('stroke-width', '2'); }
      }
    });
  } else if (severity >= 0.3) {
    poly.setAttribute('stroke', '#ffb300');
    poly.setAttribute('filter', 'url(#glow-amber)');
    poly.style.animation = 'hexPulse 1.5s ease-in-out infinite';
    if (sevText) sevText.setAttribute('fill', '#ffb300');
    if (sonarG) sonarG.innerHTML = '';
  } else {
    poly.setAttribute('stroke', '#00f5ff');
    poly.setAttribute('filter', 'url(#glow-cyan)');
    poly.style.animation = 'hexPulse 3s ease-in-out infinite';
    if (sevText) sevText.setAttribute('fill', '#6b7fa3');
    if (sonarG) sonarG.innerHTML = '';
    EDGES.forEach(([a, b]) => {
      if (a === serviceId || b === serviceId) {
        const edge = svg.querySelector(`[data-edge="${a}-${b}"]`);
        if (edge) { edge.setAttribute('stroke', '#1a2535'); edge.setAttribute('stroke-width', '1.5'); }
      }
    });
  }
}

/* ══════════════════════════════════════════
   INCIDENT MODE TRANSITIONS
   ══════════════════════════════════════════ */
function enterIncidentMode(incidentId) {
  if (state.mode === 'incident') return;
  state.mode = 'incident';
  state.currentIncident = incidentId;
  state.slaStart = Date.now();

  // Screen flash red
  const flash = $('screen-flash');
  flash.classList.add('flash-red');
  setTimeout(() => flash.classList.remove('flash-red'), 250);

  // Glitch
  setTimeout(() => {
    document.body.classList.add('glitch-active');
    setTimeout(() => document.body.classList.remove('glitch-active'), 150);
  }, 150);

  // Alert banner
  setTimeout(() => {
    const banner = $('alert-banner');
    $('alert-banner-text').textContent = '⚠  INCIDENT DETECTED — AUTONOMOUS REMEDIATION INITIATING';
    banner.classList.remove('resolved');
    banner.classList.add('visible');
  }, 300);

  // Layout morph
  setTimeout(() => {
    $('hero-grid').classList.add('incident-mode');
    // Dim non-essential panels
    $('panel-evidence').classList.add('dimmed');
    // Glow timeline
    $('panel-timeline').classList.add('glow-red');
  }, 600);

  // SLA timer with pop-in
  setTimeout(() => {
    const slaCont = $('sla-timer-container');
    slaCont.classList.remove('hidden');
    slaCont.classList.add('pop-in');
    $('sla-timer').className = 'sla-timer'; // reset color classes
    startSLATimer();
  }, 600);

  // Disable demo button
  const demoBtn = $('demo-btn');
  if (demoBtn) demoBtn.classList.add('running');

  // Header status
  $('system-status-dot').classList.add('critical');
  $('system-status-text').textContent = `INCIDENT ${incidentId.toUpperCase()}`;
  $('system-status-text').style.color = '#ff2d55';

  // Timeline panel
  $('timeline-idle').classList.add('hidden');
  $('timeline-active').classList.remove('hidden');
  $('timeline-badge').textContent = 'ACTIVE';
  $('timeline-badge').classList.add('active');
  $('milestone-list').innerHTML = '';
  state.milestoneLineEl = null; // reset line for new incident

  // Ticker
  $('tick-incidents').textContent = '1';
}

function exitIncidentMode(totalTime) {
  state.mode = 'idle';
  stopSLATimer();

  // Screen flash green
  const flash = $('screen-flash');
  flash.classList.add('flash-green');
  setTimeout(() => flash.classList.remove('flash-green'), 250);

  // SLA timer freeze green
  const timer = $('sla-timer');
  timer.classList.remove('warning', 'breach');
  timer.classList.add('met');
  timer.textContent = formatSLATime(totalTime);

  // Banner resolved
  const banner = $('alert-banner');
  $('alert-banner-text').textContent = '✓ INCIDENT RESOLVED — AUTONOMOUS REMEDIATION SUCCESSFUL';
  banner.classList.add('resolved');
  setTimeout(() => banner.classList.remove('visible'), 4000);

  // Layout revert
  setTimeout(() => {
    $('hero-grid').classList.remove('incident-mode');
    $('panel-evidence').classList.remove('dimmed');
    $('panel-timeline').classList.remove('glow-red');
    $('sla-timer-container').classList.add('hidden');
    $('sla-timer-container').classList.remove('pop-in');
    // Re-enable demo button
    const demoBtn = $('demo-btn');
    if (demoBtn) demoBtn.classList.remove('running');
  }, 3000);

  // Header
  $('system-status-dot').classList.remove('critical');
  $('system-status-text').textContent = 'ALL SYSTEMS OPERATIONAL';
  $('system-status-text').style.color = '';

  // Stats
  state.incidentsResolved++;
  state.totalResolutionTime += totalTime;
  state.avgResolution = state.totalResolutionTime / state.incidentsResolved;
  $('incidents-resolved-count').textContent = state.incidentsResolved;
  $('avg-resolution').textContent = state.avgResolution.toFixed(1) + 's';
  $('tick-incidents').textContent = '0';

  // Timeline
  $('timeline-badge').textContent = 'RESOLVED';
  $('timeline-badge').classList.remove('active');

  // Update milestone line color
  if (state.milestoneLineEl) state.milestoneLineEl.classList.add('resolved');
}

/* ── SLA Timer ── */
function startSLATimer() {
  const timer = $('sla-timer');
  state.slaTimerInterval = setInterval(() => {
    const elapsed = (Date.now() - state.slaStart) / 1000;
    timer.textContent = formatSLATime(elapsed);
    timer.classList.remove('warning', 'breach');
    if (elapsed > 15) timer.classList.add('breach');
    else if (elapsed > 12) timer.classList.add('warning');
  }, 10);
}
function stopSLATimer() { clearInterval(state.slaTimerInterval); }
function formatSLATime(s) {
  const mins = Math.floor(s / 60).toString().padStart(2, '0');
  const secs = Math.floor(s % 60).toString().padStart(2, '0');
  const cs = Math.floor((s % 1) * 100).toString().padStart(2, '0');
  return `${mins}:${secs}.${cs}`;
}

/* ══════════════════════════════════════════
   MILESTONE RENDERER
   ══════════════════════════════════════════ */
function addMilestone(time, title, details, dotClass = 'filled') {
  const list = $('milestone-list');
  // Update or create the vertical line
  if (!state.milestoneLineEl) {
    const line = document.createElement('div');
    line.className = 'milestone-line';
    line.style.height = '0px';
    list.append(line);
    state.milestoneLineEl = line;
  }

  const ms = document.createElement('div');
  ms.className = 'milestone';
  ms.innerHTML = `
    <div class="milestone-dot ${dotClass}"></div>
    <div class="milestone-time">T+${time.toFixed(2)}s</div>
    <div class="milestone-title">${title}</div>
    <div class="milestone-detail">${details}</div>
  `;
  list.append(ms);

  // Auto-scroll timeline to show latest milestone
  const panelBody = $('timeline-body');
  if (panelBody) {
    requestAnimationFrame(() => panelBody.scrollTop = panelBody.scrollHeight);
  }

  // Extend line
  requestAnimationFrame(() => {
    const allMs = list.querySelectorAll('.milestone');
    if (allMs.length > 1) {
      const first = allMs[0].getBoundingClientRect();
      const last = allMs[allMs.length - 1].getBoundingClientRect();
      state.milestoneLineEl.style.height = (last.top - first.top) + 'px';
    }
  });
}

/* ══════════════════════════════════════════
   RL WIDGET UPDATE
   ══════════════════════════════════════════ */
function updateRLWidget(data) {
  // State vector
  if (data.state) {
    const cells = $('rl-state-cells').children;
    data.state.forEach((v, i) => {
      if (cells[i]) {
        cells[i].textContent = v;
        cells[i].className = 'state-cell ' + (v === 2 ? 'critical' : v === 1 ? 'degraded' : 'healthy');
      }
    });
  }
  // Q-values
  if (data.q_values) {
    const actions = ['restart', 'scale_up', 'force_kill', 'scale_down'];
    const qVals = Object.values(data.q_values);
    const maxQ = Math.max(...qVals.map(Math.abs), 0.01);
    actions.forEach(action => {
      const qVal = data.q_values[action] ?? data.q_values[action.replace('_', '')] ?? 0;
      const row = $(`q-${action}`);
      if (!row) return;
      const fill = row.querySelector('.q-bar-fill');
      const valEl = row.querySelector('.q-val');
      const pct = Math.max(0, ((qVal + maxQ) / (2 * maxQ)) * 100);
      fill.style.width = pct + '%';
      fill.classList.toggle('chosen', data.chosen_action === action);
      valEl.textContent = qVal.toFixed(2);
    });
  }
  if (data.chosen_action) {
    $('rl-status-badge').textContent = '◉ ACTIVE';
    $('rl-status-badge').style.animation = 'pulse-dot 0.8s infinite';
  }
}

/* ══════════════════════════════════════════
   EVIDENCE PANEL
   ══════════════════════════════════════════ */
function updateEvidence(data) {
  $('evidence-empty').classList.add('hidden');
  $('evidence-content').classList.remove('hidden');
  $('panel-evidence').classList.remove('dimmed');
  $('evidence-label').textContent = `ROOT CAUSE: ${(data.confidence * 100).toFixed(0)}%`;
  $('evidence-label').classList.remove('dim');
  $('evidence-label').style.color = '#ff2d55';

  // Candidates
  const cEl = $('evidence-candidates');
  cEl.innerHTML = '<div class="evidence-section-label">CANDIDATES</div>';
  (data.candidates || []).forEach((c, i) => {
    cEl.innerHTML += `<div class="candidate-bar">
      <span class="candidate-name">${c.service}</span>
      <div class="candidate-track"><div class="candidate-fill ${i === 0 ? 'root' : ''}" style="width:${c.probability * 100}%"></div></div>
      <span class="candidate-pct">${(c.probability * 100).toFixed(0)}%</span>
    </div>`;
  });

  // Traces
  const tEl = $('evidence-traces');
  tEl.innerHTML = '<div class="evidence-section-label">TRACES</div>';
  (data.traces || []).forEach(t => { tEl.innerHTML += `<div class="evidence-item">◉ ${t}</div>`; });

  // Metrics
  const mEl = $('evidence-metrics');
  mEl.innerHTML = '<div class="evidence-section-label">METRICS</div>';
  (data.metrics || []).forEach(m => { mEl.innerHTML += `<div class="evidence-item">${m}</div>`; });

  // Logs
  const lEl = $('evidence-logs');
  lEl.innerHTML = '<div class="evidence-section-label">LOGS</div>';
  (data.logs || []).forEach(l => { lEl.innerHTML += `<div class="evidence-item error">[ERR] ${l}</div>`; });
}

/* ══════════════════════════════════════════
   RECOVERY CHART (Chart.js)
   ══════════════════════════════════════════ */
function renderRecoveryChart(chartData) {
  if (state.recoveryChartInstance) state.recoveryChartInstance.destroy();
  const ctx = $('recovery-chart').getContext('2d');
  $('chart-label').textContent = chartData.service || 'RECOVERY';
  $('chart-label').classList.remove('dim');

  state.recoveryChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: chartData.labels || [],
      datasets: [{
        label: 'p95 latency (ms)',
        data: chartData.values || [],
        borderColor: '#00f5ff',
        backgroundColor: 'rgba(255,45,85,0.08)',
        fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: { duration: 1200, easing: 'easeInOutQuart' },
      scales: {
        x: { grid: { color: 'rgba(0,245,255,0.04)' }, ticks: { color: '#3a4a63', font: { family: "'JetBrains Mono'", size: 10 } } },
        y: { grid: { color: 'rgba(0,245,255,0.04)' }, ticks: { color: '#3a4a63', font: { family: "'JetBrains Mono'", size: 10 } } },
      },
      plugins: { legend: { display: false } },
    },
  });
}

/* ══════════════════════════════════════════
   SSE CONNECTIONS
   ══════════════════════════════════════════ */
function connectSSE() {
  // Health stream
  const healthSSE = new EventSource(`${API_BASE}/stream/health`);
  healthSSE.onmessage = e => {
    try {
      const data = JSON.parse(e.data);
      if (data.services) {
        let online = 0;
        Object.entries(data.services).forEach(([svc, info]) => {
          state.serviceHealth[svc] = info.severity || 0;
          updateHexNode(svc, info.severity || 0);
          if ((info.severity || 0) < 0.7) online++;
        });
        $('tick-services').textContent = `${online}/${Object.keys(data.services).length}`;
      }
      if (data.request_rate != null) $('tick-rps').textContent = data.request_rate.toFixed(0);
      if (data.error_rate != null) $('tick-err').textContent = (data.error_rate * 100).toFixed(2) + '%';
    } catch (err) { console.warn('Health SSE parse error:', err); }
  };
  healthSSE.onerror = () => setTimeout(() => connectSSE(), 3000);

  // Incidents stream
  const incSSE = new EventSource(`${API_BASE}/stream/incidents`);
  incSSE.onmessage = e => {
    try {
      const evt = JSON.parse(e.data);
      handleIncidentEvent(evt);
    } catch (err) { console.warn('Incident SSE parse error:', err); }
  };

  // RL stream
  const rlSSE = new EventSource(`${API_BASE}/stream/rl`);
  rlSSE.onmessage = e => {
    try {
      const data = JSON.parse(e.data);
      handleRLEvent(data);
    } catch (err) { console.warn('RL SSE parse error:', err); }
  };
}

/* ── Event Handlers ── */
function handleIncidentEvent(evt) {
  const t = evt.timestamp_relative || 0;
  const d = evt.data || {};

  switch (evt.type) {
    case 'ANOMALY_DETECTED':
      enterIncidentMode(evt.incident_id);
      addMilestone(t, 'ANOMALY DETECTED',
        (d.anomalies || []).map(a =>
          `${a.service} <span class="severity-bar" style="width:${a.severity*60}px"></span> ${a.severity.toFixed(2)} ${a.severity>=0.7?'CRITICAL':'DEGRADED'}`
        ).join('<br>'), 'filled');
      break;

    case 'ROOT_CAUSE_IDENTIFIED':
      addMilestone(t, 'ROOT CAUSE IDENTIFIED',
        `${d.root_cause} (confidence: ${(d.confidence*100).toFixed(0)}%)` +
        (d.evidence ? '<br>↳ ' + (d.evidence.traces||[]).join('<br>↳ ') : ''), 'filled');
      if (d.evidence) updateEvidence({ confidence: d.confidence, candidates: d.candidates, ...d.evidence });
      break;

    case 'DECISION_MADE':
      addMilestone(t, 'DECISION MADE',
        `RL AGENT → ${d.action}  Q=${(d.q_value||0).toFixed(2)}  [${d.confidence || 'HIGH'}]` +
        `<br>decision_latency: ${d.decision_latency_ms || 0}ms`, 'blue');
      break;

    case 'ACTION_FIRED':
      addMilestone(t, 'ACTION FIRED',
        `${d.action}<br>api_latency: ${d.api_latency_ms || 0}ms`, 'blue');
      break;

    case 'PROVISIONALLY_RECOVERED':
      addMilestone(t, 'PROVISIONALLY RECOVERED',
        `container status: ${d.container_status || 'running'}`, 'amber');
      break;

    case 'CONFIRMED_RECOVERED': {
      const totalTime = t || ((Date.now() - state.slaStart) / 1000);
      const slaText = totalTime <= 15 ? '✓ SLA MET' : '✗ SLA BREACH';
      addMilestone(t, `CONFIRMED RECOVERED  ${slaText}`,
        `${d.error_rate || '—'}  p95: ${d.p95_latency || '—'}`, 'green');
      exitIncidentMode(totalTime);
      if (d.chart_data) renderRecoveryChart(d.chart_data);
      break;
    }

    case 'DECISION_BLOCKED':
      addMilestone(t, 'DECISION BLOCKED', `reason: ${d.reason || 'safety gate'}`, 'red');
      break;

    case 'REMEDIATION_INEFFECTIVE':
      addMilestone(t, 'REMEDIATION INEFFECTIVE', `${d.failure_reason || ''}`, 'red');
      exitIncidentMode(t || 15);
      break;

    default:
      console.log('Unknown incident event:', evt.type, evt);
  }
}

function handleRLEvent(evt) {
  const d = evt.data || evt;
  updateRLWidget(d);
  if (d.reward != null) {
    $('rl-reward').textContent = (d.reward >= 0 ? '+' : '') + d.reward.toFixed(2);
    $('rl-reward').style.color = d.reward >= 0 ? '#00ff88' : '#ff2d55';
  }
  if (d.live_episodes != null) {
    state.rlEpisodes = d.live_episodes;
    $('rl-live').textContent = d.live_episodes;
    $('tick-episodes').textContent = d.live_episodes;
  }
  if (d.q_table_size != null) $('rl-qtable-size').textContent = `Q-table: ${d.q_table_size} cells`;
}

/* ── Uptime ticker ── */
function updateUptime() {
  const s = Math.floor((Date.now() - state.uptimeStart) / 1000);
  const h = Math.floor(s / 3600).toString().padStart(2, '0');
  const m = Math.floor((s % 3600) / 60).toString().padStart(2, '0');
  const sec = (s % 60).toString().padStart(2, '0');
  $('tick-uptime').textContent = `${h}:${m}:${sec}`;
}

/* ══════════════════════════════════════════
   DEMO SIMULATION (for testing without backend)
   ══════════════════════════════════════════ */
function runDemoSimulation() {
  if (state.mode === 'incident') return; // prevent double-trigger
  console.log('%c[AXIOM] Running demo simulation...', 'color:#00f5ff;font-weight:bold');
  
  // Disable button immediately
  const btn = $('demo-btn');
  if (btn) btn.classList.add('running');

  // Initialize all services healthy
  SERVICES.forEach(s => updateHexNode(s.id, 0.05 + Math.random() * 0.15));
  $('tick-rps').textContent = '847';
  $('tick-err').textContent = '0.02%';
  $('tick-services').textContent = '7/7';
  $('tick-episodes').textContent = '2003';

  setTimeout(() => {
    handleIncidentEvent({
      type: 'ANOMALY_DETECTED', incident_id: 'inc-1042', timestamp_relative: 6.0,
      data: { anomalies: [
        { service: 'payment', severity: 0.91 },
        { service: 'order', severity: 0.61 },
      ]}
    });
    updateHexNode('payment', 0.91);
    updateHexNode('order', 0.61);
  }, 2000);

  setTimeout(() => {
    handleIncidentEvent({
      type: 'ROOT_CAUSE_IDENTIFIED', incident_id: 'inc-1042', timestamp_relative: 9.0,
      data: {
        root_cause: 'payment', confidence: 0.84,
        candidates: [
          { service: 'payment', probability: 0.84 },
          { service: 'postgres', probability: 0.47 },
          { service: 'order', probability: 0.30 },
        ],
        evidence: {
          traces: ['span payment: 1.9s vs 500ms baseline'],
          metrics: ['p95 latency 3.8× baseline', 'error rate 12% > 5%'],
          logs: ['DB connection timeout to postgres', 'retry exhausted for /charge'],
        }
      }
    });
  }, 5000);

  setTimeout(() => {
    handleIncidentEvent({
      type: 'DECISION_MADE', incident_id: 'inc-1042', timestamp_relative: 9.03,
      data: { action: 'restart', service: 'payment', q_value: 1.23, confidence: 'HIGH', decision_latency_ms: 28 }
    });
    handleRLEvent({ data: {
      state: [0,0,1,0,2,1], chosen_action: 'restart',
      q_values: { restart: 1.23, scale_up: 0.84, force_kill: 0.61, scale_down: -0.12 },
    }});
  }, 6000);

  setTimeout(() => {
    handleIncidentEvent({
      type: 'ACTION_FIRED', incident_id: 'inc-1042', timestamp_relative: 9.43,
      data: { action: 'docker restart payment', api_latency_ms: 250 }
    });
  }, 7000);

  setTimeout(() => {
    handleIncidentEvent({
      type: 'PROVISIONALLY_RECOVERED', incident_id: 'inc-1042', timestamp_relative: 11.03,
      data: { container_status: 'running' }
    });
    updateHexNode('payment', 0.45);
  }, 9000);

  setTimeout(() => {
    handleIncidentEvent({
      type: 'CONFIRMED_RECOVERED', incident_id: 'inc-1042', timestamp_relative: 13.03,
      data: { error_rate: '0.8%', p95_latency: '312ms',
        chart_data: {
          service: 'payment',
          labels: ['T-10','T-8','T-6','T-4','T-2','T+0','T+2','T+4','T+6','T+8','T+10','T+12','T+14'],
          values: [320,310,340,1800,1950,2000,1900,800,400,350,320,315,312],
        }
      }
    });
    updateHexNode('payment', 0.08);
    updateHexNode('order', 0.12);
    handleRLEvent({ data: {
      reward: 1.84, live_episodes: 4, q_table_size: 2916,
      state: [0,0,0,0,0,0],
      q_values: { restart: 1.31, scale_up: 0.84, force_kill: 0.61, scale_down: -0.12 },
      chosen_action: 'restart',
    }});
  }, 12000);
}

/* ══════════════════════════════════════════
   INIT
   ══════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  renderHexMap();
  setInterval(updateUptime, 1000);

  // Try SSE connection (will silently fail if server not running)
  try {
    connectSSE();
  } catch (e) {
    console.warn('SSE connection failed — use RUN DEMO button');
  }

  // URL param ?demo=1 also triggers simulation
  if (new URLSearchParams(window.location.search).has('demo')) {
    setTimeout(() => runDemoSimulation(), 500);
  }
});
