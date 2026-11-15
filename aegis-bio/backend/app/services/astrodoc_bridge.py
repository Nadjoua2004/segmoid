"""
Bridge between Aegis-Bio and the AstroDoc AI chatbot (astrodoc/backend).

* Loads the AstroDoc package under its own name (`astrodoc_app`) so it never
  clashes with this backend's `app` package, and reads astrodoc/backend/.env
  (Groq / Hugging Face keys) without overriding variables already set.
* `AegisDataProvider` gives the chatbot this backend's real data: telemetry
  logs, the dual-classifier triage, and the emergency alarm system
  (dead-man's switch + escalation to the closest crewmate).

Override the AstroDoc location with ASTRODOC_BACKEND_DIR if the folders move.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Optional

ASTRODOC_BACKEND = Path(os.getenv("ASTRODOC_BACKEND_DIR",
                                  Path(__file__).resolve().parents[4] / "astrodoc" / "backend"))
PKG = "astrodoc_app"

# Aegis telemetry column -> AstroDoc metric id
COLUMN_TO_METRIC = {
    "heart_rate": "hr", "bp_sys": "bp_sys", "bp_dia": "bp_dia", "spo2": "spo2", "sleep_hours": "sleep_h",
    "radiation_msv": "rad_msv", "blood_glucose": "glucose", "mood_score": "mood", "core_temp_c": "temp_c",
    "hrv_rmssd": "hrv_ms", "cabin_co2_mmhg": "cabin_co2",
}
METRIC_TO_COLUMN = {v: k for k, v in COLUMN_TO_METRIC.items()}
STATUS_TO_LEVEL = {"NORMAL": "Nominal", "MEDIUM": "Warning", "CRITICAL": "Critical"}
HAZARD_FIELDS = [("radiation_score", "Radiation"), ("microgravity_score", "Gravity"),
                 ("isolation_score", "Isolation"), ("distance_score", "Distance"),
                 ("hostile_env_score", "Hostile environment")]


def load_astrodoc():
    """Import astrodoc/backend/app as the package `astrodoc_app` (idempotent)."""
    if PKG in sys.modules:
        return sys.modules[PKG]
    init = ASTRODOC_BACKEND / "app" / "__init__.py"
    if not init.is_file():
        raise ImportError(f"AstroDoc not found at {ASTRODOC_BACKEND}")
    try:
        from dotenv import load_dotenv
        load_dotenv(ASTRODOC_BACKEND / ".env", override=False)
    except ImportError:
        pass
    spec = importlib.util.spec_from_file_location(PKG, init, submodule_search_locations=[str(init.parent)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[PKG] = module
    spec.loader.exec_module(module)
    return module


def build_astrodoc_assistant():
    """The AstroDoc assistant wired to this backend's database."""
    load_astrodoc()
    from astrodoc_app.assistant.chain import AstroDocAssistant
    return AstroDocAssistant(AegisDataProvider())


def create_astrodoc_router(bot, prefix: str = "/api/astrodoc"):
    """AstroDoc's full API (chat with cards/chips/red flags, voice, greeting) under /api/astrodoc."""
    from astrodoc_app.assistant.router import create_assistant_router
    return create_assistant_router(bot.provider, bot, prefix=prefix)


class AegisDataProvider:
    """Implements AstroDoc's AstroDataProvider protocol over the Aegis-Bio SQLite database."""

    def __init__(self):
        load_astrodoc()
        from astrodoc_app.assistant import contracts as c
        from astrodoc_app.assistant.metrics_meta import METRICS, describe_value
        self.c, self.METRICS, self.describe_value = c, METRICS, describe_value

    # ------------------------------------------------------------ helpers ---
    @staticmethod
    def _db():
        from app.database import SessionLocal
        return SessionLocal()

    @staticmethod
    def _logs(db, astronaut_id: str):
        from app.models import TelemetryLog
        return (db.query(TelemetryLog).filter(TelemetryLog.astronaut_id == astronaut_id)
                .order_by(TelemetryLog.mission_day.asc(), TelemetryLog.id.asc()).all())

    @staticmethod
    def _latest(db, astronaut_id: str):
        from app.models import TelemetryLog
        return (db.query(TelemetryLog).filter(TelemetryLog.astronaut_id == astronaut_id)
                .order_by(TelemetryLog.mission_day.desc(), TelemetryLog.id.desc()).first())

    @staticmethod
    def _user(db, astronaut_id: str):
        from app.models import UserModel
        return db.query(UserModel).filter(
            (UserModel.callsign == astronaut_id) | (UserModel.username == astronaut_id)).first()

    def _astronaut(self, db, astronaut_id: str):
        user = self._user(db, astronaut_id)
        name = (user.callsign or user.username) if user else astronaut_id
        role = "Crew Lead" if (user and user.is_lead) else "Crew Member"
        return self.c.Astronaut(id=astronaut_id, name=name, role=role)

    # ----------------------------------------------------------- protocol ---
    def list_crew(self):
        db = self._db()
        try:
            from app.models import TelemetryLog, UserModel
            ids = {r[0] for r in db.query(TelemetryLog.astronaut_id).distinct()}
            ids |= {u.callsign or u.username for u in db.query(UserModel).all()}
            return [self._astronaut(db, i) for i in sorted(i for i in ids if i)]
        except Exception:          # tables not created yet at import time
            return []
        finally:
            db.close()

    def get_context(self, astronaut_id: str):
        from app.config import settings
        from app.models import EmergencyAlertModel
        db = self._db()
        try:
            latest = self._latest(db, astronaut_id)
            alerts = (db.query(EmergencyAlertModel)
                      .filter(EmergencyAlertModel.astronaut_id == astronaut_id,
                              EmergencyAlertModel.acknowledged == False,  # noqa: E712
                              EmergencyAlertModel.status.in_(["PENDING_OWNER", "SWITCHED_TO_EMERGENCY_CONTACT"]))
                      .order_by(EmergencyAlertModel.timestamp.desc()).limit(5).all())
            return self.c.AstronautContext(
                astronaut=self._astronaut(db, astronaut_id),
                mission_day=latest.mission_day if latest else settings.MISSION_DAY,
                checkin_status="Done" if latest else "Due",
                active_alerts=[self.c.AlertInfo(
                    id=a.alert_id, level="Critical" if "CRITICAL" in (a.severity or "") else "Warning",
                    reason=a.message, acknowledged=False,
                    created_at=a.timestamp.isoformat() if a.timestamp else None) for a in alerts])
        finally:
            db.close()

    def get_triage(self, astronaut_id: str):
        from app.api.triage import evaluate_multi_hazard_triage
        from app.services.telemetry_metrics import health_metrics_from_log
        c = self.c
        db = self._db()
        try:
            latest = self._latest(db, astronaut_id)
            if latest is None:
                return c.Triage(astronaut_id=astronaut_id, mission_day=1, level="Nominal",
                                reasons=["No telemetry has been logged for this astronaut yet."])
            # real values only: CO2 comes from the linked check-in, unmeasured values stay empty
            result = evaluate_multi_hazard_triage(health_metrics_from_log(db, latest))
        finally:
            db.close()

        status = result.overall_status
        level = "Critical" if (status == "CRITICAL" or result.requires_emergency_escalation) else \
            "Warning" if status in ("ELEVATED", "HIGH") else "Nominal"

        metric_levels, factors = [], []
        for col, ev in (result.metric_evaluations or {}).items():
            metric = COLUMN_TO_METRIC.get(col, col)
            lv = STATUS_TO_LEVEL.get(ev.status, "Nominal")
            reason = ev.clinical_note or f"{ev.label} {ev.value:g} {ev.unit} ({ev.deviation})"
            if ev.nominal_range:   # the real range, so the AI never has to guess a threshold
                reason += f" Normal range for this crew's environment: {ev.nominal_range}."
            metric_levels.append(c.MetricLevel(metric=metric, level=lv, value=ev.value, unit=ev.unit, reason=reason))
            if lv != "Nominal":
                factors.append(c.TopFactor(feature=col, label=f"{ev.label} {ev.value:g} {ev.unit}",
                                           importance=1.0 if lv == "Critical" else 0.5))

        risks = []
        for field, hazard in HAZARD_FIELDS:
            score = float(getattr(result.hazards, field))
            hz_metric_levels = [m.level for m in metric_levels
                                if self.METRICS.get(m.metric, {}).get("hazard") == hazard]
            by_score = "Critical" if score >= 80 else "Warning" if score >= 50 else "Nominal"
            hz_level = c.worst(by_score, *hz_metric_levels)
            if c.LEVEL_RANK[hz_level] > c.LEVEL_RANK[level]:   # never exceed the overall triage level
                hz_level = level
            flagged = [m.reason for m in metric_levels if m.level != "Nominal"
                       and self.METRICS.get(m.metric, {}).get("hazard") == hazard]
            risks.append(c.RankedRisk(hazard=hazard, level=hz_level, score=round(score, 1),
                                      reason=" ".join(flagged) or f"{hazard} risk score {score:.0f}/100."))
        risks.sort(key=lambda r: -r.score)

        reasons = list(result.clinical_flags) + [
            f"Aegis-Bio triage status {status} (risk {result.overall_risk_score:.0f}/100)."]
        return c.Triage(astronaut_id=astronaut_id, mission_day=result.mission_day, level=level,
                        metric_levels=metric_levels, ranked_risks=risks, reasons=reasons,
                        top_factors=factors[:5], timestamp=result.evaluated_at.isoformat())

    def _daily(self, astronaut_id: str, column: str) -> list[tuple[int, float]]:
        db = self._db()
        try:
            per_day: dict[int, list[float]] = {}
            for row in self._logs(db, astronaut_id):
                v = getattr(row, column, None)
                if v is not None:
                    per_day.setdefault(row.mission_day, []).append(float(v))
            return [(d, round(mean(vs), 2)) for d, vs in sorted(per_day.items())]
        finally:
            db.close()

    def get_metric_history(self, astronaut_id: str, metric: str, days: int):
        column = METRIC_TO_COLUMN.get(metric)
        if column is None:
            raise ValueError(f"metric '{metric}' is not recorded by Aegis-Bio")
        series = self._daily(astronaut_id, column)
        base = [v for _, v in series[:14]]
        recent = series[-max(1, min(int(days), 180)):]
        return self.c.MetricHistory(
            metric=metric, unit=self.METRICS[metric]["unit"],
            baseline_mean=round(mean(base), 2) if base else None,
            baseline_sd=round(pstdev(base), 2) if len(base) > 1 else None,
            points=[self.c.HistoryPoint(day=d, value=v) for d, v in recent])

    def _readiness_series(self, astronaut_id: str) -> list[tuple[int, float]]:
        """Readiness Index 0-100 = 35% sleep (8 h = full) + 25% mood + 20% HRV (60 ms = full)
        + 20% radiation (0 mSv = full, 2 mSv/day or more = 0)."""
        sleep = dict(self._daily(astronaut_id, "sleep_hours"))
        mood = dict(self._daily(astronaut_id, "mood_score"))
        hrv = dict(self._daily(astronaut_id, "hrv_rmssd"))
        rad = dict(self._daily(astronaut_id, "radiation_msv"))
        out = []
        for d in sorted(sleep):
            score = (0.35 * min(sleep[d] / 8, 1) + 0.25 * (mood.get(d, 3) - 1) / 4
                     + 0.20 * min(hrv.get(d, 42) / 60, 1) + 0.20 * max(0.0, 1 - rad.get(d, 0) / 2))
            out.append((d, round(100 * score, 1)))
        return out

    def get_forecast(self, astronaut_id: str, target: str, horizon_days: int):
        c = self.c
        if target == "readiness":
            series, warn = self._readiness_series(astronaut_id), {"warn_low": 60, "crit_low": 40}
            name = "Readiness Index"
        else:
            column = METRIC_TO_COLUMN.get(target)
            if column is None:
                raise ValueError(f"metric '{target}' is not recorded by Aegis-Bio")
            series, warn, name = self._daily(astronaut_id, column), self.METRICS[target], self.METRICS[target]["name"]
        series = series[-14:]
        if len(series) < 2:
            return c.Forecast(target=target, horizon_days=horizon_days,
                              current=series[-1][1] if series else None,
                              message="Not enough history yet to project a trend.")
        xs, ys = [d for d, _ in series], [v for _, v in series]
        mx, my = mean(xs), mean(ys)
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sum((x - mx) ** 2 for x in xs) or 1)
        resid = math.sqrt(sum((y - (my + slope * (x - mx))) ** 2 for x, y in zip(xs, ys)) / max(1, len(xs) - 2))
        last = xs[-1]
        points, dw, dc = [], None, None
        for i in range(1, horizon_days + 1):
            v = my + slope * (last + i - mx)
            band = resid * (1 + i / 7)
            points.append(c.ForecastPoint(day=last + i, value=round(v, 2), lower=round(v - band, 2),
                                          upper=round(v + band, 2)))
            if dw is None and _crosses(warn, v, "warn"):
                dw = i
            if dc is None and _crosses(warn, v, "crit"):
                dc = i
        end = points[min(4, len(points) - 1)].value
        msg = (f"Projection if current trends continue: {name} goes from {ys[-1]:g} to {end:g} within "
               f"{min(5, horizon_days)} days" + (f", reaching the Warning range in {dw} days." if dw else ".")
               + " This is a projection, not a certainty.")
        return c.Forecast(target=target, horizon_days=horizon_days, current=ys[-1], points=points,
                          days_until_warning=dw, days_until_critical=dc, message=msg)

    def log_measurement(self, astronaut_id, metric, value, note=None, source="chat"):
        """Values from chat are appended to the latest telemetry log's subjective notes."""
        label = f"Logged: {self.describe_value(metric, value, note)}"
        db = self._db()
        try:
            latest = self._latest(db, astronaut_id)
            if latest is not None:
                stamp = datetime.utcnow().strftime("%H:%M")
                latest.subjective_notes = ((latest.subjective_notes or "") +
                                           f"\n[AstroDoc chat {stamp}] {label[len('Logged: '):]}").strip()
                db.commit()
        finally:
            db.close()
        return self.c.LoggedMeasurement(metric=metric, value=value, note=note, source=source, label=label)

    def raise_alert(self, astronaut_id, level, reason, source="chat"):
        """Creates an alarm in the Aegis-Bio dead-man's switch (owner must acknowledge before timeout)."""
        from app.models import EmergencyAlertModel
        from app.services.alarm_service import get_initial_emergency_contact, sync_to_supabase_escalation
        db = self._db()
        try:
            existing = (db.query(EmergencyAlertModel)
                        .filter(EmergencyAlertModel.astronaut_id == astronaut_id,
                                EmergencyAlertModel.acknowledged == False,  # noqa: E712
                                EmergencyAlertModel.status == "PENDING_OWNER")
                        .order_by(EmergencyAlertModel.timestamp.desc()).first())
            alert = existing or self._new_alert(db, astronaut_id, level, reason, get_initial_emergency_contact)
            if not existing:
                try:
                    sync_to_supabase_escalation(astro_id=astronaut_id, state="PENDING_ACK",
                                                recipient_crew_id=alert.emergency_contact_callsign,
                                                countdown_seconds=alert.timeout_seconds, reason=reason)
                except Exception:
                    pass
            return self.c.AlertInfo(id=alert.alert_id, level=level, reason=alert.message, acknowledged=False,
                                    created_at=alert.timestamp.isoformat())
        finally:
            db.close()

    @staticmethod
    def _new_alert(db, astronaut_id, level, reason, get_contact):
        from app.models import EmergencyAlertModel
        contact = get_contact(db, astronaut_id)
        timeout = int(contact["alert_timeout_seconds"])
        now = datetime.utcnow()
        alert = EmergencyAlertModel(
            alert_id=f"ASTRODOC-{astronaut_id}-{int(now.timestamp())}", astronaut_id=astronaut_id,
            user_id=contact.get("user_id"), severity="CRITICAL" if level == "Critical" else "WARNING",
            hazard_origin="AstroDoc AI: astronaut chat", message=reason,
            suggested_crew_actions=json.dumps(["Go to the astronaut now", "Check vitals: HR, BP, SpO2",
                                               "Follow the onboard emergency medical checklist"]),
            timestamp=now, acknowledged=False, owner_answered=False, status="PENDING_OWNER",
            timeout_seconds=timeout, timeout_at=now + timedelta(seconds=timeout),
            emergency_contact_name=contact["emergency_contact_name"],
            emergency_contact_callsign=contact["emergency_contact_callsign"],
            emergency_contact_email=contact.get("emergency_contact_email"),
            emergency_contact_phone=contact.get("emergency_contact_phone"),
            emergency_contact_role=contact["emergency_contact_role"],
            source="ASTRODOC_CHAT", requires_action=True)
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert

    def trigger_crew_alert(self, astronaut_id, reason) -> dict[str, Any]:
        """Escalates now: the alarm is switched to the closest crewmate (Intra-Crew Escalation Protocol)."""
        from app.models import EmergencyAlertModel
        from app.services.alarm_service import check_and_escalate_alarms
        alert_info = self.raise_alert(astronaut_id, "Critical", reason)
        db = self._db()
        try:
            alert = db.query(EmergencyAlertModel).filter(EmergencyAlertModel.alert_id == alert_info.id).first()
            alert.timeout_at = datetime.utcnow() - timedelta(seconds=1)   # expire the owner window now
            db.commit()
            check_and_escalate_alarms(db)
            db.refresh(alert)
            return {"id": alert.alert_id, "affected": astronaut_id, "notified": alert.emergency_contact_callsign,
                    "notified_name": alert.emergency_contact_name, "status": alert.status, "reason": reason}
        finally:
            db.close()


def _crosses(meta: dict, v: float, kind: str) -> bool:
    lo, hi = meta.get(f"{kind}_low"), meta.get(f"{kind}_high")
    return (lo is not None and v < lo) or (hi is not None and v > hi)
