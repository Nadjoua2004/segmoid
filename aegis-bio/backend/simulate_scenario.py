#!/usr/bin/env python3
"""
Aegis-Bio Spaceflight Scenario Simulator
Allows demonstration and live pitching of specific deep-space clinical crises:
1. Solar Particle Event (SPE) Radiation Storm
2. Microgravity Severe Cardiovascular Deconditioning
3. Chronic Sleep Deprivation & Psychomotor Vigilance Collapse
4. Nominal Exploration Baseline
"""
import sys
import argparse
import requests

API_BASE = "http://localhost:8000/api"

SCENARIOS = {
    "spe": {
        "title": "Solar Particle Event (SPE) Radiation Ingress",
        "payload": {
            "astronaut_id": "ASTRO-7702-HELENA",
            "mission_day": 35,
            "heart_rate": 88.0,
            "bp_sys": 132.0,
            "bp_dia": 86.0,
            "spo2": 97.5,
            "sleep_hours": 5.2,
            "radiation_msv": 24.8,  # > 20 mSv/day Critical SPE threshold
            "blood_glucose": 98.0,
            "mood_score": 3,
            "subjective_notes": "Solar dosimeter alarm triggered. Proton flux surge detected."
        }
    },
    "cardio": {
        "title": "Microgravity Cardiovascular Deconditioning & Autonomic Overload",
        "payload": {
            "astronaut_id": "ASTRO-7702-HELENA",
            "mission_day": 35,
            "heart_rate": 122.0,  # > 115 bpm threshold
            "bp_sys": 146.0,      # > 140 mmHg threshold
            "bp_dia": 94.0,       # > 90 mmHg threshold
            "spo2": 96.0,
            "sleep_hours": 6.0,
            "radiation_msv": 0.8,
            "blood_glucose": 105.0,
            "mood_score": 3,
            "subjective_notes": "Severe orthostatic intolerance upon standing, cephalad pressure."
        }
    },
    "fatigue": {
        "title": "Circadian Disruption & Severe Behavioral Exhaustion",
        "payload": {
            "astronaut_id": "ASTRO-7702-HELENA",
            "mission_day": 35,
            "heart_rate": 82.0,
            "bp_sys": 125.0,
            "bp_dia": 80.0,
            "spo2": 97.0,
            "sleep_hours": 3.4,  # < 4.5h threshold
            "radiation_msv": 0.6,
            "blood_glucose": 92.0,
            "mood_score": 1,     # <= 2 threshold
            "subjective_notes": "Extreme fatigue following 3 back-to-back EVAs. Executive cognitive lag."
        }
    },
    "nominal": {
        "title": "Nominal Exploration Baseline",
        "payload": {
            "astronaut_id": "ASTRO-7702-HELENA",
            "mission_day": 35,
            "heart_rate": 68.0,
            "bp_sys": 118.0,
            "bp_dia": 76.0,
            "spo2": 98.8,
            "sleep_hours": 7.5,
            "radiation_msv": 0.45,
            "blood_glucose": 94.0,
            "mood_score": 5,
            "subjective_notes": "Optimal recovery. Resistive countermeasure completed."
        }
    }
}

def inject_scenario(scenario_key: str):
    if scenario_key not in SCENARIOS:
        print(f"Unknown scenario '{scenario_key}'. Choose from: {list(SCENARIOS.keys())}")
        return

    sc = SCENARIOS[scenario_key]
    print(f"\n[Aegis-Bio Simulator] Injecting Scenario: {sc['title']}")
    
    try:
        # Ingest telemetry
        res = requests.post(f"{API_BASE}/metrics/ingest", json=sc["payload"])
        if res.status_code == 200:
            print("✓ Telemetry successfully ingested into SQLite store.")
        else:
            print(f"✗ Failed to ingest telemetry: {res.text}")
            return

        # Query triage evaluation
        triage_res = requests.get(f"{API_BASE}/triage/current")
        if triage_res.status_code == 200:
            t_data = triage_res.json()
            print("\n--- CLINICAL TRIAGE ASSESSMENT ---")
            print(f"Overall Status: {t_data.get('overall_status')} (Risk Score: {t_data.get('overall_risk_score')}/100)")
            print(f"Active Flags: {len(t_data.get('clinical_flags', []))}")
            for flag in t_data.get("clinical_flags", []):
                print(f"  • {flag}")
            print(f"Prescribed Countermeasures: {len(t_data.get('countermeasures', []))}")
            for cm in t_data.get("countermeasures", []):
                print(f"  [+] {cm['title']} ({cm['urgency']}): {cm['protocol']}")
            print(f"Emergency Escalation Required: {t_data.get('requires_emergency_escalation')}")
        
    except requests.exceptions.ConnectionError:
        print("✗ Could not connect to Aegis-Bio backend. Please ensure 'python run.py' is running on http://localhost:8000.")

def main():
    parser = argparse.ArgumentParser(description="Aegis-Bio Clinical Scenario Simulator")
    parser.add_argument(
        "scenario",
        choices=["spe", "cardio", "fatigue", "nominal"],
        help="Spaceflight crisis to simulate (spe, cardio, fatigue, nominal)"
    )
    args = parser.parse_args()
    inject_scenario(args.scenario)

if __name__ == "__main__":
    main()
