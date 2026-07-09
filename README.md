# GeoSQL + PostGIS + Dekart — Wellington CBD Traffic Playground

Local setup to explore geospatial data with Claude's GeoSQL skill, PostGIS, and Dekart map visualizations.

**What you get:** Wellington CBD street network + simulated traffic data in PostGIS, Dekart for map rendering, and Claude Desktop with GeoSQL to query and visualize it all.

---

## Prerequisites

- Docker Desktop running
- Python 3.10+
- [Claude Desktop](https://claude.ai/download) installed

---

## Step-by-step Setup

### 1. Start PostGIS + Dekart

```bash
docker compose up -d
```

This starts:
- **PostGIS** on `localhost:5432` (db: `geosql`, user: `geosql`, password: `geosql123`)
- **Dekart** on `http://localhost:8080`

Wait a few seconds for Postgres to initialize, then verify:

```bash
docker compose ps
```

Both containers should show "running" / "healthy".

---

### 2. Install Python dependencies

```bash
pip3 install -r requirements.txt
```

---

### 3. Load Wellington CBD street network into PostGIS

```bash
python3 scripts/ingest_graphml.py
```

This parses `data/wellington_cbd.graphml` and loads ~nodes and edges into PostGIS.

---

### 4. Generate artificial traffic data

```bash
python3 scripts/generate_traffic.py
```

This simulates 50 vehicles driving through the Wellington CBD road network for 1 hour (morning rush 08:00–09:00) and loads:
- `vehicle_positions` — individual GPS pings along road segments
- `traffic_density` — aggregated vehicle counts per road segment per 5-minute window

---

### 5. Connect Dekart to PostGIS

Open **http://localhost:8080** in your browser. Dekart is already configured to connect to PostGIS via the docker-compose environment variables. You should be able to create a new report and run SQL queries immediately.

Test it by creating a new report and running:

```sql
SELECT name, highway, length_m, geom FROM edges LIMIT 100;
```

You should see Wellington CBD streets rendered on the map.

---

### 6. Install GeoSQL and Dekart

See https://github.com/dekart-xyz/geosql for reference.

```bash
pip3 install geosql dekart
```

---

### 7. Initialize Dekart CLI

```bash
dekart init
```

When prompted:
1. **Endpoint:** Select **"Local Dekart: http://localhost:8080"** (arrow down, Enter)
2. **Authorize:** A browser will open — click **Approve** in the Dekart UI
3. **Local snapshot:** Select **"Install local snapshot now (recommended)"**

This connects the CLI to your docker-compose Dekart instance (already running from step 1).

---

### 8. Install GeoSQL skill

```bash
geosql install claude
```

This installs the GeoSQL skill at `~/.claude/skills/geosql/SKILL.md`. It works with:
- **VS Code + GitHub Copilot** (Claude model) — the skill is auto-loaded
- **Claude Code CLI** (`claude` in terminal)

> **Note:** Claude Desktop does not support skills/MCP tools from the `dekart` CLI. Use VS Code Copilot or Claude Code instead.

---

### 9. Use GeoSQL

Open **VS Code with GitHub Copilot** (Claude model) or **Claude Code CLI** and try these prompts:

**Explore the road network:**
```
/geosql Show all roads in Wellington CBD colored by road type (highway classification), render as a map
```

**Traffic density heatmap:**
```
/geosql Show traffic congestion on Wellington CBD roads. Use the traffic_density table, color edges by average congestion level. Render as a map.
```

**Vehicle movement:**
```
/geosql Show the path of vehicle VEH-0001 through Wellington CBD as a time-ordered line, render as a map
```

**Find congestion hotspots:**
```
/geosql Find the top 10 most congested road segments in Wellington CBD during 08:00-09:00 UTC. Show vehicle count and average speed. Render as a map.
```

**Spatial analysis:**
```
/geosql Find all intersections (nodes) within 200 meters of the most congested road segment. Render both the segment and nearby intersections on a map.
```

---

## Database Schema

| Table | Description |
|-------|-------------|
| `nodes` | Intersections/junctions with Point geometry |
| `edges` | Road segments with LineString geometry, speed, highway type |
| `vehicle_positions` | Simulated GPS pings (vehicle_id, timestamp, speed, geometry) |
| `traffic_density` | Aggregated traffic per edge per 5-min bucket (count, avg speed, congestion 0–1) |

---

## Quick Reference

| Service | URL / Connection |
|---------|-----------------|
| Dekart UI | http://localhost:8080 |
| PostGIS | `postgresql://geosql:geosql123@localhost:5432/geosql` |

```bash
# Reset everything
docker compose down -v
docker compose up -d
python3 scripts/ingest_graphml.py
python3 scripts/generate_traffic.py
```

---

## Troubleshooting

**Dekart can't connect to PostGIS:** Make sure both containers are healthy (`docker compose ps`). Dekart waits for PostGIS via `depends_on` health check.

**GeoSQL not working in Claude:** Restart Claude Desktop after `geosql install claude`. Check config at `~/Library/Application Support/Claude/claude_desktop_config.json`.

**Port 5432 already in use:** Stop any local PostgreSQL (`brew services stop postgresql`) or change the port mapping in `docker-compose.yml`.