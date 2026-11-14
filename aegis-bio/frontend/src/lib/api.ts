/**
 * Aegis-Bio API Client
 * Typed HTTP methods for FastAPI backend communication.
 */
import {
  CrewMember,
  WeeklyTelemetryResponse,
  PredictorResponse,
  HealthMetrics,
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
  // -------------------------------------------------------------
  // OpenTelemetry Weekly Pipeline & Telemetry
  // -------------------------------------------------------------
  async getCrewMembers(): Promise<{ crew: CrewMember[]; count: number }> {
    return request<{ crew: CrewMember[]; count: number }>("/api/otel/crew");
  },

  async getWeeklyTelemetry(astronautId: string = "ASTRO-01", weekNumber: number = 1): Promise<WeeklyTelemetryResponse> {
    return request<WeeklyTelemetryResponse>(`/api/otel/week/${astronautId}/${weekNumber}`);
  },

  async predictUpcomingHealth(astronautId: string = "ASTRO-01", weekNumber: number = 1, forecastDays: number = 7): Promise<PredictorResponse> {
    return request<PredictorResponse>(`/api/otel/predict?astronaut_id=${astronautId}&week_number=${weekNumber}&forecast_days=${forecastDays}`, {
      method: "POST",
    });
  },

  // -------------------------------------------------------------
  // Emergency Protocol & RAG Agent
  // -------------------------------------------------------------
  async getEmergencyStatus(astronautId: string = "ASTRO-01"): Promise<EmergencyAlert | null> {
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

  async answerAlarmAsOwner(alertId: string, notes?: string): Promise<{ success: boolean; message: string; alert: EmergencyAlert }> {
    return request<{ success: boolean; message: string; alert: EmergencyAlert }>("/api/emergency/answer-owner", {
      method: "POST",
      body: JSON.stringify({ alert_id: alertId, notes }),
    });
  },

  async acknowledgeAsEmergencyContact(alertId: string, contactCallsign: string, interventionNotes?: string): Promise<EmergencyAlert> {
    return request<EmergencyAlert>("/api/emergency/contact-ack", {
      method: "POST",
      body: JSON.stringify({
        alert_id: alertId,
        contact_callsign: contactCallsign,
        intervention_notes: interventionNotes,
      }),
    });
  },

  async checkEmergencyTimeout(): Promise<EmergencyAlert[]> {
    return request<EmergencyAlert[]>("/api/emergency/check-timeout", {
      method: "POST",
    });
  },

  // -------------------------------------------------------------
  // Astronaut Authentication & Emergency Contact Settings
  // -------------------------------------------------------------
  async loginAstronaut(usernameOrEmail: string, password: string): Promise<any> {
    return request<any>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username_or_email: usernameOrEmail, password }),
    });
  },

  async registerAstronaut(payload: any): Promise<any> {
    return request<any>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async getMyProfile(token?: string): Promise<any> {
    return request<any>("/api/auth/me", {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  },

  async getAvailableCrewContacts(): Promise<{ contacts: any[]; count: number }> {
    return request<{ contacts: any[]; count: number }>("/api/auth/crew-contacts");
  },

  async queryFlightSurgeon(query: string, astronautId: string = "ASTRO-01"): Promise<ChatMessage> {
    return request<ChatMessage>("/api/chat/query", {
      method: "POST",
      body: JSON.stringify({
        query,
        astronaut_id: astronautId,
        include_current_vitals: true,
      }),
    });
  },

  async getProactiveChat(astronautId: string = "ASTRO-01"): Promise<ProactiveChatPayload> {
    return request<ProactiveChatPayload>(`/api/chat/proactive?astronaut_id=${astronautId}`, {
      method: "POST",
    });
  },

  async ingestMetrics(payload: HealthMetrics): Promise<any> {
    return request<any>("/api/metrics/ingest", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};
