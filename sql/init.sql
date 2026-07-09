-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================
-- STREET NETWORK TABLES (from OpenStreetMap / GraphML)
-- ============================================================

-- Intersections / junctions (graph nodes)
CREATE TABLE nodes (
    node_id       BIGINT PRIMARY KEY,
    geom          GEOMETRY(Point, 4326) NOT NULL
);

CREATE INDEX idx_nodes_geom ON nodes USING GIST (geom);

-- Road segments (graph edges)
CREATE TABLE edges (
    edge_id       SERIAL PRIMARY KEY,
    source_node   BIGINT NOT NULL REFERENCES nodes(node_id),
    target_node   BIGINT NOT NULL REFERENCES nodes(node_id),
    highway       TEXT,
    name          TEXT,
    oneway        BOOLEAN DEFAULT FALSE,
    length_m      DOUBLE PRECISION,
    speed_kph     DOUBLE PRECISION,
    geom          GEOMETRY(LineString, 4326)
);

CREATE INDEX idx_edges_geom ON edges USING GIST (geom);
CREATE INDEX idx_edges_source ON edges (source_node);
CREATE INDEX idx_edges_target ON edges (target_node);

-- ============================================================
-- ARTIFICIAL TRAFFIC DATA
-- ============================================================

-- Simulated vehicle positions (moving through the network)
CREATE TABLE vehicle_positions (
    id            SERIAL PRIMARY KEY,
    vehicle_id    TEXT NOT NULL,
    timestamp     TIMESTAMPTZ NOT NULL,
    speed_kph     DOUBLE PRECISION,
    heading       DOUBLE PRECISION,
    edge_id       INTEGER REFERENCES edges(edge_id),
    geom          GEOMETRY(Point, 4326) NOT NULL
);

CREATE INDEX idx_vehicle_positions_geom ON vehicle_positions USING GIST (geom);
CREATE INDEX idx_vehicle_positions_time ON vehicle_positions (timestamp);
CREATE INDEX idx_vehicle_positions_vehicle ON vehicle_positions (vehicle_id);

-- Traffic density aggregated per edge (e.g. per 5-min window)
CREATE TABLE traffic_density (
    id            SERIAL PRIMARY KEY,
    edge_id       INTEGER NOT NULL REFERENCES edges(edge_id),
    time_bucket   TIMESTAMPTZ NOT NULL,
    vehicle_count INTEGER NOT NULL,
    avg_speed_kph DOUBLE PRECISION,
    congestion    DOUBLE PRECISION  -- 0.0 = free flow, 1.0 = gridlock
);

CREATE INDEX idx_traffic_density_edge ON traffic_density (edge_id);
CREATE INDEX idx_traffic_density_time ON traffic_density (time_bucket);