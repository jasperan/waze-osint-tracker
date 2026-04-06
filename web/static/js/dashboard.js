// === HTML Escape Helper (XSS prevention) ===
function escapeHTML(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// === GridStack Initialization ===
const grid = GridStack.init({
    column: 12,
    cellHeight: 40,
    margin: 6,
    float: true,
    animate: true,
    draggable: { handle: '.widget-header' },
    resizable: { handles: 'e,se,s,sw,w' },
    acceptWidgets: true,
    removable: false,
});

// === Widget System ===

function createWidget(id, title, contentHTML, gridOpts) {
    const actions = `
        <div class="widget-header-actions">
            <button onclick="minimizeWidget('${id}')" title="Minimize">_</button>
            <button onclick="expandWidget('${id}')" title="Expand">&#x25A1;</button>
            <button onclick="closeWidget('${id}')" title="Close">&times;</button>
        </div>`;
    const html = `
        <div class="widget-panel" id="widget-${id}">
            <div class="widget-header">
                <h3>${title}</h3>
                ${actions}
            </div>
            <div class="widget-body">${contentHTML}</div>
        </div>`;

    grid.addWidget({
        id: id,
        content: html,
        ...gridOpts,
    });
}

// Widget content registry
const WIDGET_CONTENT = {
    'stats': () => `
        <div class="stat-row">
            <span class="stat-label">Total Events</span>
            <div class="stat-right">
                <canvas class="sparkline" id="spark-events"></canvas>
                <span class="stat-value" id="stat-total">--</span>
                <span class="stat-delta" id="delta-total"></span>
            </div>
        </div>
        <div class="stat-row">
            <span class="stat-label">Unique Users</span>
            <div class="stat-right">
                <span class="stat-value" id="stat-users">--</span>
            </div>
        </div>
        <div class="stat-row">
            <span class="stat-label">Date Range</span>
            <div class="stat-right">
                <span class="stat-value" id="stat-time">--</span>
            </div>
        </div>
        <div class="stat-row">
            <span class="stat-label">Events/Hour</span>
            <div class="stat-right">
                <canvas class="sparkline" id="spark-rate"></canvas>
                <span class="stat-value" id="stat-rate">--</span>
                <span class="stat-delta" id="delta-rate"></span>
            </div>
        </div>
    `,
    'leaderboard': () => `<div class="leaderboard" id="leaderboard"></div>`,
    'feed': () => `
        <div class="feed-header-bar">
            <span class="live-indicator"><span class="live-dot"></span> LIVE</span>
            <span id="connection-status-feed">Connecting...</span>
        </div>
        <div class="feed-items" id="feed-items"></div>
    `,
    'filters': () => `
        <div class="filter-group">
            <label>Region</label>
            <select id="filter-region" onchange="onFilterChange()">
                <option value="">All Regions</option>
                <option value="europe">Europe</option>
                <option value="americas">Americas</option>
                <option value="asia">Asia</option>
                <option value="oceania">Oceania</option>
                <option value="africa">Africa</option>
            </select>
        </div>
        <div class="filter-group">
            <label>Time Range</label>
            <select id="filter-time" onchange="onFilterChange()">
                <option value="">All Data</option>
                <option value="1">Last Hour</option>
                <option value="6">Last 6 Hours</option>
                <option value="24">Last 24 Hours</option>
                <option value="168">Last Week</option>
                <option value="custom">Custom Range</option>
            </select>
        </div>
        <div class="filter-group" id="date-range-group" style="display: none;">
            <label>From</label>
            <input type="date" id="filter-date-from" onchange="onFilterChange()">
            <label style="margin-top: 8px;">To</label>
            <input type="date" id="filter-date-to" onchange="onFilterChange()">
        </div>
        <div class="filter-group">
            <label>Event Type</label>
            <div class="type-filters" id="type-filters"></div>
        </div>
        <div class="filter-group">
            <label>Track User</label>
            <div style="position: relative;">
                <input type="text" id="user-search" placeholder="Search username..."
                       autocomplete="off" oninput="searchUsers(this.value)" onfocus="showUserDropdown()"
                       onkeydown="if(event.key==='Enter'){event.preventDefault();const v=this.value.trim();if(v)selectUser(v);}">
                <div id="user-dropdown" class="user-dropdown" style="display: none;"></div>
            </div>
            <div id="selected-user" class="selected-user" style="display: none;">
                <span id="selected-user-name"></span>
                <button class="btn-clear" onclick="clearUserFilter()">&times;</button>
            </div>
        </div>
        <div style="margin-top: 12px;">
            <button class="btn btn-ghost btn-small" onclick="resetFilters()">Reset All</button>
        </div>
    `,
    'display': () => `
        <div class="filter-group">
            <label class="checkbox-label">
                <input type="checkbox" id="show-heatmap" checked onchange="toggleHeatmap()">
                Heatmap Layer
            </label>
        </div>
        <div class="filter-group">
            <label class="checkbox-label">
                <input type="checkbox" id="show-markers" onchange="toggleMarkers()">
                Event Markers
            </label>
        </div>
        <div class="filter-group">
            <label class="checkbox-label">
                <input type="checkbox" id="auto-follow" checked>
                Auto-Follow Events
            </label>
            <div class="auto-follow-info" id="auto-follow-info">
                Teleports every 10s
            </div>
        </div>
        <div class="filter-group">
            <label class="checkbox-label">
                <input type="checkbox" id="sound-enabled">
                Sound Notifications
            </label>
        </div>
    `,
};

// === Tabbed Widget System ===

function createTabbedWidget(id, title, tabs, gridOpts) {
  const tabsHTML = tabs.map((t, i) =>
    `<button class="widget-tab${i === 0 ? ' active' : ''}" data-tab="${t.id}" onclick="switchWidgetTab('${id}', '${t.id}')">${t.label}</button>`
  ).join('');
  const panelsHTML = tabs.map((t, i) =>
    `<div class="tab-panel${i === 0 ? ' active' : ''}" id="tab-${id}-${t.id}">${t.content}</div>`
  ).join('');
  const contentHTML = `
    <div class="widget-tabs">${tabsHTML}</div>
    <div class="tab-panels">${panelsHTML}</div>
  `;
  createWidget(id, title, contentHTML, gridOpts);
}

function switchWidgetTab(widgetId, tabId) {
  const widget = document.getElementById(`widget-${widgetId}`);
  if (!widget) return;
  widget.querySelectorAll('.widget-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tabId));
  widget.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === `tab-${widgetId}-${tabId}`));
}

WIDGET_CONTENT['intel'] = () => ''; // placeholder - content provided by createTabbedWidget

// === New Widget Content (Tasks 10-15) ===

WIDGET_CONTENT['detail-map'] = () => '<div id="detail-map-container" style="width:100%;height:100%;min-height:200px"></div>';

WIDGET_CONTENT['collector'] = () => `
  <div id="collector-status">
    <div class="collector-regions" id="collector-regions"></div>
    <div class="collector-summary" style="margin-top:8px;border-top:1px solid var(--border);padding-top:8px">
      <div class="stat-row"><span class="stat-label">Events/min</span><span class="stat-value" id="coll-rate">--</span></div>
      <div class="stat-row"><span class="stat-label">Last Scan</span><span class="stat-value" id="coll-last">--</span></div>
    </div>
  </div>
`;

WIDGET_CONTENT['alerts'] = () => '<div class="alerts-feed" id="alerts-feed">Loading alerts...</div>';

WIDGET_CONTENT['type-breakdown'] = () => `
  <div id="type-breakdown">
    <div class="type-bar-chart" id="type-bar-chart"></div>
    <div class="type-list" id="type-list">Loading...</div>
  </div>
`;

WIDGET_CONTENT['privacy'] = () => '<div class="privacy-list" id="privacy-list">Loading risk scores...</div>';

WIDGET_CONTENT['social-graph'] = () => '<div id="social-graph-container" style="width:100%;height:100%;min-height:300px;position:relative"></div>';

WIDGET_CONTENT['encounter-map'] = () => `
  <div id="encounter-controls" style="display:flex;gap:8px;padding:4px 8px;font-size:0.7rem;align-items:center">
    <label style="color:var(--text-secondary)">Day:</label>
    <select id="encounter-day" style="background:var(--bg-deep);color:var(--text-primary);border:1px solid var(--border);border-radius:4px;padding:2px 4px;font-size:0.7rem">
      <option value="">All</option>
      <option value="0">Mon</option><option value="1">Tue</option><option value="2">Wed</option>
      <option value="3">Thu</option><option value="4">Fri</option><option value="5">Sat</option><option value="6">Sun</option>
    </select>
    <label style="color:var(--text-secondary)">Hour:</label>
    <input type="range" id="encounter-hour" min="-1" max="23" value="-1" style="width:80px">
    <span id="encounter-hour-label" style="color:var(--text-muted);min-width:30px">All</span>
    <label style="color:var(--text-secondary);margin-left:auto"><input type="checkbox" id="encounter-layer-toggle" checked> Show</label>
  </div>
  <div id="encounter-info" style="padding:4px 8px;font-size:0.7rem;color:var(--text-secondary)">Loading encounter data...</div>
`;

// === Deck Preset System ===

const DECK_PRESETS = {
    live: {
        name: 'Live Collection',
        icon: '\u25C9',
        widgets: [
            { id: 'stats', title: 'Statistics', x: 0, y: 0, w: 3, h: 5 },
            { id: 'feed', title: 'Live Feed', x: 0, y: 5, w: 3, h: 8 },
            { id: 'display', title: 'Display', x: 9, y: 0, w: 3, h: 4 },
            { id: 'collector', title: 'Collector Status', x: 9, y: 4, w: 3, h: 5 },
            { id: 'alerts', title: 'System Alerts', x: 9, y: 9, w: 3, h: 4 },
        ],
        layers: ['heatmap'],
        mapView: { center: [45, 10], zoom: 4 },
    },
    intel: {
        name: 'User Intelligence',
        icon: '\u25C8',
        widgets: [
            { id: 'filters', title: 'Filters', x: 0, y: 0, w: 3, h: 6 },
            { id: 'intel-panel', title: 'Intelligence', x: 0, y: 6, w: 3, h: 7,
              tabs: [
                { id: 'live', label: 'LIVE', contentId: 'feed' },
                { id: 'users', label: 'TOP USERS', contentId: 'leaderboard' },
              ]
            },
            { id: 'display', title: 'Display', x: 9, y: 0, w: 3, h: 4 },
            { id: 'social-graph', title: 'Social Network', x: 3, y: 0, w: 6, h: 7 },
            { id: 'encounter-map', title: 'Encounter Predictions', x: 9, y: 4, w: 3, h: 5 },
        ],
        layers: ['markers'],
        mapView: { center: [45, 10], zoom: 4 },
    },
    analytics: {
        name: 'Traffic Analytics',
        icon: '\u25A3',
        widgets: [
            { id: 'stats', title: 'Statistics', x: 0, y: 0, w: 4, h: 5 },
            { id: 'filters', title: 'Filters', x: 8, y: 0, w: 4, h: 5 },
            { id: 'type-breakdown', title: 'Event Types', x: 0, y: 5, w: 4, h: 6 },
            { id: 'feed', title: 'Live Feed', x: 8, y: 5, w: 4, h: 6 },
            { id: 'detail-map', title: 'Detail Map', x: 8, y: 11, w: 4, h: 6 },
        ],
        layers: ['heatmap', 'markers'],
        mapView: { center: [30, 0], zoom: 3 },
    },
    risk: {
        name: 'Privacy Risk',
        icon: '\u25B2',
        widgets: [
            { id: 'privacy', title: 'Privacy Risks', x: 0, y: 0, w: 3, h: 8 },
            { id: 'stats', title: 'Statistics', x: 0, y: 8, w: 3, h: 5 },
            { id: 'feed', title: 'Live Feed', x: 9, y: 0, w: 3, h: 6 },
        ],
        layers: ['markers'],
        mapView: { center: [45, 10], zoom: 4 },
    },
};

let currentDeck = 'live';

function initDeckSelector() {
    const container = document.getElementById('deck-selector');
    if (!container) return;
    Object.entries(DECK_PRESETS).forEach(([key, deck]) => {
        const btn = document.createElement('button');
        btn.className = 'deck-btn' + (key === 'live' ? ' active' : '');
        btn.dataset.deck = key;
        btn.innerHTML = `<span class="deck-icon">${deck.icon}</span> ${deck.name}`;
        btn.onclick = () => switchDeck(key);
        container.appendChild(btn);
    });
}

function switchDeck(deckKey) {
    const deck = DECK_PRESETS[deckKey];
    if (!deck) return;
    currentDeck = deckKey;

    // Update active button
    document.querySelectorAll('.deck-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`.deck-btn[data-deck="${deckKey}"]`)?.classList.add('active');

    // Clear all widgets
    grid.removeAll();

    // Add widgets for this deck
    deck.widgets.forEach(w => {
        if (w.tabs) {
            createTabbedWidget(w.id, w.title, w.tabs.map(t => ({
                id: t.id,
                label: t.label,
                content: WIDGET_CONTENT[t.contentId] ? WIDGET_CONTENT[t.contentId]() : '',
            })), { x: w.x, y: w.y, w: w.w, h: w.h });
        } else {
            const contentFn = WIDGET_CONTENT[w.id];
            if (contentFn) {
                createWidget(w.id, w.title, contentFn(), { x: w.x, y: w.y, w: w.w, h: w.h });
            }
        }
    });

    // Set map layers via layer bar if available
    if (typeof setMapLayers === 'function') {
      setMapLayers(deck.layers || []);
    } else {
      const showHeatmap = deck.layers.includes('heatmap');
      const showMarkers = deck.layers.includes('markers');

      const heatmapCheckbox = document.getElementById('show-heatmap');
      const markersCheckbox = document.getElementById('show-markers');
      if (heatmapCheckbox) heatmapCheckbox.checked = showHeatmap;
      if (markersCheckbox) markersCheckbox.checked = showMarkers;

      if (showHeatmap) loadHeatmap();
      else if (heatLayer) { map.removeLayer(heatLayer); }

      if (showMarkers) loadMarkers();
      else { markersLayer.clearLayers(); }
    }

    // Animate map view
    if (deck.mapView) {
        map.flyTo(deck.mapView.center, deck.mapView.zoom, { duration: 1.5 });
    }

    // Reload data
    loadStats();
    loadLeaderboard();
    if (typeof loadTypes === 'function') loadTypes();

    // Load data for new widgets
    if (deck.widgets.some(w => w.id === 'collector')) loadCollectorStatus();
    if (deck.widgets.some(w => w.id === 'alerts')) loadAlerts();
    if (deck.widgets.some(w => w.id === 'type-breakdown')) loadTypeBreakdown();
    if (deck.widgets.some(w => w.id === 'privacy')) loadPrivacyLeaderboard();
    if (deck.widgets.some(w => w.id === 'detail-map')) initDetailMap();
    if (deck.widgets.some(w => w.id === 'social-graph') && window.WazeDash?.socialGraph) window.WazeDash.socialGraph.init('social-graph-container');
    if (deck.widgets.some(w => w.id === 'encounter-map') && window.WazeDash?.encounterMap) window.WazeDash.encounterMap.init('encounter-controls');

    // Re-render Leaflet map after GridStack layout changes
    setTimeout(() => map.invalidateSize(), 200);
}

// === Widget Actions ===

function minimizeWidget(id) {
    const el = document.querySelector(`.grid-stack-item[gs-id="${id}"]`);
    if (!el) return;
    const body = el.querySelector('.widget-body');
    if (body.style.display === 'none') {
        body.style.display = '';
        grid.update(el, { h: el._gsOrigH || 5 });
    } else {
        el._gsOrigH = +el.getAttribute('gs-h');
        body.style.display = 'none';
        grid.update(el, { h: 2 });
    }
}

function expandWidget(id) {
    const el = document.querySelector(`.grid-stack-item[gs-id="${id}"]`);
    if (!el) return;
    if (el._gsExpanded) {
        grid.update(el, el._gsOrigPos);
        el._gsExpanded = false;
    } else {
        el._gsOrigPos = {
            x: +el.getAttribute('gs-x'), y: +el.getAttribute('gs-y'),
            w: +el.getAttribute('gs-w'), h: +el.getAttribute('gs-h')
        };
        grid.update(el, { x: 0, y: 0, w: 12, h: 10 });
        el._gsExpanded = true;
    }
}

function closeWidget(id) {
    const el = document.querySelector(`.grid-stack-item[gs-id="${id}"]`);
    if (el) grid.removeWidget(el);
}

// === Map Initialization ===
const map = L.map('map', { zoomControl: false }).setView([45, 10], 4);
L.control.zoom({ position: 'bottomleft' }).addTo(map);

L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '',
    maxZoom: 19,
    opacity: 0.8
}).addTo(map);

// Layers
let heatLayer = null;
let markersLayer = L.layerGroup().addTo(map);

// Current filter state
let currentFilters = {
    type: null,
    subtype: null,
    since: null,
    dateFrom: null,
    dateTo: null,
    user: null,
    region: null
};

// User search debounce timer
let userSearchTimer = null;

// Event type colors (cyber theme)
const typeColors = {
    'POLICE': '#3b82f6',
    'JAM': '#f97316',
    'HAZARD': '#facc15',
    'ROAD_CLOSED': '#8b5cf6',
    'ACCIDENT': '#ef4444',
    'CONSTRUCTION': '#64748b'
};

// === Type Badge Config ===
const TYPE_BADGES = {
  ACCIDENT:    { color: '#f87171', bg: 'rgba(248,113,113,0.12)', label: 'ACC' },
  HAZARD:      { color: '#fb923c', bg: 'rgba(251,146,60,0.12)',  label: 'HAZ' },
  JAM:         { color: '#fbbf24', bg: 'rgba(251,191,36,0.12)',  label: 'JAM' },
  POLICE:      { color: '#3b82f6', bg: 'rgba(59,130,246,0.12)',  label: 'POL' },
  ROAD_CLOSED: { color: '#a78bfa', bg: 'rgba(167,139,250,0.12)', label: 'RCL' },
  CHIT_CHAT:   { color: '#34d399', bg: 'rgba(52,211,153,0.12)',  label: 'CHT' },
};

function formatTimeAgo(timestamp) {
  if (!timestamp) return '--';
  const diff = Date.now() - new Date(timestamp).getTime();
  if (diff < 0) return 'just now';
  if (diff < 60000) return 'just now';
  if (diff < 3600000) return `${Math.floor(diff/60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff/3600000)}h ago`;
  return `${Math.floor(diff/86400000)}d ago`;
}

// Auto-follow throttling (teleport max once per 10 seconds)
let lastTeleportTime = 0;
const TELEPORT_INTERVAL = 10000;
let pendingTeleport = null;

// Sound notification
const notificationSound = new Audio('data:audio/wav;base64,UklGRl9vT19XQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YU' + 'tvT18'.repeat(100));

function playNotificationSound() {
    const soundEnabled = document.getElementById('sound-enabled');
    if (soundEnabled && soundEnabled.checked) {
        notificationSound.volume = 0.3;
        notificationSound.play().catch(() => {});
    }
}

// === Data Loading Functions ===

async function loadStats() {
    try {
        const res = await fetch('/api/stats');
        const stats = await res.json();
        document.getElementById('stat-total').textContent = stats.total_events.toLocaleString();
        document.getElementById('stat-users').textContent = stats.unique_users.toLocaleString();
        if (stats.first_event && stats.last_event) {
            const first = stats.first_event.substring(0, 7);
            const last = stats.last_event.substring(0, 7);
            document.getElementById('stat-time').textContent = first === last ? first : `${first} — ${last}`;
        }
    } catch (err) {
        console.error('Failed to load stats:', err);
    }
}

// === Sparkline Renderer ===

function drawSparkline(canvas, data, color) {
  if (!canvas || !data || data.length < 2) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.offsetWidth;
  const h = canvas.offsetHeight;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  ctx.scale(dpr, dpr);
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const range = max - min || 1;
  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.lineJoin = 'round';
  ctx.beginPath();
  data.forEach((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * (h - 4) - 2;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();
  // Fill area under curve
  ctx.lineTo(w, h);
  ctx.lineTo(0, h);
  ctx.closePath();
  ctx.fillStyle = color.replace(')', ',0.08)').replace('rgb', 'rgba');
  ctx.fill();
}

async function loadSparklines() {
  try {
    const res = await fetch('/api/timeline?hours=24&buckets=24');
    const data = await res.json();
    if (!data.buckets) return;
    const counts = data.buckets.map(b => b.count);

    const evtCanvas = document.getElementById('spark-events');
    if (evtCanvas) drawSparkline(evtCanvas, counts, '#e8a817');

    const rateCanvas = document.getElementById('spark-rate');
    if (rateCanvas) drawSparkline(rateCanvas, counts, '#3b82f6');

    // Calculate delta (last hour vs previous hour)
    if (counts.length >= 2) {
      const lastHour = counts[counts.length - 1] || 0;
      const prevHour = counts[counts.length - 2] || 1;
      const delta = ((lastHour - prevHour) / Math.max(prevHour, 1) * 100).toFixed(1);
      const deltaEl = document.getElementById('delta-total');
      if (deltaEl) {
        deltaEl.textContent = `${delta > 0 ? '+' : ''}${delta}%`;
        deltaEl.className = 'stat-delta ' + (delta >= 0 ? 'delta-up' : 'delta-down');
      }
    }

    // Update events/hour stat
    const totalEvents = counts.reduce((a, b) => a + b, 0);
    const rateEl = document.getElementById('stat-rate');
    if (rateEl) rateEl.textContent = (totalEvents / Math.max(counts.length, 1)).toFixed(1);
  } catch (err) {
    console.error('Failed to load sparklines:', err);
  }
}

async function loadTypes() {
    try {
        const res = await fetch('/api/types');
        const types = await res.json();
        const container = document.getElementById('type-filters');
        container.innerHTML = '';

        types.forEach(t => {
            const color = typeColors[t.type] || '#64748b';
            const hasSubtypes = t.subtypes && t.subtypes.length > 0;

            const group = document.createElement('div');
            group.className = 'type-group';

            const header = document.createElement('div');
            header.className = 'type-group-header';

            if (hasSubtypes) {
                const expandBtn = document.createElement('button');
                expandBtn.className = 'type-expand';
                expandBtn.innerHTML = '▶';
                expandBtn.dataset.type = t.type;
                expandBtn.onclick = (e) => {
                    e.stopPropagation();
                    toggleSubtypes(expandBtn);
                };
                header.appendChild(expandBtn);
            }

            const chip = document.createElement('div');
            chip.className = 'type-chip';
            chip.dataset.type = t.type;
            chip.innerHTML = `<span class="dot" style="background: ${color}"></span>${t.type}<span class="count">${t.count.toLocaleString()}</span>`;
            chip.onclick = () => selectType(chip);
            header.appendChild(chip);

            group.appendChild(header);

            if (hasSubtypes) {
                const subtypesContainer = document.createElement('div');
                subtypesContainer.className = 'subtypes-container';
                subtypesContainer.dataset.parentType = t.type;

                t.subtypes.forEach(st => {
                    const subChip = document.createElement('div');
                    subChip.className = 'subtype-chip';
                    subChip.dataset.type = t.type;
                    subChip.dataset.subtype = st.subtype;
                    const displayName = st.subtype.replace(t.type + '_', '').replace(/_/g, ' ');
                    subChip.innerHTML = `<span class="dot" style="background: ${color}"></span>${displayName}<span class="count">${st.count.toLocaleString()}</span>`;
                    subChip.onclick = () => selectSubtype(subChip);
                    subtypesContainer.appendChild(subChip);
                });

                group.appendChild(subtypesContainer);
            }

            container.appendChild(group);
        });
    } catch (err) {
        console.error('Failed to load types:', err);
    }
}

// Toggle subtypes visibility
function toggleSubtypes(expandBtn) {
    const type = expandBtn.dataset.type;
    const subtypesContainer = document.querySelector(`.subtypes-container[data-parent-type="${type}"]`);

    if (subtypesContainer) {
        const isExpanded = subtypesContainer.classList.contains('expanded');
        subtypesContainer.classList.toggle('expanded');
        expandBtn.classList.toggle('expanded');
        expandBtn.innerHTML = isExpanded ? '▶' : '▼';
    }
}

// Select a single type (exclusive selection)
function selectType(chip) {
    const wasActive = chip.classList.contains('active');

    document.querySelectorAll('.type-chip, .subtype-chip').forEach(c => c.classList.remove('active'));

    if (!wasActive) {
        chip.classList.add('active');
        currentFilters.type = chip.dataset.type;
        currentFilters.subtype = null;
    } else {
        currentFilters.type = null;
        currentFilters.subtype = null;
    }

    applyFilters();
}

// Select a subtype
function selectSubtype(chip) {
    const wasActive = chip.classList.contains('active');

    document.querySelectorAll('.type-chip, .subtype-chip').forEach(c => c.classList.remove('active'));

    if (!wasActive) {
        chip.classList.add('active');
        currentFilters.type = chip.dataset.type;
        currentFilters.subtype = chip.dataset.subtype;
    } else {
        currentFilters.type = null;
        currentFilters.subtype = null;
    }

    applyFilters();
}

// Handle filter changes
function onFilterChange() {
    const timeValue = document.getElementById('filter-time').value;
    const regionValue = document.getElementById('filter-region').value;
    const dateRangeGroup = document.getElementById('date-range-group');

    currentFilters.region = regionValue || null;

    if (timeValue === 'custom') {
        dateRangeGroup.style.display = 'block';
        currentFilters.since = null;
        currentFilters.dateFrom = document.getElementById('filter-date-from').value || null;
        currentFilters.dateTo = document.getElementById('filter-date-to').value || null;
    } else {
        dateRangeGroup.style.display = 'none';
        currentFilters.since = timeValue || null;
        currentFilters.dateFrom = null;
        currentFilters.dateTo = null;
    }

    applyFilters();
}

// Apply all filters
function applyFilters() {
    loadHeatmap();
    if (document.getElementById('show-markers').checked) {
        loadMarkers();
    }
    loadStats();
}

// Reset filters
function resetFilters() {
    document.getElementById('filter-region').value = '';
    document.getElementById('filter-time').value = '';
    document.getElementById('filter-date-from').value = '';
    document.getElementById('filter-date-to').value = '';
    document.getElementById('date-range-group').style.display = 'none';
    document.getElementById('user-search').value = '';
    document.getElementById('selected-user').style.display = 'none';
    document.querySelectorAll('.type-chip.active, .subtype-chip.active').forEach(c => c.classList.remove('active'));
    document.querySelectorAll('.subtypes-container').forEach(c => c.classList.remove('expanded'));
    document.querySelectorAll('.type-expand').forEach(c => {
        c.classList.remove('expanded');
        c.innerHTML = '▶';
    });

    currentFilters = { type: null, subtype: null, since: null, dateFrom: null, dateTo: null, user: null, region: null };
    applyFilters();
    loadStats();
}

// Build URL with current filters
function buildFilterUrl(baseUrl) {
    let url = baseUrl + '?';
    if (currentFilters.type) url += `type=${currentFilters.type}&`;
    if (currentFilters.subtype) url += `subtype=${encodeURIComponent(currentFilters.subtype)}&`;
    if (currentFilters.since) url += `since=${currentFilters.since}&`;
    if (currentFilters.dateFrom) url += `from=${currentFilters.dateFrom}&`;
    if (currentFilters.dateTo) url += `to=${currentFilters.dateTo}&`;
    if (currentFilters.user) url += `user=${encodeURIComponent(currentFilters.user)}&`;
    if (currentFilters.region) url += `region=${currentFilters.region}&`;
    return url;
}

// === User Search ===

async function searchUsers(query) {
    clearTimeout(userSearchTimer);
    userSearchTimer = setTimeout(async () => {
        const dropdown = document.getElementById('user-dropdown');
        if (!query || query.length < 2) {
            dropdown.style.display = 'none';
            return;
        }

        try {
            const res = await fetch(`/api/users?q=${encodeURIComponent(query)}&limit=20`);
            const users = await res.json();

            if (users.length > 0) {
                dropdown.innerHTML = users.map(u =>
                    `<div class="user-option" onclick="selectUser('${escapeHTML(u.username).replace(/'/g, "\\'")}')">
                        <span>${escapeHTML(u.username)}</span>
                        <span class="count">${u.count} events</span>
                    </div>`
                ).join('');
                dropdown.style.display = 'block';
            } else {
                dropdown.innerHTML = '<div class="user-option" style="color:var(--text-muted)">No users found</div>';
                dropdown.style.display = 'block';
            }
        } catch (err) {
            console.error('User search failed:', err);
        }
    }, 300);
}

function showUserDropdown() {
    const input = document.getElementById('user-search');
    if (input.value.length >= 2) {
        document.getElementById('user-dropdown').style.display = 'block';
    }
}

function selectUser(username) {
    currentFilters.user = username;

    document.getElementById('user-search').value = '';
    document.getElementById('user-dropdown').style.display = 'none';
    document.getElementById('selected-user').style.display = 'flex';
    document.getElementById('selected-user-name').textContent = username;

    applyFilters();

    document.getElementById('status-text').textContent = 'Tracking user: ' + username;
}

function clearUserFilter() {
    currentFilters.user = null;
    document.getElementById('selected-user').style.display = 'none';
    document.getElementById('user-search').value = '';
    applyFilters();
}

// Hide dropdown when clicking outside
document.addEventListener('click', (e) => {
    if (!e.target.closest('#user-search') && !e.target.closest('#user-dropdown')) {
        document.getElementById('user-dropdown').style.display = 'none';
    }
});

// === Map Data Functions ===

async function loadHeatmap() {
    try {
        const url = buildFilterUrl('/api/heatmap');
        const res = await fetch(url);
        const data = await res.json();

        if (heatLayer) {
            map.removeLayer(heatLayer);
            heatLayer = null;
        }

        if (data.length > 0) {
            let maxIntensity = 0;
            for (let i = 0; i < data.length; i++) {
                if (data[i][2] > maxIntensity) maxIntensity = data[i][2];
            }
            heatLayer = L.heatLayer(data, {
                radius: 25,
                blur: 15,
                maxZoom: 17,
                max: maxIntensity || 1,
                minOpacity: 0.3,
                gradient: {
                    0.0: '#1a1008',
                    0.2: '#3d2608',
                    0.4: '#6b4310',
                    0.6: '#9b6a15',
                    0.8: '#c9901a',
                    1.0: '#e8a817'
                }
            });

            if (document.getElementById('show-heatmap').checked) {
                heatLayer.addTo(map);
            }
        }

        let filterInfo = '';
        if (currentFilters.subtype) {
            filterInfo = ` (${currentFilters.subtype})`;
        } else if (currentFilters.type) {
            filterInfo = ` (${currentFilters.type})`;
        }
        document.getElementById('status-text').textContent =
            `Showing ${data.length.toLocaleString()} locations` + filterInfo;
    } catch (err) {
        console.error('Failed to load heatmap:', err);
        document.getElementById('status-text').textContent = 'Heatmap unavailable — data still accessible';
    }
}

async function loadMarkers() {
    try {
        const url = buildFilterUrl('/api/events') + 'limit=500&';
        const res = await fetch(url);
        const events = await res.json();

        markersLayer.clearLayers();

        events.forEach(event => {
            const color = typeColors[event.type] || '#64748b';
            const marker = L.circleMarker([event.latitude, event.longitude], {
                radius: 6,
                fillColor: color,
                color: 'rgba(255,255,255,0.3)',
                weight: 1,
                opacity: 1,
                fillOpacity: 0.9
            });

            marker.bindPopup(`
                <div class="event-popup">
                    <h4>${escapeHTML(event.type)}</h4>
                    <div class="detail"><strong>User:</strong> ${escapeHTML(event.username)}</div>
                    <div class="detail"><strong>Time:</strong> ${event.timestamp.substring(0, 19)}</div>
                    <div class="detail"><strong>Location:</strong> ${event.latitude.toFixed(4)}, ${event.longitude.toFixed(4)}</div>
                    ${event.subtype ? `<div class="detail"><strong>Subtype:</strong> ${escapeHTML(event.subtype)}</div>` : ''}
                </div>
            `);

            markersLayer.addLayer(marker);
        });
    } catch (err) {
        console.error('Failed to load markers:', err);
    }
}

// Toggle heatmap visibility
function toggleHeatmap() {
    if (document.getElementById('show-heatmap').checked) {
        if (heatLayer) heatLayer.addTo(map);
        else loadHeatmap();
    } else if (heatLayer) {
        map.removeLayer(heatLayer);
    }
}

// Toggle markers visibility
function toggleMarkers() {
    if (document.getElementById('show-markers').checked) {
        loadMarkers();
    } else {
        markersLayer.clearLayers();
    }
}

// === Live Feed & SSE ===

function addFeedItem(data) {
    const feed = document.getElementById('feed-items');
    if (!feed) return;

    if (data.type === 'new_event' && data.event) {
        const e = data.event;
        const eventType = e.report_type || e.type || '';
        const badge = TYPE_BADGES[eventType] || { color: '#64748b', bg: 'rgba(100,116,139,0.1)', label: eventType?.substring(0,3) || '???' };
        const age = Date.now() - new Date(e.timestamp || Date.now()).getTime();
        const isNew = age < 300000; // <5 min
        const item = document.createElement('div');
        item.className = 'feed-item' + (isNew ? ' feed-item-new' : '');
        item.innerHTML = `
            <span class="feed-badge" style="color:${badge.color};background:${badge.bg};border:1px solid ${badge.color}33">${badge.label}</span>
            <span class="feed-user">${escapeHTML(e.username) || 'anonymous'}</span>
            <span class="feed-location">${(e.latitude || 0).toFixed(2)}, ${(e.longitude || 0).toFixed(2)}</span>
            <span class="feed-time">${formatTimeAgo(e.timestamp)}</span>
        `;

        // Auto-follow: teleport to new event location (throttled)
        const color = typeColors[eventType] || badge.color;
        const autoFollow = document.getElementById('auto-follow');
        if (autoFollow && autoFollow.checked && e.latitude && e.longitude) {
            const now = Date.now();
            pendingTeleport = { lat: e.latitude, lng: e.longitude, color: color };

            if (now - lastTeleportTime >= TELEPORT_INTERVAL) {
                lastTeleportTime = now;
                map.flyTo([e.latitude, e.longitude], 14, { duration: 0.8 });

                const pulseMarker = L.circleMarker([e.latitude, e.longitude], {
                    radius: 15,
                    color: color,
                    fillColor: color,
                    fillOpacity: 0.4,
                    weight: 2
                }).addTo(map);

                setTimeout(() => map.removeLayer(pulseMarker), 2500);
                pendingTeleport = null;
            }
        }

        // Make event items clickable to navigate to location
        if (e.latitude && e.longitude) {
            item.classList.add('clickable');
            item.dataset.lat = e.latitude;
            item.dataset.lng = e.longitude;
            item.dataset.type = eventType;
            item.title = 'Click to view on map';
            item.addEventListener('click', () => {
                const lat = parseFloat(item.dataset.lat);
                const lng = parseFloat(item.dataset.lng);
                map.flyTo([lat, lng], 14, { duration: 1 });

                const markerColor = typeColors[item.dataset.type] || '#00d4ff';
                const pulseMarker = L.circleMarker([lat, lng], {
                    radius: 12,
                    color: markerColor,
                    fillColor: markerColor,
                    fillOpacity: 0.4,
                    weight: 2
                }).addTo(map);

                setTimeout(() => map.removeLayer(pulseMarker), 3000);
            });
        }

        feed.prepend(item);

        if (typeof playNotificationSound === 'function') playNotificationSound();
    } else if (data.type === 'status') {
        if (data.alerts_found === 0 && data.new_events === 0) {
            return;
        }

        const item = document.createElement('div');
        item.className = 'feed-item';
        const color = typeColors[data.event_types?.[0]] || '#00d4ff';
        item.innerHTML = `
            <span class="feed-badge" style="color:var(--text-muted);background:rgba(100,116,139,0.1);border:1px solid rgba(100,116,139,0.2)">SCN</span>
            <span class="feed-user">${data.cell_name || 'scan'}</span>
            <span class="feed-location">${data.country || '--'}</span>
            <span class="feed-time">${data.cell_idx}/${data.total_cells} +${data.new_events}</span>
        `;

        document.getElementById('status-text').textContent =
            `[${data.region.toUpperCase()}] ${data.cell_name} (${data.country}) • ${data.alerts_found} alerts, +${data.new_events} new`;

        feed.prepend(item);
    } else {
        return;
    }

    while (feed.children.length > 50) {
        feed.removeChild(feed.lastChild);
    }
}

function setConnectionStatus(text) {
    const toolbar = document.getElementById('connection-status');
    const feed = document.getElementById('connection-status-feed');
    if (toolbar) toolbar.textContent = text;
    if (feed) feed.textContent = text;
}

function connectSSE() {
    setConnectionStatus('Connecting...');

    const eventSource = new EventSource('/api/stream');

    eventSource.onopen = () => {
        setConnectionStatus('Connected');
    };

    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);

            if (data.type === 'connected') {
                setConnectionStatus('Live');
            } else if (data.type === 'heartbeat') {
                // Ignore heartbeats
            } else if (data.type === 'new_event') {
                addFeedItem(data);
                loadStats();
            } else if (data.type === 'status') {
                addFeedItem(data);
            }
        } catch (err) {
            console.error('SSE parse error:', err);
        }
    };

    eventSource.onerror = () => {
        setConnectionStatus('Reconnecting...');
        eventSource.close();
        setTimeout(connectSSE, 5000);
    };
}

async function loadRecentActivity() {
    try {
        const res = await fetch('/api/recent-activity');
        const events = await res.json();

        events.slice(0, 10).forEach(e => {
            addFeedItem({
                type: 'new_event',
                event: {
                    ...e,
                    report_type: e.type
                }
            });
        });
    } catch (err) {
        console.error('Failed to load recent activity:', err);
    }
}

async function loadLeaderboard() {
    try {
        const res = await fetch('/api/leaderboard?limit=10');
        const users = await res.json();
        const container = document.getElementById('leaderboard');

        container.innerHTML = users.map(user => {
            let rankClass = 'normal';
            if (user.rank === 1) rankClass = 'gold';
            else if (user.rank === 2) rankClass = 'silver';
            else if (user.rank === 3) rankClass = 'bronze';

            return `
                <div class="leaderboard-item" onclick="selectUser('${escapeHTML(user.username).replace(/'/g, "\\'")}')">
                    <span class="leaderboard-rank ${rankClass}">${user.rank}</span>
                    <span class="leaderboard-username">${escapeHTML(user.username)}</span>
                    <span class="leaderboard-count">${user.count.toLocaleString()}</span>
                </div>
            `;
        }).join('');
    } catch (err) {
        console.error('Failed to load leaderboard:', err);
    }
}

// === Map Layer Toggle Toolbar ===

const MAP_LAYERS = {
  heatmap:   { name: 'Heatmap',    icon: '\u2593', active: true,  layer: null },
  markers:   { name: 'Events',     icon: '\u25CF', active: false, layer: null },
  police:    { name: 'Police',     icon: '\u{1F6A8}', active: false, layer: null },
  jams:      { name: 'Jams',       icon: '\u{26A0}', active: false, layer: null },
  hazards:   { name: 'Hazards',    icon: '\u26A0', active: false, layer: null },
  accidents: { name: 'Accidents',  icon: '\u2622', active: false, layer: null },
  grid:      { name: 'Grid Cells', icon: '\u25A2', active: false, layer: null },
};

function initLayerBar() {
  const bar = document.getElementById('layer-bar');
  if (!bar) return;
  bar.innerHTML = '';
  Object.entries(MAP_LAYERS).forEach(([key, cfg]) => {
    const btn = document.createElement('button');
    btn.className = 'layer-btn' + (cfg.active ? ' active' : '');
    btn.dataset.layer = key;
    btn.innerHTML = `<span class="layer-icon">${cfg.icon}</span>`;
    btn.title = cfg.name;
    btn.onclick = () => toggleMapLayer(key);
    bar.appendChild(btn);
  });

  // 3D Globe toggle
  const globeBtn = document.createElement('button');
  globeBtn.className = 'layer-btn globe-toggle';
  globeBtn.innerHTML = '\u{1F310}';
  globeBtn.title = 'Toggle 3D Globe';
  globeBtn.onclick = toggleGlobe;
  bar.appendChild(globeBtn);
}

function toggleMapLayer(key) {
  const cfg = MAP_LAYERS[key];
  if (!cfg) return;
  cfg.active = !cfg.active;
  document.querySelector(`.layer-btn[data-layer="${key}"]`)
    ?.classList.toggle('active', cfg.active);

  if (cfg.active) {
    loadLayerData(key);
  } else if (cfg.layer) {
    map.removeLayer(cfg.layer);
    cfg.layer = null;
  }
}

async function loadLayerData(key) {
  const layerTypeColors = {
    police: '#3b82f6',
    jams: '#fbbf24',
    hazards: '#fb923c',
    accidents: '#f87171',
  };
  const typeMap = {
    police: 'POLICE',
    jams: 'JAM',
    hazards: 'HAZARD',
    accidents: 'ACCIDENT',
  };

  switch (key) {
    case 'heatmap':
      loadHeatmap();
      break;
    case 'markers':
      loadMarkers();
      break;
    case 'police':
    case 'jams':
    case 'hazards':
    case 'accidents':
      await loadTypedMarkers(key, typeMap[key], layerTypeColors[key]);
      break;
    case 'grid':
      await loadGridOverlay();
      break;
  }
}

async function loadTypedMarkers(layerKey, type, color) {
  try {
    const url = buildFilterUrl('/api/events') + `type=${type}&limit=1000&`;
    const res = await fetch(url);
    const events = await res.json();
    if (MAP_LAYERS[layerKey]?.layer) map.removeLayer(MAP_LAYERS[layerKey].layer);
    const markers = events.map(e =>
      L.circleMarker([e.latitude, e.longitude], {
        radius: 5, fillColor: color, color: 'rgba(255,255,255,0.2)',
        weight: 1, fillOpacity: 0.85,
      }).bindPopup(`<b>${escapeHTML(e.type)}</b><br>${escapeHTML(e.username)}<br>${e.timestamp?.substring(0,19)}`)
    );
    MAP_LAYERS[layerKey].layer = L.layerGroup(markers).addTo(map);
  } catch (err) {
    console.error(`Failed to load ${layerKey} layer:`, err);
  }
}

async function loadGridOverlay() {
  try {
    const res = await fetch('/api/grid-cells');
    const cells = await res.json();
    if (MAP_LAYERS.grid?.layer) map.removeLayer(MAP_LAYERS.grid.layer);
    const rects = cells.map(c =>
      L.rectangle([[c.south, c.west], [c.north, c.east]], {
        color: 'rgba(232, 168, 23, 0.3)', weight: 1, fillOpacity: 0.03,
      })
    );
    MAP_LAYERS.grid.layer = L.layerGroup(rects).addTo(map);
  } catch (err) {
    console.error('Failed to load grid overlay:', err);
  }
}

function setMapLayers(layers) {
  Object.entries(MAP_LAYERS).forEach(([key, cfg]) => {
    const shouldBeActive = layers.includes(key);
    if (cfg.active !== shouldBeActive) {
      toggleMapLayer(key);
    }
  });
}

// === Time Controls ===

function initTimeControls() {
  const container = document.getElementById('time-controls');
  if (!container) return;
  container.innerHTML = `
    <div class="time-presets">
      <button class="time-btn active" data-hours="">ALL</button>
      <button class="time-btn" data-hours="1">1H</button>
      <button class="time-btn" data-hours="6">6H</button>
      <button class="time-btn" data-hours="24">24H</button>
      <button class="time-btn" data-hours="168">7D</button>
      <button class="time-btn" data-hours="720">30D</button>
    </div>
    <div class="time-jump">
      <input type="datetime-local" id="time-jump-input" title="Jump to date">
    </div>
  `;
  container.querySelectorAll('.time-btn').forEach(btn => {
    btn.onclick = () => {
      container.querySelectorAll('.time-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentFilters.since = btn.dataset.hours || null;
      applyFilters();
    };
  });
  document.getElementById('time-jump-input').onchange = (e) => {
    const dt = new Date(e.target.value);
    if (!isNaN(dt)) {
      currentFilters.dateFrom = e.target.value.split('T')[0];
      currentFilters.since = null;
      container.querySelectorAll('.time-btn').forEach(b => b.classList.remove('active'));
      applyFilters();
    }
  };
}

// === Timeline Sparkline ===

function initTimeline() {
  const mapLayer = document.querySelector('.map-layer');
  if (!mapLayer) return;
  const bar = document.createElement('div');
  bar.className = 'timeline-bar';
  bar.id = 'timeline-bar';
  mapLayer.appendChild(bar);
  loadTimelineData();
}

async function loadTimelineData() {
  try {
    const res = await fetch('/api/timeline?hours=24&buckets=48');
    const data = await res.json();
    const bar = document.getElementById('timeline-bar');
    if (!bar || !data.buckets) return;
    const max = Math.max(...data.buckets.map(b => b.count), 1);
    bar.innerHTML = data.buckets.map(b => {
      const h = Math.max(2, (b.count / max) * 24);
      const opacity = 0.3 + (b.count / max) * 0.7;
      return `<div class="timeline-tick" style="height:${h}px;opacity:${opacity}" title="${b.label}: ${b.count} events"></div>`;
    }).join('');
  } catch (err) {
    console.error('Failed to load timeline:', err);
  }
}

// === 3D Globe View (Task 10) ===

let globeInstance = null;
let globeActive = false;

function toggleGlobe() {
  globeActive = !globeActive;
  const mapEl = document.getElementById('map');
  let globeContainer = document.getElementById('globe-container');
  document.querySelector('.globe-toggle')?.classList.toggle('active', globeActive);

  if (globeActive) {
    if (!globeContainer) {
      globeContainer = document.createElement('div');
      globeContainer.id = 'globe-container';
      document.querySelector('.map-layer').appendChild(globeContainer);
    }
    mapEl.style.display = 'none';
    globeContainer.style.display = 'block';
    initGlobe(globeContainer);
  } else {
    mapEl.style.display = 'block';
    if (globeContainer) globeContainer.style.display = 'none';
  }
}

function initGlobe(container) {
  if (globeInstance) {
    refreshGlobeData();
    return;
  }

  const width = container.clientWidth;
  const height = container.clientHeight;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 1000);
  camera.position.z = 250;

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setSize(width, height);
  renderer.setPixelRatio(window.devicePixelRatio);
  container.innerHTML = '';
  container.appendChild(renderer.domElement);

  const globe = new ThreeGlobe()
    .globeImageUrl('https://unpkg.com/three-globe/example/img/earth-night.jpg')
    .bumpImageUrl('https://unpkg.com/three-globe/example/img/earth-topology.png');

  scene.add(globe);
  scene.add(new THREE.AmbientLight(0xcccccc, Math.PI));
  scene.add(new THREE.DirectionalLight(0xffffff, 0.6 * Math.PI));

  let isDragging = false;
  container.addEventListener('mousedown', () => isDragging = true);
  container.addEventListener('mouseup', () => isDragging = false);

  function animate() {
    if (!isDragging) globe.rotation.y += 0.002;
    renderer.render(scene, camera);
    if (globeActive) requestAnimationFrame(animate);
  }
  animate();

  window.addEventListener('resize', () => {
    const w = container.clientWidth;
    const h = container.clientHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  });

  globeInstance = { globe, renderer, scene, camera };
  refreshGlobeData();
}

async function refreshGlobeData() {
  if (!globeInstance) return;
  try {
    const res = await fetch('/api/heatmap?limit=2000');
    const data = await res.json();
    const points = data.map(d => ({
      lat: d[0], lng: d[1], size: 0.4, color: '#e8a817'
    }));
    globeInstance.globe
      .pointsData(points)
      .pointAltitude('size')
      .pointColor('color')
      .pointRadius(0.15);
  } catch (err) {
    console.error('Failed to load globe data:', err);
  }
}

// === Detail Map (Task 11) ===

function initDetailMap() {
  setTimeout(() => {
    const container = document.getElementById('detail-map-container');
    if (!container || container._leafletInit) return;
    container._leafletInit = true;
    const detailMap = L.map(container, { zoomControl: true }).setView([40.4, -3.7], 10);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 19, opacity: 0.8
    }).addTo(detailMap);

    map.on('click', (e) => {
      detailMap.setView(e.latlng, 12);
      loadDetailMarkers(detailMap, e.latlng);
    });

    setTimeout(() => detailMap.invalidateSize(), 200);
  }, 300);
}

async function loadDetailMarkers(detailMap, center) {
  try {
    const res = await fetch('/api/events?limit=200');
    const events = await res.json();
    detailMap.eachLayer(l => { if (l instanceof L.CircleMarker) detailMap.removeLayer(l); });
    const nearby = events.filter(e =>
      Math.abs(e.latitude - center.lat) < 0.2 && Math.abs(e.longitude - center.lng) < 0.2
    );
    nearby.forEach(e => {
      const badge = TYPE_BADGES[e.type] || { color: '#64748b' };
      L.circleMarker([e.latitude, e.longitude], {
        radius: 6, fillColor: badge.color, color: '#fff', weight: 1, fillOpacity: 0.9,
      }).bindPopup(`<b>${escapeHTML(e.type)}</b><br>${escapeHTML(e.username)}`).addTo(detailMap);
    });
  } catch (err) {
    console.error('Detail map load failed:', err);
  }
}

// === Collector Status (Task 12) ===

async function loadCollectorStatus() {
  try {
    const res = await fetch('/api/status');
    const status = await res.json();
    const container = document.getElementById('collector-regions');
    if (!container) return;

    const regions = ['europe', 'americas', 'asia', 'oceania', 'africa'];
    container.innerHTML = regions.map(r => {
      const s = status[r] || status;
      const running = s.running || s.status === 'running' || false;
      const dotColor = running ? 'var(--accent-green)' : 'var(--accent-red)';
      const events = s.events_collected || s.total_events || 0;
      return `<div class="region-status">
        <span class="region-dot" style="background:${dotColor}"></span>
        <span class="region-name">${r}</span>
        <span class="region-count">${events.toLocaleString()}</span>
      </div>`;
    }).join('');

    const rateEl = document.getElementById('coll-rate');
    const lastEl = document.getElementById('coll-last');
    if (rateEl) rateEl.textContent = (status.events_per_minute || '--');
    if (lastEl) lastEl.textContent = status.last_scan ? formatTimeAgo(status.last_scan) : '--';
  } catch (e) { /* silent */ }
}

// === System Alerts (Task 13) ===

async function loadAlerts() {
  try {
    const res = await fetch('/api/alerts');
    const alerts = await res.json();
    const feed = document.getElementById('alerts-feed');
    if (!feed) return;

    const severityColors = {
      high: { color: '#f87171', bg: 'rgba(248,113,113,0.1)' },
      medium: { color: '#fbbf24', bg: 'rgba(251,191,36,0.1)' },
      info: { color: '#3b82f6', bg: 'rgba(59,130,246,0.1)' },
    };

    feed.innerHTML = alerts.length ? alerts.map(a => {
      const s = severityColors[a.severity] || severityColors.info;
      return `<div class="alert-item" style="border-left:3px solid ${s.color};background:${s.bg}">
        <span class="alert-severity" style="color:${s.color}">${a.severity.toUpperCase()}</span>
        <span class="alert-message">${a.message}</span>
      </div>`;
    }).join('') : '<div style="color:var(--text-muted);padding:12px;text-align:center;font-size:0.8rem">No alerts</div>';
  } catch (e) { /* silent */ }
}

// === Event Type Breakdown (Task 14) ===

async function loadTypeBreakdown() {
  try {
    const res = await fetch('/api/types');
    const types = await res.json();
    const list = document.getElementById('type-list');
    const chart = document.getElementById('type-bar-chart');
    if (!list || !chart) return;

    const total = types.reduce((s, t) => s + t.count, 0) || 1;

    chart.innerHTML = types.map(t => {
      const badge = TYPE_BADGES[t.type] || { color: '#64748b' };
      const pct = (t.count / total * 100).toFixed(1);
      return `<div class="type-bar-segment" style="width:${pct}%;background:${badge.color}" title="${t.type}: ${pct}%"></div>`;
    }).join('');

    list.innerHTML = types.map(t => {
      const badge = TYPE_BADGES[t.type] || { color: '#64748b' };
      const pct = (t.count / total * 100).toFixed(1);
      return `<div class="type-row">
        <span class="type-dot" style="background:${badge.color}"></span>
        <span class="type-name">${t.type}</span>
        <span class="type-pct">${pct}%</span>
        <span class="type-count">${t.count.toLocaleString()}</span>
      </div>`;
    }).join('');
  } catch (e) { /* silent */ }
}

// === Privacy Risk Leaderboard (Task 15) ===

async function loadPrivacyLeaderboard() {
  try {
    const res = await fetch('/api/privacy-score/leaderboard?limit=10');
    const users = await res.json();
    const list = document.getElementById('privacy-list');
    if (!list) return;

    if (users.error) {
      list.innerHTML = '<div style="color:var(--text-muted);padding:12px;font-size:0.8rem">Privacy scoring unavailable</div>';
      return;
    }

    list.innerHTML = users.map((u, i) => {
      const score = u.overall_score || 0;
      const level = score >= 70 ? 'critical' : score >= 40 ? 'high' : score >= 20 ? 'medium' : 'low';
      const levelColors = {
        critical: { color: '#f87171', bg: 'rgba(248,113,113,0.1)' },
        high: { color: '#fb923c', bg: 'rgba(251,146,60,0.1)' },
        medium: { color: '#fbbf24', bg: 'rgba(251,191,36,0.1)' },
        low: { color: '#34d399', bg: 'rgba(52,211,153,0.1)' },
      };
      const c = levelColors[level];
      return `<div class="privacy-row">
        <span class="privacy-rank">${i + 1}</span>
        <span class="privacy-user">${escapeHTML(u.username)}</span>
        <span class="privacy-badge" style="color:${c.color};background:${c.bg}">${level.toUpperCase()}</span>
        <span class="privacy-score" style="color:${c.color}">${score.toFixed(0)}</span>
      </div>`;
    }).join('') || '<div style="color:var(--text-muted);padding:12px;text-align:center;font-size:0.8rem">No data yet</div>';
  } catch (e) {
    const list = document.getElementById('privacy-list');
    if (list) list.innerHTML = '<div style="color:var(--text-muted);padding:12px;font-size:0.8rem">Privacy scoring unavailable</div>';
  }
}

// === Initialize Everything ===

document.addEventListener('DOMContentLoaded', () => {
    // 1. GridStack is already initialized at the top of this file

    // 2. Build toolbar components
    initDeckSelector();
    initTimeControls();
    initLayerBar();
    initTimeline();

    // 3. Load default deck (creates widgets and loads data)
    switchDeck('live');

    // 4. Start SSE and load recent activity for feed backfill
    connectSSE();
    loadRecentActivity();
    loadSparklines();

    // 5. Data refresh intervals
    setInterval(loadStats, 60000);
    setInterval(loadSparklines, 60000);
    setInterval(loadCollectorStatus, 10000);
    setInterval(loadAlerts, 30000);
    setInterval(loadTimelineData, 120000);
    setInterval(loadTypeBreakdown, 60000);

    // Process pending teleports every second
    setInterval(() => {
        const autoFollow = document.getElementById('auto-follow');
        if (autoFollow && autoFollow.checked && pendingTeleport) {
            const now = Date.now();
            if (now - lastTeleportTime >= TELEPORT_INTERVAL) {
                lastTeleportTime = now;
                map.flyTo([pendingTeleport.lat, pendingTeleport.lng], 14, { duration: 0.8 });

                const pulseMarker = L.circleMarker([pendingTeleport.lat, pendingTeleport.lng], {
                    radius: 15,
                    color: pendingTeleport.color,
                    fillColor: pendingTeleport.color,
                    fillOpacity: 0.4,
                    weight: 2
                }).addTo(map);
                setTimeout(() => map.removeLayer(pulseMarker), 2500);

                pendingTeleport = null;
            }
        }
    }, 1000);
});

// Keyboard shortcuts: layer toggles, deck switching (1-4)
document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;

    // Deck switching with number keys
    const deckKeys = { '1': 'live', '2': 'intel', '3': 'analytics', '4': 'risk' };
    if (deckKeys[e.key]) {
        e.preventDefault();
        switchDeck(deckKeys[e.key]);
        return;
    }

    switch(e.key.toLowerCase()) {
        case 'h': {
            const heatmapCheckbox = document.getElementById('show-heatmap');
            if (heatmapCheckbox) { heatmapCheckbox.checked = !heatmapCheckbox.checked; toggleHeatmap(); }
            break;
        }
        case 'm': {
            const markersCheckbox = document.getElementById('show-markers');
            if (markersCheckbox) { markersCheckbox.checked = !markersCheckbox.checked; toggleMarkers(); }
            break;
        }
        case 'f': {
            const followCheckbox = document.getElementById('auto-follow');
            if (followCheckbox) followCheckbox.checked = !followCheckbox.checked;
            break;
        }
        case 's': {
            const soundCheckbox = document.getElementById('sound-enabled');
            if (soundCheckbox) soundCheckbox.checked = !soundCheckbox.checked;
            break;
        }
        case 'r':
            resetFilters();
            break;
    }
});
