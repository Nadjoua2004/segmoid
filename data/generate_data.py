import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Configuration
CREW_MEMBERS = [
    {"id": "ASTRO-01", "name": "Cmdr. Vance", "role": "Commander"},
    {"id": "ASTRO-02", "name": "Dr. Chen", "role": "Medical Officer"},
    {"id": "ASTRO-03", "name": "Eng. Kowalski", "role": "Flight Engineer"},
    {"id": "ASTRO-04", "name": "Spec. Al-Mansoor", "role": "Mission Specialist"}
]

MISSION_DAYS = 180
HOURS_PER_DAY = 24
START_TIME = datetime(2028, 6, 1, 0, 0, 0)

np.random.seed(42)
records = []

print("Generating high-frequency deep-space telemetry...")

for crew in CREW_MEMBERS:
    cumulative_rad = 0.0
    
    for day in range(MISSION_DAYS):
        # Space event triggers
        is_solar_storm = (112 <= day <= 114) # Day 112-114: Solar Storm Crisis
        is_eva_day = (day in [30, 60, 90, 120, 150]) and (crew["id"] in ["ASTRO-01", "ASTRO-03"])
        
        for hour in range(HOURS_PER_DAY):
            timestamp = START_TIME + timedelta(days=day, hours=hour)
            
            # Circadian cycle (0-7 sleep, 8-23 awake)
            is_sleep = 0 <= hour <= 7
            
            # Baseline Vitals with Circadian variance
            if is_sleep:
                base_hr = np.random.normal(56, 3)
                base_spo2 = np.random.normal(97.5, 0.4)
                activity = "SLEEP"
            else:
                base_hr = np.random.normal(74, 5)
                base_spo2 = np.random.normal(98.2, 0.4)
                activity = "NOMINAL_DUTY"
                
            # Exercise periods (ARED resistive workout at 15:00)
            if hour == 15 and not is_solar_storm:
                base_hr = np.random.normal(145, 8)
                activity = "ARED_EXERCISE"

            # EVA Spacewalk
            if is_eva_day and (10 <= hour <= 16):
                base_hr = np.random.normal(125, 7)
                activity = "EVA_OPERATIONS"

            # Microgravity Core Body Temp ("Space Fever" - rises 1°C over months)
            temp_drift = (day / MISSION_DAYS) * 0.8
            core_temp = round(36.6 + temp_drift + np.random.normal(0, 0.15), 2)
            
            # Stress & Autonomic Nervous System: HRV RMSSD (ms)
            # Lower HRV = Higher physical/mental strain
            base_hrv = 65 - (day * 0.1) + np.random.normal(0, 4)
            
            # Radiation (uSv/h): Background GCR vs Solar Particle Event
            if is_solar_storm:
                rad_rate_uSv = np.random.normal(850.0, 50.0) # Massive radiation storm
                base_hr += 20 # Stress / tachycardia
                base_hrv -= 25
                status = "CRITICAL"
                hazard_flag = "SPACE_RADIATION_SPE"
            elif is_eva_day and (10 <= hour <= 16):
                rad_rate_uSv = np.random.normal(45.0, 5.0) # Higher exposure outside hull
                status = "WARNING"
                hazard_flag = "ELEVATED_EVA_RADIATION"
            else:
                rad_rate_uSv = np.random.normal(18.5, 2.0) # Nominal background GCR in deep space
                status = "NOMINAL"
                hazard_flag = "NONE"

            # Accumulate radiation into mSv
            cumulative_rad += (rad_rate_uSv / 1000.0)

            # Cabin CO2 (Elevated CO2 triggers headaches and microgravity vision syndrome)
            cabin_co2_mmhg = round(np.random.normal(3.2, 0.4), 2) # Nominal ISS is ~2.5 - 4.0 mmHg

            records.append({
                "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "mission_day": day + 1,
                "hour": hour,
                "astronaut_id": crew["id"],
                "astronaut_name": crew["name"],
                "activity_state": activity,
                "heart_rate_bpm": int(np.clip(base_hr, 45, 185)),
                "hrv_rmssd_ms": max(10, int(base_hrv)),
                "spo2_percent": round(np.clip(base_spo2, 88.0, 100.0), 1),
                "core_temp_c": core_temp,
                "radiation_rate_usv_h": round(rad_rate_uSv, 2),
                "cumulative_radiation_msv": round(cumulative_rad, 2),
                "cabin_co2_mmhg": cabin_co2_mmhg,
                "status": status,
                "primary_hazard": hazard_flag
            })

df = pd.DataFrame(records)
df.to_csv("deep_space_crew_telemetry_large.csv", index=False)
print(f"Dataset generated: {len(df):,} rows! Saved to 'deep_space_crew_telemetry_large.csv'")