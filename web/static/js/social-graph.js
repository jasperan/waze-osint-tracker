// === Social Graph Widget (D3.js Force-Directed) ===
// Namespace: window.WazeDash.socialGraph

window.WazeDash = window.WazeDash || {};

window.WazeDash.socialGraph = (function () {
    'use strict';

    // --- Constants ---
    const RELATIONSHIP_COLORS = {
        SAME_PERSON: '#f87171',
        CONVOY: '#e8a817',
        SIMILAR_ROUTINE: '#3b82f6',
        WEAK_MATCH: '#4e5d73',
    };

    const COMMUNITY_COLORS = d3.schemeTableau10;

    // --- State ---
    let svg = null;
    let simulation = null;
    let containerId = null;
    let currentData = null;
    let isEgoView = false;
    let resizeObserver = null;
    let tooltip = null;

    // --- Helpers ---
    function nodeRadius(eventCount) {
        return Math.max(4, Math.min(20, Math.sqrt(eventCount || 1) * 2));
    }

    function edgeWidth(weight) {
        return Math.max(1, Math.min(4, weight));
    }

    function escapeText(str) {
        if (typeof escapeHTML === 'function') return escapeHTML(str);
        if (!str) return '';
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // --- Legend ---
    function buildLegend(container) {
        let legend = container.querySelector('.social-graph-legend');
        if (legend) legend.remove();

        legend = document.createElement('div');
        legend.className = 'social-graph-legend';

        Object.entries(RELATIONSHIP_COLORS).forEach(function (entry) {
            var type = entry[0];
            var color = entry[1];
            var item = document.createElement('div');
            item.className = 'social-graph-legend-item';
            var swatch = document.createElement('span');
            swatch.className = 'social-graph-legend-swatch';
            swatch.style.background = color;
            var label = document.createElement('span');
            label.textContent = type.replace(/_/g, ' ');
            item.appendChild(swatch);
            item.appendChild(label);
            legend.appendChild(item);
        });

        container.appendChild(legend);
    }

    // --- Back Button ---
    function buildBackButton(container) {
        let btn = container.querySelector('.social-graph-back-btn');
        if (btn) btn.remove();

        btn = document.createElement('button');
        btn.className = 'social-graph-back-btn';
        btn.textContent = '\u2190 Back to full graph';
        btn.style.display = 'none';
        btn.addEventListener('click', function () {
            isEgoView = false;
            btn.style.display = 'none';
            fetchAndRender('/api/social-graph?limit=200');
        });
        container.appendChild(btn);
        return btn;
    }

    // --- Tooltip ---
    function ensureTooltip(container) {
        if (tooltip) return tooltip;
        tooltip = document.createElement('div');
        tooltip.className = 'social-graph-tooltip';
        tooltip.style.display = 'none';
        container.appendChild(tooltip);
        return tooltip;
    }

    function showTooltip(event, d, container) {
        var tt = ensureTooltip(container);
        tt.innerHTML =
            '<div class="tt-user">' + escapeText(d.id) + '</div>' +
            '<div class="tt-stat">Events: ' + (d.event_count || 0) + '</div>' +
            '<div class="tt-stat">Type: ' + escapeText(d.top_type || 'N/A') + '</div>' +
            '<div class="tt-stat">Community: ' + (d.community != null ? d.community : '?') + '</div>';
        tt.style.display = 'block';

        var rect = container.getBoundingClientRect();
        var x = event.clientX - rect.left + 12;
        var y = event.clientY - rect.top - 10;

        // Keep tooltip inside container
        if (x + 160 > rect.width) x = x - 170;
        if (y + 80 > rect.height) y = y - 80;

        tt.style.left = x + 'px';
        tt.style.top = y + 'px';
    }

    function hideTooltip() {
        if (tooltip) tooltip.style.display = 'none';
    }

    // --- Render ---
    function render(data, container) {
        currentData = data;

        // Clear previous SVG
        var existing = container.querySelector('svg');
        if (existing) existing.remove();
        if (simulation) simulation.stop();

        var width = container.clientWidth || 400;
        var height = container.clientHeight || 300;

        svg = d3.select(container)
            .append('svg')
            .attr('width', width)
            .attr('height', height)
            .attr('viewBox', [0, 0, width, height]);

        if (!data || !data.nodes || data.nodes.length === 0) {
            svg.append('text')
                .attr('x', width / 2)
                .attr('y', height / 2)
                .attr('text-anchor', 'middle')
                .attr('fill', '#8b9ab5')
                .attr('font-size', '0.85rem')
                .text('No social graph data available');
            return;
        }

        // Build node id set for edge filtering
        var nodeIds = new Set(data.nodes.map(function (n) { return n.id; }));
        var edges = data.edges.filter(function (e) {
            return nodeIds.has(e.source) && nodeIds.has(e.target);
        });

        // Force simulation
        simulation = d3.forceSimulation(data.nodes)
            .force('link', d3.forceLink(edges).id(function (d) { return d.id; })
                .distance(function (d) { return 80 / (d.weight || 1); }))
            .force('charge', d3.forceManyBody().strength(-120))
            .force('center', d3.forceCenter(width / 2, height / 2))
            .force('collision', d3.forceCollide().radius(function (d) { return nodeRadius(d.event_count) + 2; }));

        // Edges
        var linkGroup = svg.append('g').attr('class', 'links');
        var link = linkGroup.selectAll('line')
            .data(edges)
            .enter()
            .append('line')
            .attr('stroke', function (d) { return RELATIONSHIP_COLORS[d.relationship] || '#4e5d73'; })
            .attr('stroke-width', function (d) { return edgeWidth(d.weight); })
            .attr('stroke-opacity', 0.6);

        // Nodes
        var nodeGroup = svg.append('g').attr('class', 'nodes');
        var node = nodeGroup.selectAll('circle')
            .data(data.nodes)
            .enter()
            .append('circle')
            .attr('r', function (d) { return nodeRadius(d.event_count); })
            .attr('fill', function (d) {
                var ci = (d.community != null ? d.community : 0) % COMMUNITY_COLORS.length;
                return COMMUNITY_COLORS[ci];
            })
            .attr('stroke', '#0c1017')
            .attr('stroke-width', 1.5)
            .style('cursor', 'pointer')
            .on('mouseover', function (event, d) { showTooltip(event, d, container); })
            .on('mousemove', function (event, d) { showTooltip(event, d, container); })
            .on('mouseout', hideTooltip)
            .on('click', function (event, d) {
                isEgoView = true;
                var backBtn = container.querySelector('.social-graph-back-btn');
                if (backBtn) backBtn.style.display = 'block';
                fetchAndRender('/api/social-graph/' + encodeURIComponent(d.id));
            })
            .call(d3.drag()
                .on('start', function (event, d) {
                    if (!event.active) simulation.alphaTarget(0.3).restart();
                    d.fx = d.x;
                    d.fy = d.y;
                })
                .on('drag', function (event, d) {
                    d.fx = event.x;
                    d.fy = event.y;
                })
                .on('end', function (event, d) {
                    if (!event.active) simulation.alphaTarget(0);
                    d.fx = null;
                    d.fy = null;
                }));

        // Labels for larger nodes
        var labels = nodeGroup.selectAll('text')
            .data(data.nodes.filter(function (d) { return (d.event_count || 0) > 10; }))
            .enter()
            .append('text')
            .text(function (d) { return d.id.length > 12 ? d.id.slice(0, 11) + '\u2026' : d.id; })
            .attr('font-size', '0.55rem')
            .attr('fill', '#e8e4dc')
            .attr('text-anchor', 'middle')
            .attr('dy', function (d) { return -nodeRadius(d.event_count) - 4; })
            .style('pointer-events', 'none');

        // Tick
        simulation.on('tick', function () {
            link
                .attr('x1', function (d) { return d.source.x; })
                .attr('y1', function (d) { return d.source.y; })
                .attr('x2', function (d) { return d.target.x; })
                .attr('y2', function (d) { return d.target.y; });

            node
                .attr('cx', function (d) { return d.x = Math.max(10, Math.min(width - 10, d.x)); })
                .attr('cy', function (d) { return d.y = Math.max(10, Math.min(height - 10, d.y)); });

            labels
                .attr('x', function (d) { return d.x; })
                .attr('y', function (d) { return d.y - nodeRadius(d.event_count) - 4; });
        });
    }

    // --- Fetch & Render ---
    function fetchAndRender(url) {
        var container = document.getElementById(containerId);
        if (!container) return;

        fetch(url)
            .then(function (res) { return res.json(); })
            .then(function (data) { render(data, container); })
            .catch(function (err) {
                console.error('Social graph fetch error:', err);
                var existing = container.querySelector('svg');
                if (existing) existing.remove();

                var fallbackSvg = d3.select(container)
                    .append('svg')
                    .attr('width', container.clientWidth || 400)
                    .attr('height', container.clientHeight || 300);

                fallbackSvg.append('text')
                    .attr('x', (container.clientWidth || 400) / 2)
                    .attr('y', (container.clientHeight || 300) / 2)
                    .attr('text-anchor', 'middle')
                    .attr('fill', '#8b9ab5')
                    .attr('font-size', '0.85rem')
                    .text('Failed to load social graph');
            });
    }

    // --- Resize ---
    function handleResize(container) {
        if (!currentData) return;
        render(currentData, container);
    }

    // --- Public API ---
    function init(id) {
        containerId = id;
        var container = document.getElementById(id);
        if (!container) return;

        ensureTooltip(container);
        buildLegend(container);
        var backBtn = buildBackButton(container);

        // ResizeObserver for responsive SVG
        if (resizeObserver) resizeObserver.disconnect();
        resizeObserver = new ResizeObserver(function () {
            handleResize(container);
        });
        resizeObserver.observe(container);

        isEgoView = false;
        backBtn.style.display = 'none';
        fetchAndRender('/api/social-graph?limit=200');
    }

    function destroy() {
        if (simulation) { simulation.stop(); simulation = null; }
        if (resizeObserver) { resizeObserver.disconnect(); resizeObserver = null; }
        hideTooltip();
        tooltip = null;
        currentData = null;
        isEgoView = false;
        if (containerId) {
            var container = document.getElementById(containerId);
            if (container) container.innerHTML = '';
        }
        containerId = null;
    }

    return { init: init, destroy: destroy };
})();
