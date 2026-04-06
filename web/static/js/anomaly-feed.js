/**
 * Anomaly Feed Widget — SSE-connected real-time anomaly alerts.
 *
 * Namespace: window.WazeDash.anomalyFeed
 * Listens for "anomaly" event type on the shared SSE stream.
 */
window.WazeDash = window.WazeDash || {};
window.WazeDash.anomalyFeed = (function () {
    'use strict';

    let _containerId = null;
    let _sseSource = null;
    let _alerts = [];
    let _totalCount = 0;
    let _scoreSum = 0;

    // ---- helpers ----

    function severityClass(score) {
        if (score >= 70) return 'high';
        if (score >= 30) return 'medium';
        return 'low';
    }

    function typeIcon(anomalyType) {
        switch (anomalyType) {
            case 'time': return '\u23F0';       // alarm clock
            case 'location': return '\uD83D\uDCCD'; // pin
            case 'frequency': return '\uD83D\uDCC8'; // chart increasing
            default: return '\u26A0';           // warning
        }
    }

    function formatTime(ts) {
        if (!ts) return '--';
        try {
            var d = new Date(ts);
            return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        } catch (_) {
            return ts;
        }
    }

    function renderCard(alert) {
        var sev = severityClass(alert.score);
        var gfBadge = alert.geofence_name
            ? '<span class="anomaly-geofence">' + escapeHTML(alert.geofence_name) + '</span>'
            : '';
        return (
            '<div class="anomaly-card severity-' + sev + '">' +
                '<span class="anomaly-score ' + sev + '">' + Math.round(alert.score) + '</span>' +
                '<span style="font-size:0.85rem">' + typeIcon(alert.anomaly_type) + '</span>' +
                '<span class="anomaly-user">' + escapeHTML(alert.username || 'unknown') + '</span>' +
                '<span class="anomaly-type">' + escapeHTML(alert.anomaly_type || '') + '</span>' +
                gfBadge +
                '<span class="anomaly-time">' + formatTime(alert.timestamp) + '</span>' +
            '</div>'
        );
    }

    function updateSummary() {
        var countEl = document.getElementById('anomaly-count');
        var avgEl = document.getElementById('anomaly-avg');
        if (countEl) countEl.textContent = _totalCount;
        if (avgEl) avgEl.textContent = _totalCount > 0 ? (_scoreSum / _totalCount).toFixed(1) : '--';
    }

    function renderAll() {
        var container = document.getElementById(_containerId);
        if (!container) return;
        // Reverse chronological
        var html = '';
        for (var i = _alerts.length - 1; i >= 0; i--) {
            html += renderCard(_alerts[i]);
        }
        container.innerHTML = html;
        updateSummary();
    }

    function addAlert(alert) {
        _alerts.push(alert);
        // Cap at 200 in the UI
        if (_alerts.length > 200) _alerts.shift();
        _totalCount++;
        _scoreSum += (alert.score || 0);

        // Prepend card for efficiency (reverse chronological)
        var container = document.getElementById(_containerId);
        if (!container) return;
        var tmp = document.createElement('div');
        tmp.innerHTML = renderCard(alert);
        if (container.firstChild) {
            container.insertBefore(tmp.firstElementChild, container.firstChild);
        } else {
            container.appendChild(tmp.firstElementChild);
        }
        // Trim DOM children
        while (container.children.length > 200) {
            container.removeChild(container.lastChild);
        }
        updateSummary();
    }

    // ---- SSE ----

    function connectSSE() {
        // Reuse the existing EventSource if dashboard.js already created one
        // Otherwise create our own
        if (window._sseSource && window._sseSource.readyState !== 2) {
            _sseSource = window._sseSource;
        } else {
            _sseSource = new EventSource('/api/events/stream');
        }

        _sseSource.addEventListener('message', function (e) {
            try {
                var data = JSON.parse(e.data);
                if (data && data.type === 'anomaly' && data.alert) {
                    addAlert(data.alert);
                }
            } catch (_) { /* ignore parse errors */ }
        });
    }

    // ---- fetch initial data ----

    function fetchInitial() {
        fetch('/api/anomalies?limit=100')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data && data.anomalies && data.anomalies.length) {
                    _alerts = data.anomalies;
                    _totalCount = data.anomalies.length;
                    _scoreSum = 0;
                    for (var i = 0; i < data.anomalies.length; i++) {
                        _scoreSum += (data.anomalies[i].score || 0);
                    }
                    renderAll();
                }
            })
            .catch(function () { /* endpoint might not have data yet */ });
    }

    // ---- public API ----

    function init(containerId) {
        _containerId = containerId;
        _alerts = [];
        _totalCount = 0;
        _scoreSum = 0;
        fetchInitial();
        connectSSE();
    }

    function destroy() {
        // Don't close shared SSE source
        _sseSource = null;
        _containerId = null;
        _alerts = [];
        _totalCount = 0;
        _scoreSum = 0;
    }

    return { init: init, destroy: destroy };
})();
