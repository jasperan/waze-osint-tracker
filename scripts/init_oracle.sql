-- =============================================================================
-- Waze Behavioral Intelligence Engine — Oracle 26ai Free Schema
-- =============================================================================
-- Run as SYS against FREEPDB1 to create the waze schema user and all objects.
-- =============================================================================

ALTER SESSION SET CONTAINER = FREEPDB1;

-- Create schema user
CREATE USER waze IDENTIFIED BY WazeIntel2026  -- pragma: allowlist secret
    DEFAULT TABLESPACE USERS
    TEMPORARY TABLESPACE TEMP
    QUOTA UNLIMITED ON USERS;

GRANT CONNECT, RESOURCE TO waze;
GRANT CREATE SESSION TO waze;
GRANT CREATE TABLE TO waze;
GRANT CREATE VIEW TO waze;
GRANT CREATE SEQUENCE TO waze;
GRANT CREATE PROCEDURE TO waze;
GRANT CREATE ANY INDEX TO waze;
GRANT CREATE MINING MODEL TO waze;

-- Grant vector privileges (Oracle 26ai)
GRANT DB_DEVELOPER_ROLE TO waze;

-- Connect as waze user for object creation
ALTER SESSION SET CURRENT_SCHEMA = waze;

-- =============================================================================
-- EVENTS — Partitioned by region
-- =============================================================================
CREATE TABLE waze.events (
    event_id        NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_hash      VARCHAR2(64) NOT NULL,
    report_type     VARCHAR2(50),
    subtype         VARCHAR2(100),
    severity        NUMBER(1),
    reliability     NUMBER(2),
    confidence      NUMBER(3),
    latitude        NUMBER(10,6),
    longitude       NUMBER(10,6),
    street          VARCHAR2(500),
    city            VARCHAR2(200),
    country         VARCHAR2(100),
    region          VARCHAR2(50) NOT NULL,
    username        VARCHAR2(200),
    report_rating   NUMBER(3),
    report_mood     NUMBER(2),
    timestamp_utc   TIMESTAMP DEFAULT SYSTIMESTAMP,
    timestamp_ms    NUMBER(15),
    collected_at    TIMESTAMP DEFAULT SYSTIMESTAMP,
    grid_cell       VARCHAR2(200),
    speed           NUMBER(6,2),
    road_type       NUMBER(2),
    magvar          NUMBER(6,2),
    nearby_count    NUMBER(5),
    raw_json        CLOB,
    CONSTRAINT events_hash_region_uq UNIQUE (event_hash, region)
)
PARTITION BY LIST (region) (
    PARTITION p_europe   VALUES ('europe'),
    PARTITION p_americas VALUES ('americas'),
    PARTITION p_asia     VALUES ('asia'),
    PARTITION p_oceania  VALUES ('oceania'),
    PARTITION p_africa   VALUES ('africa'),
    PARTITION p_madrid   VALUES ('madrid')
);

CREATE INDEX idx_events_username ON waze.events (username) LOCAL;
CREATE INDEX idx_events_timestamp ON waze.events (timestamp_utc) LOCAL;
CREATE INDEX idx_events_type ON waze.events (report_type) LOCAL;
CREATE INDEX idx_events_location ON waze.events (latitude, longitude) LOCAL;
CREATE INDEX idx_events_city ON waze.events (city) LOCAL;

-- =============================================================================
-- COLLECTION_RUNS — Tracks each collection session
-- =============================================================================
CREATE TABLE waze.collection_runs (
    run_id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    region          VARCHAR2(50) NOT NULL,
    started_at      TIMESTAMP DEFAULT SYSTIMESTAMP,
    ended_at        TIMESTAMP,
    events_collected NUMBER DEFAULT 0,
    events_new      NUMBER DEFAULT 0,
    cells_scanned   NUMBER DEFAULT 0,
    status          VARCHAR2(20) DEFAULT 'running',
    error_message   CLOB
);

CREATE INDEX idx_collection_runs_region ON waze.collection_runs (region);
CREATE INDEX idx_collection_runs_started ON waze.collection_runs (started_at);

-- =============================================================================
-- TRACKED_USERS — Unique usernames seen across all regions
-- =============================================================================
CREATE TABLE waze.tracked_users (
    user_id         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username        VARCHAR2(200) NOT NULL,
    first_seen      TIMESTAMP DEFAULT SYSTIMESTAMP,
    last_seen       TIMESTAMP DEFAULT SYSTIMESTAMP,
    event_count     NUMBER DEFAULT 1,
    region_list     VARCHAR2(500),
    is_flagged      NUMBER(1) DEFAULT 0,
    notes           CLOB,
    CONSTRAINT tracked_users_username_uq UNIQUE (username)
);

CREATE INDEX idx_tracked_users_last_seen ON waze.tracked_users (last_seen);
CREATE INDEX idx_tracked_users_flagged ON waze.tracked_users (is_flagged);

-- =============================================================================
-- DAILY_STATS — Aggregated daily statistics
-- =============================================================================
CREATE TABLE waze.daily_stats (
    stat_id         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    stat_date       DATE NOT NULL,
    region          VARCHAR2(50),
    total_events    NUMBER DEFAULT 0,
    unique_users    NUMBER DEFAULT 0,
    police_count    NUMBER DEFAULT 0,
    jam_count       NUMBER DEFAULT 0,
    accident_count  NUMBER DEFAULT 0,
    hazard_count    NUMBER DEFAULT 0,
    closure_count   NUMBER DEFAULT 0,
    CONSTRAINT daily_stats_date_region_uq UNIQUE (stat_date, region)
);

CREATE INDEX idx_daily_stats_date ON waze.daily_stats (stat_date);

-- =============================================================================
-- USER_BEHAVIORAL_VECTORS — 44-dimensional behavioral fingerprint per user
-- =============================================================================
CREATE TABLE waze.user_behavioral_vectors (
    vector_id           NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username            VARCHAR2(200) NOT NULL,
    region              VARCHAR2(50),
    event_count         NUMBER DEFAULT 0,
    first_seen          TIMESTAMP WITH TIME ZONE,
    last_seen           TIMESTAMP WITH TIME ZONE,
    centroid_lat        NUMBER(10,6),
    centroid_lon        NUMBER(10,6),
    geo_spread_km       NUMBER(8,2),
    hour_histogram      CLOB,
    dow_histogram       CLOB,
    type_distribution   CLOB,
    cadence_stats       CLOB,
    behavior_vector     VECTOR(44, FLOAT32),
    vector_updated_at   TIMESTAMP DEFAULT SYSTIMESTAMP,
    dossier             CLOB,
    dossier_updated_at  TIMESTAMP,
    cluster_id          NUMBER,
    anomaly_score       NUMBER(8,6),
    CONSTRAINT ubv_username_uq UNIQUE (username)
);

-- HNSW vector index for similarity search
CREATE VECTOR INDEX idx_behavior_vector_hnsw
    ON waze.user_behavioral_vectors (behavior_vector)
    ORGANIZATION NEIGHBOR PARTITIONS
    DISTANCE COSINE
    WITH TARGET ACCURACY 95;

CREATE INDEX idx_ubv_cluster ON waze.user_behavioral_vectors (cluster_id);
CREATE INDEX idx_ubv_anomaly ON waze.user_behavioral_vectors (anomaly_score);

-- =============================================================================
-- USER_CO_OCCURRENCES — Pairs of users seen near each other
-- =============================================================================
CREATE TABLE waze.user_co_occurrences (
    co_id           NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_a          VARCHAR2(200) NOT NULL,
    user_b          VARCHAR2(200) NOT NULL,
    co_count        NUMBER DEFAULT 1,
    first_co        TIMESTAMP DEFAULT SYSTIMESTAMP,
    last_co         TIMESTAMP DEFAULT SYSTIMESTAMP,
    avg_distance_m  NUMBER(10,2),
    avg_time_gap_s  NUMBER(10,2),
    regions         VARCHAR2(500),
    CONSTRAINT co_occ_pair_uq UNIQUE (user_a, user_b),
    CONSTRAINT co_occ_canonical_order CHECK (user_a < user_b)
);

CREATE INDEX idx_co_occ_a ON waze.user_co_occurrences (user_a);
CREATE INDEX idx_co_occ_b ON waze.user_co_occurrences (user_b);
CREATE INDEX idx_co_occ_count ON waze.user_co_occurrences (co_count);

-- =============================================================================
-- USER_ROUTINES — Detected routine patterns for users
-- =============================================================================
CREATE TABLE waze.user_routines (
    routine_id      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username        VARCHAR2(200) NOT NULL,
    routine_type    VARCHAR2(50) NOT NULL,
    latitude        NUMBER(10,6),
    longitude       NUMBER(10,6),
    confidence      NUMBER(5,4),
    typical_hours   CLOB,
    typical_days    CLOB,
    evidence_count  NUMBER DEFAULT 0,
    first_observed  TIMESTAMP DEFAULT SYSTIMESTAMP,
    last_observed   TIMESTAMP DEFAULT SYSTIMESTAMP,
    CONSTRAINT routines_user_type_uq UNIQUE (username, routine_type)
);

CREATE INDEX idx_routines_username ON waze.user_routines (username);
CREATE INDEX idx_routines_type ON waze.user_routines (routine_type);
CREATE INDEX idx_routines_location ON waze.user_routines (latitude, longitude);

-- =============================================================================
-- IDENTITY_CORRELATIONS — Links between potentially related users
-- =============================================================================
CREATE TABLE waze.identity_correlations (
    correlation_id      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_a              VARCHAR2(200) NOT NULL,
    user_b              VARCHAR2(200) NOT NULL,
    correlation_type    VARCHAR2(50) NOT NULL,
    vector_similarity   NUMBER(5,4),
    graph_score         NUMBER(5,4),
    combined_score      NUMBER(5,4) NOT NULL,
    explanation         CLOB,
    computed_at         TIMESTAMP DEFAULT SYSTIMESTAMP,
    CONSTRAINT id_corr_pair_type_uq UNIQUE (user_a, user_b, correlation_type)
);

CREATE INDEX idx_id_corr_a ON waze.identity_correlations (user_a);
CREATE INDEX idx_id_corr_b ON waze.identity_correlations (user_b);
CREATE INDEX idx_id_corr_score ON waze.identity_correlations (combined_score);

-- =============================================================================
-- SQL Property Graph — Social/co-occurrence graph
-- =============================================================================
CREATE OR REPLACE PROPERTY GRAPH waze.waze_social_graph
    VERTEX TABLES (
        waze.tracked_users
            KEY (user_id)
            LABEL person
            PROPERTIES (username, first_seen, last_seen, event_count, is_flagged)
    )
    EDGE TABLES (
        waze.user_co_occurrences
            KEY (co_id)
            SOURCE KEY (user_a) REFERENCES tracked_users (username)
            DESTINATION KEY (user_b) REFERENCES tracked_users (username)
            LABEL co_located
            PROPERTIES (co_count, first_co, last_co, avg_distance_m, avg_time_gap_s)
    );

-- =============================================================================
-- Summary
-- =============================================================================
-- Schema created:
--   waze.events              (partitioned by region, 6 partitions)
--   waze.collection_runs
--   waze.tracked_users       (unique username)
--   waze.daily_stats         (unique stat_date + region)
--   waze.user_behavioral_vectors (VECTOR(44, FLOAT32) + HNSW index)
--   waze.user_co_occurrences (canonical pair ordering)
--   waze.user_routines
--   waze.identity_correlations
--   waze.waze_social_graph   (SQL Property Graph)
-- =============================================================================
