"""
Production Health Predictor Agent Service
Ingests 7-day historical telemetry & spacecraft environmental variables
(stress/HRV, oxygen/SpO2, cabin ppCO2, ambient radiation rate).
Computes 7-day forward predictive trajectory and multidimensional risk indices.
"""
from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import PolynomialFeatures
from sklearn.pipeline import make_pipeline

class HealthPredictorAgent:
    """
    Autonomous Spaceflight Clinical Forecasting Agent.
    Combines physiological regression with spacecraft environmental stress coupling.
    """

    def predict_upcoming_health(self, weekly_data: Dict[str, Any], forecast_days: int = 7) -> Dict[str, Any]:
        """
        Takes 7-day real weekly telemetry data and predicts the next 7 days of astronaut health.
        """
        daily_rollups = weekly_data.get("stress_recovery_daily", [])
        hourly_vitals = weekly_data.get("hourly_vitals", [])
        env_metrics = weekly_data.get("ship_environment", [])
        astro = weekly_data.get("astronaut", {})
        kpis = weekly_data.get("summary_kpis", {})

        if not daily_rollups or len(daily_rollups) < 3:
            return self._fallback_prediction(astro.get("id", "ASTRO-01"))

        # Convert daily rollups to arrays
        days = np.array([d["sol"] for d in daily_rollups])
        hrv_vals = np.array([d["stress_hrv_rmssd"] for d in daily_rollups])
        sleep_vals = np.array([d["sleep_hours"] for d in daily_rollups])
        co2_vals = np.array([d["avg_cabin_co2"] for d in daily_rollups])
        rad_vals = np.array([d["peak_radiation_usv"] for d in daily_rollups])

        # Hourly values for detailed regression
        df_hourly = pd.DataFrame(hourly_vitals).dropna(subset=["heart_rate"])
        if df_hourly.empty:
            hr_series = np.array([72.0] * len(days))
        else:
            # Group hourly heart rate by sol
            hr_series = df_hourly.groupby("sol")["heart_rate"].mean().values

        last_sol = int(days[-1])
        future_sols = np.array([last_sol + i for i in range(1, forecast_days + 1)])

        # -------------------------------------------------------------
        # 1. Multi-step Regression for Core Vitals
        # -------------------------------------------------------------
        X = days.reshape(-1, 1)
        future_X = future_sols.reshape(-1, 1)

        # Heart Rate Trend (Polynomial degree 2)
        poly_hr = make_pipeline(PolynomialFeatures(degree=1 if len(days) < 5 else 2), Ridge(alpha=1.0))
        poly_hr.fit(X, hr_series if len(hr_series) == len(days) else np.repeat(np.mean(hr_series), len(days)))
        pred_hr = poly_hr.predict(future_X)

        # SpO2 trend
        df_env = pd.DataFrame(env_metrics).dropna(subset=["spo2"])
        if not df_env.empty:
            spo2_by_sol = df_env.groupby("sol")["spo2"].mean().values
            poly_spo2 = Ridge(alpha=1.0)
            poly_spo2.fit(X, spo2_by_sol if len(spo2_by_sol) == len(days) else np.repeat(97.8, len(days)))
            pred_spo2 = np.clip(poly_spo2.predict(future_X), 88.0, 99.5)
        else:
            pred_spo2 = np.array([97.8] * forecast_days)

        # Environmental Forecasting (Cabin CO2 & Radiation)
        poly_co2 = Ridge(alpha=1.0)
        poly_co2.fit(X, co2_vals)
        pred_co2 = np.clip(poly_co2.predict(future_X), 1.5, 8.0)

        poly_rad = Ridge(alpha=1.0)
        poly_rad.fit(X, rad_vals)
        pred_rad = np.clip(poly_rad.predict(future_X), 10.0, 500.0)

        # Sleep trend
        poly_sleep = Ridge(alpha=1.0)
        poly_sleep.fit(X, sleep_vals)
        pred_sleep = np.clip(poly_sleep.predict(future_X), 3.0, 9.0)

        # HRV stress trend
        poly_hrv = Ridge(alpha=1.0)
        poly_hrv.fit(X, hrv_vals)
        pred_hrv = np.clip(poly_hrv.predict(future_X), 12.0, 100.0)

        # -------------------------------------------------------------
        # 2. Environmental Stress Coupling
        # Cabin CO2 and Radiation impact cardiovascular and cognitive indices
        # -------------------------------------------------------------
        projected_trajectory = []
        cv_strain_indices = []
        cog_fatigue_indices = []
        hypoxia_risks = []
        radiation_indices = []

        for idx, sol_num in enumerate(future_sols):
            h_rate = float(round(pred_hr[idx], 1))
            sp_val = float(round(pred_spo2[idx], 1))
            co2_val = float(round(pred_co2[idx], 2))
            rad_val = float(round(pred_rad[idx], 1))
            sleep_h = float(round(pred_sleep[idx], 1))
            hrv_v = float(round(pred_hrv[idx], 1))

            # Environmental Coupling: High cabin CO2 elevates autonomic drive & vascular resistance
            co2_penalty = max(0.0, (co2_val - 3.2) * 5.0)
            h_rate += co2_penalty

            # Cardiovascular Strain (0-100)
            hr_strain = max(0.0, (h_rate - 60.0) / (120.0 - 60.0)) * 60.0
            spo2_strain = max(0.0, (98.0 - sp_val) / 8.0) * 40.0
            cv_strain = min(100.0, max(0.0, hr_strain + spo2_strain + (co2_penalty * 1.5)))

            # Cognitive Degradation Risk (0-100)
            sleep_deficit = max(0.0, (7.0 - sleep_h) / 3.5) * 60.0
            autonomic_fatigue = max(0.0, (45.0 - hrv_v) / 35.0) * 40.0
            cog_fatigue = min(100.0, max(0.0, sleep_deficit + autonomic_fatigue))

            # Hypoxia / ECLSS Risk (0-100)
            hypoxia = min(100.0, max(0.0, ((97.0 - sp_val) / 7.0) * 70.0 + ((co2_val - 2.5) / 3.0) * 30.0))

            # Radiation Hazard Index (0-100)
            rad_risk = min(100.0, max(0.0, (rad_val / 250.0) * 100.0))

            # Daily overall classification
            if cv_strain >= 70.0 or hypoxia >= 70.0 or rad_risk >= 70.0 or cog_fatigue >= 80.0:
                day_status = "CRITICAL"
            elif cv_strain >= 40.0 or hypoxia >= 40.0 or rad_risk >= 40.0 or cog_fatigue >= 50.0:
                day_status = "MEDIUM"
            else:
                day_status = "NORMAL"

            cv_strain_indices.append(cv_strain)
            cog_fatigue_indices.append(cog_fatigue)
            hypoxia_risks.append(hypoxia)
            radiation_indices.append(rad_risk)

            projected_trajectory.append({
                "day_offset": idx + 1,
                "sol": int(sol_num),
                "sol_label": f"Sol +{idx + 1} (Sol {int(sol_num)})",
                "predicted_heart_rate": round(h_rate, 1),
                "predicted_spo2": round(sp_val, 1),
                "predicted_cabin_co2": round(co2_val, 2),
                "predicted_radiation_rate": round(rad_val, 1),
                "cardiovascular_strain": round(cv_strain, 1),
                "cognitive_fatigue": round(cog_fatigue, 1),
                "status": day_status
            })

        # Summary risk metrics
        mean_cv_strain = float(round(np.mean(cv_strain_indices), 1))
        mean_cog_fatigue = float(round(np.mean(cog_fatigue_indices), 1))
        mean_hypoxia = float(round(np.mean(hypoxia_risks), 1))
        mean_rad_index = float(round(np.mean(radiation_indices), 1))

        # Overall health trajectory state
        if mean_cv_strain >= 65.0 or mean_hypoxia >= 65.0 or mean_rad_index >= 65.0:
            health_outlook = "CRITICAL_DRIFT"
        elif mean_cv_strain >= 35.0 or mean_cog_fatigue >= 45.0 or mean_hypoxia >= 35.0:
            health_outlook = "ELEVATED_STRAIN"
        else:
            health_outlook = "OPTIMAL_STABILITY"

        # -------------------------------------------------------------
        # 3. Actionable Clinical Mitigation Directives
        # -------------------------------------------------------------
        directives = []
        if mean_rad_index >= 50.0 or any(p["predicted_radiation_rate"] > 150.0 for p in projected_trajectory):
            directives.append({
                "category": "Radiation Protection",
                "urgency": "IMMEDIATE",
                "action": "Enact Solar Storm Shelter protocol; defer scheduled EVA sorties.",
                "reference": "NASA-STD-3001 Vol 1 §4.3"
            })
        if mean_cv_strain >= 55.0 or any(p["predicted_heart_rate"] > 105.0 for p in projected_trajectory):
            directives.append({
                "category": "Cardiovascular Countermeasure",
                "urgency": "WITHIN_4H",
                "action": "Schedule 45m Lower Body Negative Pressure (LBNP) suit session at -35 mmHg.",
                "reference": "NASA SP-2009-3405"
            })
        if any(p["predicted_cabin_co2"] > 3.8 for p in projected_trajectory):
            directives.append({
                "category": "ECLSS Life Support",
                "urgency": "IMMEDIATE",
                "action": "Purge Amine / LiOH scrubber canisters; inspect habitat air circulation fans.",
                "reference": "NASA Flight Rule ECLSS-14"
            })
        if mean_cog_fatigue >= 55.0:
            directives.append({
                "category": "Circadian Entrainment",
                "urgency": "ROUTINE",
                "action": "Enforce 8.0h quiet dark sleep window + 460nm blue spectrum lighting during wake.",
                "reference": "NASA TM-2020-5008149"
            })

        if not directives:
            directives.append({
                "category": "Preventive Baseline",
                "urgency": "NOMINAL",
                "action": "Maintain scheduled ARED cycle ergometry workout and standard hydration.",
                "reference": "NASA Crew Medical Protocol"
            })

        return {
            "astronaut_id": astro.get("id", "ASTRO-01"),
            "astronaut_name": astro.get("name", "Cmdr. Vance"),
            "evaluated_week": astro.get("week_number", 1),
            "forecast_horizon_days": forecast_days,
            "health_outlook": health_outlook,
            "cardiovascular_strain_score": mean_cv_strain,
            "cognitive_fatigue_risk": mean_cog_fatigue,
            "hypoxia_eclss_risk": mean_hypoxia,
            "radiation_hazard_index": mean_rad_index,
            "projected_trajectory": projected_trajectory,
            "clinical_directives": directives,
            "environmental_drivers": {
                "cabin_co2_impact": "High" if kpis.get("peak_cabin_co2", 0) > 3.5 else "Nominal",
                "radiation_state": "Elevated SPE" if kpis.get("peak_radiation_rate", 0) > 150 else "Background GCR",
                "stress_recovery_ratio": f"{kpis.get('avg_hrv_rmssd', 45)} ms / {kpis.get('avg_sleep_hours', 6.5)} h",
            }
        }

    def _fallback_prediction(self, astronaut_id: str) -> Dict[str, Any]:
        return {
            "astronaut_id": astronaut_id,
            "evaluated_week": 1,
            "forecast_horizon_days": 7,
            "health_outlook": "OPTIMAL_STABILITY",
            "cardiovascular_strain_score": 25.0,
            "cognitive_fatigue_risk": 20.0,
            "hypoxia_eclss_risk": 15.0,
            "radiation_hazard_index": 12.0,
            "projected_trajectory": [],
            "clinical_directives": [{
                "category": "Preventive Baseline",
                "urgency": "NOMINAL",
                "action": "Maintain standard spaceflight health protocol.",
                "reference": "NASA Standard"
            }],
            "environmental_drivers": {}
        }

health_predictor_agent = HealthPredictorAgent()
