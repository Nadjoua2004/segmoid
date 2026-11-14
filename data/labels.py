"""
Per-metric labels (NORMAL / MEDIUM / CRITICAL) from public health references.

Labels use only the measured value plus context (activity, personal baseline),
never the simulated scenario, so there is no label leakage.

References:
- NEWS2 (Royal College of Physicians, 2017) for HR, RR, SpO2, SBP, temperature.
  Sub-score 0 = NORMAL, 1-2 = MEDIUM, 3 = CRITICAL.
- ACC/AHA 2017 blood pressure categories.
- ADA glucose ranges.
- AASM/NSF sleep guidance.
- NASA-STD-3001 for cabin CO2 and radiation.
"""
import numpy as np
import pandas as pd

NAMES = np.array(["NORMAL", "MEDIUM", "CRITICAL"])


def to_label(score):
    s = np.asarray(score, dtype=float)
    out = np.full(s.shape, "UNKNOWN", dtype=object)
    ok = ~np.isnan(s)
    out[ok] = NAMES[s[ok].astype(int)]
    return out


def news2_points_hr(hr):
    p = np.select(
        [hr <= 40, hr <= 50, hr <= 90, hr <= 110, hr <= 130],
        [3, 1, 0, 1, 2], default=3).astype(float)
    p[np.isnan(hr)] = np.nan
    return p


def news2_points_rr(rr):
    p = np.select(
        [rr <= 8, rr <= 11, rr <= 20, rr <= 24],
        [3, 1, 0, 2], default=3).astype(float)
    p[np.isnan(rr)] = np.nan
    return p


def news2_points_spo2(spo2):
    p = np.select(
        [spo2 <= 91, spo2 <= 93, spo2 <= 95],
        [3, 2, 1], default=0).astype(float)
    p[np.isnan(spo2)] = np.nan
    return p


def news2_points_sbp(sbp):
    p = np.select(
        [sbp <= 90, sbp <= 100, sbp <= 110, sbp <= 219],
        [3, 2, 1, 0], default=3).astype(float)
    p[np.isnan(sbp)] = np.nan
    return p


def news2_points_temp(temp):
    p = np.select(
        [temp <= 35.0, temp <= 36.0, temp <= 38.0, temp <= 39.0],
        [3, 1, 0, 1], default=2).astype(float)
    p[np.isnan(temp)] = np.nan
    return p


def points_to_level(p):
    """NEWS2 points: 0 -> 0 (NORMAL), 1-2 -> 1 (MEDIUM), 3 -> 2 (CRITICAL)."""
    lvl = np.select([p == 0, p <= 2], [0, 1], default=2).astype(float)
    lvl[np.isnan(p)] = np.nan
    return lvl


def level_hr(df):
    """Resting: NEWS2. Exercise/EVA: fraction of predicted max HR."""
    hr = df["heart_rate_bpm"].to_numpy(float)
    rest_lvl = points_to_level(news2_points_hr(hr))
    pct = hr / df["hr_max_pred_bpm"].to_numpy(float)
    ex_lvl = np.select([pct < 0.85, pct < 0.95], [0, 1], default=2).astype(float)
    ex_lvl[np.isnan(hr)] = np.nan
    active = df["activity_state"].isin(["EXERCISE", "EVA"]).to_numpy()
    return np.where(active, ex_lvl, rest_lvl)


def level_rr(df):
    rr = df["respiratory_rate_bpm"].to_numpy(float)
    lvl = points_to_level(news2_points_rr(rr))
    active = df["activity_state"].isin(["EXERCISE", "EVA"]).to_numpy()
    ex_lvl = np.select([rr <= 35, rr <= 45], [0, 1], default=2).astype(float)
    ex_lvl[np.isnan(rr)] = np.nan
    return np.where(active, ex_lvl, lvl)


def level_spo2(df):
    return points_to_level(news2_points_spo2(df["spo2_percent"].to_numpy(float)))


def level_temp(df):
    t = df["core_temp_c"].to_numpy(float)
    lvl = points_to_level(news2_points_temp(t))
    # NEWS2 gives max 2 points for >=39.1 C; treat >=39.5 C as CRITICAL
    lvl[t >= 39.5] = 2
    active = df["activity_state"].isin(["EXERCISE", "EVA"]).to_numpy()
    ex_lvl = np.select([t <= 38.5, t <= 39.5], [0, 1], default=2).astype(float)
    ex_lvl[np.isnan(t)] = np.nan
    return np.where(active, ex_lvl, lvl)


def level_bp(df):
    """Worst of NEWS2 (low SBP) and ACC/AHA (high BP). Not scored during exercise."""
    sbp = df["systolic_bp_mmhg"].to_numpy(float)
    dbp = df["diastolic_bp_mmhg"].to_numpy(float)
    low = points_to_level(news2_points_sbp(sbp))
    high = np.select(
        [(sbp > 180) | (dbp > 120), (sbp >= 140) | (dbp >= 90), (sbp >= 130) | (dbp >= 80)],
        [2, 1, 1], default=0).astype(float)
    lvl = np.maximum(low, high)
    active = df["activity_state"].isin(["EXERCISE", "EVA"]).to_numpy()
    ex_lvl = np.select([sbp <= 200, sbp <= 230], [0, 1], default=2).astype(float)
    return np.where(active, ex_lvl, lvl)


def level_glucose(df):
    g = df["blood_glucose_mgdl"].to_numpy(float)
    lvl = np.select([(g < 54) | (g > 250), (g < 70) | (g > 180)], [2, 1], default=0).astype(float)
    lvl[np.isnan(g)] = np.nan
    return lvl


def level_sleep(df):
    s = df["sleep_hours_last_night"].to_numpy(float)
    return np.select([s < 4.5, s < 6.0], [2, 1], default=0).astype(float)


def level_hrv(df):
    ratio = df["hrv_rmssd_ms"].to_numpy(float) / df["hrv_baseline_ms"].to_numpy(float)
    lvl = np.select([ratio < 0.4, ratio < 0.6], [2, 1], default=0).astype(float)
    lvl[np.isnan(ratio)] = np.nan
    # HRV naturally collapses during exercise -> not scored then
    active = df["activity_state"].isin(["EXERCISE", "EVA"]).to_numpy()
    lvl[active] = 0
    return lvl


def level_co2(df):
    c = df["cabin_co2_mmhg"].to_numpy(float)
    return np.select([c > 5.3, c > 3.0], [2, 1], default=0).astype(float)


def level_radiation(df):
    r = df["radiation_rate_usv_h"].to_numpy(float)
    return np.select([r > 300, r > 150], [2, 1], default=0).astype(float)


METRIC_FUNCS = {
    "hr_status": level_hr,
    "bp_status": level_bp,
    "rr_status": level_rr,
    "spo2_status": level_spo2,
    "temp_status": level_temp,
    "hrv_status": level_hrv,
    "glucose_status": level_glucose,
    "sleep_status": level_sleep,
    "co2_status": level_co2,
    "radiation_status": level_radiation,
}


def news2_total(df):
    """Aggregate NEWS2 score (resting rows only; NaN-safe)."""
    pts = [
        news2_points_hr(df["heart_rate_bpm"].to_numpy(float)),
        news2_points_rr(df["respiratory_rate_bpm"].to_numpy(float)),
        news2_points_spo2(df["spo2_percent"].to_numpy(float)),
        news2_points_sbp(df["systolic_bp_mmhg"].to_numpy(float)),
        news2_points_temp(df["core_temp_c"].to_numpy(float)),
    ]
    total = np.nansum(np.vstack(pts), axis=0)
    active = df["activity_state"].isin(["EXERCISE", "EVA"]).to_numpy()
    total[active] = np.nan
    return total


def label_dataframe(df):
    levels = {}
    for col, fn in METRIC_FUNCS.items():
        levels[col] = np.asarray(fn(df), dtype=float)
        df[col] = to_label(levels[col])

    stack = np.vstack(list(levels.values()))
    worst = np.nanmax(stack, axis=0)
    n_critical = np.nansum(stack == 2, axis=0)
    n_medium = np.nansum(stack == 1, axis=0)

    news2 = news2_total(df)
    df["news2_score"] = news2

    # Overall: CRITICAL if any metric critical or NEWS2 >= 7;
    # MEDIUM if any metric medium or NEWS2 5-6; else NORMAL.
    overall = np.where(
        (worst == 2) | (news2 >= 7), 2,
        np.where((worst == 1) | (news2 >= 5), 1, 0))
    df["n_critical_metrics"] = n_critical.astype(int)
    df["n_medium_metrics"] = n_medium.astype(int)
    df["overall_status"] = NAMES[overall]

    # Primary driver: first metric at the worst level (for explainability)
    cols = list(levels.keys())
    driver = []
    for i in range(stack.shape[1]):
        if overall[i] == 0:
            driver.append("NONE")
            continue
        idx = np.where(stack[:, i] == worst[i])[0]
        driver.append(cols[idx[0]].replace("_status", "").upper() if len(idx) else "NEWS2")
    df["primary_driver"] = driver
    return df
