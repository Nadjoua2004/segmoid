"""
30-Day Artemis Mission Telemetry Generator
Generates or loads realistic physiological data modeling spaceflight deconditioning,
circadian shifts, and radiation fluctuations during lunar surface operations.
"""
from datetime import datetime, timedelta
from pathlib import Path
import math
import random
import pandas as pd
from sqlalchemy.orm import Session
from app.models import TelemetryLog

def load_or_generate_artemis_telemetry(astronaut_id: str = "ASTRO-7702-HELENA", days: int = 30) -> list[dict]:
    """
    Checks for existing CSV telemetry data in ../data/astronaut_telemetry.csv
    or ../../data/astronaut_telemetry.csv. If present, ingests it; otherwise
    generates 30 days of high-fidelity synthetic Artemis biometrics.
    """
    potential_paths = [
        Path(__file__).resolve().parent.parent.parent.parent / "data" / "astronaut_telemetry.csv",
        Path(__file__).resolve().parent.parent.parent / "data" / "astronaut_telemetry.csv",
        Path("data/astronaut_telemetry.csv"),
    ]

    for p in potential_paths:
        if p.exists():
            try:
                df = pd.read_csv(p)
                records = []
                base_date = datetime.utcnow() - timedelta(days=len(df))
                for _, row in df.iterrows():
                    day_val = int(row.get("day", 1))
                    records.append({
                        "astronaut_id": astronaut_id,
                        "mission_day": day_val,
                        "timestamp": base_date + timedelta(days=day_val),
                        "heart_rate": float(row.get("heart_rate", 72.0)),
                        "bp_sys": float(row.get("bp_sys", 120.0)),
                        "bp_dia": float(row.get("bp_dia", 80.0)),
                        "spo2": float(row.get("spo2", 98.0)),
                        "sleep_hours": float(row.get("sleep_hours", 7.0)),
                        "radiation_msv": float(row.get("radiation_msv", 0.45)),
                        "blood_glucose": 95.0,
                        "mood_score": int(row.get("mood_score", 4)),
                        "core_temp_c": 36.8,
                        "hrv_rmssd": 45.0,
                        "subjective_notes": str(row.get("mission_notes", "Routine operations"))
                    })
                if records:
                    return records
            except Exception as e:
                print(f"[Aegis-Bio Seeder] Note: CSV import attempt ({p}): {e}. Falling back to generator.")

    # Generator Fallback
    records = []
    base_date = datetime.utcnow() - timedelta(days=days)
    random.seed(42)
    
    for day in range(1, days + 1):
        record_date = base_date + timedelta(days=day)
        
        base_hr = 68.0 + (day * 0.45) + math.sin(day * 0.8) * 3.5 + random.uniform(-2.0, 2.0)
        if day in [27, 28]:
            base_hr += 14.0
        
        bp_sys = 118.0 + (day * 0.35) + math.cos(day * 0.5) * 4.0 + random.uniform(-2.5, 2.5)
        bp_dia = 76.0 + (day * 0.22) + random.uniform(-1.5, 2.0)
        
        spo2 = 98.2 - (0.04 * day) + random.uniform(-0.4, 0.4)
        if day in [28, 29]:
            spo2 -= 1.8
        spo2 = max(92.0, min(99.5, round(spo2, 1)))
        
        sleep_hours = 7.6 - (day * 0.08) + math.sin(day * 0.7) * 0.8 + random.uniform(-0.3, 0.3)
        if day in [26, 27, 28]:
            sleep_hours -= 1.2
        sleep_hours = max(3.8, min(8.5, round(sleep_hours, 1)))
        
        if day < 25:
            radiation_msv = 0.42 + (math.sin(day * 0.3) * 0.15) + random.uniform(-0.05, 0.08)
        elif day < 29:
            radiation_msv = 1.65 + (day - 25) * 0.85 + random.uniform(-0.1, 0.2)
        else:
            radiation_msv = 18.5 + random.uniform(1.2, 3.8)
            
        radiation_msv = max(0.2, round(radiation_msv, 3))
        blood_glucose = 92.0 + math.cos(day * 0.4) * 6.0 + random.uniform(-3.0, 4.0)
        
        if sleep_hours > 6.5 and day < 20:
            mood_score = 5 if random.random() > 0.4 else 4
        elif sleep_hours > 5.0 and day < 28:
            mood_score = 3 if random.random() > 0.3 else 4
        else:
            mood_score = 2
            
        hrv_rmssd = max(18.0, 55.0 - (day * 0.9) + random.uniform(-3.0, 3.0))
        core_temp_c = round(36.8 + (day * 0.01) + random.uniform(-0.15, 0.15), 2)
        
        notes = "Nominal Artemis operations"
        if day == 1:
            notes = "Mission inception: Lunar orbit insertion nominal. Crew cleared for surface descent."
        elif day == 19 or day == 20:
            notes = "Solar Particle Event (SPE) Alert: elevated dosimeter flux."
            
        records.append({
            "astronaut_id": astronaut_id,
            "mission_day": day,
            "timestamp": record_date,
            "heart_rate": round(base_hr, 1),
            "bp_sys": round(bp_sys, 1),
            "bp_dia": round(bp_dia, 1),
            "spo2": spo2,
            "sleep_hours": sleep_hours,
            "radiation_msv": radiation_msv,
            "blood_glucose": round(blood_glucose, 1),
            "mood_score": mood_score,
            "core_temp_c": core_temp_c,
            "hrv_rmssd": round(hrv_rmssd, 1),
            "subjective_notes": notes
        })
        
    return records

def seed_initial_telemetry(db: Session, force: bool = False) -> int:
    """
    Populates database with 30-day realistic Artemis mission telemetry
    if no records exist or force is requested.
    """
    existing_count = db.query(TelemetryLog).count()
    if existing_count > 0 and not force:
        return existing_count
        
    telemetry_data = load_or_generate_artemis_telemetry()
    for row in telemetry_data:
        log_entry = TelemetryLog(**row)
        db.add(log_entry)
        
    db.commit()
    return len(telemetry_data)
