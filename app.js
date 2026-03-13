const BASE_URL = 'http://localhost:8000';
const apiFetch = async (path, options = {}) => {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  if (response.status === 204) return null;
  return response.json();
};
const ui = {
  loginForm: document.getElementById('login-form'),
  loginStatus: document.getElementById('login-status'),
  start: document.getElementById('start-sim'),
  stop: document.getElementById('stop-sim'),
  grid: document.getElementById('device-grid'),
  stats: {
    total: document.getElementById('stat-count'),
    active: document.getElementById('stat-active'),
    errors: document.getElementById('stat-errors')
  }
};
let simState = { running: false, devices: [], stats: { total:0, active:0, errors:0 }, organisations: [], timeouts: [], createdCases: [] };
let isAuthenticated = false;
const clusters = [
  { latitude: 51.5074, longitude: -0.1278, name: 'London' },
  { latitude: 53.4808, longitude: -2.2426, name: 'Manchester' },
  { latitude: 52.4862, longitude: -1.8904, name: 'Birmingham' },
  { latitude: 55.9533, longitude: -3.1883, name: 'Edinburgh' },
  { latitude: 53.3498, longitude: -6.2603, name: 'Dublin' },
  { latitude: 51.4545, longitude: -2.5879, name: 'Bristol' },
  { latitude: 51.4816, longitude: -3.1791, name: 'Cardiff' },
  { latitude: 53.4084, longitude: -2.9916, name: 'Liverpool' },
  { latitude: 52.9225, longitude: -1.4767, name: 'Nottingham' },
  { latitude: 50.8225, longitude: -0.1372, name: 'Brighton' },
  { latitude: 55.8642, longitude: -4.2518, name: 'Glasgow' },
  { latitude: 54.5973, longitude: -5.9301, name: 'Belfast' },
  { latitude: 51.7520, longitude: -1.2577, name: 'Oxford' },
  { latitude: 51.3811, longitude: -2.3590, name: 'Bath' },
  { latitude: 51.5154, longitude: -0.0922, name: 'Islington' },
  { latitude: 53.8008, longitude: -1.5491, name: 'Sheffield' },
  { latitude: 52.2280, longitude: 0.1218, name: 'Cambridge' },
  { latitude: 57.1497, longitude: -2.0943, name: 'Aberdeen' },
  { latitude: 54.5682, longitude: -1.2348, name: 'Newcastle' },
  { latitude: 51.8979, longitude: -3.1695, name: 'Cardiff' }
];
const names = ['Jamie','Morgan','Alex','Taylor','Jordan','Cameron','Casey'];
const surnames = ['Reed','Morgan','Bryan','Stewart','Doyle','Lennon'];
const osTypes = ['Android','Apple'];
const getRandom = (arr) => arr[Math.floor(Math.random()*arr.length)];
const jitter = (value, delta) => value + (Math.random()-0.5)*delta;
const randomPhone = () => `07${Math.floor(10000000 + Math.random()*89999999)}`;
const citySpread = 0.06;
const move = (base) => {
  const distance = Math.random()*citySpread;
  const angle = Math.random()*Math.PI*2;
  return {
    latitude: base.latitude + Math.cos(angle)*distance,
    longitude: base.longitude + Math.sin(angle)*distance
  };
};

const randomRegionBase = () => ({
  latitude: 50 + Math.random()*8,
  longitude: -7 + Math.random()*8
});

const sampleBaseLocation = () => Math.random() < 0.7 ? { ...getRandom(clusters) } : randomRegionBase();
const updateStats = () => {
  ui.stats.total.textContent = simState.stats.total;
  ui.stats.active.textContent = simState.stats.active;
  ui.stats.errors.textContent = simState.stats.errors;
};
const setLightState = (device, state) => {
  if (!device.el) return;
  device.el.classList.remove('idle','normal','active');
  device.el.classList.add(state);
};
const flashLight = (device) => {
  if (!device.el) return;
  clearTimeout(device.flashTimer);
  device.el.classList.add('flash');
  device.flashTimer = setTimeout(() => {
    device.el?.classList.remove('flash');
  }, 2000);
};
const createGrid = () => {
  ui.grid.innerHTML = '';
  simState.devices.forEach((d) => {
    const el = document.createElement('div');
    el.className = 'device-cell idle';
    el.title = `Device ${d.deviceId}`;
    el.textContent = d.deviceId.slice(-2);
    ui.grid.appendChild(el);
    d.el = el;
    setLightState(d, 'idle');
  });
};
const simulateUpdate = async (device, active) => {
  try {
    await apiFetch(`/api/devices/statusupdate`, { method: 'POST', body: JSON.stringify({
      device_id: device.deviceId,
      api_key: device.apiKey,
      latitude: device.location.latitude,
      longitude: device.location.longitude,
      battery: Math.max(5, 100 - (device.updates % 100)),
      speed: active ? 12 : 3,
      heading: Math.random()*360,
      activation: active ? 1 : 0
    })});
    device.updates += 1;
    setLightState(device, active ? 'active' : 'normal');
    flashLight(device);
  } catch (err) {
    simState.stats.errors += 1;
    setLightState(device, 'idle');
    flashLight(device);
  }
  updateStats();
};
const getRandomInterval = () => {
  const min = Number.isFinite(config.updateMinMs) ? config.updateMinMs : 0;
  const max = Number.isFinite(config.updateMaxMs) ? config.updateMaxMs : min;
  const range = Math.max(0, max - min);
  return min + Math.random()*range;
};

const schedule = (device, next, active=false) => {
  if (!simState.running) return;
  const delay = Number.isFinite(next) ? next : 1000;
  const timer = setTimeout(async () => {
    if (!simState.running) return;
    device.location = move(device.base);
    await simulateUpdate(device, active);
    if (active) {
      simState.stats.active += 1;
      updateStats();
      setTimeout(() => {
        simState.stats.active -= 1;
        updateStats();
        schedule(device, getRandomInterval(), false);
      }, config.activeDurationMs);
    } else {
      const shouldActivate = Math.random() < config.activationChance;
      const nextDelay = shouldActivate ? config.activationIntervalMs : getRandomInterval();
      schedule(device, nextDelay, shouldActivate);
    }
  }, delay);
  simState.timeouts.push(timer);
};
let config = {};
const createCasePayload = (organisation_id, deviceId) => ({
  registered_user: `${getRandom(names)} ${getRandom(surnames)}`,
  gender: getRandom(['Female','Male']),
  risk_level: getRandom(['High','Medium','Low']),
  local_reference: `Perf-${Math.floor(Math.random()*100000)}`,
  officer_name: 'System Perf',
  officer_staff_id: 'PERF01',
  map_label: 'PerfSim',
  os_type: getRandom(osTypes),
  status: 'Open',
  language_code: 'en-GB'
  , device: deviceId
  , organisation_id
});

const buildDevices = async () => {
  simState.devices = [];
  simState.createdCases = [];
  simState.timeouts = [];
  for (let i=0;i<config.deviceCount;i++) {
    const base = sampleBaseLocation();
    const location = move(base);
    const org = getRandom(simState.organisations);
    const organisationId = org ? org.id : undefined;
    const deviceId = randomPhone();
    const payload = createCasePayload(organisationId, deviceId);
    let created;
    try {
      created = await apiFetch('/api/cases', { method: 'POST', body: JSON.stringify(payload) });
    } catch (caseErr) {
      console.error('Case creation failed', caseErr, payload);
      throw caseErr;
    }
    const activationCode = created.activation_code ?? created.case?.activation_code;
    if (!activationCode) throw new Error('Activation code missing from case response');
    const enroll = await apiFetch('/api/devices/enroll', { method: 'POST', body: JSON.stringify({ device_id: deviceId, pin: activationCode }) });
    const caseId = created.case?.id ?? created.id;
    if (caseId) simState.createdCases.push(caseId);
    const device = {
      caseId,
      deviceId,
      apiKey: enroll.api_key,
      location,
      base,
      updates: 0,
      active: false
    };
    simState.devices.push(device);
  }
};
const startDeviceLoops = () => {
  const initialDelayMs = 500;
  simState.devices.forEach((device) => schedule(device, initialDelayMs, false));
};

const clearTimers = () => {
  simState.timeouts.forEach(clearTimeout);
  simState.timeouts = [];
};

const teardownCases = async () => {
  if (!simState.createdCases.length) return;
  const cases = Array.from(new Set(simState.createdCases));
  for (const caseId of cases) {
    try {
      if (config.teardownMode === 'delete') {
        await apiFetch(`/api/cases/${caseId}`, { method: 'DELETE' });
      } else {
        await apiFetch(`/api/cases/${caseId}`, { method: 'PATCH', body: JSON.stringify({ status: 'Archived', enrollment: 0 }) });
      }
    } catch (err) {
      console.error(`Teardown failed for case ${caseId}`, err);
    }
  }
  simState.createdCases = [];
};

const stopSimulation = async () => {
  if (!simState.running) return;
  simState.running = false;
  clearTimers();
  ui.loginStatus.textContent = 'Stopping simulation...';
  try {
    await teardownCases();
    ui.loginStatus.textContent = 'Simulation stopped';
  } catch (err) {
    console.error('Teardown failed', err);
    ui.loginStatus.textContent = 'Simulation stopped (teardown errors logged)';
  }
  ui.start.disabled = false;
  ui.stop.disabled = true;
};

const startSimulation = async () => {
  if (!isAuthenticated) {
    alert('Please authenticate before starting the simulation.');
    return;
  }
  if (simState.running) return;
  clearTimers();
  const minMinutesInput = parseInt(document.getElementById('update-min').value,10);
  const maxMinutesInput = parseInt(document.getElementById('update-max').value,10);
  const minMinutes = Number.isFinite(minMinutesInput) ? minMinutesInput : 30;
  const maxMinutes = Math.max(minMinutes, Number.isFinite(maxMinutesInput) ? maxMinutesInput : 60);
  const minMs = minMinutes * 60 * 1000;
  const maxMs = maxMinutes * 60 * 1000;
  const activeRatio = Math.max(0, Math.min(1, (parseFloat(document.getElementById('active-ratio').value) || 3) / 100));
  const activeIntervalMs = Math.max(1000, (parseInt(document.getElementById('active-interval').value,10) || 30) * 1000);
  const activeDurationMs = Math.max(1000, (parseInt(document.getElementById('active-duration').value,10) || 15) * 60 * 1000);
  const teardownMode = document.getElementById('teardown-mode').value || 'archive';
  config = {
    deviceCount: parseInt(document.getElementById('device-count').value,10) || 200,
    updateMinMs: minMs,
    updateMaxMs: maxMs,
    activationChance: activeRatio,
    activationIntervalMs: activeIntervalMs,
    activeDurationMs,
    teardownMode
  };
  simState.running = true;
  simState.stats = { total: config.deviceCount, active:0, errors:0 };
  try {
    await buildDevices();
    createGrid();
    updateStats();
    startDeviceLoops();
    ui.loginStatus.textContent = `Simulation running (${simState.stats.total} devices)`;
    ui.start.disabled = true;
    ui.stop.disabled = false;
  } catch (err) {
    console.error('Simulation failed to start', err);
    simState.running = false;
    ui.loginStatus.textContent = `Simulator error: ${err.message}`;
    ui.start.disabled = false;
    ui.stop.disabled = true;
  }
};
ui.loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const body = { email: document.getElementById('sim-email').value, password: document.getElementById('sim-password').value };
  try {
    await apiFetch('/api/auth/login', { method: 'POST', body: JSON.stringify(body) });
    ui.loginStatus.textContent = 'Authenticated';
    isAuthenticated = true;
    ui.start.disabled = false;
    let orgResponse = [];
    try {
      const list = await apiFetch('/api/organisations?limit=1000');
      orgResponse = list.items || [];
    } catch (err) {
      console.error('Failed to load organizations', err);
    }
    simState.organisations = orgResponse;
    if (!simState.organisations.length) {
      const current = await apiFetch('/api/auth/me');
      if (current.organisation_id) {
        simState.organisations = [{ id: current.organisation_id, name: 'Default Org' }];
      }
    }
    if (!simState.organisations.length) {
      ui.loginStatus.textContent = 'No accessible organisations';
      isAuthenticated = false;
      ui.start.disabled = true;
    }
  } catch (err) {
    ui.loginStatus.textContent = 'Login failed';
  }
});
ui.start.addEventListener('click', startSimulation);
ui.stop.addEventListener('click', () => {
  stopSimulation();
});
