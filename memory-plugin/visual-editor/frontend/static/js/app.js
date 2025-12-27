/**
 * Knowledge Graph Visual Editor - Main Application
 *
 * Read-only graph visualization using D3.js force-directed layout
 */

// ============================================================================
// Configuration
// ============================================================================

const CONFIG = {
    apiBaseUrl: window.location.origin,
    mcpServerUrl: 'http://127.0.0.1:8765',
    refreshInterval: 30000, // 30 seconds
    simulation: {
        linkDistance: 150,
        linkStrength: 0.3,
        chargeStrength: -400,
        centerStrength: 0.1,
        collisionRadius: 50,
    },
    node: {
        radius: 8,
        radiusSelected: 12,
    },
};

// ============================================================================
// State Management
// ============================================================================

const state = {
    graphData: null,
    selectedNode: null,
    graphLevel: 'user',  // 'user' or 'project'
    selectedProject: null,  // project_path when level='project'
    projects: [],  // Available projects from /api/projects
    simulation: null,
    zoom: null,
};

// ============================================================================
// Utility Functions
// ============================================================================

function showElement(id) {
    document.getElementById(id)?.classList.remove('hidden');
}

function hideElement(id) {
    document.getElementById(id)?.classList.add('hidden');
}

function setConnectionStatus(status, text) {
    const statusDot = document.getElementById('connection-status');
    const statusText = document.getElementById('connection-text');

    statusDot.className = `status-dot status-${status}`;
    statusText.textContent = text;
}

function updateStats(nodeCount, edgeCount) {
    document.getElementById('node-count').textContent = `Nodes: ${nodeCount}`;
    document.getElementById('edge-count').textContent = `Edges: ${edgeCount}`;
}

function showError(message) {
    document.getElementById('error-message').textContent = message;
    hideElement('graph-loading');
    showElement('graph-error');
    setConnectionStatus('error', 'Disconnected');
}

// ============================================================================
// API Functions
// ============================================================================

async function fetchProjects() {
    try {
        const response = await fetch(`${CONFIG.apiBaseUrl}/api/projects`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error fetching projects:', error);
        return [];
    }
}

async function fetchGraphData() {
    try {
        let params = '';
        if (state.graphLevel === 'project' && state.selectedProject) {
            params = `?project_path=${encodeURIComponent(state.selectedProject)}`;
        }

        const response = await fetch(`${CONFIG.apiBaseUrl}/api/graph${params}`);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Error fetching graph data:', error);
        throw error;
    }
}

async function checkHealth() {
    try {
        const response = await fetch(`${CONFIG.apiBaseUrl}/api/health`);
        const health = await response.json();

        if (health.status === 'ok' && health.mcp_server?.status === 'ok') {
            setConnectionStatus('connected', 'Connected');
            return true;
        } else {
            setConnectionStatus('error', 'MCP Server Down');
            return false;
        }
    } catch (error) {
        setConnectionStatus('error', 'Connection Failed');
        return false;
    }
}

// ============================================================================
// Project Management
// ============================================================================

async function loadProjects() {
    try {
        const projects = await fetchProjects();
        state.projects = projects;

        const selector = document.getElementById('project-selector');
        selector.innerHTML = '<option value="">Select a project...</option>';

        projects.forEach(project => {
            const option = document.createElement('option');
            option.value = project.project_path;

            // Format: "DevProj/project-name (235N • 127E)"
            let label = project.display_name;
            if (project.has_graph && project.node_count !== null) {
                label += ` (${project.node_count}N • ${project.edge_count}E)`;
            } else {
                label += ' (no graph)';
            }

            option.textContent = label;
            option.title = project.project_path;  // Tooltip shows full path
            selector.appendChild(option);
        });

        console.log(`Loaded ${projects.length} projects`);
    } catch (error) {
        console.error('Failed to load projects:', error);
    }
}

// ============================================================================
// Data Transformation
// ============================================================================

function transformGraphData(rawData) {
    /**
     * Transform MCP graph format into D3.js-compatible format
     *
     * Input format:
     * {
     *   "user": { "nodes": {...}, "edges": {...} },
     *   "project": { "nodes": {...}, "edges": {...} }
     * }
     *
     * Output format:
     * {
     *   nodes: [{id, gist, level, archived, orphaned, ...}, ...],
     *   links: [{source, target, rel, ...}, ...]
     * }
     */
    const nodes = [];
    const links = [];

    // Process user-level nodes
    if (rawData.user?.nodes) {
        Object.values(rawData.user.nodes).forEach(node => {
            nodes.push({
                ...node,
                level: 'user',
                archived: node._archived || false,
                orphaned: node._orphaned_ts != null,
            });
        });
    }

    // Process project-level nodes
    if (rawData.project?.nodes) {
        Object.values(rawData.project.nodes).forEach(node => {
            nodes.push({
                ...node,
                level: 'project',
                archived: node._archived || false,
                orphaned: node._orphaned_ts != null,
            });
        });
    }

    // Create node ID set for validation
    const nodeIds = new Set(nodes.map(n => n.id));

    // Process user-level edges (with validation)
    if (rawData.user?.edges) {
        Object.values(rawData.user.edges).forEach(edge => {
            // Skip orphaned edges (pointing to non-existent nodes)
            if (!nodeIds.has(edge.from)) {
                console.warn(`Skipping orphaned edge: ${edge.from} -> ${edge.to} (source node missing)`);
                return;
            }
            if (!nodeIds.has(edge.to)) {
                console.warn(`Skipping orphaned edge: ${edge.from} -> ${edge.to} (target node missing)`);
                return;
            }

            links.push({
                ...edge,
                source: edge.from,
                target: edge.to,
                level: 'user',
            });
        });
    }

    // Process project-level edges (with validation)
    if (rawData.project?.edges) {
        Object.values(rawData.project.edges).forEach(edge => {
            // Skip orphaned edges (pointing to non-existent nodes)
            if (!nodeIds.has(edge.from)) {
                console.warn(`Skipping orphaned edge: ${edge.from} -> ${edge.to} (source node missing)`);
                return;
            }
            if (!nodeIds.has(edge.to)) {
                console.warn(`Skipping orphaned edge: ${edge.from} -> ${edge.to} (target node missing)`);
                return;
            }

            links.push({
                ...edge,
                source: edge.from,
                target: edge.to,
                level: 'project',
            });
        });
    }

    return { nodes, links };
}

function applyLevelFilter(data, graphLevel) {
    // With new design: user OR project (not both, not "all")
    const filter = graphLevel === 'user' ? 'user' : 'project';

    const filteredNodes = data.nodes.filter(n => n.level === filter);
    const nodeIds = new Set(filteredNodes.map(n => n.id));
    const filteredLinks = data.links.filter(
        l => nodeIds.has(l.source.id || l.source) && nodeIds.has(l.target.id || l.target)
    );

    return {
        nodes: filteredNodes,
        links: filteredLinks,
    };
}

// ============================================================================
// D3.js Visualization
// ============================================================================

function initializeGraph() {
    const svg = d3.select('#graph-svg');
    const container = svg.append('g');

    // Setup zoom behavior
    state.zoom = d3.zoom()
        .scaleExtent([0.1, 4])
        .on('zoom', (event) => {
            container.attr('transform', event.transform);
        });

    svg.call(state.zoom);

    // Create force simulation
    const width = document.getElementById('graph-container').clientWidth;
    const height = document.getElementById('graph-container').clientHeight;

    state.simulation = d3.forceSimulation()
        .force('link', d3.forceLink().id(d => d.id).distance(CONFIG.simulation.linkDistance).strength(CONFIG.simulation.linkStrength))
        .force('charge', d3.forceManyBody().strength(CONFIG.simulation.chargeStrength))
        .force('center', d3.forceCenter(width / 2, height / 2).strength(CONFIG.simulation.centerStrength))
        .force('collision', d3.forceCollide().radius(CONFIG.simulation.collisionRadius));

    return { svg, container };
}

function renderGraph(graphData) {
    const { svg, container } = state.svgElements || initializeGraph();

    if (!state.svgElements) {
        state.svgElements = { svg, container };
    }

    // Clear existing elements
    container.selectAll('*').remove();

    // Apply level filter
    const filteredData = applyLevelFilter(graphData, state.graphLevel);

    // Update stats
    updateStats(filteredData.nodes.length, filteredData.links.length);

    if (filteredData.nodes.length === 0) {
        showEmptyState('No nodes to display');
        return;
    }

    // Create links
    const link = container.append('g')
        .selectAll('line')
        .data(filteredData.links)
        .enter()
        .append('line')
        .attr('class', 'link')
        .attr('stroke-width', 1.5);

    // Create link labels
    const linkLabel = container.append('g')
        .selectAll('text')
        .data(filteredData.links)
        .enter()
        .append('text')
        .attr('class', 'link-label')
        .text(d => d.rel);

    // Create nodes
    const node = container.append('g')
        .selectAll('circle')
        .data(filteredData.nodes)
        .enter()
        .append('circle')
        .attr('class', d => {
            const classes = ['node', `node-${d.level}`];
            if (d.archived) classes.push('node-archived');
            if (d.orphaned) classes.push('node-orphan');
            return classes.join(' ');
        })
        .attr('r', CONFIG.node.radius)
        .on('click', (event, d) => handleNodeClick(event, d))
        .call(d3.drag()
            .on('start', dragStarted)
            .on('drag', dragged)
            .on('end', dragEnded));

    // Create node labels
    const nodeLabel = container.append('g')
        .selectAll('text')
        .data(filteredData.nodes)
        .enter()
        .append('text')
        .attr('class', 'node-label')
        .attr('dy', -15)
        .text(d => truncateText(d.id, 20));

    // Update simulation
    state.simulation
        .nodes(filteredData.nodes)
        .on('tick', () => {
            link
                .attr('x1', d => d.source.x)
                .attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x)
                .attr('y2', d => d.target.y);

            linkLabel
                .attr('x', d => (d.source.x + d.target.x) / 2)
                .attr('y', d => (d.source.y + d.target.y) / 2);

            node
                .attr('cx', d => d.x)
                .attr('cy', d => d.y);

            nodeLabel
                .attr('x', d => d.x)
                .attr('y', d => d.y);
        });

    state.simulation.force('link').links(filteredData.links);
    state.simulation.alpha(1).restart();
}

function showEmptyState(message) {
    const container = state.svgElements?.container;
    if (!container) return;

    container.selectAll('*').remove();

    const width = document.getElementById('graph-container').clientWidth;
    const height = document.getElementById('graph-container').clientHeight;

    container.append('text')
        .attr('x', width / 2)
        .attr('y', height / 2)
        .attr('text-anchor', 'middle')
        .attr('class', 'empty-state')
        .style('fill', '#cbd5e1')
        .style('font-size', '1.1rem')
        .text(message);
}

// ============================================================================
// Event Handlers
// ============================================================================

function handleNodeClick(event, node) {
    // Update selection state
    d3.selectAll('.node').classed('selected', false);
    d3.select(event.target).classed('selected', true);

    state.selectedNode = node;
    renderNodeDetails(node);
}

function renderNodeDetails(node) {
    const container = document.getElementById('detail-content');

    const html = `
        <div class="node-detail">
            <div class="detail-section">
                <h3>Node Information</h3>
                <div class="detail-field">
                    <div class="detail-label">ID</div>
                    <div class="detail-value"><code>${escapeHtml(node.id)}</code></div>
                </div>
                <div class="detail-field">
                    <div class="detail-label">Level</div>
                    <div class="detail-value">
                        <span class="badge badge-${node.level}">${node.level}</span>
                        ${node.archived ? '<span class="badge badge-archived">Archived</span>' : ''}
                        ${node.orphaned ? '<span class="badge badge-archived">Orphaned</span>' : ''}
                    </div>
                </div>
                <div class="detail-field">
                    <div class="detail-label">Description</div>
                    <div class="detail-value">${escapeHtml(node.gist)}</div>
                </div>
            </div>

            ${node.notes && node.notes.length > 0 ? `
                <div class="detail-section">
                    <h3>Notes</h3>
                    <ul class="detail-list">
                        ${node.notes.map(note => `<li>${escapeHtml(note)}</li>`).join('')}
                    </ul>
                </div>
            ` : ''}

            ${node.touches && node.touches.length > 0 ? `
                <div class="detail-section">
                    <h3>Files & Artifacts</h3>
                    <ul class="detail-list">
                        ${node.touches.map(file => `<li><code>${escapeHtml(file)}</code></li>`).join('')}
                    </ul>
                </div>
            ` : ''}
        </div>
    `;

    container.innerHTML = html;
}

function dragStarted(event, d) {
    if (!event.active) state.simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
}

function dragged(event, d) {
    d.fx = event.x;
    d.fy = event.y;
}

function dragEnded(event, d) {
    if (!event.active) state.simulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
}

// ============================================================================
// Main Application Logic
// ============================================================================

async function loadGraph() {
    try {
        hideElement('graph-error');
        showElement('graph-loading');

        const rawData = await fetchGraphData();
        state.graphData = transformGraphData(rawData);

        renderGraph(state.graphData);

        hideElement('graph-loading');
        setConnectionStatus('connected', 'Connected');
    } catch (error) {
        console.error('Failed to load graph:', error);
        showError(`Failed to load graph: ${error.message}`);
    }
}

async function initialize() {
    console.log('Initializing Knowledge Graph Visual Editor...');

    // Check server health
    const healthy = await checkHealth();
    if (!healthy) {
        showError('Cannot connect to MCP server. Please ensure the server is running.');
        return;
    }

    // Load projects and populate dropdown
    await loadProjects();

    // Load initial graph
    await loadGraph();

    // Setup event listeners
    document.getElementById('refresh-btn').addEventListener('click', loadGraph);
    document.getElementById('retry-btn').addEventListener('click', loadGraph);

    document.getElementById('zoom-in-btn').addEventListener('click', () => {
        state.svgElements?.svg.transition().call(state.zoom.scaleBy, 1.3);
    });

    document.getElementById('zoom-out-btn').addEventListener('click', () => {
        state.svgElements?.svg.transition().call(state.zoom.scaleBy, 0.7);
    });

    document.getElementById('zoom-reset-btn').addEventListener('click', () => {
        state.svgElements?.svg.transition().call(state.zoom.transform, d3.zoomIdentity);
    });

    // Level selector radio buttons
    document.getElementById('level-user').addEventListener('change', (e) => {
        if (e.target.checked) {
            state.graphLevel = 'user';
            document.getElementById('project-selector').disabled = true;
            loadGraph();
        }
    });

    document.getElementById('level-project').addEventListener('change', (e) => {
        if (e.target.checked) {
            state.graphLevel = 'project';
            const selector = document.getElementById('project-selector');
            selector.disabled = false;
            if (selector.value) {
                state.selectedProject = selector.value;
                loadGraph();
            }
        }
    });

    // Project selector dropdown
    document.getElementById('project-selector').addEventListener('change', (e) => {
        state.selectedProject = e.target.value;
        if (state.graphLevel === 'project' && state.selectedProject) {
            loadGraph();
        }
    });

    // Mobile detection
    updateScreenSize();
    window.addEventListener('resize', updateScreenSize);

    // Auto-refresh
    setInterval(async () => {
        console.log('Auto-refreshing graph...');
        await loadGraph();
    }, CONFIG.refreshInterval);

    console.log('Editor initialized successfully');
}

function updateScreenSize() {
    const width = window.innerWidth;
    document.getElementById('current-width').textContent = width;
}

function truncateText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength - 3) + '...';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================================================
// Entry Point
// ============================================================================

document.addEventListener('DOMContentLoaded', initialize);
