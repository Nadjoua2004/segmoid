"""
Predictive Vital Forecasting Service
Implements lightweight regression algorithms (Linear & Polynomial trend fitting)
to project astronaut physiological trajectories, cardiovascular strain, and
cognitive degradation risks over the subsequent 7 mission days.
"""
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.preprocessing import PolynomialFeatures
from sklearn.pipeline import make_pipeline
from app.schemas import PredictionResult, TrajectoryPoint

def calculate_trajectory_forecast(
    history_records: List[Dict[str, Any]],
    astronaut_id: str = "ASTRO-7702-HELENA",
    horizon_days: int = 7
) -> PredictionResult:
    """
    Fits historical time-series data using regression models to project
    biometric deterioration, cumulative radiation burden, and strain indices.
    """
    if not history_records:
        # Default baseline if history is empty
        return PredictionResult(
            astronaut_id=astronaut_id,
            forecast_horizon_days=horizon_days,
            projected_trajectory=[],
            cardiovascular_strain_score=25.0,
            cognitive_degradation_risk=15.0,
            early_warnings=["Insufficient historical data to compute confident 7-day regression."],
            critical_inflection_day=None,
            r2_fit_quality=0.0
        )
    
    df = pd.DataFrame(history_records).sort_values("mission_day")
    
    # Feature X is mission day
    X = df[["mission_day"]].values
    last_day = int(df["mission_day"].max())
    future_days = np.array([[last_day + i] for i in range(1, horizon_days + 1)])
    
    # 1. Heart Rate Forecast (Polynomial Degree 2 to capture acceleration)
    poly_hr = make_pipeline(PolynomialFeatures(degree=2), Ridge(alpha=1.0))
    poly_hr.fit(X, df["heart_rate"].values)
    hr_pred = poly_hr.predict(future_days)
    hr_r2 = poly_hr.score(X, df["heart_rate"].values)
    
    # 2. SpO2 Forecast (Linear Regression with floor)
    lin_spo2 = LinearRegression()
    lin_spo2.fit(X, df["spo2"].values)
    spo2_pred = np.clip(lin_spo2.predict(future_days), 88.0, 99.5)
    
    # 3. Sleep Hours Forecast (Linear decline modeling)
    lin_sleep = LinearRegression()
    lin_sleep.fit(X, df["sleep_hours"].values)
    sleep_pred = np.clip(lin_sleep.predict(future_days), 2.5, 9.0)
    
    # 4. Radiation Dose Forecast
    # Recent radiation trend has higher weight
    recent_df = df.tail(10) if len(df) >= 10 else df
    lin_rad = LinearRegression()
    lin_rad.fit(recent_df[["mission_day"]].values, recent_df["radiation_msv"].values)
    rad_pred = np.clip(lin_rad.predict(future_days), 0.1, 50.0)
    
    # Compute composite indices for each projected day
    projected_points: List[TrajectoryPoint] = []
    early_warnings: List[str] = []
    inflection_day: Optional[int] = None
    
    for idx, f_day_arr in enumerate(future_days):
        f_day = int(f_day_arr[0])
        pred_hr = float(round(hr_pred[idx], 1))
        pred_spo2 = float(round(spo2_pred[idx], 1))
        pred_rad = float(round(rad_pred[idx], 3))
        pred_sleep = float(round(sleep_pred[idx], 1))
        
        # Cardiovascular Strain Index (0 - 100):
        # Normalized weighted combination of elevated HR, lower SpO2, and baseline shift
        hr_strain = max(0.0, (pred_hr - 65.0) / (120.0 - 65.0)) * 60.0
        spo2_strain = max(0.0, (98.0 - pred_spo2) / 8.0) * 40.0
        cv_strain = min(100.0, max(0.0, hr_strain + spo2_strain))
        
        # Cognitive Readiness Index (0 - 100):
        # High when sleep is >= 7.5h, degrades steeply below 5.5h
        sleep_ratio = max(0.0, min(1.0, (pred_sleep - 3.5) / 4.0))
        cog_readiness = min(100.0, max(0.0, sleep_ratio * 85.0 + 15.0))
        
        # Detection of critical inflection point
        if (cv_strain > 75.0 or pred_sleep < 4.2 or pred_rad > 15.0) and inflection_day is None:
            inflection_day = f_day
            
        projected_points.append(
            TrajectoryPoint(
                day=f_day,
                heart_rate_predicted=pred_hr,
                spo2_predicted=pred_spo2,
                radiation_cumulative_predicted=pred_rad,
                sleep_predicted=pred_sleep,
                cardiovascular_strain_index=round(cv_strain, 1),
                cognitive_readiness_index=round(cog_readiness, 1)
            )
        )
    
    # Overall summary metrics over the 7-day horizon
    mean_cv_strain = float(round(np.mean([p.cardiovascular_strain_index for p in projected_points]), 1))
    mean_cog_readiness = float(np.mean([p.cognitive_readiness_index for p in projected_points]))
    cognitive_degradation_risk = float(round(max(0.0, 100.0 - mean_cog_readiness), 1))
    
    # Synthesize intelligent warnings
    if any(p.heart_rate_predicted > 95.0 for p in projected_points):
        early_warnings.append(
            "Projected resting heart rate indicates acceleration of microgravity cardiovascular deconditioning."
        )
    if any(p.sleep_predicted < 4.5 for p in projected_points):
        early_warnings.append(
            "Cumulative sleep deficit projected to exceed 16 hours by Day +4; high risk of psychomotor vigilance lapse."
        )
    if any(p.radiation_cumulative_predicted > 15.0 for p in projected_points):
        early_warnings.append(
            "Radiation trajectory suggests ingress of solar particle event plume; storm shelter readiness advised."
        )
    if mean_cv_strain > 60.0:
        early_warnings.append(
            "Elevated cardiovascular strain forecasted. Prescribe targeted resistive cycle ergometry countermeasure."
        )
        
    return PredictionResult(
        astronaut_id=astronaut_id,
        forecast_horizon_days=horizon_days,
        projected_trajectory=projected_points,
        cardiovascular_strain_score=mean_cv_strain,
        cognitive_degradation_risk=cognitive_degradation_risk,
        early_warnings=early_warnings,
        critical_inflection_day=inflection_day,
        r2_fit_quality=float(round(max(0.0, min(1.0, hr_r2)), 3))
    )
