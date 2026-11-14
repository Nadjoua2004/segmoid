/**
 * Aegis-Bio API Client
 * Connects Next.js frontend to the FastAPI + Supabase backend.
 */
import {
  HealthMetrics,
  EmergencyAlert,
  EmergencyAckRequest,
  ChatMessage,
  ProactiveChatPayload,
  TriageResult,
  PredictionResult,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
// Replace or set NEXT_PUBLIC_CHAT_API_URL when connecting an external AstroDoc webhook/endpoint
const CHAT_API_URL = process.env.NEXT_PUBLIC_CHAT_API_URL || `${API_BASE}/api/chat/query`;

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

export interface CrewSummaryItem {
  id: string;
  name: string;
  role: string;
  mission_day: number;
  status: "NORMAL" | "MEDIUM" | "CRITICAL";
  vitals_bars: string[]; // 5 items: HR, SpO2, Sleep, Temp, Dose
  has_telemetry: boolean;
  emergency_contact_callsign: string;
  emergency_contact_name: string;
}

export interface ChatHistoryItem {
  id: number;
  astronaut_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations: string[];
  timestamp: string;
}

export const api = {
  // Crew & Telemetry (Database-backed, empty when no records logged)
  async getActiveCrew(): Promise<{ crew: CrewSummaryItem[]; count: number }> {
    return request<{ crew: CrewSummaryItem[]; count: number }>("/api/metrics/crew");
  },

  async getMetricsHistory(astronautId?: string, limit: number = 100): Promise<any[]> {
    const q = new URLSearchParams();
    if (astronautId) q.set("astronaut_id", astronautId);
    q.set("limit", String(limit));
    return request<any[]>(`/api/metrics/history?${q.toString()}`);
  },

  async getLatestMetrics(astronautId?: string): Promise<any | null> {
    const q = astronautId ? `?astronaut_id=${encodeURIComponent(astronautId)}` : "";
    return request<any | null>(`/api/metrics/latest${q}`);
  },

  async ingestMetrics(payload: HealthMetrics): Promise<any> {
    return request<any>("/api/metrics/ingest", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async registerAstronaut(payload: any): Promise<any> {
    return request<any>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  // Dual-Classifier Triage
  async getCurrentTriage(astronautId?: string): Promise<TriageResult | null> {
    const q = astronautId ? `?astronaut_id=${encodeURIComponent(astronautId)}` : "";
    return request<TriageResult | null>(`/api/triage/current${q}`);
  },

  async classifyMetrics(payload: HealthMetrics): Promise<TriageResult> {
    return request<TriageResult>("/api/triage/classify", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  // Multi-Scale Health Trajectory Forecast (DAILY, WEEKLY, MONTHLY)
  async getTrajectoryForecast(
    astronautId?: string,
    horizonDays?: number,
    timeScale: "DAILY" | "WEEKLY" | "MONTHLY" = "WEEKLY"
  ): Promise<PredictionResult | null> {
    const defaultHorizon = timeScale === "DAILY" ? 24 : timeScale === "MONTHLY" ? 30 : 7;
    const finalHorizon = horizonDays ?? defaultHorizon;
    const q = new URLSearchParams({
      horizon_days: String(finalHorizon),
      time_scale: timeScale,
    });
    if (astronautId) q.set("astronaut_id", astronautId);
    return request<PredictionResult | null>(`/api/predict/trajectory?${q.toString()}`, {
      method: "POST",
    });
  },

  // Alerts & Dead-Man's Switch Escalation
  async getEmergencyStatus(astronautId?: string): Promise<EmergencyAlert | null> {
    const q = astronautId ? `?astronaut_id=${encodeURIComponent(astronautId)}` : "";
    return request<EmergencyAlert | null>(`/api/emergency/status${q}`);
  },

  async getAllAlarms(astronautId?: string): Promise<EmergencyAlert[]> {
    const q = astronautId ? `?astronaut_id=${encodeURIComponent(astronautId)}` : "";
    return request<EmergencyAlert[]>(`/api/emergency/alarms${q}`);
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

  async acknowledgeEmergency(payload: EmergencyAckRequest): Promise<EmergencyAlert> {
    return request<EmergencyAlert>("/api/emergency/ack", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  // Station Crew & Lead Authentication
  async registerLead(payload: { username: string; key: string; station_name: string; crew_name: string }): Promise<any> {
    return request<any>("/api/auth/register-lead", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async loginWithKey(username: string, key: string): Promise<any> {
    return request<any>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, key }),
    });
  },

  async createCrewMember(payload: { username: string; key: string; callsign?: string }, token: string): Promise<any> {
    return request<any>("/api/auth/crew/members", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify(payload),
    });
  },

  async listCrewMembers(token: string): Promise<any[]> {
    return request<any[]>("/api/auth/crew/members", {
      headers: { Authorization: `Bearer ${token}` },
    });
  },

  async getMyProfile(token?: string): Promise<any> {
    return request<any>("/api/auth/me", {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  },

  // AstroDoc AI Flight Surgeon Chat
  async queryFlightSurgeon(query: string, astronautId: string = "CM-1"): Promise<ChatMessage> {
    const response = await fetch(CHAT_API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        astronaut_id: astronautId,
        include_current_vitals: true,
      }),
    });
    if (!response.ok) {
      const errorBody = await response.text();
      throw new Error(`Chat API Error [${response.status}]: ${errorBody}`);
    }
    return response.json();
  },

  async getChatHistory(astronautId?: string): Promise<ChatHistoryItem[]> {
    const q = astronautId ? `?astronaut_id=${encodeURIComponent(astronautId)}` : "";
    return request<ChatHistoryItem[]>(`/api/chat/history${q}`);
  },

  async getProactiveChat(astronautId: string = "CM-1"): Promise<ProactiveChatPayload> {
    return request<ProactiveChatPayload>(`/api/chat/proactive?astronaut_id=${encodeURIComponent(astronautId)}`, {
      method: "POST",
    });
  },
};
