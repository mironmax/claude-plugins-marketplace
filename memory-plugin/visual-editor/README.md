# Knowledge Graph Visual Editor

Read-only web-based visualization tool for the Memory Plugin knowledge graph.

## Overview

The Visual Editor provides an interactive D3.js force-directed graph visualization of your knowledge graph, showing both user-level and project-level nodes and edges.

## Features

- **Real-time Visualization**: Force-directed graph layout using D3.js
- **Dual-Level Support**: View user and project graphs simultaneously
- **Interactive**: Click nodes to view details, drag to rearrange
- **Filtering**: Toggle between all levels, user-only, or project-only
- **Responsive**: Desktop-optimized (minimum 1366px width)
- **Auto-refresh**: Graph updates every 30 seconds

## Architecture

```
┌─────────────┐
│   Browser   │
│  localhost: │
│    3000     │
└──────┬──────┘
       │ HTTP
       ▼
┌─────────────────┐
│ Visual Editor   │
│ FastAPI Server  │
│  (backend/)     │
└──────┬──────────┘
       │ HTTP
       ▼
┌─────────────────┐
│  MCP Server     │
│  localhost:8765 │
│ (mcp_http/app)  │
└─────────────────┘
```

## Requirements

- Python 3.10+
- MCP HTTP Server running on `http://127.0.0.1:8765`
- Desktop browser (1366px minimum width)

## Installation

```bash
cd visual-editor
pip install -r requirements.txt
```

## Usage

### 1. Start MCP Server

First, ensure the MCP HTTP server is running:

```bash
cd ../server
./manage_server.sh start
```

Verify it's running:
```bash
curl http://127.0.0.1:8765/api/health
```

### 2. Start Visual Editor

```bash
cd visual-editor/backend
python server.py
```

The editor will start on `http://127.0.0.1:3000`

### 3. Open in Browser

Navigate to: `http://localhost:3000`

## Configuration

Environment variables (optional):

- `EDITOR_PORT`: Port for visual editor (default: 3000)
- `EDITOR_HOST`: Host binding (default: 127.0.0.1)
- `MCP_SERVER_URL`: MCP server URL (default: http://127.0.0.1:8765)

Example:
```bash
EDITOR_PORT=8080 MCP_SERVER_URL=http://localhost:8765 python server.py
```

## Usage Guide

### Interface Layout

```
┌─────────────────────────────────────────────────┐
│ Header: Title | Refresh | Connection Status    │
├─────────────────────────────────────────────────┤
│                                                 │
│  Graph Visualization Panel                      │
│  - Force-directed layout                        │
│  - Zoom/pan controls                            │
│  - Level filter dropdown                        │
│                                                 │
├─────────────────────────────────────────────────┤
│ Detail Panel (bottom)                           │
│ - Node details shown on click                   │
│ - ID, level, description, notes, files          │
└─────────────────────────────────────────────────┘
```

### Node Colors

- **Blue**: Active user-level node
- **Cyan**: Active project-level node
- **Dark grey**: Archived node (semi-transparent)
- **Light grey**: Orphaned node (very transparent)

### Controls

- **Click node**: View details in bottom panel
- **Drag node**: Rearrange graph layout
- **Zoom**: Use +/- buttons or mouse wheel
- **Filter**: Select level from dropdown (All/User/Project)
- **Refresh**: Manual refresh button (also auto-refreshes every 30s)

### Keyboard Shortcuts

None currently implemented (read-only mode).

## Development

### File Structure

```
visual-editor/
├── backend/
│   └── server.py          # FastAPI application
├── frontend/
│   ├── index.html         # Main HTML page
│   └── static/
│       ├── css/
│       │   └── style.css  # Styles
│       └── js/
│           └── app.js     # D3.js visualization logic
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

### API Endpoints

**Visual Editor Backend:**
- `GET /` - Serve HTML page
- `GET /api/health` - Health check (includes MCP server status)
- `GET /api/graph?session_id=<id>` - Fetch graph data

**MCP Server (proxied):**
- `GET /api/graph/read?session_id=<id>` - Raw graph data

## Limitations (Read-Only MVP)

- ❌ No editing capabilities (create/update/delete nodes/edges)
- ❌ No WebSocket real-time updates (uses polling)
- ❌ No authentication/authorization
- ❌ Desktop only (no mobile support)

These will be addressed in Phase 6 (Write Support).

## Troubleshooting

### "Cannot connect to MCP server"

1. Verify MCP server is running:
   ```bash
   curl http://127.0.0.1:8765/api/health
   ```

2. Check server logs:
   ```bash
   cd ../server
   ./manage_server.sh status
   ```

3. Restart MCP server:
   ```bash
   ./manage_server.sh restart
   ```

### "Desktop Required" message

- Minimum screen width: 1366px
- Use a desktop or laptop browser
- This is intentional (graph visualization needs space)

### Graph not loading

1. Check browser console for errors (F12)
2. Verify network requests in DevTools
3. Check MCP server is returning data:
   ```bash
   curl http://127.0.0.1:8765/api/graph/read
   ```

### Empty graph

- No nodes in knowledge graph yet
- Use Claude Code to create nodes first
- Check if session_id is set correctly

## Next Steps (Phase 6)

- [ ] Add edit capabilities (create/update/delete)
- [ ] WebSocket real-time updates
- [ ] Authentication and authorization
- [ ] Search and filtering improvements
- [ ] Undo/redo functionality
- [ ] Export/import capabilities

## License

Same as parent project (see ../LICENSE)
