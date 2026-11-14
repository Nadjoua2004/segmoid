"""
Aegis-Bio - Deep-Space Crew Telemetry Generator (v2)

Synthetic hourly telemetry for a 6-person crew over a 180-day mission,
with per-metric labels (NORMAL / MEDIUM / CRITICAL).

Label thresholds follow public health references:
  - NEWS2 (Royal College of Physicians, 2017): HR, RR, SpO2, SBP, temperature
  - ACC/AHA 2017 blood pressure categories
  - ADA glucose ranges
  - AASM/NSF adult sleep guidance (7-9 h)
  - NASA-STD-3001 (cabin CO2, radiation)

Spaceflight adjustments (approximate, from published studies):
  - core temperature drifts up ~0.5-1.0 C over months (Stahn 2017)
  - 24h systolic BP ~8 mmHg lower in flight (Norsk 2015)
  - average sleep ~6 h in flight (Barger 2014)
  - deep-space GCR ~1.8 mSv/day (Zeitlin 2013, MSL-RAD)
  - cabin CO2 typically 2-4 mmHg (ISS)

This is SYNTHETIC data for prototyping, not real crew data.
"""
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from labels import label_dataframe

SEED = 2028
rng = np.random.default_rng(SEED)

OUT_DIR = Path(__file__).resolve().parent
OUT_CSV = OUT_DIR / "deep_space_crew_telemetry_large.csv"

MISSION_DAYS = 180
START_TIME = datetime(2028, 6, 1)
HOURS = MISSION_DAYS * 24

CREW = [
    dict(id="ASTRO-01", name="Cmdr. Vance", sex="M", age=48, rhr=58, sbp=122, dbp=78, hrv=48, rr=14, temp=36.6, glu=92, eva=True, split="train"),
    dict(id="ASTRO-02", name="Dr. Chen", sex="F", age=41, rhr=62, sbp=112, dbp=72, hrv=58, rr=15, temp=36.7, glu=88, eva=False, split="train"),
    dict(id="ASTRO-03", name="Eng. Kowalski", sex="M", age=39, rhr=54, sbp=118, dbp=76, hrv=66, rr=13, temp=36.5, glu=90, eva=True, split="train"),
    dict(id="ASTRO-04", name="Spec. Al-Mansoor", sex="F", age=36, rhr=60, sbp=110, dbp=70, hrv=62, rr=15, temp=36.7, glu=86, eva=False, split="train"),
    dict(id="ASTRO-05", name="Pilot Okafor", sex="M", age=44, rhr=57, sbp=126, dbp=82, hrv=45, rr=14, temp=36.6, glu=95, eva=True, split="val"),
    dict(id="ASTRO-06", name="Dr. Lindqvist", sex="F", age=52, rhr=64, sbp=124, dbp=80, hrv=38, rr=16, temp=36.6, glu=97, eva=False, split="test"),
]

# Crew-wide environmental events (day ranges, 1-indexed, inclusive)
SPE_DAYS = (112, 114)          # solar particle event
CO2_FAULT_DAYS = (60, 63)      # scrubber degradation
LEAK_DAY, LEAK_HOURS = 150, (9, 13)   # cabin pressure leak -> lower ppO2
HIGH_WORKLOAD_DAYS = (95, 101) # short sleep period
EVA_DAYS = [30, 60, 90, 120, 150, 170]

# Individual events: astronaut -> list of (type, start_day, end_day)
INDIVIDUAL_EVENTS = {
    "ASTRO-02": [("fever", 41, 44)],
    "ASTRO-04": [("low_glucose", 130, 130)],
    "ASTRO-05": [("fever", 77, 79), ("arrhythmia", 140, 140)],
    "ASTRO-06": [("hypertension_trend", 85, 180), ("arrhythmia", 160, 160)],
    "ASTRO-01": [("dehydration", 121, 122)],
}


def ar1(n, phi, sigma):
    """Autocorrelated noise: consecutive hours are correlated like real signals."""
    out = np.empty(n)
    out[0] = rng.normal(0, sigma)
    scale = sigma * np.sqrt(1 - phi ** 2)
    for i in range(1, n):
        out[i] = phi * out[i - 1] + rng.normal(0, scale)
    return out


def circadian(hours, amplitude, peak_hour):
    return amplitude * np.cos(2 * np.pi * (hours - peak_hour) / 24.0)


def simulate_astronaut(c):
    n = HOURS
    t = np.arange(n)
    day = t // 24 + 1
    hour = t % 24
    frac = day / MISSION_DAYS

    # activity schedule
    activity = np.array(["DUTY"] * n, dtype=object)
    asleep = (hour >= 23) | (hour < 7)
    activity[asleep] = "SLEEP"
    ex = (hour == 15) | (hour == 16)
    activity[ex] = "EXERCISE"
    eva = np.zeros(n, bool)
    if c["eva"]:
        for d in EVA_DAYS:
            eva |= (day == d) & (hour >= 9) & (hour <= 15)
    activity[eva] = "EVA"

    # nightly sleep duration
    nightly = rng.normal(6.2, 0.7, MISSION_DAYS)
    nightly[:7] -= 0.8
    nightly[HIGH_WORKLOAD_DAYS[0] - 1:HIGH_WORKLOAD_DAYS[1]] -= rng.uniform(1.2, 2.0)
    nightly[SPE_DAYS[0] - 1:SPE_DAYS[1]] -= 1.5
    nightly = np.clip(nightly, 2.5, 9.0).round(1)
    sleep_hours = nightly[day - 1]
    sleep_debt = np.clip(6.5 - sleep_hours, 0, None)

    hr_max = 208 - 0.7 * c["age"]

    hr = c["rhr"] + circadian(hour, 4, 16) + ar1(n, 0.8, 2.5)
    hr[asleep] -= 7
    hr[ex] = rng.normal(0.72 * hr_max, 0.06 * hr_max, ex.sum())
    hr[eva] = rng.normal(0.62 * hr_max, 0.05 * hr_max, eva.sum())
    hr += 3 * sleep_debt

    adapt = np.minimum(frac * 6, 1)
    sbp = c["sbp"] - 8 * adapt + circadian(hour, 5, 15) + ar1(n, 0.85, 4)
    dbp = c["dbp"] - 4 * adapt + circadian(hour, 3, 15) + ar1(n, 0.85, 3)
    sbp[asleep] -= 10
    dbp[asleep] -= 6
    sbp[ex] += rng.normal(25, 6, ex.sum())

    rr = c["rr"] + ar1(n, 0.7, 1.0)
    rr[asleep] -= 1.5
    rr[ex] = rng.normal(26, 3, ex.sum())
    rr[eva] = rng.normal(20, 2, eva.sum())

    spo2 = 97.8 + ar1(n, 0.6, 0.5)
    spo2[asleep] -= 0.6
    spo2[ex] -= 0.8

    temp = c["temp"] + 0.8 * (1 - np.exp(-day / 60)) + circadian(hour, 0.35, 17) + ar1(n, 0.9, 0.08)
    temp[ex] += rng.normal(0.6, 0.15, ex.sum())
    temp[eva] += rng.normal(0.4, 0.15, eva.sum())

    hrv = c["hrv"] * (1 - 0.08 * frac) + ar1(n, 0.8, 5)
    hrv[asleep] += 10
    hrv[ex] *= 0.35
    hrv -= 2.5 * sleep_debt

    glu = c["glu"] + ar1(n, 0.85, 5)
    for meal in (8, 13, 19):
        glu += 35 * np.exp(-((hour - meal - 1) ** 2) / 1.5)
    glu[ex] -= 12

    # environment: radiation (uSv/h) and cabin CO2 (mmHg)
    rad = rng.normal(75, 6, n)
    rad[eva] = rng.normal(140, 15, eva.sum())
    spe = (day >= SPE_DAYS[0]) & (day <= SPE_DAYS[1])
    centre = (SPE_DAYS[0] - 1) * 24 + 20
    rad[spe] += 400 * np.exp(-((t[spe] - centre) / 18.0) ** 2) + rng.normal(0, 25, spe.sum())
    rad = np.clip(rad, 30, None)

    co2 = 2.6 + ar1(n, 0.95, 0.25)
    fault = (day >= CO2_FAULT_DAYS[0]) & (day <= CO2_FAULT_DAYS[1])
    ramp = np.clip((t - (CO2_FAULT_DAYS[0] - 1) * 24) / 30.0, 0, 1)
    co2[fault] += 4.5 * ramp[fault]
    co2 = np.clip(co2, 1.5, None)
    excess = np.clip(co2 - 3.0, 0, None)
    rr += 1.2 * excess
    hr += 1.5 * excess

    leak = (day == LEAK_DAY) & (hour >= LEAK_HOURS[0]) & (hour <= LEAK_HOURS[1])
    spo2[leak] -= rng.uniform(5, 9, leak.sum())
    rr[leak] += 6
    hr[leak] += 15

    hr[spe] += 6
    hrv[spe] -= 8

    sig = dict(hr=hr, sbp=sbp, dbp=dbp, rr=rr, spo2=spo2, temp=temp, hrv=hrv, glu=glu)
    apply_individual_events(c, sig, t, day, hour)

    return pd.DataFrame({
        "timestamp": [START_TIME + timedelta(hours=int(i)) for i in t],
        "mission_day": day,
        "hour": hour,
        "astronaut_id": c["id"],
        "astronaut_name": c["name"],
        "sex": c["sex"],
        "age": c["age"],
        "split": c["split"],
        "activity_state": activity,
        "heart_rate_bpm": sig["hr"].round(0),
        "hr_max_pred_bpm": round(hr_max, 1),
        "systolic_bp_mmhg": sig["sbp"].round(0),
        "diastolic_bp_mmhg": sig["dbp"].round(0),
        "respiratory_rate_bpm": sig["rr"].round(0),
        "spo2_percent": np.clip(sig["spo2"], 70, 100).round(1),
        "core_temp_c": sig["temp"].round(2),
        "hrv_rmssd_ms": np.clip(sig["hrv"], 5, None).round(0),
        "hrv_baseline_ms": c["hrv"],
        "blood_glucose_mgdl": sig["glu"].round(0),
        "sleep_hours_last_night": sleep_hours,
        "radiation_rate_usv_h": rad.round(1),
        "cumulative_radiation_msv": (np.cumsum(rad) / 1000).round(2),
        "cabin_co2_mmhg": co2.round(2),
    })


def apply_individual_events(c, s, t, day, hour):
    """Individual clinical scenarios so each label class has varied causes."""
    for kind, d0, d1 in INDIVIDUAL_EVENTS.get(c["id"], []):
        m = (day >= d0) & (day <= d1)
        if not m.any():
            continue
        span = (d1 - d0 + 1) * 24
        shape = np.sin(np.pi * np.clip((t[m] - (d0 - 1) * 24) / span, 0, 1))
        if kind == "fever":
            peak = 1.6 + rng.uniform(0, 1.0)
            s["temp"][m] += peak * shape
            s["hr"][m] += 10 * peak * shape
            s["rr"][m] += 4 * shape
            s["spo2"][m] -= 1.5 * shape
            s["hrv"][m] -= 15 * shape
        elif kind == "arrhythmia":
            w = m & (hour >= 2) & (hour <= 6)
            s["hr"][w] = rng.normal(138, 12, w.sum())
            s["sbp"][w] -= 12
        elif kind == "hypertension_trend":
            s["sbp"][m] += np.linspace(0, 22, m.sum())
            s["dbp"][m] += np.linspace(0, 12, m.sum())
        elif kind == "low_glucose":
            w = m & (hour >= 16) & (hour <= 19)
            s["glu"][w] = rng.normal(58, 8, w.sum())
            s["hr"][w] += 10
        elif kind == "dehydration":
            s["hr"][m] += 12 * shape
            s["sbp"][m] -= 14 * shape
            s["temp"][m] += 0.3 * shape


def add_sensor_noise(df):
    """Real wearables drop out and produce artefacts - include them."""
    df["data_quality"] = "GOOD"
    vital_cols = ["heart_rate_bpm", "spo2_percent", "hrv_rmssd_ms",
                  "respiratory_rate_bpm", "core_temp_c", "blood_glucose_mgdl"]
    n = len(df)
    for col in vital_cols:
        drop = rng.random(n) < 0.005
        df.loc[drop, col] = np.nan
        df.loc[drop, "data_quality"] = "MISSING"
    ex = df["activity_state"].isin(["EXERCISE", "EVA"]).to_numpy()
    artefact = ex & (rng.random(n) < 0.03)
    df.loc[artefact, "spo2_percent"] -= rng.uniform(2, 5, artefact.sum())
    df.loc[artefact, "data_quality"] = "MOTION_ARTEFACT"
    return df


def main():
    print("Generating deep-space crew telemetry ...")
    frames = [simulate_astronaut(c) for c in CREW]
    df = pd.concat(frames, ignore_index=True)
    df = add_sensor_noise(df)
    df = label_dataframe(df)
    df.to_csv(OUT_CSV, index=False)
    print(f"Saved {len(df):,} rows x {df.shape[1]} cols -> {OUT_CSV.name}")
    print("\nOverall status distribution:")
    print(df["overall_status"].value_counts())
    print("\nPer-split rows:")
    print(df["split"].value_counts())


if __name__ == "__main__":
    main()
