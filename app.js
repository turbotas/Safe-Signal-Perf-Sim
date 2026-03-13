const DEFAULT_BASE_URL = 'http://localhost:8000';
let baseUrl = localStorage.getItem('simBaseUrl') || DEFAULT_BASE_URL;
const setBaseUrl = (url) => {
  const trimmed = url ? url.replace(/\/+$/, '') : DEFAULT_BASE_URL;
  baseUrl = trimmed || DEFAULT_BASE_URL;
  localStorage.setItem('simBaseUrl', baseUrl);
};
setBaseUrl(baseUrl);
const apiFetch = async (path, options = {}) => {
  const response = await fetch(`${baseUrl}${path}`, {
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
  retryTeardown: document.getElementById('retry-teardown'),
  grid: document.getElementById('device-grid'),
  stats: {
    total: document.getElementById('stat-count'),
    active: document.getElementById('stat-active'),
    errors: document.getElementById('stat-errors')
  }
};
const femaleNames = ['Aisling','Ciara','Fiona','Maeve','Niamh','Róisín','Sinead','Orla','Cara','Bronagh','Aoife','Siobhán','Eabha'];
const maleNames = ['Connor','Liam','Sean','Eoin','Patrick','Declan','Finn','Cian','Darragh','Ronan','Emmett'];
const lastNames = ['O’Brien','Murphy','Kelly','McCarthy','Walsh','Byrne','Sullivan','O’Neill','Fitzgerald','Doyle','Reilly','Lynch','Kane','Brennan'];
const officerNames = ['Sergeant Hynes','DS Murray','Inspector Stratton','PC Avery','Lieutenant Fisher','Supt. Blake'];
const mapLabels = ['PerfSim','SafeSignal','Control','OpsBeat'];
const languages = ['en-GB','cy-GB','gd-GB','ga-IE'];
let simState = { running: false, devices: [], stats: { total:0, active:0, errors:0 }, organisations: [], timeouts: [], createdCases: [], failedTeardowns: [] };
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
  { latitude: 54.7850, longitude: -6.0190, name: 'Derry' },
  { latitude: 54.5780, longitude: -8.4761, name: 'Sligo' },
  { latitude: 53.2707, longitude: -9.0568, name: 'Galway' },
  { latitude: 52.6680, longitude: -8.6305, name: 'Cork' },
  { latitude: 52.6638, longitude: -8.6267, name: 'Limerick' },
  { latitude: 52.2574, longitude: -7.1129, name: 'Waterford' },
  { latitude: 53.2978, longitude: -6.3621, name: 'Meath' },
  { latitude: 53.3498, longitude: -6.2603, name: 'Dublin (Docklands)' },
  { latitude: 54.9776, longitude: -1.6130, name: 'Newcastle upon Tyne' }
];
const osTypes = ['Android','Apple'];
const getRandom = (arr) => arr[Math.floor(Math.random()*arr.length)];
const pickGender = () => (Math.random() < 0.9 ? 'Female' : 'Male');
const pickName = (gender) => gender === 'Female' ? getRandom(femaleNames) : getRandom(maleNames);
const sanitizeForEmail = (value) => value.replace(/[^a-zA-Z]/g, '').toLowerCase();
const randomEmail = (first, last) => `${sanitizeForEmail(first)}.${sanitizeForEmail(last)}@perfsim.local`;
const randomFutureDate = (minDays = 21, maxDays = 90) => {
  const date = new Date();
  const offset = minDays + Math.floor(Math.random() * (maxDays - minDays + 1));
  date.setDate(date.getDate() + offset);
  return date.toISOString().split('T')[0];
};
const randomDob = () => {
  const date = new Date();
  const age = 25 + Math.floor(Math.random() * 30);
  date.setFullYear(date.getFullYear() - age);
  date.setDate(date.getDate() - Math.floor(Math.random() * 365));
  return date.toISOString().split('T')[0];
};
const jitter = (value, delta) => value + (Math.random()-0.5)*delta;
const randomPhone = () => `07${Math.floor(10000000 + Math.random()*89999999)}`;
const citySpread = 0.12;
const distanceFromCentre = () => citySpread * (0.2 + Math.pow(Math.random(), 2) * 2.0);
const move = (base) => {
  const distance = distanceFromCentre();
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
const endpointInput = document.getElementById('api-endpoint');
const endpointDisplay = document.getElementById('api-endpoint-display');
const refreshEndpointInfo = () => {
  if (endpointDisplay) endpointDisplay.textContent = baseUrl;
  if (endpointInput) endpointInput.value = baseUrl;
};
if (endpointInput) {
  endpointInput.addEventListener('change', (event) => {
    setBaseUrl(event.target.value);
    refreshEndpointInfo();
  });
}
refreshEndpointInfo();
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
    device.base = { ...device.location };
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
const riskLevels = ['High','Medium','Low'];
const createCasePayload = (organisation_id, deviceId) => {
  const gender = pickGender();
  const firstName = pickName(gender);
  const lastName = getRandom(lastNames);
  const registered_user = `${firstName} ${lastName}`;
  const review_date = randomFutureDate();
  const payload = {
    registered_user,
    gender,
    risk_level: getRandom(riskLevels),
    email_address: randomEmail(firstName, lastName),
    local_reference: `Perf-${Math.floor(Math.random()*100000)}`,
    officer_name: getRandom(officerNames),
    officer_staff_id: `PERF-${Math.floor(100 + Math.random()*900)}`,
    authorising_officer: getRandom(officerNames),
    map_label: `${getRandom(mapLabels)}-${Math.floor(Math.random()*500)}`,
    os_type: getRandom(osTypes),
    status: 'Open',
    language_code: getRandom(languages),
    review_date,
    device: deviceId,
    organisation_id
  };
  if (Math.random() < 0.35) {
    const perpGender = pickGender();
    payload.perp_name = `${pickName(perpGender)} ${getRandom(lastNames)}`;
    payload.perp_gender = perpGender;
    payload.perp_dob = randomDob();
    payload.perp_pnd_id = `PND-${Math.floor(100000 + Math.random()*899999)}`;
    payload.perp_court_order = `Bail Order ${Math.floor(Math.random()*900)+100}`;
  }
  return payload;
};

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

const updateRetryButtonState = () => {
  if (ui.retryTeardown) {
    ui.retryTeardown.disabled = !simState.failedTeardowns.length;
  }
};

const executeTeardownForCase = async (caseId) => {
  if (config.teardownMode === 'delete') {
    await apiFetch(`/api/cases/${caseId}`, { method: 'DELETE' });
  } else {
    await apiFetch(`/api/cases/${caseId}`, { method: 'PATCH', body: JSON.stringify({ status: 'Archived', enrollment: 0 }) });
  }
};

const teardownCases = async (caseIds) => {
  const failures = [];
  const targets = Array.from(new Set(caseIds));
  for (const caseId of targets) {
    try {
      await executeTeardownForCase(caseId);
    } catch (err) {
      console.error(`Teardown failed for case ${caseId}`, err);
      failures.push(caseId);
    }
  }
  return failures;
};

const stopSimulation = async () => {
  if (!simState.running) return;
  simState.running = false;
  clearTimers();
  ui.loginStatus.textContent = 'Stopping simulation...';
  const failures = await teardownCases(simState.createdCases);
  simState.failedTeardowns = failures;
  simState.createdCases = [];
  updateRetryButtonState();
  if (failures.length) {
    ui.loginStatus.textContent = `${failures.length} case(s) still need cleanup; hit Retry Failed Teardowns.`;
  } else {
    ui.loginStatus.textContent = 'Simulation stopped';
  }
  ui.start.disabled = false;
  ui.stop.disabled = true;
};

const retryFailedTeardowns = async () => {
  if (!simState.failedTeardowns.length) return;
  ui.loginStatus.textContent = 'Retrying failed teardowns...';
  ui.retryTeardown.disabled = true;
  const failures = await teardownCases(simState.failedTeardowns);
  simState.failedTeardowns = failures;
  updateRetryButtonState();
  if (failures.length) {
    ui.loginStatus.textContent = `${failures.length} case(s) still require manual cleanup.`;
  } else {
    ui.loginStatus.textContent = 'All tear-downs now completed';
  }
};

const startSimulation = async () => {
  if (!isAuthenticated) {
    alert('Please authenticate before starting the simulation.');
    return;
  }
  if (simState.running) return;
  clearTimers();
  simState.failedTeardowns = [];
  updateRetryButtonState();
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
if (ui.retryTeardown) {
  ui.retryTeardown.addEventListener('click', retryFailedTeardowns);
}
