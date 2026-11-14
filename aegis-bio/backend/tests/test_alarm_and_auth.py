"""
Automated Integration Tests for Aegis-Bio Alarm Escalation and Authentication System.
Tests:
1. Astronaut user registration with designated emergency contact
2. User authentication & JWT token generation
3. Emergency contact profile management
4. Health Predictor Agent autonomous critical alarm generation
5. Owner answering within timeout window (halting siren)
6. Dead-man's switch timeout: Automatic switch to Emergency Contact when owner is unresponsive
7. Emergency contact acknowledgment and rescue logging
"""
import unittest
from datetime import datetime, timedelta
import json
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app, on_startup
from app.database import SessionLocal
from app.models import UserModel, EmergencyAlertModel

class TestAlarmAndAuthentication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        on_startup()
        cls.client = TestClient(app)

    def setUp(self):
        self.db: Session = SessionLocal()
        # Clean up alarms between tests for clean isolation
        self.db.query(EmergencyAlertModel).delete()
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_01_user_registration_with_emergency_contact(self):
        """Verify astronaut registration stores mandatory emergency contact details."""
        reg_payload = {
            "username": f"astro_test_{int(datetime.utcnow().timestamp())}",
            "email": f"test_{int(datetime.utcnow().timestamp())}@artemis.nasa.gov",
            "password": "MissionPassword2028!",
            "full_name": "Dr. Sarah Connor",
            "callsign": "ASTRO-99",
            "role": "Biosphere Specialist",
            "emergency_contact_name": "Dr. Marcus Chen",
            "emergency_contact_callsign": "ASTRO-02",
            "emergency_contact_email": "chen@artemis.nasa.gov",
            "emergency_contact_phone": "MCC-CH-02",
            "emergency_contact_role": "Crew Medical Officer",
            "alert_timeout_seconds": 45
        }
        response = self.client.post("/api/auth/register", json=reg_payload)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("access_token", data)
        user = data["user"]
        self.assertEqual(user["callsign"], "ASTRO-99")
        self.assertEqual(user["emergency_contact_name"], "Dr. Marcus Chen")
        self.assertEqual(user["emergency_contact_callsign"], "ASTRO-02")
        self.assertEqual(user["alert_timeout_seconds"], 45)

    def test_02_user_login(self):
        """Verify login succeeds and returns user profile with emergency contact."""
        login_payload = {
            "username_or_email": "cmdr_vance",
            "password": "Password123!"
        }
        response = self.client.post("/api/auth/login", json=login_payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["user"]["callsign"], "ASTRO-01")
        self.assertEqual(data["user"]["emergency_contact_callsign"], "ASTRO-02")

    def test_03_update_emergency_contact(self):
        """Verify an astronaut can update their chosen emergency contact."""
        # 1. Login to get token
        login_res = self.client.post("/api/auth/login", json={
            "username_or_email": "eng_kowalski",
            "password": "Password123!"
        })
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Update contact
        update_payload = {
            "emergency_contact_name": "Cmdr. Elena Vance",
            "emergency_contact_callsign": "ASTRO-01",
            "emergency_contact_email": "vance@artemis.nasa.gov",
            "emergency_contact_phone": "MCC-CH-01",
            "emergency_contact_role": "Mission Commander",
            "alert_timeout_seconds": 90
        }
        res = self.client.put("/api/auth/emergency-contact", json=update_payload, headers=headers)
        self.assertEqual(res.status_code, 200)
        updated = res.json()
        self.assertEqual(updated["emergency_contact_callsign"], "ASTRO-01")
        self.assertEqual(updated["alert_timeout_seconds"], 90)

    def test_04_predictor_triggers_alarm_on_critical_prediction(self):
        """
        Verify that when the health predictor agent forecasts a dangerous or critical
        condition requiring action, an active alarm is autonomously dispatched.
        """
        # Week 9 for ASTRO-01 contains critical SPE / severe cardiovascular drift and ECLSS CO2 surge
        res = self.client.post("/api/otel/predict?astronaut_id=ASTRO-01&week_number=9&forecast_days=7")
        self.assertEqual(res.status_code, 200)
        pred = res.json()

        # The prediction should indicate critical risk and trigger alarm routed to closest astronaut
        self.assertTrue(pred["alarm_triggered"])
        self.assertIsNotNone(pred["alarm_id"])
        alarm_details = pred["alarm_details"]
        self.assertEqual(alarm_details["status"], "PENDING_OWNER")
        self.assertIsNotNone(alarm_details["emergency_contact_callsign"])
        self.assertIn("away", alarm_details["emergency_contact_role"].lower())
        self.assertGreater(alarm_details["remaining_seconds"], 0)

    def test_05_owner_answers_alarm_in_time(self):
        """Verify that when the owner answers the alarm before timeout, escalation is halted."""
        # Trigger a test drill with 60 second timeout for ASTRO-01
        drill_res = self.client.post("/api/emergency/trigger?astronaut_id=ASTRO-01&timeout_seconds=60")
        self.assertEqual(drill_res.status_code, 200)
        alarm = drill_res.json()
        alert_id = alarm["alert_id"]

        # Owner answers
        ans_res = self.client.post("/api/emergency/answer-owner", json={
            "alert_id": alert_id,
            "notes": "Commander Vance responsive. Acknowledged nominal."
        })
        self.assertEqual(ans_res.status_code, 200)
        ans_data = ans_res.json()
        self.assertTrue(ans_data["success"])
        self.assertEqual(ans_data["alert"]["status"], "ACKNOWLEDGED_BY_OWNER")
        self.assertTrue(ans_data["alert"]["acknowledged"])
        self.assertTrue(ans_data["alert"]["owner_answered"])

    def test_06_dead_man_switch_timeout_escalates_to_emergency_contact(self):
        """
        Verify that if the owner does not answer within the timeout window,
        the alert automatically switches / escalates to the CLOSEST astronaut
        to the person's device in real-time.
        """
        now = datetime.utcnow()
        expired_alert_id = f"TEST-TIMEOUT-{int(now.timestamp())}"
        alert_record = EmergencyAlertModel(
            alert_id=expired_alert_id,
            astronaut_id="ASTRO-01",
            severity="CRITICAL",
            hazard_origin="Agent Predictor: Hypoxia & Autonomic Collapse",
            message="Critical hypoxia risk detected; immediate LiOH scrub needed.",
            suggested_crew_actions=json.dumps(["Purge LiOH canister"]),
            timestamp=now - timedelta(seconds=120),
            status="PENDING_OWNER",
            timeout_seconds=30,
            timeout_at=now - timedelta(seconds=90),  # expired 90s ago
            emergency_contact_name="Pending",
            emergency_contact_callsign="ASTRO-02",
            emergency_contact_role="Crew Medical Officer",
            acknowledged=False,
            owner_answered=False,
            source="HEALTH_PREDICTOR_AGENT",
            requires_action=True
        )
        self.db.add(alert_record)
        self.db.commit()

        # Query status / check timeout
        status_res = self.client.get(f"/api/emergency/status?astronaut_id=ASTRO-01")
        self.assertEqual(status_res.status_code, 200)
        current_status = status_res.json()
        self.assertEqual(current_status["alert_id"], expired_alert_id)
        # Should have automatically switched to the closest astronaut to ASTRO-01's device!
        self.assertEqual(current_status["status"], "SWITCHED_TO_EMERGENCY_CONTACT")
        self.assertIsNotNone(current_status["emergency_contact_callsign"])
        self.assertIn("Nearest:", current_status["emergency_contact_role"])
        self.assertEqual(current_status["remaining_seconds"], 0)

        # Now, if the owner attempts to answer after timeout:
        late_answer_res = self.client.post("/api/emergency/answer-owner", json={
            "alert_id": expired_alert_id,
            "notes": "Trying to answer too late"
        })
        self.assertEqual(late_answer_res.status_code, 200)
        late_data = late_answer_res.json()
        self.assertFalse(late_data["success"])
        self.assertIn("switched", late_data["message"].lower())

    def test_07_emergency_contact_acknowledges_escalated_alarm(self):
        """
        Verify that after the alert switches to the emergency contact,
        the emergency contact can acknowledge the alert and record intervention.
        """
        now = datetime.utcnow()
        alert_record = EmergencyAlertModel(
            alert_id=f"ESCALATED-{int(now.timestamp())}",
            astronaut_id="ASTRO-01",
            severity="CRITICAL",
            hazard_origin="Agent Predictor: Acute Cardiac Decompensation",
            message="Severe tachycardia > 130 bpm unresponsive.",
            suggested_crew_actions=json.dumps(["Immediate IV administration"]),
            timestamp=now - timedelta(seconds=120),
            status="SWITCHED_TO_EMERGENCY_CONTACT",
            timeout_seconds=30,
            timeout_at=now - timedelta(seconds=90),
            emergency_contact_name="Dr. Marcus Chen",
            emergency_contact_callsign="ASTRO-02",
            emergency_contact_role="Crew Medical Officer",
            acknowledged=False,
            owner_answered=False,
            source="HEALTH_PREDICTOR_AGENT",
            requires_action=True
        )
        self.db.add(alert_record)
        self.db.commit()

        contact_ack_res = self.client.post("/api/emergency/contact-ack", json={
            "alert_id": alert_record.alert_id,
            "contact_callsign": "ASTRO-02",
            "intervention_notes": "Dr. Chen entered module, administered supplemental O2, astronaut stabilized."
        })
        self.assertEqual(contact_ack_res.status_code, 200)
        resolved_data = contact_ack_res.json()
        self.assertEqual(resolved_data["status"], "ACKNOWLEDGED_BY_CONTACT")
        self.assertTrue(resolved_data["acknowledged"])
        self.assertEqual(resolved_data["acknowledged_by"], "ASTRO-02")

if __name__ == "__main__":
    unittest.main()
