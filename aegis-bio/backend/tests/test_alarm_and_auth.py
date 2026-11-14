"""
Automated Integration Tests for Aegis-Bio Alarm Escalation and Station Crew System.
Tests:
1. Crew Lead registers Station & Crew with username and key (no full names, no roles).
2. Crew Lead provisions Crew Members with username & key.
3. Non-lead crew member cannot provision crew members.
4. Member authentication using username and key.
5. Predictor triggers critical alarm routed within victim's crew.
6. Owner answers within timeout (halting siren).
7. Dead-Man's Switch Timeout & Strict Crew-Isolation:
   If an astronaut from Crew A is a victim, the closest astronaut is chosen ONLY from Crew A,
   strictly ignoring members from Crew B even if physically closer (0.1m away)!
8. Closest crew member acknowledges intervention and logs rescue to Supabase.
"""
import unittest
from datetime import datetime, timedelta
import json
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app, on_startup
from app.database import SessionLocal
from app.models import UserModel, EmergencyAlertModel
from app.services.alarm_service import find_closest_astronaut

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

    def test_01_crew_lead_registers_station_and_crew(self):
        """Crew Lead registers Station and Crew using username and key."""
        unique_id = int(datetime.utcnow().timestamp())
        lead_payload = {
            "username": f"lead_artemis_{unique_id}",
            "key": "StationKey2028!",
            "station_name": "ARTEMIS-BASE-ALPHA",
            "crew_name": "CREW-A"
        }
        response = self.client.post("/api/auth/register-lead", json=lead_payload)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("access_token", data)
        user = data["user"]
        self.assertEqual(user["username"], lead_payload["username"])
        self.assertEqual(user["crew_name"], "CREW-A")
        self.assertEqual(user["station_name"], "ARTEMIS-BASE-ALPHA")
        self.assertTrue(user["is_lead"])

    def test_02_lead_provisions_crew_members_with_username_and_key(self):
        """Crew Lead provisions crew members using only username and key."""
        unique_id = int(datetime.utcnow().timestamp())
        # 1. Register lead
        lead_res = self.client.post("/api/auth/register-lead", json={
            "username": f"lead_provisioner_{unique_id}",
            "key": "LeadKey2028!",
            "station_name": "GATEWAY-ORBITAL",
            "crew_name": "EXPEDITION-7"
        })
        lead_token = lead_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {lead_token}"}

        # 2. Lead provisions Member A (username + key only)
        member_payload = {
            "username": f"astro_spec_{unique_id}",
            "key": "MemberKey2028!",
            "callsign": "ASTRO-SPEC"
        }
        member_res = self.client.post("/api/auth/crew/members", json=member_payload, headers=headers)
        self.assertEqual(member_res.status_code, 201)
        member_data = member_res.json()
        self.assertEqual(member_data["username"], member_payload["username"])
        self.assertEqual(member_data["crew_name"], "EXPEDITION-7")
        self.assertEqual(member_data["station_name"], "GATEWAY-ORBITAL")
        self.assertFalse(member_data["is_lead"])

        # 3. Verify member can now log in using username and key
        login_res = self.client.post("/api/auth/login", json={
            "username": member_payload["username"],
            "key": member_payload["key"]
        })
        self.assertEqual(login_res.status_code, 200)
        self.assertIn("access_token", login_res.json())

    def test_03_non_lead_cannot_provision_crew_members(self):
        """Regular crew member cannot create/provision other crew members."""
        # dr_chen is a regular crew member in seeded database (is_lead=False)
        login_res = self.client.post("/api/auth/login", json={
            "username": "dr_chen",
            "key": "Key1234!"
        })
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        res = self.client.post("/api/auth/crew/members", json={
            "username": "illegal_member",
            "key": "Key1234!"
        }, headers=headers)
        self.assertEqual(res.status_code, 403)
        self.assertIn("Only the Crew Lead", res.json()["detail"])

    def test_04_strict_crew_isolation_proximity_algorithm(self):
        """
        Verify that when an astronaut from CREW-A is a victim:
        The algorithm selects the closest astronaut from CREW-A,
        and strictly IGNORES astronauts from CREW-B even if they are physically closer (0.1m away)!
        """
        # In our device map:
        # ASTRO-01 is in CREW-A at (-5.8, 1.2, 0)
        # ASTRO-05 (Crew B) is at (-5.9, 1.1, 0) -> distance is 0.14m! Closer than anyone!
        # ASTRO-7702-HELENA is in CREW-A at (-6.0, 1.0, 0) -> distance is 0.28m!
        # The algorithm MUST skip ASTRO-05 because ASTRO-05 is in CREW-B!
        closest = find_closest_astronaut("ASTRO-01", crew_name="CREW-A", db=self.db)

        # Must be from CREW-A!
        self.assertEqual(closest["closest_crew"], "CREW-A")
        self.assertNotEqual(closest["closest_callsign"], "ASTRO-05")  # ASTRO-05 is Crew B!
        self.assertEqual(closest["closest_callsign"], "ASTRO-7702-HELENA")
        self.assertEqual(closest["distance_meters"], 0.3)

        # Conversely, if ASTRO-05 (Crew B) is the victim, it must find someone from Crew B!
        closest_b = find_closest_astronaut("ASTRO-05", crew_name="CREW-B", db=self.db)
        self.assertEqual(closest_b["closest_crew"], "CREW-B")
        self.assertEqual(closest_b["closest_callsign"], "ASTRO-06")

    def test_05_predictor_triggers_alarm_routed_within_crew(self):
        """Verify health predictor agent triggers alarm routed within the astronaut's crew."""
        res = self.client.post("/api/otel/predict?astronaut_id=ASTRO-01&week_number=9&forecast_days=7")
        self.assertEqual(res.status_code, 200)
        pred = res.json()

        self.assertTrue(pred["alarm_triggered"])
        self.assertIsNotNone(pred["alarm_id"])
        alarm_details = pred["alarm_details"]
        self.assertEqual(alarm_details["status"], "PENDING_OWNER")
        self.assertEqual(alarm_details["crew_name"], "CREW-A")
        self.assertGreater(alarm_details["remaining_seconds"], 0)

    def test_06_owner_answers_alarm_in_time(self):
        """Verify owner can answer alarm before timeout window expires."""
        drill_res = self.client.post("/api/emergency/trigger?astronaut_id=ASTRO-01&timeout_seconds=60")
        self.assertEqual(drill_res.status_code, 200)
        alarm = drill_res.json()

        ans_res = self.client.post("/api/emergency/answer-owner", json={
            "alert_id": alarm["alert_id"],
            "notes": "Cmdr. Vance responsive."
        })
        self.assertEqual(ans_res.status_code, 200)
        self.assertTrue(ans_res.json()["success"])
        self.assertEqual(ans_res.json()["alert"]["status"], "ACKNOWLEDGED_BY_OWNER")

    def test_07_dead_man_switch_timeout_switches_to_closest_crew_member(self):
        """
        Verify that on timeout, the alarm switches to the closest member of the SAME CREW.
        """
        now = datetime.utcnow()
        expired_alert_id = f"TEST-TIMEOUT-CREW-{int(now.timestamp())}"
        alert_record = EmergencyAlertModel(
            alert_id=expired_alert_id,
            astronaut_id="ASTRO-01",
            crew_name="CREW-A",
            station_name="LUNAR-BASE-ALPHA",
            severity="CRITICAL",
            hazard_origin="Agent Predictor: Critical Hypercapnia",
            message="Cabin CO2 surge > 5.0 mmHg.",
            suggested_crew_actions=json.dumps(["Inspect LiOH scrubbers"]),
            timestamp=now - timedelta(seconds=120),
            status="PENDING_OWNER",
            timeout_seconds=30,
            timeout_at=now - timedelta(seconds=90),  # expired
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

        status_res = self.client.get(f"/api/emergency/status?astronaut_id=ASTRO-01")
        self.assertEqual(status_res.status_code, 200)
        current_status = status_res.json()
        self.assertEqual(current_status["alert_id"], expired_alert_id)
        self.assertEqual(current_status["status"], "SWITCHED_TO_EMERGENCY_CONTACT")
        # Must have routed to closest astronaut in CREW-A (ASTRO-7702-HELENA), not Crew B!
        self.assertEqual(current_status["emergency_contact_callsign"], "ASTRO-7702-HELENA")
        self.assertIn("CREW-A", current_status["emergency_contact_role"])

        # Closest crew member acknowledges intervention
        contact_ack_res = self.client.post("/api/emergency/contact-ack", json={
            "alert_id": expired_alert_id,
            "contact_callsign": "ASTRO-7702-HELENA",
            "intervention_notes": "Helena reached Vance's quarters and administered O2."
        })
        self.assertEqual(contact_ack_res.status_code, 200)
        self.assertEqual(contact_ack_res.json()["status"], "ACKNOWLEDGED_BY_CONTACT")
        self.assertTrue(contact_ack_res.json()["acknowledged"])

if __name__ == "__main__":
    unittest.main()
