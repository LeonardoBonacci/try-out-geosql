"""
Generate artificial traffic data for Wellington CBD.

Simulates vehicles moving along the road network and produces:
- vehicle_positions: individual GPS pings along edges
- traffic_density: aggregated counts per edge per 5-minute bucket

Usage:
    python scripts/generate_traffic.py
"""

import random
from datetime import datetime, timedelta, timezone

import psycopg2
from psycopg2.extras import execute_values

# ─── Configuration ───────────────────────────────────────────────────────────

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "geosql",
    "user": "geosql",
    "password": "geosql123",
}

NUM_VEHICLES = 50
SIMULATION_DURATION_MINUTES = 60  # 1 hour of data
PING_INTERVAL_SECONDS = 10  # GPS ping every 10 seconds
BUCKET_MINUTES = 5

random.seed(42)


def fetch_edges(conn):
    """Fetch all edges with geometry from the database."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT edge_id, source_node, target_node, length_m, speed_kph,
                   ST_X(ST_StartPoint(geom)) AS x1, ST_Y(ST_StartPoint(geom)) AS y1,
                   ST_X(ST_EndPoint(geom)) AS x2, ST_Y(ST_EndPoint(geom)) AS y2
            FROM edges
            WHERE geom IS NOT NULL AND length_m IS NOT NULL
        """)
        return cur.fetchall()


def fetch_adjacency(conn):
    """Build adjacency list: node -> list of (edge_id, next_node, length_m, speed_kph)."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT edge_id, source_node, target_node, length_m, speed_kph
            FROM edges
            WHERE geom IS NOT NULL AND length_m IS NOT NULL
        """)
        rows = cur.fetchall()

    adj = {}
    for edge_id, src, tgt, length_m, speed_kph in rows:
        if src not in adj:
            adj[src] = []
        adj[src].append((edge_id, tgt, length_m, speed_kph or 30.0))
        # For non-oneway roads, allow reverse traversal
        if tgt not in adj:
            adj[tgt] = []
        adj[tgt].append((edge_id, src, length_m, speed_kph or 30.0))

    return adj


def interpolate_position(edge, fraction):
    """Linearly interpolate a position along an edge."""
    _, _, _, _, _, x1, y1, x2, y2 = edge
    x = x1 + (x2 - x1) * fraction
    y = y1 + (y2 - y1) * fraction
    return x, y


def simulate_vehicles(conn):
    """Simulate vehicles moving through the network."""
    edges = fetch_edges(conn)
    adj = fetch_adjacency(conn)

    if not edges or not adj:
        print("No edges found in database. Run ingest_graphml.py first.")
        return

    edge_lookup = {e[0]: e for e in edges}
    all_nodes = list(adj.keys())

    start_time = datetime(2025, 3, 15, 8, 0, 0, tzinfo=timezone.utc)  # morning rush
    end_time = start_time + timedelta(minutes=SIMULATION_DURATION_MINUTES)

    positions = []
    density_counts = {}  # (edge_id, bucket) -> [speeds]

    print(f"Simulating {NUM_VEHICLES} vehicles over {SIMULATION_DURATION_MINUTES} minutes...")

    for v_idx in range(NUM_VEHICLES):
        vehicle_id = f"VEH-{v_idx:04d}"
        current_node = random.choice(all_nodes)
        current_time = start_time + timedelta(seconds=random.randint(0, 300))

        while current_time < end_time:
            # Pick a random outgoing edge
            neighbors = adj.get(current_node, [])
            if not neighbors:
                current_node = random.choice(all_nodes)
                continue

            edge_id, next_node, length_m, speed_kph = random.choice(neighbors)
            edge = edge_lookup.get(edge_id)
            if edge is None:
                current_node = next_node
                continue

            # Add some speed variation (0.5x to 1.2x)
            actual_speed = speed_kph * random.uniform(0.5, 1.2)
            travel_time_s = (length_m / 1000.0) / (actual_speed / 3600.0)

            # Generate pings along this edge
            num_pings = max(1, int(travel_time_s / PING_INTERVAL_SECONDS))
            for i in range(num_pings):
                if current_time >= end_time:
                    break
                fraction = i / max(num_pings, 1)
                x, y = interpolate_position(edge, fraction)
                heading = random.uniform(0, 360)

                positions.append((
                    vehicle_id,
                    current_time.isoformat(),
                    actual_speed,
                    heading,
                    edge_id,
                    f"SRID=4326;POINT({x} {y})",
                ))

                # Track density
                bucket = current_time.replace(
                    minute=(current_time.minute // BUCKET_MINUTES) * BUCKET_MINUTES,
                    second=0, microsecond=0
                )
                key = (edge_id, bucket)
                if key not in density_counts:
                    density_counts[key] = []
                density_counts[key].append(actual_speed)

                current_time += timedelta(seconds=PING_INTERVAL_SECONDS)

            current_node = next_node

    print(f"  Generated {len(positions)} vehicle position records.")
    print(f"  Generated {len(density_counts)} density buckets.")
    return positions, density_counts


def insert_positions(conn, positions):
    """Bulk insert vehicle positions."""
    sql = """
        INSERT INTO vehicle_positions (vehicle_id, timestamp, speed_kph, heading, edge_id, geom)
        VALUES %s
    """
    with conn.cursor() as cur:
        execute_values(
            cur, sql, positions,
            template="(%s, %s, %s, %s, %s, ST_GeomFromEWKT(%s))",
            page_size=500,
        )
    conn.commit()
    print(f"  Inserted {len(positions)} position records.")


def insert_density(conn, density_counts):
    """Compute and insert traffic density records."""
    rows = []
    for (edge_id, bucket), speeds in density_counts.items():
        avg_speed = sum(speeds) / len(speeds)
        vehicle_count = len(set())  # unique vehicles approximated by count
        # Congestion: ratio of speed reduction from free flow (assume 50 kph free flow)
        free_flow = 50.0
        congestion = max(0.0, min(1.0, 1.0 - (avg_speed / free_flow)))
        rows.append((
            edge_id,
            bucket.isoformat(),
            len(speeds),
            avg_speed,
            congestion,
        ))

    sql = """
        INSERT INTO traffic_density (edge_id, time_bucket, vehicle_count, avg_speed_kph, congestion)
        VALUES %s
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=500)
    conn.commit()
    print(f"  Inserted {len(rows)} density records.")


def main():
    print("Connecting to PostGIS ...")
    conn = psycopg2.connect(**DB_CONFIG)

    try:
        # Clear old traffic data
        with conn.cursor() as cur:
            cur.execute("TRUNCATE vehicle_positions, traffic_density RESTART IDENTITY")
        conn.commit()

        result = simulate_vehicles(conn)
        if result is None:
            return

        positions, density_counts = result

        print("Inserting vehicle positions ...")
        insert_positions(conn, positions)

        print("Inserting traffic density ...")
        insert_density(conn, density_counts)

        # Summary
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM vehicle_positions")
            pos_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM traffic_density")
            den_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(DISTINCT vehicle_id) FROM vehicle_positions")
            veh_count = cur.fetchone()[0]

        print(f"\nDone! Traffic data generated:")
        print(f"  {veh_count} unique vehicles")
        print(f"  {pos_count} GPS position records")
        print(f"  {den_count} density aggregation records")
        print(f"  Time range: 1 hour morning rush (08:00-09:00 UTC)")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
