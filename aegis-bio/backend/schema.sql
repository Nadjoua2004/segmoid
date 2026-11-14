-- ============================================================================
-- AEGIS-BIO OPERATIONAL DATABASE SCHEMA (PostgreSQL / Firebase Data Connect / Supabase SQL)
-- Note:
--   * If using Google Cloud Firestore (NoSQL), you DO NOT need SQL!
--     Firestore creates all collections automatically when you run:
--     `python seed_firebase.py`
--   * If using Firebase Data Connect (Cloud SQL PostgreSQL) or Supabase SQL Editor,
--     paste and run this script to create all 7 operational tables and seed test data.
-- ============================================================================

-- 1. ASTRONAUTS (Crew Profiles)
CREATE TABLE IF NOT EXISTS astronauts (
    id VARCHAR(32) PRIMARY KEY,                        -- e.g., 'ASTRO-01'
    name VARCHAR(120) NOT NULL,
    role VARCHAR(120) NOT NULL,
    mission_day INT NOT NULL DEFAULT 112,
    baseline_vitals JSONB NOT NULL DEFAULT '{}'::jsonb,
    current_status VARCHAR(20) NOT NULL DEFAULT 'NOMINAL'
        CHECK (current_status IN ('NOMINAL', 'WARNING', 'CRITICAL')),
    emergency_contact_id VARCHAR(32),
    last_checkin TIMESTAMPTZ DEFAULT NOW()
);

-- 2. TELEMETRY LOGS (Equivalent to astronauts/{astroId}/telemetry_logs)
CREATE TABLE IF NOT EXISTS telemetry_logs (
    id VARCHAR(64) PRIMARY KEY,
    astronaut_id VARCHAR(32) NOT NULL REFERENCES astronauts(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    mission_day INT NOT NULL,
    hour INT NOT NULL CHECK (hour BETWEEN 0 AND 23),
    heart_rate_bpm INT NOT NULL,
    hrv_rmssd_ms INT NOT NULL,
    spo2_percent NUMERIC(5,2) NOT NULL,
    core_temp_c NUMERIC(4,2) NOT NULL,
    radiation_rate_usv_h NUMERIC(8,2) NOT NULL,
    cumulative_radiation_msv NUMERIC(8,3) NOT NULL,
    cabin_co2_mmhg NUMERIC(5,2) NOT NULL,
    activity_state VARCHAR(32) NOT NULL DEFAULT 'DUTY',
    status VARCHAR(20) NOT NULL DEFAULT 'NOMINAL'
        CHECK (status IN ('NOMINAL', 'WARNING', 'CRITICAL')),
    primary_hazard VARCHAR(64) NOT NULL DEFAULT 'NONE'
);

CREATE INDEX IF NOT EXISTS idx_telemetry_astro_ts
    ON telemetry_logs (astronaut_id, timestamp DESC);

-- 3. DAILY CHECKINS ({astroId}_day_{missionDay})
CREATE TABLE IF NOT EXISTS daily_checkins (
    id VARCHAR(64) PRIMARY KEY,                        -- e.g., 'ASTRO-01_day_112'
    astronaut_id VARCHAR(32) NOT NULL REFERENCES astronauts(id) ON DELETE CASCADE,
    mission_day INT NOT NULL,
    sleep_hours NUMERIC(4,2) NOT NULL,
    sleep_quality_score INT NOT NULL CHECK (sleep_quality_score BETWEEN 1 AND 5),
    mood_score INT NOT NULL CHECK (mood_score BETWEEN 1 AND 5),
    reported_symptoms JSONB NOT NULL DEFAULT '[]'::jsonb,
    notes TEXT DEFAULT '',
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. TRIAGE ALERTS (Real-time clinical events)
CREATE TABLE IF NOT EXISTS triage_alerts (
    alert_id VARCHAR(64) PRIMARY KEY,                  -- e.g., 'ALT-SPE-112-01'
    astronaut_id VARCHAR(32) NOT NULL REFERENCES astronauts(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    severity VARCHAR(20) NOT NULL
        CHECK (severity IN ('WARNING', 'CRITICAL')),
    hazard_type VARCHAR(64) NOT NULL,                  -- e.g., 'SPACE_RADIATION_SPE'
    hazard_title VARCHAR(255) NOT NULL,
    triggering_vitals JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'ACKNOWLEDGED', 'RESOLVED'))
);

-- 5. CHAT SESSIONS & MESSAGES (AI Flight Surgeon Log)
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id VARCHAR(64) PRIMARY KEY,                -- e.g., 'ASTRO-01_session_112'
    astronaut_id VARCHAR(32) NOT NULL REFERENCES astronauts(id) ON DELETE CASCADE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_preview VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    message_id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
    sender VARCHAR(32) NOT NULL
        CHECK (sender IN ('astronaut', 'astrodoc_agent')),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    text TEXT NOT NULL,
    countermeasures JSONB NOT NULL DEFAULT '[]'::jsonb,
    nasa_references JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_ts
    ON chat_messages (session_id, timestamp ASC);

-- 6. EMERGENCY ESCALATIONS (Intra-Crew Dead-Man's Switch)
CREATE TABLE IF NOT EXISTS emergency_escalations (
    id VARCHAR(64) PRIMARY KEY,                        -- e.g., 'ASTRO-01_escalation'
    astronaut_id VARCHAR(32) NOT NULL REFERENCES astronauts(id) ON DELETE CASCADE,
    recipient_crew_id VARCHAR(32) NOT NULL,
    alert_level VARCHAR(64) NOT NULL DEFAULT 'CODE_RED_UNRESPONSIVE',
    countdown_seconds_remaining INT NOT NULL DEFAULT 180,
    escalation_state VARCHAR(32) NOT NULL DEFAULT 'PENDING_ACK'
        CHECK (escalation_state IN ('PENDING_ACK', 'ACKNOWLEDGED', 'TRIGGERED')),
    reason TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 7. HEALTH PREDICTIONS (7-Day Vital Degradation & Cognitive Strain Projections)
CREATE TABLE IF NOT EXISTS health_predictions (
    id VARCHAR(64) PRIMARY KEY,                        -- e.g., 'ASTRO-01_trajectory'
    astronaut_id VARCHAR(32) NOT NULL REFERENCES astronauts(id) ON DELETE CASCADE,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    prediction_window_days INT NOT NULL DEFAULT 7,
    projected_dates JSONB NOT NULL DEFAULT '[]'::jsonb,
    projected_risk_scores JSONB NOT NULL DEFAULT '[]'::jsonb,
    dominant_risk VARCHAR(120) NOT NULL,
    clinical_warning TEXT NOT NULL
);

-- ============================================================================
-- INITIAL SEED DATA (4 Crew Profiles, Active Alert, Dead-Man's Switch, Trajectory)
-- ============================================================================
INSERT INTO astronauts (id, name, role, mission_day, baseline_vitals, current_status, emergency_contact_id, last_checkin)
VALUES
    ('ASTRO-01', 'Cmdr. Elena Vance', 'Mission Commander & EVA Lead', 112,
     '{"heart_rate_bpm": 58, "hrv_rmssd_ms": 52, "spo2_percent": 98.4, "core_temp_c": 36.6, "systolic_bp_mmhg": 118, "diastolic_bp_mmhg": 74}'::jsonb,
     'CRITICAL', 'ASTRO-02', '2028-09-20T12:00:00Z'),
    ('ASTRO-02', 'Dr. Marcus Chen', 'Crew Medical Officer & Payload Specialist', 112,
     '{"heart_rate_bpm": 62, "hrv_rmssd_ms": 58, "spo2_percent": 98.7, "core_temp_c": 36.7, "systolic_bp_mmhg": 112, "diastolic_bp_mmhg": 72}'::jsonb,
     'NOMINAL', 'ASTRO-03', '2028-09-20T15:00:00Z'),
    ('ASTRO-03', 'Eng. Jan Kowalski', 'Chief Flight & ECLSS Systems Engineer', 112,
     '{"heart_rate_bpm": 55, "hrv_rmssd_ms": 64, "spo2_percent": 98.2, "core_temp_c": 36.5, "systolic_bp_mmhg": 120, "diastolic_bp_mmhg": 76}'::jsonb,
     'WARNING', 'ASTRO-02', '2028-09-20T14:00:00Z'),
    ('ASTRO-04', 'Spec. Layla Al-Mansoor', 'Navigation & Astrobiology Specialist', 112,
     '{"heart_rate_bpm": 60, "hrv_rmssd_ms": 61, "spo2_percent": 98.8, "core_temp_c": 36.7, "systolic_bp_mmhg": 110, "diastolic_bp_mmhg": 70}'::jsonb,
     'NOMINAL', 'ASTRO-02', '2028-09-20T16:00:00Z')
ON CONFLICT (id) DO UPDATE SET
    current_status = EXCLUDED.current_status,
    mission_day = EXCLUDED.mission_day;

INSERT INTO triage_alerts (alert_id, astronaut_id, timestamp, severity, hazard_type, hazard_title, triggering_vitals, is_acknowledged, status)
VALUES (
    'ALT-SPE-112-01',
    'ASTRO-01',
    '2028-09-20T17:42:00Z',
    'CRITICAL',
    'SPACE_RADIATION_SPE',
    'Acute Solar Particle Event (SPE) Radiation Surge & Autonomic Strain',
    '{"radiation_rate_usv_h": 486.4, "cumulative_radiation_msv": 87.92, "heart_rate_bpm": 118, "hrv_rmssd_ms": 19, "spo2_percent": 94.6, "core_temp_c": 37.9}'::jsonb,
    FALSE,
    'ACTIVE'
)
ON CONFLICT (alert_id) DO NOTHING;

INSERT INTO emergency_escalations (id, astronaut_id, recipient_crew_id, alert_level, countdown_seconds_remaining, escalation_state, reason, updated_at)
VALUES (
    'ASTRO-01_escalation',
    'ASTRO-01',
    'ASTRO-02',
    'CODE_RED_UNRESPONSIVE',
    145,
    'PENDING_ACK',
    'CRITICAL Solar Particle Event dosimetry threshold (>450 uSv/h) + autonomic decompensation (HR 118 BPM, HRV 19 ms) unacknowledged by ASTRO-01.',
    '2028-09-20T18:00:00Z'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO health_predictions (id, astronaut_id, generated_at, prediction_window_days, projected_dates, projected_risk_scores, dominant_risk, clinical_warning)
VALUES (
    'ASTRO-01_trajectory',
    'ASTRO-01',
    '2028-09-20T18:00:00Z',
    7,
    '["2028-09-21", "2028-09-22", "2028-09-23", "2028-09-24", "2028-09-25", "2028-09-26", "2028-09-27"]'::jsonb,
    '[78.5, 84.2, 88.0, 76.4, 64.1, 52.8, 43.5]'::jsonb,
    'SPACE_RADIATION_SPE_AND_AUTONOMIC_FATIGUE',
    'Peak hematologic & autonomic strain projected at +48h to +72h post-SPE exposure (Risk Score 88.0/100). Restrict ASTRO-01 from EVA duties for 7 days.'
)
ON CONFLICT (id) DO NOTHING;
