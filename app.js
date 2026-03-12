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
let simState = { running: false, devices: [], stats: { total:0, active:0, errors:0 }, organisations: [] };
let isAuthenticated = false;
const clusters = [
  { lat: 51.5074, lon: -0.1278 }, { lat: 55.9533, lon: -3.1883 }, { lat: 53.3498, lon: -6.2603 },
  { lat: 52.4862, lon: -1.8904 }, { lat: 51.4816, lon: -3.1791 }, { lat: 53.4839, lon: -2.2446 },
  { lat: 54.5973, lon: -5.9301 }, { lat: 51.8985, lon: -8.4756 }
];
const names = ['Jamie','Morgan','Alex','Taylor','Jordan','Cameron','Casey'];
const surnames = ['Reed','Morgan','Bryan','Stewart','Doyle','Lennon'];
const osTypes = ['Android','Apple'];
const getRandom = (arr) => arr[Math.floor(Math.random()*arr.length)];
const jitter = (value, delta) => value + (Math.random()-0.5)*delta;
const randomPhone = () => `07${Math.floor(10000000 + Math.random()*89999999)}`;
const move = (base) => {
  const distance = Math.random()*0.02;
  const angle = Math.random()*Math.PI*2;
  return { latitude: base.lat + Math.cos(angle)*distance, longitude: base.lon + Math.sin(angle)*distance };
};
const updateStats = () => {
  ui.stats.total.textContent = simState.stats.total;
  ui.stats.active.textContent = simState.stats.active;
  ui.stats.errors.textContent = simState.stats.errors;
};
const setLight = (device, state) => {
  device.el.classList.remove('idle','normal','active');
  device.el.classList.add(state);
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
    setLight(device, active ? 'active' : 'normal');
  } catch (err) {
    simState.stats.errors += 1;
    setLight(device, 'idle');
  }
  updateStats();
};
const schedule = (device, next, active=false) => {
  if (!simState.running) return;
  setTimeout(async () => {
    device.location = move(device.base);
    await simulateUpdate(device, active);
    if (active) {
      simState.stats.active += 1;
      updateStats();
      setTimeout(() => {
        simState.stats.active -= 1;
        updateStats();
        schedule(device, Math.random()*config.updateIntervalMs + config.updateIntervalMs, false);
      }, config.activeDurationMs);
    } else {
      schedule(device, Math.random()*config.updateIntervalMs + config.updateIntervalMs, device.active);
    }
  }, next);
};
let config = {};
const createCasePayload = (organisation_id) => ({
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
  , organisation_id
});

const buildDevices = async () => {
  simState.devices = [];
  for (let i=0;i<config.deviceCount;i++) {
    const cluster = getRandom(clusters);
    const location = move(cluster);
    const org = getRandom(simState.organisations) || null;
    const payload = createCasePayload(org?.id ?? undefined);
    const created = await apiFetch('/api/cases', { method: 'POST', body: JSON.stringify(payload) });
    const enroll = await apiFetch('/api/devices/enroll', { method: 'POST', body: JSON.stringify({ device_id: randomPhone(), pin: created.activation_code }) });
    const device = {
      caseId: created.id,
      deviceId: enroll.device_id,
      apiKey: enroll.api_key,
      location,
      base: cluster,
      updates: 0,
      active: false
    };
    simState.devices.push(device);
  }
};
const startSimulation = async () => {
  if (!isAuthenticated) {
    alert('Please authenticate before starting the simulation.');
    return;
  }
  if (simState.running) return;
  config = {
    deviceCount: parseInt(document.getElementById('device-count').value,10) || 200,
    updateIntervalMs: (parseInt(document.getElementById('update-max').value,10) || 60) * 60 * 1000,
    activeDurationMs: (parseInt(document.getElementById('active-duration').value,10) || 15) * 60 * 1000
  };
  simState.running = true;
  simState.stats = { total: config.deviceCount, active:0, errors:0 };
  await buildDevices();
  createGrid();
  updateStats();
};
ui.loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const body = { email: document.getElementById('sim-email').value, password: document.getElementById('sim-password').value };
  try {
    await apiFetch('/api/auth/login', { method: 'POST', body: JSON.stringify(body) });
    ui.loginStatus.textContent = 'Authenticated';
    isAuthenticated = true;
    ui.start.disabled = false;
    if (!simState.organisations.length) {
      try {
        simState.organisations = await apiFetch('/api/organisations?limit=1000');
      } catch (err) {
        console.error('Failed to load organizations', err);
      }
    }
  } catch (err) {
    ui.loginStatus.textContent = 'Login failed';
  }
});
ui.start.addEventListener('click', startSimulation);
