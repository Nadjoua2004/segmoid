"""How the assistant reads astronaut data and raises alerts.

The assistant never computes triage itself. It talks to the rest of AstroDoc
through `AstroDataProvider`. Three ways to plug it in:

* In-process (recommended when the backend lives in the same FastAPI app):
  write a class with these methods that calls your triage / forecast /
  escalation code directly, and pass it to `create_assistant_router(...)`.
* Over HTTP: `HttpDataProvider(base_url)` calls the REST API from SPEC §10.
* Standalone demo: `MockDataProvider()` serves the PART C storyline
  (Sara day 47 Warning, day 120 solar particle event, Tomás day 121).
"""
from __future__ import annotations

import json
import math
import random
import uuid
from datetime import datetime, timezone
from typing import Optional, Protocol, runtime_checkable

from .contracts import (AlertInfo, Astronaut, AstronautContext, Forecast, ForecastPoint, HistoryPoint,
                        LoggedMeasurement, MetricHistory, MetricLevel, RankedRisk, TopFactor, Triage)
from .metrics_meta import METRICS, describe_value
from .paths import EVENTS_DIR


@runtime_checkable
class AstroDataProvider(Protocol):
    def list_crew(self) -> list[Astronaut]: ...
    def get_context(self, astronaut_id: str) -> AstronautContext: ...
    def get_triage(self, astronaut_id: str) -> Triage: ...
    def get_metric_history(self, astronaut_id: str, metric: str, days: int) -> MetricHistory: ...
    def get_forecast(self, astronaut_id: str, target: str, horizon_days: int) -> Forecast: ...
    def log_measurement(self, astronaut_id: str, metric: str, value: Optional[float],
                        note: Optional[str] = None, source: str = "chat") -> LoggedMeasurement: ...
    def raise_alert(self, astronaut_id: str, level: str, reason: str, source: str = "chat") -> AlertInfo:
        """Create an alert the astronaut must acknowledge (starts the dead-man's switch timer)."""
    def trigger_crew_alert(self, astronaut_id: str, reason: str) -> dict:
        """Start the Intra-Crew Escalation Protocol immediately."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# =========================================================== HTTP adapter ===
class HttpDataProvider:
    """Calls the backend REST API (SPEC §10).

    Besides the SPEC endpoints it expects three small additions, listed in
    docs/ASSISTANT_INTEGRATION.md: GET /api/crew, POST /api/measurements,
    POST /api/escalations, POST /api/alerts.
    """

    def __init__(self, base_url: str, timeout: float = 5.0):
        import httpx
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)

    def _get(self, path: str, **params):
        r = self._http.get(path, params={k: v for k, v in params.items() if v is not None})
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict):
        r = self._http.post(path, json=body)
        r.raise_for_status()
        return r.json()

    def list_crew(self) -> list[Astronaut]:
        return [Astronaut(**a) for a in self._get("/api/crew")]

    def get_context(self, astronaut_id: str) -> AstronautContext:
        crew = {a.id: a for a in self.list_crew()}
        triage = self.get_triage(astronaut_id)
        alerts = [AlertInfo(**a) for a in self._get("/api/alerts", astronaut_id=astronaut_id)]
        status = self._get(f"/api/checkin/status/{astronaut_id}").get("status", "Due")
        return AstronautContext(astronaut=crew[astronaut_id], mission_day=triage.mission_day,
                                checkin_status=status, active_alerts=[a for a in alerts if not a.acknowledged])

    def get_triage(self, astronaut_id: str) -> Triage:
        return Triage(**self._get(f"/api/triage/{astronaut_id}"))

    def get_metric_history(self, astronaut_id: str, metric: str, days: int) -> MetricHistory:
        data = self._get(f"/api/metrics/{astronaut_id}/{metric}", last_days=days)
        return MetricHistory(**data)

    def get_forecast(self, astronaut_id: str, target: str, horizon_days: int) -> Forecast:
        path = f"/api/readiness/{astronaut_id}" if target == "readiness" else f"/api/forecast/{astronaut_id}/{target}"
        return Forecast(**self._get(path, horizon=horizon_days))

    def log_measurement(self, astronaut_id, metric, value, note=None, source="chat") -> LoggedMeasurement:
        self._post("/api/measurements", {"astronaut_id": astronaut_id, "metric": metric, "value": value,
                                         "note": note, "source": source})
        return LoggedMeasurement(metric=metric, value=value, note=note, source=source,
                                 label=f"Logged: {describe_value(metric, value, note)}")

    def raise_alert(self, astronaut_id, level, reason, source="chat") -> AlertInfo:
        return AlertInfo(**self._post("/api/alerts", {"astronaut_id": astronaut_id, "level": level,
                                                      "reason": reason, "source": source}))

    def trigger_crew_alert(self, astronaut_id, reason) -> dict:
        return self._post("/api/escalations", {"astronaut_id": astronaut_id, "reason": reason, "source": "chat"})


# ========================================================== Mock provider ===
CREW = [
    Astronaut(id="sara", name="Sara Okafor", role="Commander"),
    Astronaut(id="lin", name="Lin Wei", role="Flight Engineer"),
    Astronaut(id="tomas", name="Tomás Rivera", role="Mission Specialist"),
    Astronaut(id="amina", name="Amina Diallo", role="Mission Specialist / Crew Medical Officer", is_cmo=True),
]

# per-astronaut baseline (mean, sd)
_BASE = {
    "sara": {"hr": (62, 4), "bp_sys": (118, 6), "bp_dia": (76, 4), "spo2": (98, 0.6), "sleep_h": (7.1, 0.4),
             "glucose": (92, 8), "temp_c": (36.7, 0.15), "rad_msv": (0.26, 0.03), "mood": (4, 0.5), "hrv_ms": (58, 5)},
    "lin": {"hr": (66, 4), "bp_sys": (122, 6), "bp_dia": (79, 4), "spo2": (98, 0.6), "sleep_h": (6.9, 0.4),
            "glucose": (95, 8), "temp_c": (36.6, 0.15), "rad_msv": (0.25, 0.03), "mood": (4, 0.5), "hrv_ms": (52, 5)},
    "tomas": {"hr": (58, 4), "bp_sys": (116, 6), "bp_dia": (74, 4), "spo2": (98, 0.6), "sleep_h": (7.3, 0.4),
              "glucose": (90, 8), "temp_c": (36.7, 0.15), "rad_msv": (0.27, 0.03), "mood": (4, 0.5), "hrv_ms": (64, 5)},
    "amina": {"hr": (64, 4), "bp_sys": (114, 6), "bp_dia": (72, 4), "spo2": (98, 0.6), "sleep_h": (7.0, 0.4),
              "glucose": (88, 8), "temp_c": (36.8, 0.15), "rad_msv": (0.24, 0.03), "mood": (4, 0.5), "hrv_ms": (60, 5)},
}
SPE_DAY = 120


def _load_spe_event() -> dict:
    try:
        events = json.loads((EVENTS_DIR / "donki_sep_sample.json").read_text(encoding="utf-8"))
        return events[0]
    except Exception:
        return {"sepID": "2024-05-09T13:59:00-SEP-001", "eventTime": "2024-05-09T13:59Z",
                "link": "https://ccmc.gsfc.nasa.gov/DONKI/view/SEP/30609/-1"}


class MockDataProvider:
    """Deterministic demo data for the PART C storyline. `day` is the current mission day."""

    def __init__(self, day: int = 47, seed: int = 42):
        self.day = day
        self.seed = seed
        self.measurements: list[dict] = []
        self.alerts: dict[str, list[AlertInfo]] = {a.id: [] for a in CREW}
        self.escalations: list[dict] = []
        self.spe = _load_spe_event()

    # ---- helpers
    def _astro(self, astronaut_id: str) -> Astronaut:
        for a in CREW:
            if a.id == astronaut_id:
                return a
        raise KeyError(f"unknown astronaut '{astronaut_id}' (crew: {[a.id for a in CREW]})")

    def _value(self, aid: str, metric: str, day: int) -> float:
        mean, sd = _BASE[aid][metric]
        rng = random.Random(f"{self.seed}-{aid}-{metric}-{day}")
        v = mean + rng.gauss(0, sd * 0.6)
        if metric == "rad_msv":
            v *= 1 + 0.002 * day                       # slowly rising cumulative environment
            if aid == "sara" and 40 <= day <= 47:     # planted scenario: rising dose
                v = mean * (1.2 + (day - 40) * 0.17)
            if day == SPE_DAY:
                v = 38.0 + rng.uniform(-3, 3)         # solar particle event spike
            if day > SPE_DAY:
                v = mean * 1.8 if day <= SPE_DAY + 3 else v
        if aid == "sara" and 40 <= day <= 47:
            k = (day - 40) / 7
            if metric == "sleep_h":
                v = mean - 2.0 * k + rng.uniform(-0.3, 0.3)
            if metric == "hrv_ms":
                v = mean * (1 - 0.25 * k)
        if metric == "mood":
            v = max(1, min(5, round(v)))
        return round(v, 2)

    # ---- protocol
    def list_crew(self) -> list[Astronaut]:
        return list(CREW)

    def get_context(self, astronaut_id: str) -> AstronautContext:
        checkin = "Done"
        if astronaut_id == "tomas" and self.day == SPE_DAY + 1:
            checkin = "Overdue"
        open_alerts = [a for a in self.alerts[astronaut_id] if not a.acknowledged]
        return AstronautContext(astronaut=self._astro(astronaut_id), mission_day=self.day,
                                checkin_status=checkin, active_alerts=open_alerts)

    def get_triage(self, astronaut_id: str) -> Triage:
        a = self._astro(astronaut_id)
        d = self.day
        if d == SPE_DAY:
            dose = self._value(a.id, "rad_msv", d)
            reason = (f"Active solar particle event alert ({self.spe['sepID']}, NASA DONKI). "
                      f"Today's dose {dose:.1f} mSv is far above your mission average of "
                      f"{_BASE[a.id]['rad_msv'][0]:.2f} mSv/day.")
            return Triage(
                astronaut_id=a.id, mission_day=d, level="Critical", timestamp=_now(),
                metric_levels=[MetricLevel(metric="rad_msv", level="Critical", value=dose, unit="mSv", reason=reason)],
                ranked_risks=[
                    RankedRisk(hazard="Radiation", level="Critical", score=96, reason=reason,
                               top_factors=["active SPE alert", f"daily dose {dose:.1f} mSv"]),
                    RankedRisk(hazard="Isolation", level="Nominal", score=20, reason="Sleep and mood in range."),
                    RankedRisk(hazard="Gravity", level="Nominal", score=15, reason="HR and BP in range."),
                    RankedRisk(hazard="Hostile environment", level="Nominal", score=10, reason="SpO2 and temperature in range."),
                    RankedRisk(hazard="Distance", level="Nominal", score=8, reason="Glucose in range."),
                ],
                reasons=[reason],
                top_factors=[TopFactor(feature="spe_alert", label="active SPE alert", importance=0.61),
                             TopFactor(feature="rad_z", label=f"dosimeter {dose:.1f} mSv", importance=0.29)],
                model_probabilities={"Nominal": 0.0, "Warning": 0.04, "Critical": 0.96},
            )
        if a.id == "sara" and 44 <= d <= 47:
            dose, hrv, sleep = (self._value("sara", m, d) for m in ("rad_msv", "hrv_ms", "sleep_h"))
            ratio = dose / _BASE["sara"]["rad_msv"][0]
            hrv_drop = 100 * (1 - hrv / _BASE["sara"]["hrv_ms"][0])
            reasons = [
                f"Dosimeter reading {dose:.2f} mSv today, {ratio:.1f} times your mission average.",
                f"HRV {hrv:.0f} ms, {hrv_drop:.0f}% below your baseline.",
                f"Sleep {sleep:.1f} h with bedtime shifted by more than 2 h on the last 2 nights (irregular).",
            ]
            return Triage(
                astronaut_id=a.id, mission_day=d, level="Warning", timestamp=_now(),
                metric_levels=[
                    MetricLevel(metric="rad_msv", level="Warning", value=dose, unit="mSv", reason=reasons[0]),
                    MetricLevel(metric="hrv_ms", level="Warning", value=hrv, unit="ms", reason=reasons[1]),
                    MetricLevel(metric="sleep_h", level="Warning", value=sleep, unit="h", reason=reasons[2]),
                ],
                ranked_risks=[
                    RankedRisk(hazard="Radiation", level="Warning", score=68, reason=reasons[0],
                               top_factors=[f"dosimeter {ratio:.1f}x average"]),
                    RankedRisk(hazard="Isolation", level="Warning", score=61,
                               reason="Irregular sleep and HRV decline point to fatigue.",
                               top_factors=[f"sleep {sleep:.1f} h", f"HRV -{hrv_drop:.0f}%"]),
                    RankedRisk(hazard="Gravity", level="Nominal", score=22, reason="HR and BP in range."),
                    RankedRisk(hazard="Hostile environment", level="Nominal", score=12, reason="SpO2 and temperature in range."),
                    RankedRisk(hazard="Distance", level="Nominal", score=9, reason="Glucose in range."),
                ],
                reasons=reasons,
                top_factors=[TopFactor(feature="rad_z", label=f"dosimeter {ratio:.1f}x mission average", importance=0.38),
                             TopFactor(feature="sleep_irregularity", label=f"sleep {sleep:.1f} h", importance=0.27),
                             TopFactor(feature="hrv_delta", label=f"HRV -{hrv_drop:.0f}%", importance=0.21)],
                model_probabilities={"Nominal": 0.18, "Warning": 0.71, "Critical": 0.11},
            )
        if d in (SPE_DAY + 1, SPE_DAY + 2):
            dose = self._value(a.id, "rad_msv", d)
            r = f"Radiation still elevated after the solar particle event: {dose:.2f} mSv today."
            return Triage(astronaut_id=a.id, mission_day=d, level="Warning", timestamp=_now(),
                          metric_levels=[MetricLevel(metric="rad_msv", level="Warning", value=dose, unit="mSv", reason=r)],
                          ranked_risks=[RankedRisk(hazard="Radiation", level="Warning", score=58, reason=r)],
                          reasons=[r], model_probabilities={"Nominal": 0.3, "Warning": 0.62, "Critical": 0.08})
        return Triage(astronaut_id=a.id, mission_day=d, level="Nominal", timestamp=_now(),
                      reasons=["All metrics logged and within your baseline range."],
                      ranked_risks=[RankedRisk(hazard=h, level="Nominal", score=s, reason="Within range.")
                                    for h, s in (("Radiation", 18), ("Isolation", 15), ("Gravity", 12),
                                                 ("Hostile environment", 8), ("Distance", 6))],
                      model_probabilities={"Nominal": 0.93, "Warning": 0.06, "Critical": 0.01})

    def get_metric_history(self, astronaut_id: str, metric: str, days: int) -> MetricHistory:
        self._astro(astronaut_id)
        if metric not in METRICS:
            raise ValueError(f"unknown metric '{metric}'")
        days = max(1, min(int(days), 180))
        mean, sd = _BASE[astronaut_id][metric]
        pts = [HistoryPoint(day=d, value=self._value(astronaut_id, metric, d))
               for d in range(max(1, self.day - days + 1), self.day + 1)]
        return MetricHistory(metric=metric, unit=METRICS[metric]["unit"], baseline_mean=mean, baseline_sd=sd, points=pts)

    def get_forecast(self, astronaut_id: str, target: str, horizon_days: int) -> Forecast:
        self._astro(astronaut_id)
        if target == "readiness":
            if astronaut_id == "sara" and 44 <= self.day <= 47:
                start, slope = 78.0, -5.2
            else:
                start, slope = 84.0, -0.1
            pts = [ForecastPoint(day=self.day + i, value=round(start + slope * i, 1),
                                 lower=round(start + slope * i - 2 - i * 0.6, 1),
                                 upper=round(start + slope * i + 2 + i * 0.6, 1))
                   for i in range(1, horizon_days + 1)]
            end = pts[min(4, len(pts) - 1)].value
            dw = next((p.day - self.day for p in pts if p.value < 60), None)
            dc = next((p.day - self.day for p in pts if p.value < 40), None)
            msg = (f"Based on current sleep and radiation trends, your Readiness Index is projected to fall from "
                   f"{start:.0f} to {end:.0f} within 5 days if untreated. This is a projection if current trends "
                   f"continue, not a certainty.") if slope < -1 else \
                  "Readiness Index is projected to stay stable if current trends continue."
            return Forecast(target="readiness", horizon_days=horizon_days, current=start, points=pts,
                            days_until_warning=dw, days_until_critical=dc, message=msg)
        hist = self.get_metric_history(astronaut_id, target, 14)
        xs = [p.day for p in hist.points]
        ys = [p.value for p in hist.points]
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        var = sum((x - mx) ** 2 for x in xs) or 1.0
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var
        resid = math.sqrt(sum((y - (my + slope * (x - mx))) ** 2 for x, y in zip(xs, ys)) / max(1, n - 2))
        meta = METRICS[target]
        pts, dw, dc = [], None, None
        for i in range(1, horizon_days + 1):
            day = self.day + i
            v = my + slope * (day - mx)
            band = resid * (1 + i / 7)
            pts.append(ForecastPoint(day=day, value=round(v, 2), lower=round(v - band, 2), upper=round(v + band, 2)))
            if dw is None and _crosses(meta, v, "warn"):
                dw = i
            if dc is None and _crosses(meta, v, "crit"):
                dc = i
        msg = (f"Projection if current trends continue: {meta['name']} reaches the Warning threshold in {dw} days."
               if dw else f"Projection if current trends continue: {meta['name']} stays out of the Warning range "
                          f"for the next {horizon_days} days.")
        return Forecast(target=target, horizon_days=horizon_days, current=ys[-1], points=pts,
                        days_until_warning=dw, days_until_critical=dc, message=msg)

    def log_measurement(self, astronaut_id, metric, value, note=None, source="chat") -> LoggedMeasurement:
        self._astro(astronaut_id)
        self.measurements.append({"astronaut_id": astronaut_id, "metric": metric, "value": value, "note": note,
                                  "source": source, "mission_day": self.day, "timestamp": _now()})
        return LoggedMeasurement(metric=metric, value=value, note=note, source=source,
                                 label=f"Logged: {describe_value(metric, value, note)}")

    def raise_alert(self, astronaut_id, level, reason, source="chat") -> AlertInfo:
        self._astro(astronaut_id)
        alert = AlertInfo(id=uuid.uuid4().hex[:8], level=level, reason=reason, created_at=_now())
        self.alerts[astronaut_id].append(alert)
        return alert

    def trigger_crew_alert(self, astronaut_id, reason) -> dict:
        affected = self._astro(astronaut_id)
        cmo = next(a for a in CREW if a.is_cmo)
        commander = next(a for a in CREW if a.role == "Commander")
        target = commander if affected.id == cmo.id else cmo
        record = {"id": uuid.uuid4().hex[:8], "affected": affected.id, "notified": target.id,
                  "reason": reason, "created_at": _now(), "source": "chat"}
        self.escalations.append(record)
        return record


def _crosses(meta: dict, v: float, kind: str) -> bool:
    lo, hi = meta.get(f"{kind}_low"), meta.get(f"{kind}_high")
    return (lo is not None and v < lo) or (hi is not None and v > hi)
