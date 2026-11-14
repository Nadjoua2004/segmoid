"""
Standalone Supabase Database Seeder for Aegis-Bio (Team Sigmoid - NASA Space Apps).

Populates Supabase PostgreSQL with rich operational spaceflight medical data:
- 4 Astronaut crew profiles (`ASTRO-01` through `ASTRO-04`)
- 48 hours of hourly biometric & environmental telemetry per astronaut (192 records total),
  featuring an active Solar Particle Event (SPE) radiation surge for `ASTRO-01`
- Subjective daily crew check-ins (`daily_checkins`)
- 1 Active CRITICAL triage alert linked to `ASTRO-01` (`triage_alerts`)
- 1 Pending Dead-Man's Switch emergency escalation record (`emergency_escalations`)
- Sample clinical conversation history with structured NASA countermeasures (`chat_sessions` & `chat_messages`)
- 1 Seeded 7-day vital degradation & cognitive strain prediction curve (`health_predictions`)

Usage:
    cd aegis-bio/backend
    python seed_supabase.py
"""
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.supabase_config import SUPABASE_KEY, SUPABASE_URL
from app.services.supabase_service import (
    create_triage_alert,
    log_chat_message,
    save_daily_checkin,
    save_prediction_trajectory,
    set_escalation_status,
    upsert_rows,
)

RNG = random.Random(2028)
MISSION_DAY = 112
BASE_END_TIME = datetime(2028, 9, 20, 18, 0, 0, tzinfo=timezone.utc)


def get_crew_profiles() -> List[Dict[str, Any]]:
    return [
        {
            "id": "ASTRO-01",
            "name": "Cmdr. Elena Vance",
            "role": "Mission Commander & EVA Lead",
            "mission_day": MISSION_DAY,
            "baseline_vitals": {
                "heart_rate_bpm": 58,
                "hrv_rmssd_ms": 52,
                "spo2_percent": 98.4,
                "core_temp_c": 36.6,
                "systolic_bp_mmhg": 118,
                "diastolic_bp_mmhg": 74,
            },
            "current_status": "CRITICAL",
            "emergency_contact_id": "ASTRO-02",
            "last_checkin": (BASE_END_TIME - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        {
            "id": "ASTRO-02",
            "name": "Dr. Marcus Chen",
            "role": "Crew Medical Officer & Payload Specialist",
            "mission_day": MISSION_DAY,
            "baseline_vitals": {
                "heart_rate_bpm": 62,
                "hrv_rmssd_ms": 58,
                "spo2_percent": 98.7,
                "core_temp_c": 36.7,
                "systolic_bp_mmhg": 112,
                "diastolic_bp_mmhg": 72,
            },
            "current_status": "NOMINAL",
            "emergency_contact_id": "ASTRO-03",
            "last_checkin": (BASE_END_TIME - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        {
            "id": "ASTRO-03",
            "name": "Eng. Jan Kowalski",
            "role": "Chief Flight & ECLSS Systems Engineer",
            "mission_day": MISSION_DAY,
            "baseline_vitals": {
                "heart_rate_bpm": 55,
                "hrv_rmssd_ms": 64,
                "spo2_percent": 98.2,
                "core_temp_c": 36.5,
                "systolic_bp_mmhg": 120,
                "diastolic_bp_mmhg": 76,
            },
            "current_status": "WARNING",
            "emergency_contact_id": "ASTRO-02",
            "last_checkin": (BASE_END_TIME - timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        {
            "id": "ASTRO-04",
            "name": "Spec. Layla Al-Mansoor",
            "role": "Navigation & Astrobiology Specialist",
            "mission_day": MISSION_DAY,
            "baseline_vitals": {
                "heart_rate_bpm": 60,
                "hrv_rmssd_ms": 61,
                "spo2_percent": 98.8,
                "core_temp_c": 36.7,
                "systolic_bp_mmhg": 110,
                "diastolic_bp_mmhg": 70,
            },
            "current_status": "NOMINAL",
            "emergency_contact_id": "ASTRO-02",
            "last_checkin": (BASE_END_TIME - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    ]


def generate_48h_telemetry_for_astronaut(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    astro_id = profile["id"]
    base = profile["baseline_vitals"]
    start_time = BASE_END_TIME - timedelta(hours=47)
    cumulative_rad_msv = 84.20 if astro_id == "ASTRO-01" else 76.40

    records: List[Dict[str, Any]] = []

    for step in range(48):
        ts = start_time + timedelta(hours=step)
        hour = ts.hour
        day_num = MISSION_DAY - 1 if step < 24 else MISSION_DAY

        if hour >= 23 or hour < 7:
            activity = "SLEEP"
        elif hour in (15, 16):
            activity = "EXERCISE"
        elif astro_id == "ASTRO-01" and step in range(34, 41):
            activity = "EVA"
        else:
            activity = "DUTY"

        circadian_hr = 4.5 * math.cos(2 * math.pi * (hour - 16) / 24.0)
        circadian_temp = 0.28 * math.cos(2 * math.pi * (hour - 17) / 24.0)

        hr = base["heart_rate_bpm"] + circadian_hr + RNG.gauss(0, 2.2)
        hrv = base["hrv_rmssd_ms"] + RNG.gauss(0, 3.5)
        spo2 = base["spo2_percent"] + RNG.gauss(0, 0.3)
        temp = base["core_temp_c"] + 0.35 + circadian_temp + RNG.gauss(0, 0.06)
        rad_rate = 72.0 + RNG.gauss(0, 4.5)
        co2 = 2.65 + RNG.gauss(0, 0.15)

        if activity == "SLEEP":
            hr -= 7
            hrv += 9
            spo2 -= 0.4
        elif activity == "EXERCISE":
            hr += 42 + RNG.gauss(0, 5)
            hrv *= 0.48
            temp += 0.55
            spo2 -= 0.6

        status = "NOMINAL"
        primary_hazard = "NONE"

        if astro_id == "ASTRO-01" and step >= 34:
            surge_progress = (step - 33) / 14.0
            spe_spike = 420.0 * math.sin(math.pi * min(surge_progress * 0.85, 1.0))
            rad_rate += spe_spike + RNG.uniform(15.0, 45.0)
            hr += 28.0 * surge_progress + (12.0 if step >= 42 else 0.0)
            hrv -= 26.0 * surge_progress
            spo2 -= 3.2 * surge_progress
            temp += 0.85 * surge_progress

            status = "CRITICAL" if step >= 38 else "WARNING"
            primary_hazard = "SPACE_RADIATION_SPE"
        elif astro_id == "ASTRO-03" and step >= 40:
            co2 = 4.15 + RNG.uniform(0.1, 0.35)
            hr += 11
            hrv -= 10
            status = "WARNING"
            primary_hazard = "HOSTILE_CLOSED_ENVIRONMENT_CO2"

        cumulative_rad_msv += rad_rate / 1000.0

        records.append(
            {
                "id": f"{astro_id}_day_{day_num:03d}_hr_{hour:02d}_s{step:02d}",
                "astronaut_id": astro_id,
                "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "mission_day": int(day_num),
                "hour": int(hour),
                "heart_rate_bpm": int(round(max(42.0, min(185.0, hr)))),
                "hrv_rmssd_ms": int(round(max(12.0, min(110.0, hrv)))),
                "spo2_percent": round(max(88.0, min(100.0, spo2)), 1),
                "core_temp_c": round(max(35.8, min(39.8, temp)), 2),
                "radiation_rate_usv_h": round(max(30.0, rad_rate), 1),
                "cumulative_radiation_msv": round(cumulative_rad_msv, 3),
                "cabin_co2_mmhg": round(max(1.8, co2), 2),
                "activity_state": activity,
                "status": status,
                "primary_hazard": primary_hazard,
            }
        )

    return records


def main() -> None:
    print("=" * 72)
    print(f"  AEGIS-BIO SUPABASE SEEDER ({SUPABASE_URL})")
    print("=" * 72)

    crew = get_crew_profiles()
    print(f"[+] Seeding {len(crew)} Astronaut crew profiles into `astronauts`...")
    upsert_rows("astronauts", crew)

    for profile in crew:
        astro_id = profile["id"]
        rows = generate_48h_telemetry_for_astronaut(profile)
        print(f"[+] Seeding 48h hourly telemetry for {astro_id} into `telemetry_logs`...")
        upsert_rows("telemetry_logs", rows)

    print("[+] Seeding subjective crew check-ins into `daily_checkins`...")
    save_daily_checkin(
        {
            "astronaut_id": "ASTRO-01",
            "mission_day": MISSION_DAY,
            "sleep_hours": 4.2,
            "sleep_quality_score": 2,
            "mood_score": 2,
            "reported_symptoms": [
                "Acute post-EVA fatigue",
                "Mild nausea and phosphene light flashes",
                "Orthostatic lightheadedness",
            ],
            "notes": "Experienced retinal light flashes during SPE storm alarm prior to storm shelter ingress.",
            "submitted_at": (BASE_END_TIME - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )

    print("[+] Seeding CRITICAL triage alert (`ALT-SPE-112-01`) into `triage_alerts`...")
    create_triage_alert(
        {
            "alert_id": "ALT-SPE-112-01",
            "astronaut_id": "ASTRO-01",
            "timestamp": (BASE_END_TIME - timedelta(minutes=18)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "severity": "CRITICAL",
            "hazard_type": "SPACE_RADIATION_SPE",
            "hazard_title": "Acute Solar Particle Event (SPE) Radiation Surge & Autonomic Strain",
            "triggering_vitals": {
                "radiation_rate_usv_h": 486.4,
                "cumulative_radiation_msv": 87.92,
                "heart_rate_bpm": 118,
                "hrv_rmssd_ms": 19,
                "spo2_percent": 94.6,
                "core_temp_c": 37.9,
            },
            "is_acknowledged": False,
            "status": "ACTIVE",
        }
    )

    print("[+] Seeding Dead-Man's Switch escalation (`ASTRO-01_escalation`)...")
    set_escalation_status(
        astro_id="ASTRO-01",
        state="PENDING_ACK",
        recipient_crew_id="ASTRO-02",
        countdown_seconds_remaining=145,
        reason=(
            "CRITICAL Solar Particle Event dosimetry threshold (>450 uSv/h) + autonomic "
            "decompensation (HR 118 BPM, HRV 19 ms) unacknowledged by ASTRO-01."
        ),
    )

    print("[+] Seeding Flight Surgeon AI chat session (`ASTRO-01_session_112`)...")
    log_chat_message(
        "ASTRO-01_session_112",
        {
            "message_id": "MSG-001",
            "astronaut_id": "ASTRO-01",
            "sender": "astronaut",
            "timestamp": (BASE_END_TIME - timedelta(minutes=25)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "text": (
                "Aegis, I just finished emergency ingress from the lunar rover during the solar storm "
                "alarm. My dosimeter spiked above 480 uSv/h, I saw retinal phosphene flashes, and I feel "
                "nauseated with a racing pulse."
            ),
            "countermeasures": [],
            "nasa_references": [],
        },
    )
    log_chat_message(
        "ASTRO-01_session_112",
        {
            "message_id": "MSG-002",
            "astronaut_id": "ASTRO-01",
            "sender": "astrodoc_agent",
            "timestamp": (BASE_END_TIME - timedelta(minutes=24)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "text": (
                "Commander Vance, your telemetry confirms an acute Solar Particle Event (SPE) exposure "
                "(486.4 uSv/h, cumulative 87.92 mSv) accompanied by sympathetic autonomic strain "
                "(HR 118 BPM, RMSSD 19 ms). Execute the following autonomous NASA clinical countermeasures immediately:"
            ),
            "countermeasures": [
                {
                    "action": "Retreat immediately to the Polyethylene Water-Wall Storm Shelter (Zone A Core) and remain shielded until proton flux drops below 50 uSv/h.",
                    "urgency": "IMMEDIATE",
                    "protocol_ref": "NASA-STD-3001 Vol. 1 Rev C §4.2",
                },
                {
                    "action": "Administer Ondansetron 4 mg ODT sublingually for prodromal radiation nausea and initiate 500 mL isotonic oral rehydration.",
                    "urgency": "IMMEDIATE",
                    "protocol_ref": "NASA ISS IMG Prodromal ARS Checklist §3.1",
                },
            ],
            "nasa_references": [
                "NASA-STD-3001 Volume 1 Rev C: Space Flight Human-System Standard",
                "NASA HRP Evidence Report: Risk of Acute Radiation Syndromes Due to Solar Particle Events",
            ],
        },
    )

    print("[+] Seeding 7-day health prediction trajectory (`ASTRO-01_trajectory`)...")
    save_prediction_trajectory(
        "ASTRO-01",
        {
            "generated_at": BASE_END_TIME.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "prediction_window_days": 7,
            "projected_dates": [
                (BASE_END_TIME + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, 8)
            ],
            "projected_risk_scores": [78.5, 84.2, 88.0, 76.4, 64.1, 52.8, 43.5],
            "dominant_risk": "SPACE_RADIATION_SPE_AND_AUTONOMIC_FATIGUE",
            "clinical_warning": (
                "Peak hematologic & autonomic strain projected at +48h to +72h post-SPE exposure "
                "(Risk Score 88.0/100). Restrict ASTRO-01 from EVA duties for 7 days."
            ),
        },
    )

    print("=" * 72)
    print("[✓] Completed seeding all Aegis-Bio tables in Supabase!")
    print("=" * 72)


if __name__ == "__main__":
    main()
