"""
OpenTelemetry (OTEL) Collector & Controller Service
Structures spaceflight physiological & environmental metrics according to the
OpenTelemetry Metric Data Model (OTLP/HTTP v1 format).
"""
import time
from datetime import datetime
from typing import Dict, List, Any, Optional

class OpenTelemetryCollector:
    """
    OpenTelemetry Metrics Controller for Deep-Space Biometric & Environmental Streams.
    Provides standard ResourceMetrics, ScopeMetrics, and Metric DataPoints.
    """

    def __init__(self, service_name: str = "aegis-bio-spacecraft-collector"):
        self.service_name = service_name
        self.ingested_spans_count = 0
        self.last_ingest_time = datetime.utcnow()

    def build_resource(self, astronaut_id: str, spacecraft_id: str = "ARTEMIS-GATEWAY-LUNAR-ALPHA") -> Dict[str, Any]:
        return {
            "attributes": [
                {"key": "service.name", "value": {"stringValue": self.service_name}},
                {"key": "service.version", "value": {"stringValue": "2.4.0"}},
                {"key": "astronaut.id", "value": {"stringValue": astronaut_id}},
                {"key": "spacecraft.id", "value": {"stringValue": spacecraft_id}},
                {"key": "spacecraft.subsystem", "value": {"stringValue": "ECLSS-CREW-TELEMETRY"}},
                {"key": "telemetry.sdk.language", "value": {"stringValue": "python"}},
                {"key": "telemetry.sdk.name", "value": {"stringValue": "opentelemetry"}},
            ]
        }

    def format_otel_metrics(self, weekly_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Converts the weekly telemetry into OpenTelemetry ResourceMetrics format.
        """
        astro = weekly_data.get("astronaut", {})
        hourly = weekly_data.get("hourly_vitals", [])
        env = weekly_data.get("ship_environment", [])
        astronaut_id = astro.get("id", "ASTRO-01")

        resource = self.build_resource(astronaut_id)

        # Build Scope Metrics
        metrics_list = []

        # 1. Gauge: astronaut.heart_rate (BPM)
        hr_datapoints = []
        for pt in hourly[-24:]:  # Most recent 24 OTEL datapoints
            if pt.get("heart_rate") is not None:
                hr_datapoints.append({
                    "timeUnixNano": int(time.time() * 1e9),
                    "asDouble": float(pt["heart_rate"]),
                    "attributes": [
                        {"key": "sol", "value": {"intValue": pt["sol"]}},
                        {"key": "hour", "value": {"intValue": pt["hour"]}},
                        {"key": "activity", "value": {"stringValue": pt["activity"]}},
                    ]
                })

        metrics_list.append({
            "name": "astronaut.heart_rate",
            "description": "Continuous resting/active heart rate via biosensor array",
            "unit": "{beats}/min",
            "gauge": {"dataPoints": hr_datapoints}
        })

        # 2. Gauge: spacecraft.cabin_co2 (mmHg)
        co2_datapoints = []
        for pt in env[-24:]:
            co2_datapoints.append({
                "timeUnixNano": int(time.time() * 1e9),
                "asDouble": float(pt["cabin_co2"]),
                "attributes": [
                    {"key": "sol", "value": {"intValue": pt["sol"]}},
                    {"key": "sensor_location", "value": {"stringValue": "HAB_MODULE_1_ECLSS"}},
                ]
            })

        metrics_list.append({
            "name": "spacecraft.cabin_co2",
            "description": "Habitat ambient carbon dioxide partial pressure",
            "unit": "mm[Hg]",
            "gauge": {"dataPoints": co2_datapoints}
        })

        # 3. Gauge: spacecraft.radiation_flux (uSv/h)
        rad_datapoints = []
        for pt in env[-24:]:
            rad_datapoints.append({
                "timeUnixNano": int(time.time() * 1e9),
                "asDouble": float(pt["radiation_rate_usv"]),
                "attributes": [
                    {"key": "sol", "value": {"intValue": pt["sol"]}},
                    {"key": "dosimeter_type", "value": {"stringValue": "SILICON_DETECTOR_ARRAY"}},
                ]
            })

        metrics_list.append({
            "name": "spacecraft.radiation_flux",
            "description": "Ambient ionizing radiation dose rate in microSieverts per hour",
            "unit": "uSv/h",
            "gauge": {"dataPoints": rad_datapoints}
        })

        # 4. Gauge: astronaut.spo2 (%)
        spo2_datapoints = []
        for pt in env[-24:]:
            if pt.get("spo2") is not None:
                spo2_datapoints.append({
                    "timeUnixNano": int(time.time() * 1e9),
                    "asDouble": float(pt["spo2"]),
                    "attributes": [
                        {"key": "sol", "value": {"intValue": pt["sol"]}},
                    ]
                })

        metrics_list.append({
            "name": "astronaut.spo2",
            "description": "Arterial blood oxygen saturation",
            "unit": "%",
            "gauge": {"dataPoints": spo2_datapoints}
        })

        self.ingested_spans_count += len(hourly)
        self.last_ingest_time = datetime.utcnow()

        return {
            "resourceMetrics": [
                {
                    "resource": resource,
                    "scopeMetrics": [
                        {
                            "scope": {
                                "name": "aegis.bio.telemetry.collector",
                                "version": "1.2.0"
                            },
                            "metrics": metrics_list
                        }
                    ]
                }
            ],
            "collector_status": {
                "active": True,
                "protocol": "OTLP/HTTP v1.1",
                "total_spans_processed": self.ingested_spans_count,
                "last_sync": self.last_ingest_time.isoformat() + "Z",
                "connected_subsystems": ["ECLSS", "BIOSENSORS", "HABITAT_LIFE_SUPPORT"]
            }
        }

otel_collector = OpenTelemetryCollector()
