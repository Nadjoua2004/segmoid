/**
 * Aegis-Bio API Client
 * Typed HTTP methods for FastAPI backend communication with fallback resilience.
 */
import {
  HealthMetrics,
  HealthMetricsResponse,
  TriageResult,
  PredictionResult,
  EmergencyAlert,
  EmergencyAckRequest,
  ChatMessage,
  ProactiveChatPayload,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(`API Error [${response.status}] ${endpoint}: ${errorBody}`);
  }

  return response.json();
}

export const api = {
  // Telemetry Metrics
  async getMetricsHistory(astronautId = "ASTRO-7702-HELENA", limit = 30): Promise<HealthMetricsResponse[]> {
    return request<HealthMetricsResponse[]>(`/api/metrics/history?astronaut_id=${astronautId}&limit=${limit}`);
  },

  async getLatestMetrics(astronautId = "ASTRO-7702-HELENA"): Promise<HealthMetricsResponse> {
    return request<HealthMetricsResponse>(`/api/metrics/latest?astronaut_id=${astronautId}`);
  },

  async ingestMetrics(payload: HealthMetrics): Promise<HealthMetricsResponse> {
    return request<HealthMetricsResponse>("/api/metrics/ingest", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  // Triage & Spaceflight Hazard Classification
  async getCurrentTriage(astronautId = "ASTRO-7702-HELENA"): Promise<TriageResult> {
    return request<TriageResult>(`/api/triage/current?astronaut_id=${astronautId}`);
  },

  async classifyTriage(metrics: HealthMetrics): Promise<TriageResult> {
    return request<TriageResult>("/api/triage/classify", {
      method: "POST",
      body: JSON.stringify(metrics),
    });
  },

  // 7-Day Trajectory Forecasting
  async getPredictedTrajectory(astronautId = "ASTRO-7702-HELENA", horizonDays = 7): Promise<PredictionResult> {
    return request<PredictionResult>(`/api/predict/trajectory?astronaut_id=${astronautId}&horizon_days=${horizonDays}`, {
      method: "POST",
    });
  },

  // Intra-Crew Emergency Protocol
  async getEmergencyStatus(astronautId = "ASTRO-7702-HELENA"): Promise<EmergencyAlert | null> {
    return request<EmergencyAlert | null>(`/api/emergency/status?astronaut_id=${astronautId}`);
  },

  async acknowledgeEmergency(payload: EmergencyAckRequest): Promise<EmergencyAlert> {
    return request<EmergencyAlert>("/api/emergency/ack", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async triggerEmergencyDrill(): Promise<EmergencyAlert> {
    return request<EmergencyAlert>("/api/emergency/trigger", {
      method: "POST",
    });
  },

  // AI Clinical Flight Surgeon
  async queryFlightSurgeon(query: string, astronautId = "ASTRO-7702-HELENA"): Promise<ChatMessage> {
    return request<ChatMessage>("/api/chat/query", {
      method: "POST",
      body: JSON.stringify({
        query,
        astronaut_id: astronautId,
        include_current_vitals: true,
      }),
    });
  },

  async getProactiveChat(astronautId = "ASTRO-7702-HELENA"): Promise<ProactiveChatPayload> {
    return request<ProactiveChatPayload>(`/api/chat/proactive?astronaut_id=${astronautId}`, {
      method: "POST",
    });
  },
};
