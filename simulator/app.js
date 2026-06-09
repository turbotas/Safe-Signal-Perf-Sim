const DEFAULT_BASE_URL = '/';
const CASE_REGISTRY_KEY = 'simCaseRegistry:v1';
const COMPLETED_CASE_RETENTION_MS = 24 * 60 * 60 * 1000;
let baseUrl = localStorage.getItem('simBaseUrl') || DEFAULT_BASE_URL;
const setBaseUrl = (url) => {
  const trimmed = url ? url.replace(/\/+$/, '') : DEFAULT_BASE_URL;
  baseUrl = trimmed || DEFAULT_BASE_URL;
  localStorage.setItem('simBaseUrl', baseUrl);
};
setBaseUrl(baseUrl);
const loadCaseRegistry = () => {
  try {
    const raw = localStorage.getItem(CASE_REGISTRY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (err) {
    console.warn('Failed to parse persisted case registry', err);
    return [];
  }
};
let caseRegistry = loadCaseRegistry();
const saveCaseRegistry = () => {
  localStorage.setItem(CASE_REGISTRY_KEY, JSON.stringify(caseRegistry));
};
const pruneCompletedCases = () => {
  const now = Date.now();
  const before = caseRegistry.length;
  caseRegistry = caseRegistry.filter((entry) => {
    if (entry.status !== 'teardown_done') return true;
    const updated = Date.parse(entry.updatedAt || entry.createdAt || '');
    if (!Number.isFinite(updated)) return false;
    return now - updated < COMPLETED_CASE_RETENTION_MS;
  });
  if (caseRegistry.length !== before) {
    saveCaseRegistry();
  }
};
const findCaseRegistryIndex = (caseId, targetBaseUrl = baseUrl) =>
  caseRegistry.findIndex((entry) => entry.caseId === caseId && entry.baseUrl === targetBaseUrl);
const trackCaseForCleanup = ({ caseId, deviceId, teardownMode }) => {
  if (!caseId) return;
  const nowIso = new Date().toISOString();
  const index = findCaseRegistryIndex(caseId, baseUrl);
  if (index >= 0) {
    caseRegistry[index] = {
      ...caseRegistry[index],
      deviceId: deviceId || caseRegistry[index].deviceId,
      teardownMode: teardownMode || caseRegistry[index].teardownMode || 'delete',
      status: 'pending',
      lastError: '',
      updatedAt: nowIso
    };
  } else {
    caseRegistry.push({
      caseId,
      deviceId: deviceId || '',
      baseUrl,
      teardownMode: teardownMode || 'delete',
      status: 'pending',
      lastError: '',
      createdAt: nowIso,
      updatedAt: nowIso
    });
  }
  saveCaseRegistry();
};
const markCaseTeardownStatus = (caseId, status, lastError = '', targetBaseUrl = baseUrl) => {
  const index = findCaseRegistryIndex(caseId, targetBaseUrl);
  if (index < 0) return;
  caseRegistry[index] = {
    ...caseRegistry[index],
    status,
    lastError,
    updatedAt: new Date().toISOString()
  };
  saveCaseRegistry();
};
const getPersistedTeardownEntries = (targetBaseUrl = baseUrl) =>
  caseRegistry.filter((entry) => entry.baseUrl === targetBaseUrl && (entry.status === 'pending' || entry.status === 'teardown_failed'));
const apiFetch = async (path, options = {}) => {
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
  });
  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
};
const apiFetchForm = async (path, formData) => {
  const response = await fetch(`${baseUrl}${path}`, {
    method: 'POST',
    credentials: 'include',
    body: formData
  });
  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  const contentType = response.headers.get('content-type') || '';
  return contentType.includes('application/json') ? response.json() : null;
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
const CASE_PHOTO_ROOT = '/simulator/casephotos';
const CASE_PHOTO_FOLDERS = {
  male: `${CASE_PHOTO_ROOT}/male/`,
  female: `${CASE_PHOTO_ROOT}/female/`
};
const CASE_PHOTO_FILE_PATTERN = /\.(jpe?g|png|gif|webp|jfif)$/i;
const casePhotoState = {
  male: [],
  female: [],
  loaded: false,
  loadingPromise: null,
  lastError: ''
};
const femaleNames = ['Aisling','Ciara','Fiona','Maeve','Niamh','Róisín','Sinead','Orla','Cara','Bronagh','Aoife','Siobhán','Eabha','Kiera','Megan','Imelda','Nora','Isla','Saoirse','Eilis','Harper','Zara','Naomi','Elena','Priya','Maya','Ariana','Lena','Clara','Rosa','Yara','Sofia','Camila','Mila','Leah','Ruby','Lina','Zoe','Jade','Aria','Mira','Talia','Nadia','Ivy','Paige','Danielle','Vivian','June','Macy','Elsa','Amara','Ava','Freya','Skye','Poppy','Heidi','Marnie','Keira','Nina','Lila','Iris','Hazel','Phoebe','Anya','Esme','Bianca','Celeste','Esther','Holly','Marnie','Daisy','Molly','Adele','Sabrina','Noelle','Niam','Elodie','Rhea','Samira','Cleo'];
const maleNames = ['Connor','Liam','Sean','Eoin','Patrick','Declan','Finn','Cian','Darragh','Ronan','Emmett','Colm','Rory','Padraig','Callum','Tadhg','Cillian','Jamie','Bryan','Noah','Leo','Ethan','Mateo','Ibrahim','Luca','Oscar','Jasper','Adrian','Nolan','Ezra','Miles','Hugo','Alex','Pablo','Martin','Haruki','Kai','Jonas','Milo','Isaac','Tomas','Diego','Rafael','Jordan','Morgan','Gabriel','Soren','Caleb','Rian','Max','Oliver','Aiden','Blake','Carter','Dylan','Elliot','Felix','Grayson','Henry','Ivan','Jude','Kieran','Louis','Micah','Nate','Owen','Quentin','Reece','Spencer','Tristan','Victor','Warren','Xavier','Yusuf','Zane','Arlo','Bodhi','Dominic','Gavin','Harris'];
const lastNames = ['O’Brien','Murphy','Kelly','McCarthy','Walsh','Byrne','Sullivan','O’Neill','Fitzgerald','Doyle','Reilly','Lynch','Kane','Brennan','O’Donnell','O’Keefe','Donovan','O’Connor','Quinn','Sweeney','Hughes','Moreau','Schmidt','López','Rossi','Petrov','Matsuda','Nguyen','Harper','Bennett','Jackson','Khan','Martinez','Singh','Gonzalez','Silva','Costa','Rinaldi','Miller','Roy','Chang','Zhang','Brown','Santos','White','Ali','Taylor','Murphy-Smith','Anders','Larsen','Hernández','Novák','Abbott','Armstrong','Barrett','Campbell','Carter','Cunningham','Davidson','Edwards','Farrell','Fletcher','Gallagher','Garcia','Griffin','Hayes','Holland','Kennedy','Lawson','Morrison','Palmer','Parker','Reid','Saunders','Stewart','Thornton','Turner','Vargas','Wheeler','Wilkinson','Woodward','Yates'];
const officerNames = ['Sergeant Hynes','DS Murray','Inspector Stratton','PC Avery','Lieutenant Fisher','Supt. Blake'];
const mapLabels = ['PerfSim','SafeSignal','Control','OpsBeat'];

// Master data fetched from server
let masterData = {
  genders: [],
  languages: [],
  riskCategories: [],
  disabilities: [],
  warningMarkers: []
};

const fetchMasterData = async () => {
  try {
    console.info('Fetching master data...');
    const [genders, languages] = await Promise.all([
      apiFetch('/api/master/genders'),
      apiFetch('/api/languages?for_case=true')
    ]);
    masterData.genders = Array.isArray(genders) ? genders : [];
    masterData.languages = Array.isArray(languages) ? languages : [];
    console.info(`Master data loaded: ${masterData.genders.length} genders, ${masterData.languages.length} case languages`);
  } catch (err) {
    console.warn('Failed to load master data, using fallbacks', err);
    logSimulatorError(`Failed to load master data: ${err.message}`);
    // Fallback values if server queries fail
    masterData.genders = [{ name: 'Female' }, { name: 'Male' }];
    masterData.languages = [{ code: 'en-GB' }];
  }
};

const getRandomGender = () => {
  if (masterData.genders.length === 0) return 'Female';
  const genderObj = getRandom(masterData.genders);
  return genderObj.name || 'Female';
};

const getRandomLanguage = () => {
  if (masterData.languages.length === 0) return 'en-GB';
  const langObj = getRandom(masterData.languages);
  return langObj.code || 'en-GB';
};
let simState = { running: false, devices: [], stats: { total:0, active:0, errors:0 }, organisations: [], timeouts: [], createdCases: [], failedTeardowns: [], errorLog: [] };
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
const pickGender = () => getRandomGender();
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
const metersToDegrees = (meters) => meters / 111000;
const move = (base, active = false) => {
  const maxDistance = active ? metersToDegrees(50) : metersToDegrees(10000);
  const distance = Math.random() * maxDistance;
  const angle = Math.random() * Math.PI * 2;
  return {
    latitude: base.latitude + Math.cos(angle) * distance,
    longitude: base.longitude + Math.sin(angle) * distance
  };
};

const randomRegionBase = () => ({
  latitude: 50 + Math.random()*8,
  longitude: -7 + Math.random()*8
});

const parseCoordinate = (value) => {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string') {
    const trimmed = value.trim();
    const normalized = trimmed.includes(',') && !trimmed.includes('.') ? trimmed.replace(',', '.') : trimmed;
    const parsed = parseFloat(normalized);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};
const isValidCoordinatePair = (latitude, longitude) =>
  latitude !== null && longitude !== null && latitude >= -90 && latitude <= 90 && longitude >= -180 && longitude <= 180;
const tryReadCoordinatePair = (source) => {
  if (!source || typeof source !== 'object') return null;
  const latKeys = ['latitude', 'lat', 'map_default_lat', 'default_lat', 'geo_center_latitude', 'geo_centre_latitude', 'geocenter_latitude', 'geocentre_latitude', 'center_latitude', 'centre_latitude'];
  const lonKeys = ['longitude', 'lng', 'lon', 'long', 'map_default_lng', 'default_lng', 'map_default_lon', 'default_lon', 'geo_center_longitude', 'geo_centre_longitude', 'geocenter_longitude', 'geocentre_longitude', 'center_longitude', 'centre_longitude'];
  for (const latKey of latKeys) {
    if (!(latKey in source)) continue;
    for (const lonKey of lonKeys) {
      if (!(lonKey in source)) continue;
      const latitude = parseCoordinate(source[latKey]);
      const longitude = parseCoordinate(source[lonKey]);
      if (isValidCoordinatePair(latitude, longitude)) {
        return { latitude, longitude };
      }
    }
  }
  return null;
};
const findCoordinatePairDeep = (value, depth = 0, seen = new Set()) => {
  if (!value || typeof value !== 'object' || depth > 5) return null;
  if (seen.has(value)) return null;
  seen.add(value);
  if (Array.isArray(value)) {
    for (const item of value) {
      const found = findCoordinatePairDeep(item, depth + 1, seen);
      if (found) return found;
    }
    return null;
  }
  const direct = tryReadCoordinatePair(value);
  if (direct) return direct;
  const keys = Object.keys(value).sort((a, b) => {
    const aScore = /(geo|centre|center|location)/i.test(a) ? 1 : 0;
    const bScore = /(geo|centre|center|location)/i.test(b) ? 1 : 0;
    return bScore - aScore;
  });
  for (const key of keys) {
    const nested = value[key];
    if (!nested || typeof nested !== 'object') continue;
    const found = findCoordinatePairDeep(nested, depth + 1, seen);
    if (found) return found;
  }
  return null;
};
const getOrganisationGeoCenter = (org) => {
  if (!org || typeof org !== 'object') return null;
  return findCoordinatePairDeep(org);
};
const normaliseOrganisationList = (payload) => {
  if (Array.isArray(payload)) return payload;
  if (!payload || typeof payload !== 'object') return [];
  const candidates = [payload.items, payload.organisations, payload.organizations, payload.data, payload.results];
  for (const candidate of candidates) {
    if (Array.isArray(candidate)) return candidate;
  }
  return [];
};
const sampleBaseLocation = (org) => {
  const center = getOrganisationGeoCenter(org);
  if (center) {
    return center;
  }
  return Math.random() < 0.7 ? { ...getRandom(clusters) } : randomRegionBase();
};
const endpointInput = document.getElementById('api-endpoint');
const endpointDisplay = document.getElementById('api-endpoint-display');
const refreshEndpointInfo = () => {
  if (endpointDisplay) endpointDisplay.textContent = baseUrl;
  if (endpointInput) endpointInput.value = baseUrl;
};
const updateRetryButtonState = () => {
  if (ui.retryTeardown) {
    ui.retryTeardown.disabled = getPersistedTeardownEntries().length === 0;
  }
};
const parseDirectoryListingForImages = (htmlText, folderPath) => {
  const parser = new DOMParser();
  const doc = parser.parseFromString(htmlText, 'text/html');
  const links = Array.from(doc.querySelectorAll('a[href]'));
  return links
    .map((link) => link.getAttribute('href') || '')
    .map((href) => {
      try {
        const absoluteUrl = new URL(href, `${window.location.origin}${folderPath}`);
        const pathPart = absoluteUrl.pathname;
        if (!CASE_PHOTO_FILE_PATTERN.test(pathPart)) return '';
        const fileName = decodeURIComponent(pathPart.split('/').pop() || '');
        if (!fileName || fileName.startsWith('.')) return '';
        return `${folderPath}${fileName}`;
      } catch (_err) {
        return '';
      }
    })
    .filter(Boolean);
};
const loadPhotoFolder = async (folderPath) => {
  const response = await fetch(folderPath, { cache: 'no-store' });
  if (!response.ok) {
    const error = new Error(`Photo folder load failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  const html = await response.text();
  return parseDirectoryListingForImages(html, folderPath);
};
const photoInventorySummary = () => `photos M:${casePhotoState.male.length} F:${casePhotoState.female.length}`;
const ensureCasePhotosLoaded = async () => {
  if (casePhotoState.loaded) return;
  if (casePhotoState.loadingPromise) {
    await casePhotoState.loadingPromise;
    return;
  }
  casePhotoState.loadingPromise = (async () => {
    try {
      const [malePhotos, femalePhotos] = await Promise.all([
        loadPhotoFolder(CASE_PHOTO_FOLDERS.male),
        loadPhotoFolder(CASE_PHOTO_FOLDERS.female)
      ]);
      casePhotoState.male = malePhotos;
      casePhotoState.female = femalePhotos;
      casePhotoState.lastError = '';
      casePhotoState.loaded = true;
      console.info(`Case photo inventory loaded (${photoInventorySummary()})`);
    } catch (err) {
      casePhotoState.loaded = false;
      casePhotoState.lastError = err.message || 'Unknown photo inventory error';
      casePhotoState.male = [];
      casePhotoState.female = [];
      console.warn('Failed to load case photo inventory', err);
    } finally {
      casePhotoState.loadingPromise = null;
    }
  })();
  await casePhotoState.loadingPromise;
};
const randomCasePhotoForGender = (gender) => {
  const key = gender === 'Male' ? 'male' : 'female';
  const pool = casePhotoState[key] || [];
  if (!pool.length) return '';
  return randomSpreadPick(pool);
};
const guessPhotoContentType = (path) => {
  const value = String(path || '').toLowerCase();
  if (/\.(jpe?g|jfif)$/.test(value)) return 'image/jpeg';
  if (/\.png$/.test(value)) return 'image/png';
  if (/\.gif$/.test(value)) return 'image/gif';
  if (/\.webp$/.test(value)) return 'image/webp';
  return 'application/octet-stream';
};
const readPhotoAsset = async (photoPath) => {
  const response = await fetch(photoPath, { cache: 'no-store' });
  if (!response.ok) {
    const error = new Error(`Photo fetch failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  const blob = await response.blob();
  const contentType = blob.type || guessPhotoContentType(photoPath);
  const fileName = decodeURIComponent((photoPath.split('/').pop() || 'photo').split('?')[0]);
  return { blob: blob.slice(0, blob.size, contentType), fileName, contentType };
};
const uploadCasePhoto = async (caseId, photo) => {
  const photoAsset = await readPhotoAsset(photo.path);
  const formData = new FormData();
  formData.append('target_type', photo.targetType);
  formData.append('label', photo.label);
  formData.append('file', photoAsset.blob, photoAsset.fileName);
  await apiFetchForm(`/api/cases/${caseId}/photos`, formData);
};
const uploadCasePhotosBestEffort = async (caseId, photos, deviceId) => {
  for (const photo of photos) {
    try {
      await uploadCasePhoto(caseId, photo);
    } catch (err) {
      logSimulatorError(`Photo upload failed for ${deviceId}/${photo.targetType}: ${err.message}`);
    }
  }
};
const syncPersistedTeardownState = () => {
  const pendingEntries = getPersistedTeardownEntries();
  simState.failedTeardowns = pendingEntries.map((entry) => entry.caseId);
  updateRetryButtonState();
  return pendingEntries;
};
if (endpointInput) {
  endpointInput.addEventListener('change', (event) => {
    setBaseUrl(event.target.value);
    refreshEndpointInfo();
    const pendingEntries = syncPersistedTeardownState();
    if (pendingEntries.length && !simState.running) {
      ui.loginStatus.textContent = `${pendingEntries.length} persisted case(s) pending cleanup.`;
    }
  });
}
refreshEndpointInfo();
pruneCompletedCases();
const initialPendingCases = syncPersistedTeardownState();
if (initialPendingCases.length) {
  ui.loginStatus.textContent = `${initialPendingCases.length} persisted case(s) pending cleanup.`;
}
ensureCasePhotosLoaded().then(() => {
  if (!initialPendingCases.length && !isAuthenticated) {
    ui.loginStatus.textContent = `Ready (${photoInventorySummary()})`;
  }
});
const updateStats = () => {
  ui.stats.total.textContent = simState.stats.total;
  ui.stats.active.textContent = simState.stats.active;
  ui.stats.errors.textContent = simState.stats.errors;
};

const updateErrorLog = () => {
  if (!errorLogEl) return;
  errorLogEl.innerHTML = '';
  simState.errorLog.forEach((entry) => {
    const line = document.createElement('p');
    line.textContent = entry;
    errorLogEl.appendChild(line);
  });
};

const logSimulatorError = (msg) => {
  const entry = `${new Date().toLocaleTimeString()} - ${msg}`;
  simState.errorLog.unshift(entry);
  if (simState.errorLog.length > 30) {
    simState.errorLog.pop();
  }
  updateErrorLog();
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
    el.innerHTML = `<span>${d.deviceId.slice(-2)}</span>`;
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
      logSimulatorError(`Device ${device.deviceId}: ${err.message}`);
    }
  updateStats();
};
const getRandomInterval = () => {
  const min = Number.isFinite(config.updateMinMs) ? config.updateMinMs : 0;
  const max = Number.isFinite(config.updateMaxMs) ? config.updateMaxMs : min;
  const range = Math.max(0, max - min);
  return min + Math.random()*range;
};

const schedule = (device, nextDelay) => {
  if (!simState.running) return;
  const delay = Number.isFinite(nextDelay) ? nextDelay : 1000;
  const timer = setTimeout(async () => {
    if (!simState.running) return;
    const now = Date.now();
    const isActiveNow = device.activeBurstEnd && now < device.activeBurstEnd;
    if (isActiveNow && !device.isActive) {
      device.isActive = true;
      simState.stats.active += 1;
      updateStats();
    } else if (!isActiveNow && device.isActive) {
      device.isActive = false;
      simState.stats.active = Math.max(0, simState.stats.active - 1);
      updateStats();
      device.activeBurstEnd = 0;
    }
    device.location = move(device.base, isActiveNow);
    await simulateUpdate(device, isActiveNow);
    device.base = { ...device.location };
    let next;
    if (isActiveNow) {
      next = config.activeIntervalMs;
    } else if (Math.random() < config.activationChance) {
      const end = Date.now() + config.activeDurationMs;
      device.activeBurstEnd = end;
      if (!device.isActive) {
        device.isActive = true;
        simState.stats.active += 1;
        updateStats();
      }
      next = config.activeIntervalMs;
    } else {
      next = getRandomInterval();
    }
    schedule(device, next);
  }, delay);
  simState.timeouts.push(timer);
};
let config = {};
const riskLevels = ['High','Medium','Low'];
const riskCategoryIds = [1,2,3,4,5];
const disabilityIds = [1,2,3,4];
const warningMarkerIds = [1,2,3,4,5,6];
const streets = ['Harper Lane','Marlow Road','Beacon Crescent','Harrow Way','Larkspur Drive','Ridgewell Avenue','Keeley Street'];
const towns = ['Kilburn','Shankill','Greystones','Lisburn','Kingstanding','Belfast','Galway','Cork','Limerick','Brighton','Slough'];
const vehicleCatalog = {
  Toyota: ['Corolla','Camry','Yaris','RAV4'],
  Ford: ['Focus','Fiesta','Mondeo','Kuga'],
  BMW: ['320i','X3','118i','520d'],
  Audi: ['A3','A4','Q3','Q5'],
  Vauxhall: ['Astra','Corsa','Insignia','Mokka'],
  Nissan: ['Juke','Qashqai','Micra','Leaf'],
  Hyundai: ['i30','Tucson','Kona','i10'],
  Honda: ['Civic','CR-V','Jazz','Accord']
};
const vehicleMakes = Object.keys(vehicleCatalog);
const vehicleColors = ['Blue','Black','Silver','Red','White','Green','Grey','Navy'];
const randomSubset = (items) => items.filter(() => Math.random() < 0.4);
const randomSpreadPick = (items) => items[Math.floor(Math.random() * items.length)];
const randomVehicleRegistration = () => {
  const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  const randLetter = () => letters[Math.floor(Math.random() * letters.length)];
  const randDigit = () => Math.floor(Math.random() * 10);
  return `${randLetter()}${randLetter()}${randDigit()}${randDigit()} ${randLetter()}${randLetter()}${randLetter()}`;
};
const ukPostcodeAreas = ['AL','B','BA','BB','BD','BH','BL','BN','BR','BS','BT','CA','CB','CF','CH','CM','CO','CR','CT','CV','CW','DA','DD','DE','DG','DH','DL','DN','DT','DY','E','EC','EH','EN','EX','FK','FY','G','GL','GU','HA','HD','HG','HP','HR','HS','HU','HX','IG','IP','IV','KA','KT','KW','KY','L','LA','LD','LE','LL','LN','LS','LU','M','ME','MK','ML','N','NE','NG','NN','NP','NR','NW','OL','OX','PA','PE','PH','PL','PO','PR','RG','RH','RM','S','SA','SE','SG','SK','SL','SM','SN','SO','SP','SR','SS','ST','SW','SY','TA','TD','TF','TN','TQ','TR','TS','TW','UB','W','WA','WC','WD','WF','WN','WR','WS','WV','YO','ZE'];
const validInwardLetters = 'ABDEFGHJLNPQRSTUWXYZ';
const randomPostcode = () => {
  const area = ukPostcodeAreas[Math.floor(Math.random() * ukPostcodeAreas.length)];
  const digit1 = Math.floor(Math.random() * 10);
  const digit2 = Math.floor(Math.random() * 10);
  const l1 = validInwardLetters[Math.floor(Math.random() * validInwardLetters.length)];
  const l2 = validInwardLetters[Math.floor(Math.random() * validInwardLetters.length)];
  const inward = `${digit2}${l1}${l2}`;
  // More single-digit districts in shorter area codes
  if (area.length === 1 || Math.random() < 0.6) {
    return `${area}${digit1} ${inward}`;
  }
  return `${area}${digit1}${digit2} ${inward}`;
};
const randomAddresses = (targetType) => {
  const count = Math.ceil(Math.random()*2);
  return Array.from({length: count}, () => ({
    target_type: targetType,
    label: `${targetType} Address`,
    address_line1: `${Math.floor(Math.random()*200)} ${randomSpreadPick(streets)}`,
    city: randomSpreadPick(towns),
    postcode: randomPostcode()
  }));
};
const randomVehicles = (targetType, minCount = 0, maxCount = 2) => {
  const span = Math.max(0, maxCount - minCount);
  const count = minCount + Math.floor(Math.random() * (span + 1));
  return Array.from({length: count}, () => {
    const make = randomSpreadPick(vehicleMakes);
    return {
      target_type: targetType,
      make,
      model: randomSpreadPick(vehicleCatalog[make]),
      color: randomSpreadPick(vehicleColors),
      vrm: randomVehicleRegistration()
    };
  });
};
const createCasePayload = (organisation_id, deviceId) => {
  const gender = pickGender();
  const firstName = pickName(gender);
  const lastName = getRandom(lastNames);
  const registered_user = `${firstName} ${lastName}`;
  const review_date = randomFutureDate();
  const addresses = [...randomAddresses('user')];
  const vehicles = [...randomVehicles('user', 1, 3)];
  const stagedPhotos = [];
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
    language_code: getRandomLanguage(),
    review_date,
    risk_category_ids: randomSubset(riskCategoryIds),
    disability_ids: randomSubset(disabilityIds),
    device: deviceId,
    organisation_id,
    addresses,
    vehicles
  };
  const subjectPhoto = randomCasePhotoForGender(gender);
  if (subjectPhoto) {
    stagedPhotos.push({ path: subjectPhoto, targetType: 'user', label: `Subject ${registered_user}` });
  }
  if (Math.random() < 0.35) {
    const perpGender = pickGender();
    payload.perp_name = `${pickName(perpGender)} ${getRandom(lastNames)}`;
    payload.perp_gender = perpGender;
    payload.perp_dob = randomDob();
    payload.perp_pnc_id = `PNC-${Math.floor(100000 + Math.random()*899999)}`;
    payload.perp_court_order = `Bail Order ${Math.floor(Math.random()*900)+100}`;
    payload.warning_marker_ids = randomSubset(warningMarkerIds);
    addresses.push(...randomAddresses('perp'));
    vehicles.push(...randomVehicles('perp', 1, 2));
    const perpPhoto = randomCasePhotoForGender(perpGender);
    if (perpPhoto) {
      stagedPhotos.push({ path: perpPhoto, targetType: 'perp', label: `Perpetrator ${payload.perp_name}` });
    }
  }
  if (!payload.warning_marker_ids) payload.warning_marker_ids = randomSubset(warningMarkerIds);
  return { payload, stagedPhotos };
};

const buildDevices = async () => {
  await ensureCasePhotosLoaded();
  simState.devices = [];
  simState.createdCases = [];
  simState.timeouts = [];
  for (let i=0;i<config.deviceCount;i++) {
    const org = getRandom(simState.organisations);
    const base = sampleBaseLocation(org);
    const location = move(base);
    const organisationId = org ? org.id : undefined;
    const deviceId = randomPhone();
    const { payload, stagedPhotos } = createCasePayload(organisationId, deviceId);
    let created;
    try {
      created = await apiFetch('/api/cases', { method: 'POST', body: JSON.stringify(payload) });
    } catch (caseErr) {
      console.error('Case creation failed', caseErr, payload);
      // Handle 503 errors - case may have been created despite the error
      if (caseErr.status === 503) {
        console.warn(`Got 503 for device ${deviceId}, checking if case was created...`);
        try {
          // Search for the case by device ID
          const casesResponse = await apiFetch(`/api/cases?search=${encodeURIComponent(deviceId)}&limit=10`);
          if (casesResponse && casesResponse.items && casesResponse.items.length > 0) {
            // Find the most recent case with matching device
            const matchingCase = casesResponse.items.find(c => c.device === deviceId);
            if (matchingCase) {
              console.info(`Found existing case ${matchingCase.id} for device ${deviceId}, continuing with enrollment`);
              created = matchingCase;
            } else {
              logSimulatorError(`Case creation failed for ${deviceId}: HTTP 503, no matching case found`);
              continue;
            }
          } else {
            logSimulatorError(`Case creation failed for ${deviceId}: HTTP 503, no case found`);
            continue;
          }
        } catch (searchErr) {
          console.error('Failed to search for case after 503', searchErr);
          logSimulatorError(`Case creation failed for ${deviceId}: HTTP 503, search failed: ${searchErr.message}`);
          continue;
        }
      } else {
        logSimulatorError(`Case creation failed for ${deviceId}: ${caseErr.message}`);
        continue;
      }
    }
    const caseId = created.case?.id ?? created.id;
    if (caseId) {
      trackCaseForCleanup({ caseId, deviceId, teardownMode: config.teardownMode });
      simState.createdCases.push(caseId);
    }
    const activationCode = created.activation_code ?? created.case?.activation_code;
    if (!activationCode || !caseId) {
      logSimulatorError(`Case response missing id/PIN for ${deviceId}`);
      continue;
    }
    if (stagedPhotos.length) {
      await uploadCasePhotosBestEffort(caseId, stagedPhotos, deviceId);
    }
    let enroll;
    try {
      enroll = await apiFetch('/api/devices/enroll', { method: 'POST', body: JSON.stringify({ device_id: deviceId, pin: activationCode }) });
    } catch (enrollErr) {
      console.error('Enrollment failed', enrollErr, deviceId, activationCode);
      logSimulatorError(`Enrollment failed for ${deviceId}: ${enrollErr.message}`);
      continue;
    }
    if (!enroll || !enroll.api_key) {
      logSimulatorError(`Enrollment returned no API key for ${deviceId}`);
      continue;
    }
    const device = {
      caseId,
      deviceId,
      apiKey: enroll.api_key,
      location,
      base,
      updates: 0,
      isActive: false,
      activeBurstEnd: 0
    };
    simState.devices.push(device);
    if (config.caseDelayMs > 0) {
      await sleep(config.caseDelayMs);
    }
  }
};
const startDeviceLoops = () => {
  const initialDelayMs = Math.max(0, config.caseDelayMs) || 0;
  const step = 15;
  const maxJitter = 25;
  simState.devices.forEach((device, index) => {
    const delay = initialDelayMs + index * step + Math.random() * maxJitter;
    const timer = setTimeout(() => {
      if (!simState.running) return;
      schedule(device, 0);
    }, delay);
    simState.timeouts.push(timer);
  });
};

const clearTimers = () => {
  simState.timeouts.forEach(clearTimeout);
  simState.timeouts = [];
};

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const errorLogEl = document.getElementById('error-log');

const extractCaseStatus = (caseResponse) => {
  if (!caseResponse || typeof caseResponse !== 'object') return '';
  const source = caseResponse.case && typeof caseResponse.case === 'object' ? caseResponse.case : caseResponse;
  return typeof source.status === 'string' ? source.status.trim().toLowerCase() : '';
};
const updateCaseStatus = async (caseId, status) => {
  await apiFetch(`/api/cases/${caseId}`, { method: 'PATCH', body: JSON.stringify({ status, enrollment: 0 }) });
};
const executeTeardownForCase = async (caseId, teardownMode = 'delete') => {
  let caseStatus = '';
  try {
    const caseResponse = await apiFetch(`/api/cases/${caseId}`);
    caseStatus = extractCaseStatus(caseResponse);
  } catch (err) {
    if (err.status === 404) return;
    throw err;
  }
  if (caseStatus === 'open') {
    await updateCaseStatus(caseId, 'Closed');
    caseStatus = 'closed';
  }
  if (caseStatus === 'closed') {
    await updateCaseStatus(caseId, 'Archived');
    caseStatus = 'archived';
  }
  if (teardownMode === 'archive') {
    return;
  }
  if (caseStatus === 'archived' || !caseStatus) {
    try {
      await apiFetch(`/api/cases/${caseId}`, { method: 'DELETE' });
    } catch (err) {
      if (err.status !== 404) throw err;
    }
  }
};

const teardownCases = async (entries) => {
  const failures = [];
  const dedupedTargets = [];
  const seen = new Set();
  entries.forEach((entry) => {
    const key = `${entry.baseUrl}:${entry.caseId}`;
    if (seen.has(key)) return;
    seen.add(key);
    dedupedTargets.push(entry);
  });
  for (const entry of dedupedTargets) {
    try {
      await executeTeardownForCase(entry.caseId, entry.teardownMode || config.teardownMode || 'delete');
      markCaseTeardownStatus(entry.caseId, 'teardown_done', '', entry.baseUrl);
    } catch (err) {
      console.error(`Teardown failed for case ${entry.caseId}`, err);
      failures.push(entry.caseId);
      markCaseTeardownStatus(entry.caseId, 'teardown_failed', err.message, entry.baseUrl);
    }
  }
  pruneCompletedCases();
  return failures;
};

const stopSimulation = async () => {
  if (!simState.running) return;
  simState.running = false;
  clearTimers();
  ui.loginStatus.textContent = 'Stopping simulation...';
  const pendingEntries = getPersistedTeardownEntries();
  const failures = await teardownCases(pendingEntries);
  simState.createdCases = [];
  simState.failedTeardowns = failures;
  syncPersistedTeardownState();
  if (failures.length) {
    ui.loginStatus.textContent = `${failures.length} case(s) still need cleanup; hit Retry Failed Teardowns.`;
  } else {
    ui.loginStatus.textContent = 'Simulation stopped';
  }
  ui.start.disabled = false;
  ui.stop.disabled = true;
};

const retryFailedTeardowns = async () => {
  const pendingEntries = getPersistedTeardownEntries();
  if (!pendingEntries.length) return;
  ui.loginStatus.textContent = 'Retrying failed teardowns...';
  ui.retryTeardown.disabled = true;
  const failures = await teardownCases(pendingEntries);
  simState.failedTeardowns = failures;
  syncPersistedTeardownState();
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
  syncPersistedTeardownState();
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
  const caseDelayMs = Math.max(0, parseInt(document.getElementById('case-delay').value,10) || 0);
  config = {
    deviceCount: parseInt(document.getElementById('device-count').value,10) || 200,
    updateMinMs: minMs,
    updateMaxMs: maxMs,
    activationChance: activeRatio,
    activeIntervalMs: activeIntervalMs,
    activeDurationMs,
    teardownMode,
    caseDelayMs
  };
  simState.running = true;
  simState.stats = { total: config.deviceCount, active:0, errors:0 };
  simState.errorLog = [];
  updateErrorLog();
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
  const code = document.getElementById('sim-code').value.trim();
  const body = {
    email: document.getElementById('sim-email').value,
    password: document.getElementById('sim-password').value
  };
  if (code) {
    body.code = code;
  }
  try {
    await apiFetch('/api/auth/login', { method: 'POST', body: JSON.stringify(body) });
    ui.loginStatus.textContent = 'Authenticated';
    isAuthenticated = true;
    ui.start.disabled = false;
    const pendingEntries = syncPersistedTeardownState();
    if (pendingEntries.length) {
      ui.loginStatus.textContent = `Authenticated (${pendingEntries.length} persisted case(s) pending cleanup)`;
    }
    let orgResponse = [];
    try {
      const list = await apiFetch('/api/organisations?limit=1000');
      orgResponse = normaliseOrganisationList(list);
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

    // Load master data (genders, languages, etc.)
    await fetchMasterData();
    console.info(`Status update - orgs: ${simState.organisations.length}, genders: ${masterData.genders.length}, langs: ${masterData.languages.length}`);
    if (!simState.organisations.length) {
      ui.loginStatus.textContent = 'No accessible organisations';
      isAuthenticated = false;
      ui.start.disabled = true;
    } else {
      const geocentredCount = simState.organisations.filter((org) => !!getOrganisationGeoCenter(org)).length;
      const genderCount = masterData.genders.length;
      const langCount = masterData.languages.length;
      const masterDataSummary = `${genderCount} genders, ${langCount} langs`;
      const statusText = pendingEntries.length 
        ? `Authenticated (${pendingEntries.length} persisted case(s) pending cleanup, ${geocentredCount}/${simState.organisations.length} org geocenters, ${photoInventorySummary()}, ${masterDataSummary})`
        : `Authenticated (${geocentredCount}/${simState.organisations.length} org geocenters, ${photoInventorySummary()}, ${masterDataSummary})`;
      console.info('Setting status:', statusText);
      ui.loginStatus.textContent = statusText;
      if (geocentredCount === 0 && simState.organisations.length) {
        console.warn('No organisation geocenters found. Sample org payload:', simState.organisations[0]);
        logSimulatorError('No organisation geocenters detected; using fallback random clusters.');
      }
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
