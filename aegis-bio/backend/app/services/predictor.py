"""
Predictive Vital Forecasting Service
Implements adaptive Time-Series forecasting across multi-scale operational horizons:
- DAILY (24-Hour Horizon): Hourly forecasting with circadian diurnal harmonics for EVA sorties.
- WEEKLY (7-Day Horizon): Tactical trend velocity modeling with damped Holt-Winters smoothing.
- MONTHLY (30-Day Horizon): Long-duration adaptation and biological plateau asymptotic modeling.
"""
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
from app.schemas import PredictionResult, TrajectoryPoint
from app.services.time_series_forecaster import time_series_forecaster

def calculate_trajectory_forecast(
    history_records: List[Dict[str, Any]],
    astronaut_id: str = "ASTRO-7702-HELENA",
    horizon_days: int = 7,
    time_scale: str = "WEEKLY"
) -> PredictionResult:
    """
    Fits historical time-series data using optimized Holt-Winters Damped Exponential Smoothing
    and Autoregressive state dynamics to project biometric deterioration, cumulative radiation burden,
    and strain indices over the specified time scale (DAILY, WEEKLY, or MONTHLY).
    """
    scale = time_scale.upper()
    if scale == "DAILY" and horizon_days == 7:
        steps = 24
    elif scale == "MONTHLY" and horizon_days == 7:
        steps = 30
    else:
        steps = horizon_days

    if not history_records:
        return PredictionResult(
            astronaut_id=astronaut_id,
            time_scale=scale,
            forecast_horizon_days=steps,
            horizon_steps=steps,
            model_used=f"Fallback Baseline [{scale}]",
            projected_trajectory=[],
            cardiovascular_strain_score=25.0,
            cognitive_degradation_risk=15.0,
            early_warnings=["Insufficient historical telemetry to compute time-series projection."],
            critical_inflection_day=None,
            r2_fit_quality=0.0
        )
    
    df = pd.DataFrame(history_records).sort_values("mission_day")
    last_day = int(df["mission_day"].max())

    # -------------------------------------------------------------
    # Multi-Scale Time-Series Forecasting
    # -------------------------------------------------------------
    hr_ts = time_series_forecaster.fit_and_forecast(
        df["heart_rate"].values,
        horizon=steps,
        min_bound=45.0,
        max_bound=175.0,
        default_baseline=72.0,
        time_scale=scale
    )
    hr_pred = hr_ts["forecast"]
    hr_lower = hr_ts["lower_bound"]
    hr_upper = hr_ts["upper_bound"]
    hr_r2 = hr_ts["r2_fit"]

    spo2_ts = time_series_forecaster.fit_and_forecast(
        df["spo2"].values,
        horizon=steps,
        min_bound=88.0,
        max_bound=99.5,
        default_baseline=98.0,
        time_scale=scale
    )
    spo2_pred = spo2_ts["forecast"]

    sleep_ts = time_series_forecaster.fit_and_forecast(
        df["sleep_hours"].values,
        horizon=steps,
        min_bound=2.5,
        max_bound=9.0,
        default_baseline=7.0,
        time_scale=scale
    )
    sleep_pred = sleep_ts["forecast"]

    rad_ts = time_series_forecaster.fit_and_forecast(
        df["radiation_msv"].values,
        horizon=steps,
        min_bound=0.1,
        max_bound=50.0,
        default_baseline=0.5,
        time_scale=scale
    )
    rad_pred = rad_ts["forecast"]

    projected_points: List[TrajectoryPoint] = []
    early_warnings: List[str] = []
    inflection_step: Optional[int] = None
    
    for idx in range(steps):
        if scale == "DAILY":
            step_num = idx + 1
            label = f"Hour +{step_num:02d}"
        else:
            step_num = last_day + idx + 1
            label = f"Sol {step_num}"

        pred_hr = float(round(hr_pred[idx], 1))
        pred_spo2 = float(round(spo2_pred[idx], 1))
        pred_rad = float(round(rad_pred[idx], 3))
        pred_sleep = float(round(sleep_pred[idx], 1))
        
        # Cardiovascular Strain Index (0 - 100)
        hr_strain = max(0.0, (pred_hr - 65.0) / (120.0 - 65.0)) * 60.0
        spo2_strain = max(0.0, (98.0 - pred_spo2) / 8.0) * 40.0
        cv_strain = min(100.0, max(0.0, hr_strain + spo2_strain))
        
        # Cognitive Readiness Index (0 - 100)
        sleep_ratio = max(0.0, min(1.0, (pred_sleep - 3.5) / 4.0))
        cog_readiness = min(100.0, max(0.0, sleep_ratio * 85.0 + 15.0))
        
        # Detection of critical inflection point
        if (cv_strain > 75.0 or pred_sleep < 4.2 or pred_rad > 15.0) and inflection_step is None:
            inflection_step = step_num
            
        projected_points.append(
            TrajectoryPoint(
                day=step_num,
                time_label=label,
                heart_rate_predicted=pred_hr,
                spo2_predicted=pred_spo2,
                radiation_cumulative_predicted=pred_rad,
                sleep_predicted=pred_sleep,
                cardiovascular_strain_index=round(cv_strain, 1),
                cognitive_readiness_index=round(cog_readiness, 1),
                lower_ci_heart_rate=float(round(hr_lower[idx], 1)),
                upper_ci_heart_rate=float(round(hr_upper[idx], 1))
            )
        )
    
    mean_cv_strain = float(round(np.mean([p.cardiovascular_strain_index for p in projected_points]), 1))
    mean_cog_readiness = float(np.mean([p.cognitive_readiness_index for p in projected_points]))
    cognitive_degradation_risk = float(round(max(0.0, 100.0 - mean_cog_readiness), 1))
    
    # Scale-specific clinical warnings
    if scale == "DAILY":
        high_hr_hour = next((p.time_label for p in projected_points if p.heart_rate_predicted > 95.0), None)
        low_spo2_hour = next((p.time_label for p in projected_points if p.spo2_predicted < 94.0), None)
        if high_hr_hour:
            early_warnings.append(f"{high_hr_hour}: Tachycardia spike forecasted during daily shift.")
        if low_spo2_hour:
            early_warnings.append(f"{low_spo2_hour}: Hypoxia dip projected during duty window; verify suit/cabin scrubbers.")
    elif scale == "MONTHLY":
        high_rad_point = next((p.time_label for p in projected_points if p.radiation_cumulative_predicted > 25.0), None)
        if high_rad_point:
            early_warnings.append(f"{high_rad_point}: Monthly cumulative ionizing radiation projected near NASA 30-day limits.")
        if mean_cv_strain > 55.0:
            early_warnings.append("Chronic microgravity cardiovascular deconditioning drift projected over 30-day transit.")
    else:  # WEEKLY
        first_hr_breach = next((p.time_label for p in projected_points if p.heart_rate_predicted > 95.0), None)
        if first_hr_breach:
            early_warnings.append(f"{first_hr_breach}: Resting heart rate projected above 95 BPM (cardiovascular strain).")
        if mean_cv_strain > 60.0:
            early_warnings.append("Elevated weekly cardiovascular strain forecasted. Prescribe cycle ergometry countermeasure.")

    return PredictionResult(
        astronaut_id=astronaut_id,
        time_scale=scale,
        forecast_horizon_days=steps,
        horizon_steps=steps,
        model_used=hr_ts["model"],
        projected_trajectory=projected_points,
        cardiovascular_strain_score=mean_cv_strain,
        cognitive_degradation_risk=cognitive_degradation_risk,
        early_warnings=early_warnings,
        critical_inflection_day=inflection_step,
        r2_fit_quality=float(round(max(0.0, min(1.0, hr_r2)), 3))
    )
