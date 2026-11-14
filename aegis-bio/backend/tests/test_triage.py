"""
Unit Tests for Aegis-Bio Spaceflight Hazard Triage
Tests NASA 5-hazard thresholds and autonomous countermeasure prescriptions.
"""
from app.schemas import HealthMetrics
from app.api.triage import evaluate_multi_hazard_triage

def test_spe_radiation_threshold():
    """Verify radiation > 20 mSv/day triggers Critical SPE and immediate storm shelter countermeasure."""
    metrics = HealthMetrics(
        astronaut_id="ASTRO-TEST",
        mission_day=35,
        heart_rate=75.0,
        bp_sys=120.0,
        bp_dia=80.0,
        spo2=98.0,
        sleep_hours=7.0,
        radiation_msv=25.4,  # SPE breach
        blood_glucose=95.0,
        mood_score=4
    )
    result = evaluate_multi_hazard_triage(metrics)
    assert result.overall_status == "CRITICAL"
    assert result.requires_emergency_escalation is True
    assert any("Solar Particle Event" in flag for flag in result.clinical_flags)
    assert any(cm.id == "CM-RAD-SPE-01" for cm in result.countermeasures)

def test_microgravity_cardiovascular_deconditioning():
    """Verify resting HR > 115 bpm triggers microgravity deconditioning and LBNP protocol."""
    metrics = HealthMetrics(
        astronaut_id="ASTRO-TEST",
        mission_day=35,
        heart_rate=125.0,  # Resting tachycardia
        bp_sys=148.0,      # Systolic hypertension
        bp_dia=95.0,
        spo2=98.0,
        sleep_hours=7.0,
        radiation_msv=0.5,
        blood_glucose=95.0,
        mood_score=4
    )
    result = evaluate_multi_hazard_triage(metrics)
    assert result.hazards.microgravity_score >= 80.0
    assert any("Microgravity Cardiovascular Deconditioning" in flag for flag in result.clinical_flags)
    assert any(cm.id == "CM-CARD-LBNP-01" for cm in result.countermeasures)

def test_circadian_sleep_deprivation():
    """Verify sleep < 4.5h and mood <= 2 triggers acute behavioral fatigue protocol."""
    metrics = HealthMetrics(
        astronaut_id="ASTRO-TEST",
        mission_day=35,
        heart_rate=72.0,
        bp_sys=120.0,
        bp_dia=80.0,
        spo2=98.0,
        sleep_hours=3.2,  # Severe deprivation
        radiation_msv=0.4,
        blood_glucose=95.0,
        mood_score=1     # Distressed
    )
    result = evaluate_multi_hazard_triage(metrics)
    assert result.hazards.isolation_score >= 80.0
    assert any("Circadian Disruption" in flag for flag in result.clinical_flags)
    assert any(cm.id == "CM-BEHAV-SLEEP-01" for cm in result.countermeasures)

def test_nominal_spaceflight_telemetry():
    """Verify nominal baseline produces NOMINAL status without emergency flags."""
    metrics = HealthMetrics(
        astronaut_id="ASTRO-TEST",
        mission_day=35,
        heart_rate=68.0,
        bp_sys=118.0,
        bp_dia=78.0,
        spo2=98.5,
        sleep_hours=7.5,
        radiation_msv=0.42,
        blood_glucose=95.0,
        mood_score=5
    )
    result = evaluate_multi_hazard_triage(metrics)
    assert result.overall_status == "NOMINAL"
    assert result.requires_emergency_escalation is False
    assert len(result.clinical_flags) == 0

if __name__ == "__main__":
    test_spe_radiation_threshold()
    test_microgravity_cardiovascular_deconditioning()
    test_circadian_sleep_deprivation()
    test_nominal_spaceflight_telemetry()
    print("✓ All NASA hazard triage unit tests passed successfully!")
