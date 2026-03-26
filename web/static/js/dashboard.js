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
        <div class="stat-row"><span class="stat-label">Total Events</span><span class="stat-value" id="stat-total">--</span></div>
        <div class="stat-row"><span class="stat-label">Unique Users</span><span class="stat-value" id="stat-users">--</span></div>
        <div class="stat-row"><span class="stat-label">Date Range</span><span class="stat-value" id="stat-time">--</span></div>
    `,
    'leaderboard': () => `<div class="leaderboard" id="leaderboard"></div>`,
    'feed': () => `
        <div class="feed-header-bar">
            <span class="live-indicator"><span class="live-dot"></span> LIVE</span>
            <span id="connection-status">Connecting...</span>
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

function initDefaultWidgets() {
    createWidget('stats', 'Statistics', WIDGET_CONTENT['stats'](), { x: 0, y: 0, w: 3, h: 5 });
    createWidget('leaderboard', 'Top Contributors', WIDGET_CONTENT['leaderboard'](), { x: 0, y: 5, w: 3, h: 7 });
    createWidget('feed', 'Live Feed', WIDGET_CONTENT['feed'](), { x: 3, y: 8, w: 6, h: 5 });
    createWidget('filters', 'Filters', WIDGET_CONTENT['filters'](), { x: 9, y: 0, w: 3, h: 6 });
    createWidget('display', 'Display', WIDGET_CONTENT['display'](), { x: 9, y: 6, w: 3, h: 4 });
}

// === Deck Preset System ===

const DECK_PRESETS = {
    live: {
        name: 'Live Collection',
        icon: '\u25C9',
        widgets: [
            { id: 'stats', title: 'Statistics', x: 0, y: 0, w: 3, h: 5 },
            { id: 'feed', title: 'Live Feed', x: 0, y: 5, w: 3, h: 8 },
            { id: 'display', title: 'Display', x: 9, y: 0, w: 3, h: 4 },
        ],
        layers: ['heatmap'],
        mapView: { center: [45, 10], zoom: 4 },
    },
    intel: {
        name: 'User Intelligence',
        icon: '\u25C8',
        widgets: [
            { id: 'filters', title: 'Filters', x: 0, y: 0, w: 3, h: 6 },
            { id: 'leaderboard', title: 'Top Contributors', x: 0, y: 6, w: 3, h: 7 },
            { id: 'feed', title: 'Live Feed', x: 9, y: 0, w: 3, h: 6 },
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
            { id: 'leaderboard', title: 'Top Contributors', x: 0, y: 5, w: 4, h: 6 },
            { id: 'feed', title: 'Live Feed', x: 8, y: 5, w: 4, h: 6 },
        ],
        layers: ['heatmap', 'markers'],
        mapView: { center: [30, 0], zoom: 3 },
    },
    risk: {
        name: 'Privacy Risk',
        icon: '\u25B2',
        widgets: [
            { id: 'stats', title: 'Statistics', x: 0, y: 0, w: 3, h: 5 },
            { id: 'leaderboard', title: 'Top Contributors', x: 0, y: 5, w: 3, h: 7 },
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
        const contentFn = WIDGET_CONTENT[w.id];
        if (contentFn) {
            createWidget(w.id, w.title, contentFn(), { x: w.x, y: w.y, w: w.w, h: w.h });
        }
    });

    // Set map layers
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

    // Animate map view
    if (deck.mapView) {
        map.flyTo(deck.mapView.center, deck.mapView.zoom, { duration: 1.5 });
    }

    // Reload data
    loadStats();
    loadLeaderboard();
    if (typeof loadTypes === 'function') loadTypes();
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
                    `<div class="user-option" onclick="selectUser('${u.username.replace(/'/g, "\\'")}')">
                        <span>${u.username}</span>
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

    document.getElementById('status-text').textContent = `Tracking user: ${username}`;
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
                    <h4>${event.type}</h4>
                    <div class="detail"><strong>User:</strong> ${event.username}</div>
                    <div class="detail"><strong>Time:</strong> ${event.timestamp.substring(0, 19)}</div>
                    <div class="detail"><strong>Location:</strong> ${event.latitude.toFixed(4)}, ${event.longitude.toFixed(4)}</div>
                    ${event.subtype ? `<div class="detail"><strong>Subtype:</strong> ${event.subtype}</div>` : ''}
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
    const item = document.createElement('div');
    item.className = 'feed-item new';

    if (data.type === 'new_event' && data.event) {
        const e = data.event;
        const time = new Date(e.timestamp).toLocaleTimeString();
        const color = typeColors[e.report_type] || '#64748b';
        item.innerHTML = `
            <span class="type" style="color:${color}">${e.report_type}</span>
            <span class="location">${e.grid_cell || `${e.latitude.toFixed(2)}, ${e.longitude.toFixed(2)}`}</span>
            <span class="time">${time}</span>
        `;
        item.style.borderLeftColor = color;

        // Auto-follow: teleport to new event location (throttled)
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

        playNotificationSound();

        // Make event items clickable to navigate to location
        if (e.latitude && e.longitude) {
            item.classList.add('clickable');
            item.dataset.lat = e.latitude;
            item.dataset.lng = e.longitude;
            item.dataset.type = e.report_type;
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
    } else if (data.type === 'status') {
        if (data.alerts_found === 0 && data.new_events === 0) {
            return;
        }

        const color = typeColors[data.event_types?.[0]] || '#00d4ff';
        item.innerHTML = `
            <span class="type" style="color:var(--text-muted)">SCAN</span>
            <span class="location">${data.cell_name} (${data.country})</span>
            <span class="time">${data.cell_idx}/${data.total_cells} • +${data.new_events}</span>
        `;
        item.style.borderLeftColor = data.new_events > 0 ? 'var(--primary)' : 'var(--border)';

        document.getElementById('status-text').textContent =
            `[${data.region.toUpperCase()}] ${data.cell_name} (${data.country}) • ${data.alerts_found} alerts, +${data.new_events} new`;
    } else {
        return;
    }

    feed.insertBefore(item, feed.firstChild);

    setTimeout(() => item.classList.remove('new'), 1000);

    while (feed.children.length > 50) {
        feed.removeChild(feed.lastChild);
    }
}

function connectSSE() {
    const statusEl = document.getElementById('connection-status');
    statusEl.textContent = 'Connecting...';

    const eventSource = new EventSource('/api/stream');

    eventSource.onopen = () => {
        statusEl.textContent = 'Connected';
    };

    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);

            if (data.type === 'connected') {
                statusEl.textContent = 'Live';
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
        statusEl.textContent = 'Reconnecting...';
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
                <div class="leaderboard-item" onclick="selectUser('${user.username.replace(/'/g, "\\'")}')">
                    <span class="leaderboard-rank ${rankClass}">${user.rank}</span>
                    <span class="leaderboard-username">${user.username}</span>
                    <span class="leaderboard-count">${user.count.toLocaleString()}</span>
                </div>
            `;
        }).join('');
    } catch (err) {
        console.error('Failed to load leaderboard:', err);
    }
}

// === Initialize Everything ===

// Initialize deck selector and load default deck
initDeckSelector();
switchDeck('live');

// Then load remaining data
loadStats().then(() => {
    const total = document.getElementById('stat-total').textContent;
    if (total && total !== '--') {
        document.getElementById('status-text').textContent = `${total} events loaded`;
    }
});
loadRecentActivity();
connectSSE();

// Refresh stats and leaderboard every 60 seconds
setInterval(() => {
    loadStats();
    loadLeaderboard();
}, 60000);

// Process pending teleports every 10 seconds
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

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;

    switch(e.key.toLowerCase()) {
        case 'h':
            const heatmapCheckbox = document.getElementById('show-heatmap');
            heatmapCheckbox.checked = !heatmapCheckbox.checked;
            toggleHeatmap();
            break;
        case 'm':
            const markersCheckbox = document.getElementById('show-markers');
            markersCheckbox.checked = !markersCheckbox.checked;
            toggleMarkers();
            break;
        case 'f':
            const followCheckbox = document.getElementById('auto-follow');
            followCheckbox.checked = !followCheckbox.checked;
            break;
        case 's':
            const soundCheckbox = document.getElementById('sound-enabled');
            soundCheckbox.checked = !soundCheckbox.checked;
            break;
        case 'r':
            resetFilters();
            break;
    }
});
