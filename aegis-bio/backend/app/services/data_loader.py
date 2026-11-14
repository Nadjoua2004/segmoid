"""
Deep Space Real Telemetry Data Loader Service
Reads and aggregates production dataset (25,920 rows across 6 astronauts over 180 days).
Provides weekly sliding window retrieval and metric categorization.
"""
from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_CANDIDATES = [
    BASE_DIR.parent / "data" / "deep_space_crew_telemetry_large.csv",
    BASE_DIR / "data" / "deep_space_crew_telemetry_large.csv",
    Path("data/deep_space_crew_telemetry_large.csv"),
]

DATA_PATH = next((c for c in DATA_CANDIDATES if c.exists()), None)

class TelemetryDataLoader:
    _instance = None
    _df: Optional[pd.DataFrame] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TelemetryDataLoader, cls).__new__(cls)
            cls._instance._load_data()
        return cls._instance

    def _load_data(self):
        if DATA_PATH and DATA_PATH.exists():
            df = pd.read_csv(DATA_PATH)
            # Ensure proper types
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            # Calculate week number (1-indexed, resets every 7 mission days)
            df["week_number"] = ((df["mission_day"] - 1) // 7) + 1
            self._df = df
        else:
            self._df = pd.DataFrame()

    @property
    def is_loaded(self) -> bool:
        return self._df is not None and not self._df.empty

    def get_crew_members(self) -> List[Dict[str, Any]]:
        """Returns metadata for all available crew members in the dataset."""
        if not self.is_loaded:
            return []
        
        grouped = self._df.groupby(["astronaut_id", "astronaut_name", "sex", "age", "hrv_baseline_ms", "hr_max_pred_bpm"]).size().reset_index()
        members = []
        for _, row in grouped.iterrows():
            members.append({
                "id": row["astronaut_id"],
                "name": row["astronaut_name"],
                "sex": row["sex"],
                "age": int(row["age"]),
                "hrv_baseline": float(row["hrv_baseline_ms"]),
                "hr_max_pred": float(row["hr_max_pred_bpm"]),
                "total_weeks": int(self._df[self._df["astronaut_id"] == row["astronaut_id"]]["week_number"].max())
            })
        return sorted(members, key=lambda x: x["id"])

    def get_weekly_telemetry(self, astronaut_id: str, week_number: int = 1) -> Dict[str, Any]:
        """
        Retrieves exactly 7 days of real telemetry for the specified astronaut and week.
        Resets at week boundaries (e.g. Week 1 = Sol 1-7, Week 2 = Sol 8-14).
        """
        if not self.is_loaded:
            return {}

        crew_df = self._df[self._df["astronaut_id"] == astronaut_id]
        if crew_df.empty:
            # Fallback to first astronaut if id not matched
            astronaut_id = "ASTRO-01"
            crew_df = self._df[self._df["astronaut_id"] == astronaut_id]

        max_week = int(crew_df["week_number"].max())
        week_num = max(1, min(week_number, max_week))
        week_df = crew_df[crew_df["week_number"] == week_num].sort_values(["mission_day", "hour"])

        if week_df.empty:
            return {}

        astronaut_meta = {
            "id": astronaut_id,
            "name": week_df["astronaut_name"].iloc[0],
            "sex": week_df["sex"].iloc[0],
            "age": int(week_df["age"].iloc[0]),
            "week_number": week_num,
            "max_available_weeks": max_week,
            "start_sol": int(week_df["mission_day"].min()),
            "end_sol": int(week_df["mission_day"].max()),
        }

        # -----------------------------------------------------------------
        # 1. Hourly High-Resolution Vitals (for continuous Line Charts)
        # -----------------------------------------------------------------
        hourly_timeseries = []
        for _, r in week_df.iterrows():
            hourly_timeseries.append({
                "timestamp": r["timestamp"].strftime("%Y-%m-%d %H:%M"),
                "sol": int(r["mission_day"]),
                "hour": int(r["hour"]),
                "label": f"Sol {r['mission_day']} {int(r['hour']):02d}:00",
                "heart_rate": None if pd.isna(r["heart_rate_bpm"]) else round(float(r["heart_rate_bpm"]), 1),
                "systolic_bp": None if pd.isna(r["systolic_bp_mmhg"]) else round(float(r["systolic_bp_mmhg"]), 1),
                "diastolic_bp": None if pd.isna(r["diastolic_bp_mmhg"]) else round(float(r["diastolic_bp_mmhg"]), 1),
                "respiratory_rate": None if pd.isna(r["respiratory_rate_bpm"]) else round(float(r["respiratory_rate_bpm"]), 1),
                "activity": r["activity_state"],
            })

        # -----------------------------------------------------------------
        # 2. Ship Environmental & Life Support Telemetry (for Area Chart)
        # -----------------------------------------------------------------
        ship_environment = []
        for _, r in week_df.iterrows():
            ship_environment.append({
                "timestamp": r["timestamp"].strftime("%Y-%m-%d %H:%M"),
                "sol": int(r["mission_day"]),
                "hour": int(r["hour"]),
                "label": f"Sol {r['mission_day']} {int(r['hour']):02d}:00",
                "cabin_co2": round(float(r["cabin_co2_mmhg"]), 2),
                "radiation_rate_usv": round(float(r["radiation_rate_usv_h"]), 1),
                "spo2": None if pd.isna(r["spo2_percent"]) else round(float(r["spo2_percent"]), 1),
                "core_temp": None if pd.isna(r["core_temp_c"]) else round(float(r["core_temp_c"]), 2),
            })

        # -----------------------------------------------------------------
        # 3. Health Status Distribution (for Donut / Pie Chart)
        # -----------------------------------------------------------------
        status_counts = week_df["overall_status"].value_counts().to_dict()
        pie_distribution = [
            {"name": "NORMAL", "value": int(status_counts.get("NORMAL", 0)), "color": "#10B981"},
            {"name": "MEDIUM", "value": int(status_counts.get("MEDIUM", 0)), "color": "#F59E0B"},
            {"name": "CRITICAL", "value": int(status_counts.get("CRITICAL", 0)), "color": "#EF4444"},
        ]

        # -----------------------------------------------------------------
        # 4. Daily Stress vs. Recovery Balance (for Grouped Bar Chart)
        # -----------------------------------------------------------------
        daily_rollups = []
        for day_val, day_group in week_df.groupby("mission_day"):
            avg_hrv = day_group["hrv_rmssd_ms"].dropna().mean()
            sleep_h = day_group["sleep_hours_last_night"].iloc[0]
            avg_co2 = day_group["cabin_co2_mmhg"].mean()
            max_rad = day_group["radiation_rate_usv_h"].max()
            crit_count = (day_group["overall_status"] == "CRITICAL").sum()
            med_count = (day_group["overall_status"] == "MEDIUM").sum()

            daily_rollups.append({
                "sol": int(day_val),
                "sol_label": f"Sol {day_val}",
                "stress_hrv_rmssd": round(float(avg_hrv), 1) if not pd.isna(avg_hrv) else 45.0,
                "sleep_hours": round(float(sleep_h), 1),
                "avg_cabin_co2": round(float(avg_co2), 2),
                "peak_radiation_usv": round(float(max_rad), 1),
                "critical_events": int(crit_count),
                "medium_events": int(med_count),
            })

        # -----------------------------------------------------------------
        # 5. Weekly Summary Key Performance Metrics
        # -----------------------------------------------------------------
        valid_hr = week_df["heart_rate_bpm"].dropna()
        valid_spo2 = week_df["spo2_percent"].dropna()
        valid_hrv = week_df["hrv_rmssd_ms"].dropna()
        valid_temp = week_df["core_temp_c"].dropna()

        summary_kpis = {
            "avg_heart_rate": round(float(valid_hr.mean()), 1) if not valid_hr.empty else 72.0,
            "min_heart_rate": round(float(valid_hr.min()), 1) if not valid_hr.empty else 55.0,
            "max_heart_rate": round(float(valid_hr.max()), 1) if not valid_hr.empty else 135.0,
            "avg_spo2": round(float(valid_spo2.mean()), 1) if not valid_spo2.empty else 97.8,
            "min_spo2": round(float(valid_spo2.min()), 1) if not valid_spo2.empty else 92.0,
            "avg_hrv_rmssd": round(float(valid_hrv.mean()), 1) if not valid_hrv.empty else 48.0,
            "avg_sleep_hours": round(float(week_df["sleep_hours_last_night"].mean()), 1),
            "peak_cabin_co2": round(float(week_df["cabin_co2_mmhg"].max()), 2),
            "peak_radiation_rate": round(float(week_df["radiation_rate_usv_h"].max()), 1),
            "cumulative_radiation_msv": round(float(week_df["cumulative_radiation_msv"].max()), 2),
            "avg_core_temp": round(float(valid_temp.mean()), 2) if not valid_temp.empty else 36.8,
            "total_critical_hours": int((week_df["overall_status"] == "CRITICAL").sum()),
            "total_medium_hours": int((week_df["overall_status"] == "MEDIUM").sum()),
            "dominant_driver": week_df["primary_driver"].value_counts().index[0] if not week_df.empty else "NONE"
        }

        return {
            "astronaut": astronaut_meta,
            "summary_kpis": summary_kpis,
            "hourly_vitals": hourly_timeseries,
            "ship_environment": ship_environment,
            "status_distribution": pie_distribution,
            "stress_recovery_daily": daily_rollups,
        }

data_loader = TelemetryDataLoader()
