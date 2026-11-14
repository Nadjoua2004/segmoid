"""
Classifier 1: Metric-Level Severity Classifier
Evaluates each individual astronaut biometric and environmental metric:
Classifies each into: 'NORMAL', 'MEDIUM', or 'CRITICAL' based on aerospace medical baselines.
"""
from typing import Dict, Any

# Use the shared API schemas (not local look-alike copies): Pydantic v2 rejects instances of a
# different class with the same fields, which made TriageResult(metric_evaluations=...) fail.
from app.schemas import MetricEvaluation, MetricClassificationReport

# Aerospace clinical thresholds defined by NASA-STD-3001
METRIC_THRESHOLDS = {
    "heart_rate": {
        "label": "Resting Heart Rate",
        "unit": "BPM",
        "nominal": (50.0, 90.0),
        "medium_high": (90.0, 115.0),
        "critical_high": 115.0,
        "critical_low": 45.0,
    },
    "spo2": {
        "label": "Blood Oxygen (SpO2)",
        "unit": "%",
        "nominal": (96.0, 100.0),
        "medium_low": (93.0, 96.0),
        "critical_low": 93.0,
    },
    "bp_sys": {
        "label": "Systolic Blood Pressure",
        "unit": "mmHg",
        "nominal": (90.0, 130.0),
        "medium_high": (130.0, 140.0),
        "critical_high": 140.0,
        "critical_low": 85.0,
    },
    "bp_dia": {
        "label": "Diastolic Blood Pressure",
        "unit": "mmHg",
        "nominal": (60.0, 85.0),
        "medium_high": (85.0, 90.0),
        "critical_high": 90.0,
        "critical_low": 50.0,
    },
    "sleep_hours": {
        "label": "Circadian Sleep Duration",
        "unit": "Hours",
        "nominal": (6.5, 9.0),
        "medium_low": (4.5, 6.5),
        "critical_low": 4.5,
    },
    "radiation_msv": {
        "label": "Daily Radiation Exposure",
        "unit": "mSv/day",
        "nominal": (0.0, 2.0),
        "medium_high": (2.0, 20.0),
        "critical_high": 20.0,  # Acute Solar Particle Event (SPE) limit
    },
    "mood_score": {
        "label": "Subjective Psychological Morale",
        "unit": "/5",
        "nominal": (4, 5),
        "medium_low": (3, 3),
        "critical_low": 2,
    },
    "core_temp_c": {
        "label": "Core Body Temperature",
        "unit": "°C",
        "nominal": (36.5, 37.5),
        "medium_high": (37.5, 38.2),
        "critical_high": 38.2,
        "critical_low": 35.5,
    },
    "hrv_rmssd": {
        "label": "Heart Rate Variability (RMSSD)",
        "unit": "ms",
        "nominal": (35.0, 100.0),
        "medium_low": (22.0, 35.0),
        "critical_low": 22.0,
    },
    "cabin_co2_mmhg": {
        "label": "Cabin Ambient ppCO2",
        "unit": "mmHg",
        "nominal": (0.0, 3.0),
        "medium_high": (3.0, 4.5),
        "critical_high": 4.5,
    }
}

class MetricSeverityClassifier:
    """Classifier 1: Determines whether each biometric is NORMAL, MEDIUM, or CRITICAL."""

    @staticmethod
    def classify_single_metric(name: str, value: float) -> MetricEvaluation:
        cfg = METRIC_THRESHOLDS.get(name)
        if not cfg:
            return MetricEvaluation(
                metric_name=name,
                label=name.replace("_", " ").title(),
                value=float(value),
                unit="",
                status="NORMAL",
                nominal_range="Unrestricted",
                deviation="0.0%",
                clinical_note="Standard parameter within normal limits."
            )

        status = "NORMAL"
        note = "Within nominal aerospace reference range."
        deviation_str = "Nominal"

        # 1. Heart Rate
        if name == "heart_rate":
            if value >= cfg["critical_high"]:
                status = "CRITICAL"
                note = f"Severe resting tachycardia ({value} BPM). High risk of orthostatic deconditioning or dysrhythmia."
                deviation_str = f"+{value - cfg['nominal'][1]:.1f} BPM"
            elif value <= cfg["critical_low"]:
                status = "CRITICAL"
                note = f"Pathological bradycardia ({value} BPM)."
                deviation_str = f"-{cfg['nominal'][0] - value:.1f} BPM"
            elif value > cfg["nominal"][1]:
                status = "MEDIUM"
                note = f"Elevated resting heart rate ({value} BPM). Fluid cephalad shift adaptation."
                deviation_str = f"+{value - cfg['nominal'][1]:.1f} BPM"

        # 2. SpO2
        elif name == "spo2":
            if value < cfg["critical_low"]:
                status = "CRITICAL"
                note = f"Acute hypoxemia ({value}%). Arterial saturation below life-support baseline."
                deviation_str = f"-{cfg['nominal'][0] - value:.1f}%"
            elif value < cfg["nominal"][0]:
                status = "MEDIUM"
                note = f"Sub-optimal oxygen saturation ({value}%). Check habitat ppO2 and ventilation."
                deviation_str = f"-{cfg['nominal'][0] - value:.1f}%"

        # 3. Radiation
        elif name == "radiation_msv":
            if value >= cfg["critical_high"]:
                status = "CRITICAL"
                note = f"Acute SPE Radiation Storm Surge ({value} mSv/day). Immediate bunker retreat mandatory."
                deviation_str = f"+{value - cfg['nominal'][1]:.2f} mSv"
            elif value > cfg["nominal"][1]:
                status = "MEDIUM"
                note = f"Elevated radiation flux ({value} mSv/day). Galactic cosmic ray peak or early solar active region."
                deviation_str = f"+{value - cfg['nominal'][1]:.2f} mSv"

        # 4. Sleep Hours
        elif name == "sleep_hours":
            if value < cfg["critical_low"]:
                status = "CRITICAL"
                note = f"Critical sleep deprivation ({value} hrs). Severe psychomotor vigilance impairment expected."
                deviation_str = f"-{cfg['nominal'][0] - value:.1f} hrs"
            elif value < cfg["nominal"][0]:
                status = "MEDIUM"
                note = f"Mild-to-moderate sleep debt ({value} hrs). Circadian phase shift indicated."
                deviation_str = f"-{cfg['nominal'][0] - value:.1f} hrs"

        # 5. Blood Pressure (Sys / Dia)
        elif name == "bp_sys":
            if value >= cfg["critical_high"] or value <= cfg["critical_low"]:
                status = "CRITICAL"
                note = f"Stage 2 Hypertension or Hypoperfusion ({value} mmHg)."
                deviation_str = f"{value - cfg['nominal'][1]:+.0f} mmHg"
            elif value > cfg["nominal"][1]:
                status = "MEDIUM"
                note = f"Elevated systolic pressure ({value} mmHg)."
                deviation_str = f"+{value - cfg['nominal'][1]:.0f} mmHg"

        elif name == "bp_dia":
            if value >= cfg["critical_high"] or value <= cfg["critical_low"]:
                status = "CRITICAL"
                note = f"Critical diastolic blood pressure ({value} mmHg)."
                deviation_str = f"{value - cfg['nominal'][1]:+.0f} mmHg"
            elif value > cfg["nominal"][1]:
                status = "MEDIUM"
                note = f"Mild diastolic elevation ({value} mmHg)."
                deviation_str = f"+{value - cfg['nominal'][1]:.0f} mmHg"

        # 6. Mood Score
        elif name == "mood_score":
            if value <= cfg["critical_low"]:
                status = "CRITICAL"
                note = f"Acute psychological distress or behavioral exhaustion (Score: {value}/5)."
                deviation_str = f"-{cfg['nominal'][0] - value:.0f}"
            elif value == cfg["medium_low"][0]:
                status = "MEDIUM"
                note = f"Moderate crew morale dip (Score: {value}/5)."
                deviation_str = "-1"

        # 7. Cabin CO2
        elif name == "cabin_co2_mmhg":
            if value >= cfg["critical_high"]:
                status = "CRITICAL"
                note = f"Cabin hypercapnia warning ({value} mmHg). Exceeds ECLSS scrubber threshold."
                deviation_str = f"+{value - cfg['nominal'][1]:.2f} mmHg"
            elif value > cfg["nominal"][1]:
                status = "MEDIUM"
                note = f"Elevated habitat CO2 ({value} mmHg). Scrubber cycle maintenance suggested."
                deviation_str = f"+{value - cfg['nominal'][1]:.2f} mmHg"

        # 8. Core Temperature
        elif name == "core_temp_c":
            if value >= cfg["critical_high"] or value <= cfg["critical_low"]:
                status = "CRITICAL"
                note = f"Thermal dysregulation ({value}°C). Hyperthermia or hypothermia alert."
                deviation_str = f"{value - 37.0:+.1f}°C"
            elif value > cfg["nominal"][1]:
                status = "MEDIUM"
                note = f"Subfebrile elevation ({value}°C). Post-EVA exertion heat load."
                deviation_str = f"+{value - cfg['nominal'][1]:.1f}°C"

        # 9. HRV RMSSD
        elif name == "hrv_rmssd":
            if value <= cfg["critical_low"]:
                status = "CRITICAL"
                note = f"Autonomic stress exhaustion (RMSSD: {value} ms). Severe parasympathetic withdrawal."
                deviation_str = f"-{cfg['nominal'][0] - value:.0f} ms"
            elif value < cfg["nominal"][0]:
                status = "MEDIUM"
                note = f"Moderate autonomic strain (RMSSD: {value} ms)."
                deviation_str = f"-{cfg['nominal'][0] - value:.0f} ms"

        nominal_display = f"{cfg['nominal'][0]} - {cfg['nominal'][1]} {cfg['unit']}"
        return MetricEvaluation(
            metric_name=name,
            label=cfg["label"],
            value=float(value),
            unit=cfg["unit"],
            status=status,
            nominal_range=nominal_display,
            deviation=deviation_str,
            clinical_note=note
        )

    @classmethod
    def evaluate_all_metrics(cls, metrics_dict: Dict[str, Any], astronaut_id: str = "ASTRO-7702-HELENA", mission_day: int = 34) -> MetricClassificationReport:
        evaluations = {}
        for k, v in metrics_dict.items():
            if k in METRIC_THRESHOLDS and v is not None:
                evaluations[k] = cls.classify_single_metric(k, float(v))

        critical_count = sum(1 for e in evaluations.values() if e.status == "CRITICAL")
        medium_count = sum(1 for e in evaluations.values() if e.status == "MEDIUM")
        normal_count = sum(1 for e in evaluations.values() if e.status == "NORMAL")

        if critical_count > 0:
            highest = "CRITICAL"
        elif medium_count > 0:
            highest = "MEDIUM"
        else:
            highest = "NORMAL"

        return MetricClassificationReport(
            astronaut_id=astronaut_id,
            mission_day=mission_day,
            highest_severity=highest,
            metrics=evaluations,
            critical_count=critical_count,
            medium_count=medium_count,
            normal_count=normal_count
        )

metric_classifier = MetricSeverityClassifier()
