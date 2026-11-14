-- ============================================================================
-- AEGIS-BIO SUPABASE SQL SCHEMA & COMPLETE SEED DATA (Team Sigmoid - NASA Space Apps)
-- Instructions:
--   1. Open your Supabase project -> click "SQL Editor" on the left sidebar.
--   2. Click "+ New query", paste this entire script, and click "Run".
--   3. It will create all tables AND seed all 4 astronauts, 192 hourly telemetry logs
--      (48h per astronaut including ASTRO-01 Solar Particle Event surge), check-ins,
--      CRITICAL triage alert, Dead-Man's Switch escalation, chat messages, and 7-day forecast!
-- ============================================================================

-- 1. ASTRONAUTS (Crew Profiles)
CREATE TABLE IF NOT EXISTS public.astronauts (
    id TEXT PRIMARY KEY,                               -- 'ASTRO-01', 'ASTRO-02', etc.
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    mission_day INT NOT NULL DEFAULT 112,
    baseline_vitals JSONB NOT NULL DEFAULT '{}'::jsonb,
    current_status TEXT NOT NULL DEFAULT 'NOMINAL'
        CHECK (current_status IN ('NOMINAL', 'WARNING', 'CRITICAL')),
    emergency_contact_id TEXT,
    last_checkin TIMESTAMPTZ DEFAULT NOW()
);

-- 2. TELEMETRY LOGS (High-frequency hourly crew telemetry)
CREATE TABLE IF NOT EXISTS public.telemetry_logs (
    id TEXT PRIMARY KEY,
    astronaut_id TEXT NOT NULL REFERENCES public.astronauts(id) ON DELETE CASCADE,
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
    activity_state TEXT NOT NULL DEFAULT 'DUTY',
    status TEXT NOT NULL DEFAULT 'NOMINAL'
        CHECK (status IN ('NOMINAL', 'WARNING', 'CRITICAL')),
    primary_hazard TEXT NOT NULL DEFAULT 'NONE'
);

CREATE INDEX IF NOT EXISTS idx_telemetry_astro_ts
    ON public.telemetry_logs (astronaut_id, timestamp DESC);

-- 3. DAILY CHECKINS ({astroId}_day_{missionDay})
CREATE TABLE IF NOT EXISTS public.daily_checkins (
    id TEXT PRIMARY KEY,                               -- 'ASTRO-01_day_112'
    astronaut_id TEXT NOT NULL REFERENCES public.astronauts(id) ON DELETE CASCADE,
    mission_day INT NOT NULL,
    sleep_hours NUMERIC(4,2) NOT NULL,
    sleep_quality_score INT NOT NULL CHECK (sleep_quality_score BETWEEN 1 AND 5),
    mood_score INT NOT NULL CHECK (mood_score BETWEEN 1 AND 5),
    reported_symptoms JSONB NOT NULL DEFAULT '[]'::jsonb,
    notes TEXT DEFAULT '',
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. TRIAGE ALERTS (Real-time clinical events triggering frontend alerts)
CREATE TABLE IF NOT EXISTS public.triage_alerts (
    alert_id TEXT PRIMARY KEY,                         -- 'ALT-SPE-112-01'
    astronaut_id TEXT NOT NULL REFERENCES public.astronauts(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    severity TEXT NOT NULL
        CHECK (severity IN ('WARNING', 'CRITICAL')),
    hazard_type TEXT NOT NULL,                         -- e.g., 'SPACE_RADIATION_SPE'
    hazard_title TEXT NOT NULL,
    triggering_vitals JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'ACKNOWLEDGED', 'RESOLVED'))
);

-- 5. CHAT SESSIONS & MESSAGES (AI Flight Surgeon interaction log)
CREATE TABLE IF NOT EXISTS public.chat_sessions (
    session_id TEXT PRIMARY KEY,                       -- 'ASTRO-01_session_112'
    astronaut_id TEXT NOT NULL REFERENCES public.astronauts(id) ON DELETE CASCADE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_preview TEXT
);

CREATE TABLE IF NOT EXISTS public.chat_messages (
    message_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES public.chat_sessions(session_id) ON DELETE CASCADE,
    sender TEXT NOT NULL
        CHECK (sender IN ('astronaut', 'astrodoc_agent')),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    text TEXT NOT NULL,
    countermeasures JSONB NOT NULL DEFAULT '[]'::jsonb,
    nasa_references JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_ts
    ON public.chat_messages (session_id, timestamp ASC);

-- 6. EMERGENCY ESCALATIONS (Intra-Crew Dead-Man's Switch)
CREATE TABLE IF NOT EXISTS public.emergency_escalations (
    id TEXT PRIMARY KEY,                               -- 'ASTRO-01_escalation'
    astronaut_id TEXT NOT NULL REFERENCES public.astronauts(id) ON DELETE CASCADE,
    recipient_crew_id TEXT NOT NULL,
    alert_level TEXT NOT NULL DEFAULT 'CODE_RED_UNRESPONSIVE',
    countdown_seconds_remaining INT NOT NULL DEFAULT 180,
    escalation_state TEXT NOT NULL DEFAULT 'PENDING_ACK'
        CHECK (escalation_state IN ('PENDING_ACK', 'ACKNOWLEDGED', 'TRIGGERED')),
    reason TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 7. HEALTH PREDICTIONS (7-Day Vital Degradation & Cognitive Strain Projections)
CREATE TABLE IF NOT EXISTS public.health_predictions (
    id TEXT PRIMARY KEY,                               -- 'ASTRO-01_trajectory'
    astronaut_id TEXT NOT NULL REFERENCES public.astronauts(id) ON DELETE CASCADE,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    prediction_window_days INT NOT NULL DEFAULT 7,
    projected_dates JSONB NOT NULL DEFAULT '[]'::jsonb,
    projected_risk_scores JSONB NOT NULL DEFAULT '[]'::jsonb,
    dominant_risk TEXT NOT NULL,
    clinical_warning TEXT NOT NULL
);

-- ============================================================================
-- HACKATHON PROTOTYPING PERMISSIONS (Disable RLS for open read/write access)
-- ============================================================================
ALTER TABLE public.astronauts DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.telemetry_logs DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.daily_checkins DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.triage_alerts DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_sessions DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_messages DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.emergency_escalations DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.health_predictions DISABLE ROW LEVEL SECURITY;

-- ============================================================================
-- SEED 1: 4 ASTRONAUT CREW PROFILES
-- ============================================================================
INSERT INTO public.astronauts (id, name, role, mission_day, baseline_vitals, current_status, emergency_contact_id, last_checkin)
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

-- ============================================================================
-- SEED 2: 48 HOURS OF HOURLY TELEMETRY PER ASTRONAUT (192 ROWS TOTAL)
-- Includes Solar Particle Event (SPE) radiation surge for ASTRO-01
-- ============================================================================
DO $$
DECLARE
    astro RECORD;
    step INT;
    ts TIMESTAMPTZ;
    hr_of_day INT;
    m_day INT;
    act TEXT;
    hr INT;
    hrv INT;
    spo2 NUMERIC(5,2);
    temp NUMERIC(4,2);
    rad_rate NUMERIC(8,2);
    cum_rad NUMERIC(8,3);
    co2 NUMERIC(5,2);
    st TEXT;
    haz TEXT;
    surge NUMERIC;
BEGIN
    FOR astro IN SELECT * FROM public.astronauts LOOP
        cum_rad := CASE WHEN astro.id = 'ASTRO-01' THEN 84.200 ELSE 76.400 END;

        FOR step IN 0..47 LOOP
            ts := TIMESTAMPTZ '2028-09-18 19:00:00Z' + (step || ' hours')::INTERVAL;
            hr_of_day := EXTRACT(HOUR FROM ts)::INT;
            m_day := CASE WHEN step < 24 THEN 111 ELSE 112 END;

            IF hr_of_day >= 23 OR hr_of_day < 7 THEN
                act := 'SLEEP';
            ELSIF hr_of_day IN (15, 16) THEN
                act := 'EXERCISE';
            ELSIF astro.id = 'ASTRO-01' AND step BETWEEN 34 AND 40 THEN
                act := 'EVA';
            ELSE
                act := 'DUTY';
            END IF;

            hr := (astro.baseline_vitals->>'heart_rate_bpm')::INT + (4 * COS(2 * PI() * (hr_of_day - 16) / 24.0))::INT;
            hrv := (astro.baseline_vitals->>'hrv_rmssd_ms')::INT;
            spo2 := (astro.baseline_vitals->>'spo2_percent')::NUMERIC;
            temp := (astro.baseline_vitals->>'core_temp_c')::NUMERIC + 0.30;
            rad_rate := 72.5;
            co2 := 2.65;
            st := 'NOMINAL';
            haz := 'NONE';

            IF act = 'SLEEP' THEN
                hr := hr - 7;
                hrv := hrv + 9;
                spo2 := spo2 - 0.3;
            ELSIF act = 'EXERCISE' THEN
                hr := hr + 40;
                hrv := (hrv * 0.5)::INT;
                temp := temp + 0.55;
            END IF;

            -- ASTRO-01 Solar Particle Event (SPE) storm surge on final 14 hours
            IF astro.id = 'ASTRO-01' AND step >= 34 THEN
                surge := (step - 33) / 14.0;
                rad_rate := ROUND((75.0 + 415.0 * surge)::NUMERIC, 1);
                hr := hr + (28 * surge)::INT + CASE WHEN step >= 42 THEN 12 ELSE 0 END;
                hrv := GREATEST(16, hrv - (26 * surge)::INT);
                spo2 := ROUND((spo2 - 3.2 * surge)::NUMERIC, 1);
                temp := ROUND((temp + 0.85 * surge)::NUMERIC, 2);
                st := CASE WHEN step >= 38 THEN 'CRITICAL' ELSE 'WARNING' END;
                haz := 'SPACE_RADIATION_SPE';
            ELSIF astro.id = 'ASTRO-03' AND step >= 40 THEN
                co2 := 4.35;
                hr := hr + 11;
                hrv := hrv - 10;
                st := 'WARNING';
                haz := 'HOSTILE_CLOSED_ENVIRONMENT_CO2';
            END IF;

            cum_rad := ROUND((cum_rad + rad_rate / 1000.0)::NUMERIC, 3);

            INSERT INTO public.telemetry_logs (
                id, astronaut_id, timestamp, mission_day, hour,
                heart_rate_bpm, hrv_rmssd_ms, spo2_percent, core_temp_c,
                radiation_rate_usv_h, cumulative_radiation_msv, cabin_co2_mmhg,
                activity_state, status, primary_hazard
            ) VALUES (
                astro.id || '_day_' || LPAD(m_day::TEXT, 3, '0') || '_hr_' || LPAD(hr_of_day::TEXT, 2, '0') || '_s' || LPAD(step::TEXT, 2, '0'),
                astro.id, ts, m_day, hr_of_day,
                hr, hrv, spo2, temp,
                rad_rate, cum_rad, co2,
                act, st, haz
            )
            ON CONFLICT (id) DO NOTHING;
        END LOOP;
    END LOOP;
END $$;

-- ============================================================================
-- SEED 3: DAILY CHECK-INS, CRITICAL ALERT, ESCALATION, CHAT & 7-DAY FORECAST
-- ============================================================================
INSERT INTO public.daily_checkins (id, astronaut_id, mission_day, sleep_hours, sleep_quality_score, mood_score, reported_symptoms, notes, submitted_at)
VALUES
    ('ASTRO-01_day_112', 'ASTRO-01', 112, 4.2, 2, 2,
     '["Acute post-EVA fatigue", "Mild nausea and phosphene light flashes", "Orthostatic lightheadedness"]'::jsonb,
     'Experienced retinal light flashes during SPE storm alarm prior to storm shelter ingress.',
     '2028-09-20T12:00:00Z'),
    ('ASTRO-02_day_112', 'ASTRO-02', 112, 7.1, 4, 4,
     '[]'::jsonb,
     'Monitoring Cmdr. Vance dosimetry and preparing oral hydration/anti-emetic kit.',
     '2028-09-20T15:00:00Z'),
    ('ASTRO-03_day_112', 'ASTRO-03', 112, 5.8, 3, 3,
     '["Mild frontal headache"]'::jsonb,
     'Inspecting secondary LiOH CO2 scrubber cartridge in Hab Module B.',
     '2028-09-20T14:00:00Z'),
    ('ASTRO-04_day_112', 'ASTRO-04', 112, 7.4, 5, 5,
     '[]'::jsonb,
     'Nominal shift inside shielded habitat core.',
     '2028-09-20T16:00:00Z')
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.triage_alerts (alert_id, astronaut_id, timestamp, severity, hazard_type, hazard_title, triggering_vitals, is_acknowledged, status)
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

INSERT INTO public.emergency_escalations (id, astronaut_id, recipient_crew_id, alert_level, countdown_seconds_remaining, escalation_state, reason, updated_at)
VALUES (
    'ASTRO-01_escalation',
    'ASTRO-01',
    'ASTRO-02',
    'CODE_RED_UNRESPONSIVE',
    145,
    'PENDING_ACK',
    'CRITICAL Solar Particle Event dosimetry threshold (>450 uSv/h) + autonomic decompensation (HR 118 BPM, HRV 19 ms) unacknowledged by ASTRO-01. 18.5-minute Earth comm blackout active; autonomous intra-crew buddy intervention required.',
    '2028-09-20T18:00:00Z'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.chat_sessions (session_id, astronaut_id, updated_at, last_message_preview)
VALUES (
    'ASTRO-01_session_112',
    'ASTRO-01',
    '2028-09-20T17:36:00Z',
    'Commander Vance, your telemetry confirms an acute Solar Particle Event (SPE) exposure...'
)
ON CONFLICT (session_id) DO NOTHING;

INSERT INTO public.chat_messages (message_id, session_id, sender, timestamp, text, countermeasures, nasa_references)
VALUES
    ('MSG-001', 'ASTRO-01_session_112', 'astronaut', '2028-09-20T17:35:00Z',
     'Aegis, I just finished emergency ingress from the lunar rover during the solar storm alarm. My dosimeter spiked above 480 uSv/h, I saw retinal phosphene flashes, and I feel nauseated with a racing pulse.',
     '[]'::jsonb, '[]'::jsonb),
    ('MSG-002', 'ASTRO-01_session_112', 'astrodoc_agent', '2028-09-20T17:36:00Z',
     'Commander Vance, your telemetry confirms an acute Solar Particle Event (SPE) exposure (486.4 uSv/h, cumulative 87.92 mSv) accompanied by sympathetic autonomic strain (HR 118 BPM, RMSSD 19 ms). Execute the following autonomous NASA clinical countermeasures immediately:',
     '[{"action": "Retreat immediately to the Polyethylene Water-Wall Storm Shelter (Zone A Core) and remain shielded until proton flux drops below 50 uSv/h.", "urgency": "IMMEDIATE", "protocol_ref": "NASA-STD-3001 Vol. 1 Rev C §4.2"}, {"action": "Administer Ondansetron 4 mg ODT sublingually for prodromal radiation nausea and initiate 500 mL isotonic oral rehydration.", "urgency": "IMMEDIATE", "protocol_ref": "NASA ISS IMG Prodromal ARS Checklist §3.1"}, {"action": "Perform capillary CBC lymphocyte differential check at T+2h and T+6h.", "urgency": "WITHIN_2H", "protocol_ref": "NASA HRP ARS Biodosimetry Guideline §5.4"}]'::jsonb,
     '["NASA-STD-3001 Volume 1 Rev C: Space Flight Human-System Standard", "NASA HRP Evidence Report: Risk of Acute Radiation Syndromes Due to Solar Particle Events"]'::jsonb)
ON CONFLICT (message_id) DO NOTHING;

INSERT INTO public.health_predictions (id, astronaut_id, generated_at, prediction_window_days, projected_dates, projected_risk_scores, dominant_risk, clinical_warning)
VALUES (
    'ASTRO-01_trajectory',
    'ASTRO-01',
    '2028-09-20T18:00:00Z',
    7,
    '["2028-09-21", "2028-09-22", "2028-09-23", "2028-09-24", "2028-09-25", "2028-09-26", "2028-09-27"]'::jsonb,
    '[78.5, 84.2, 88.0, 76.4, 64.1, 52.8, 43.5]'::jsonb,
    'SPACE_RADIATION_SPE_AND_AUTONOMIC_FATIGUE',
    'Peak hematologic & autonomic strain projected at +48h to +72h post-SPE exposure (Risk Score 88.0/100). Restrict ASTRO-01 from EVA duties for 7 days, enforce >=8.0h circadian recovery sleep, and monitor absolute lymphocyte count daily.'
)
ON CONFLICT (id) DO NOTHING;
