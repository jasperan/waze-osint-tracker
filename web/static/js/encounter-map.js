/**
 * Encounter Prediction Heatmap Widget
 *
 * Renders predicted encounter hotspots as a Leaflet.heat overlay on the
 * existing global `map`.  Time controls (day-of-week + hour slider) filter
 * which predictions are visible.
 */
window.WazeDash = window.WazeDash || {};

window.WazeDash.encounterMap = (function () {
    'use strict';

    // --- state -----------------------------------------------------------
    let heatLayer = null;
    let allData = [];       // raw schedule from API
    let visible = true;

    // --- helpers ---------------------------------------------------------

    const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

    function formatHour(h) {
        if (h < 0) return 'All';
        return String(h).padStart(2, '0') + ':00';
    }

    function filteredPoints(day, hour) {
        return allData.filter(function (d) {
            if (day !== '' && Number(day) !== d.day_of_week) return false;
            if (hour >= 0 && hour !== d.hour) return false;
            return true;
        });
    }

    function heatPoints(items) {
        return items.map(function (d) {
            return [d.lat, d.lon, d.probability];
        });
    }

    // --- popup -----------------------------------------------------------

    function popupHTML(d) {
        var users = (d.users || []).join(', ');
        var prob  = (d.probability * 100).toFixed(1);
        var day   = DAY_NAMES[d.day_of_week] || '?';
        var hour  = String(d.hour).padStart(2, '0') + ':00';
        return '<div class="encounter-popup">' +
            '<div class="ep-users">' + escapeHTML(users) + '</div>' +
            '<div class="ep-prob">' + prob + '% probability</div>' +
            '<div class="ep-time">' + day + ' ' + hour +
                ' &middot; ' + (d.evidence_count || 0) + ' sightings</div>' +
            '</div>';
    }

    function escapeHTML(s) {
        if (!s) return '';
        return s.replace(/&/g, '&amp;').replace(/</g, '&lt;')
                .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // --- markers (click targets) -----------------------------------------

    var markerGroup = null;

    function rebuildMarkers(items) {
        if (markerGroup) {
            map.removeLayer(markerGroup);
        }
        markerGroup = L.layerGroup();
        items.forEach(function (d) {
            var m = L.circleMarker([d.lat, d.lon], {
                radius: 4 + d.probability * 8,
                color: 'rgba(232, 168, 23, 0.6)',
                fillColor: 'rgba(232, 168, 23, 0.25)',
                fillOpacity: 0.5,
                weight: 1,
            });
            m.bindPopup(popupHTML(d), { className: 'encounter-popup-wrap' });
            markerGroup.addLayer(m);
        });
        if (visible) markerGroup.addTo(map);
    }

    // --- data loading ----------------------------------------------------

    function refresh() {
        var dayEl  = document.getElementById('encounter-day');
        var hourEl = document.getElementById('encounter-hour');
        if (!dayEl || !hourEl) return;

        var day  = dayEl.value;
        var hour = parseInt(hourEl.value, 10);
        var pts  = filteredPoints(day, hour);

        if (heatLayer) heatLayer.setLatLngs(heatPoints(pts));
        rebuildMarkers(pts);

        var info = document.getElementById('encounter-info');
        if (info) info.textContent = pts.length + ' predicted encounter hotspots';
    }

    function fetchSchedule() {
        fetch('/api/encounters/schedule?limit=1000')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                allData = data.schedule || [];
                refresh();
            })
            .catch(function () {
                var info = document.getElementById('encounter-info');
                if (info) info.textContent = 'Failed to load encounter data';
            });
    }

    // --- visibility toggle -----------------------------------------------

    function setVisible(show) {
        visible = show;
        if (!heatLayer) return;
        if (show) {
            heatLayer.addTo(map);
            if (markerGroup) markerGroup.addTo(map);
        } else {
            map.removeLayer(heatLayer);
            if (markerGroup) map.removeLayer(markerGroup);
        }
    }

    // --- public API ------------------------------------------------------

    function init() {
        // Create the heat layer (leaflet.heat gradient in amber/gold theme)
        heatLayer = L.heatLayer([], {
            radius: 30,
            blur: 20,
            maxZoom: 14,
            max: 1.0,
            gradient: {
                0.0: 'rgba(232, 168, 23, 0)',
                0.3: 'rgba(232, 168, 23, 0.4)',
                0.6: 'rgba(251, 191, 36, 0.7)',
                0.8: 'rgba(248, 113, 113, 0.85)',
                1.0: 'rgba(255, 255, 255, 0.95)',
            },
        });
        if (visible) heatLayer.addTo(map);

        // Wire controls
        var dayEl    = document.getElementById('encounter-day');
        var hourEl   = document.getElementById('encounter-hour');
        var hourLbl  = document.getElementById('encounter-hour-label');
        var toggleEl = document.getElementById('encounter-layer-toggle');

        if (dayEl)    dayEl.addEventListener('change', refresh);
        if (hourEl)   hourEl.addEventListener('input', function () {
            var v = parseInt(hourEl.value, 10);
            if (hourLbl) hourLbl.textContent = formatHour(v);
            refresh();
        });
        if (toggleEl) toggleEl.addEventListener('change', function () {
            setVisible(toggleEl.checked);
        });

        fetchSchedule();
    }

    function destroy() {
        if (heatLayer)   { try { map.removeLayer(heatLayer); } catch (_) {} }
        if (markerGroup) { try { map.removeLayer(markerGroup); } catch (_) {} }
        heatLayer = null;
        markerGroup = null;
        allData = [];
    }

    return { init: init, destroy: destroy };
})();
