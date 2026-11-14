"use client";

import React, { useState, useEffect, useCallback } from "react";
import { api, CrewSummaryItem, ChatHistoryItem } from "@/lib/api";
import {
  HealthMetrics,
  EmergencyAlert,
  TriageResult,
  PredictionResult,
} from "@/lib/types";

type ScreenId = "overview" | "daily-checkin" | "crew" | "hazards" | "alerts" | "thresholds";

const SCREEN_META: Record<ScreenId, { section: string; title: string }> = {
  overview: { section: "Dashboards", title: "Overview" },
  "daily-checkin": { section: "Dashboards", title: "Daily Check-in" },
  crew: { section: "Dashboards", title: "Crew" },
  hazards: { section: "Dashboards", title: "Space Hazards" },
  alerts: { section: "Clinical", title: "Alerts" },
  thresholds: { section: "Mission", title: "Thresholds" },
};

const AVATAR_BG = ["#A5B4FC", "#A8C5DA", "#7DD3FC", "#E9A8F2", "#96E2D6"];

function getInitials(nameOrId: string): string {
  const cleaned = nameOrId.replace(/^(Cmdr\.|Dr\.|Eng\.|Spec\.|CM-\d+\s*)/i, "").trim();
  const parts = cleaned.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return cleaned.slice(0, 2).toUpperCase() || "CM";
}

function buildSvgPath(
  values: number[],
  minVal: number,
  maxVal: number,
  width = 600,
  height = 200
): string {
  if (values.length === 0) return "";
  if (values.length === 1) {
    const y = height - ((values[0] - minVal) / Math.max(1, maxVal - minVal)) * (height - 40) - 20;
    return `M0,${y.toFixed(1)} L${width},${y.toFixed(1)}`;
  }
  const range = Math.max(0.1, maxVal - minVal);
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * width;
    const clamped = Math.max(minVal, Math.min(maxVal, v));
    const y = height - ((clamped - minVal) / range) * (height - 40) - 20;
    return [x, y] as [number, number];
  });
  return pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
}

export default function AegisBioApp() {
  const [activeScreen, setActiveScreen] = useState<ScreenId>("overview");
  const [selectedAstroId, setSelectedAstroId] = useState<string>("");
  const [showLeftNav, setShowLeftNav] = useState<boolean>(true);
  const [showRightPanel, setShowRightPanel] = useState<boolean>(true);
  const [chartMetric, setChartMetric] = useState<"spo2" | "heart_rate" | "sleep">("spo2");

  // Floating Chatbot Dialog State
  const [isChatOpen, setIsChatOpen] = useState<boolean>(false);
  const [isChatExpanded, setIsChatExpanded] = useState<boolean>(false);
  const [chatInput, setChatInput] = useState<string>("");
  const [isSendingChat, setIsSendingChat] = useState<boolean>(false);
  const [chatError, setChatError] = useState<string>("");

  // Live Database State (Starts empty when database is empty)
  const [crew, setCrew] = useState<CrewSummaryItem[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [latestMetrics, setLatestMetrics] = useState<any | null>(null);
  const [triage, setTriage] = useState<TriageResult | null>(null);
  const [forecast, setForecast] = useState<PredictionResult | null>(null);
  const [activeAlert, setActiveAlert] = useState<EmergencyAlert | null>(null);
  const [allAlarms, setAllAlarms] = useState<EmergencyAlert[]>([]);
  const [chatHistory, setChatHistory] = useState<ChatHistoryItem[]>([]);

  // Time Scale State: DAILY (24h), WEEKLY (7d), MONTHLY (30d)
  const [timeScale, setTimeScale] = useState<"DAILY" | "WEEKLY" | "MONTHLY">("WEEKLY");
  const [isLoadingForecast, setIsLoadingForecast] = useState<boolean>(false);

  // Crew Lead Authentication & Provisioning State
  const [crewSubTab, setCrewSubTab] = useState<"roster" | "lead-provision">("roster");
  const [leadToken, setLeadToken] = useState<string>("");
  const [leadProfile, setLeadProfile] = useState<{
    username: string;
    station_name: string;
    crew_name: string;
    callsign: string;
    is_lead: boolean;
  } | null>(null);
  const [leadAuthMode, setLeadAuthMode] = useState<"login" | "register">("login");
  const [leadLoginForm, setLeadLoginForm] = useState({ username: "commander_alpha", key: "station_alpha_key" });
  const [leadRegisterForm, setLeadRegisterForm] = useState({
    username: "commander_alpha",
    key: "station_alpha_key",
    station_name: "Hermes Alpha Station",
    crew_name: "Crew-Alpha",
  });
  const [provisionMemberForm, setProvisionMemberForm] = useState({
    username: "astro_01",
    key: "astro_01_key",
    callsign: "ASTRO-01",
  });
  const [leadFeedback, setLeadFeedback] = useState<string>("");

  // Unified Daily Check-in Form State (Single Screen, No Tabs)
  const [checkInForm, setCheckInForm] = useState<HealthMetrics>({
    astronaut_id: "CM-1 Ibarra",
    mission_day: 1,
    heart_rate: 72,
    bp_sys: 118,
    bp_dia: 76,
    spo2: 97.5,
    sleep_hours: 7.0,
    radiation_msv: 0.85,
    blood_glucose: 92,
    mood_score: 4,
    core_temp_c: 36.8,
    hrv_rmssd: 48,
    cabin_co2_mmhg: 2.6,
    subjective_notes: "",
  });
  const [isSubmittingCheckIn, setIsSubmittingCheckIn] = useState<boolean>(false);
  const [checkInFeedback, setCheckInFeedback] = useState<string>("");

  // Crew & Emergency Contact Registration Form State
  const [crewForm, setCrewForm] = useState({
    callsign: "CM-1 Ibarra",
    full_name: "Rosa Ibarra",
    role: "Mission Commander",
    email: "ibarra@nasa.gov",
    username: "ibarra",
    password: "password123",
    emergency_contact_name: "Maya Okafor",
    emergency_contact_callsign: "CM-2 Okafor",
    emergency_contact_role: "Crew Medical Officer",
    alert_timeout_seconds: 60,
  });
  const [crewFeedback, setCrewFeedback] = useState<string>("");

  const loadAllData = useCallback(
    async (astroFilter?: string, customScale?: "DAILY" | "WEEKLY" | "MONTHLY") => {
      const targetAstro = astroFilter !== undefined ? astroFilter : selectedAstroId || undefined;
      const targetScale = customScale || timeScale;
      const horizon = targetScale === "DAILY" ? 24 : targetScale === "MONTHLY" ? 30 : 7;
      const results = await Promise.allSettled([
        api.getActiveCrew(),
        api.getMetricsHistory(targetAstro, 100),
        api.getLatestMetrics(targetAstro),
        api.getCurrentTriage(targetAstro),
        api.getTrajectoryForecast(targetAstro, horizon, targetScale),
        api.getEmergencyStatus(targetAstro),
        api.getAllAlarms(targetAstro),
        api.getChatHistory(targetAstro),
      ]);

      if (results[0].status === "fulfilled") setCrew(results[0].value.crew || []);
      if (results[1].status === "fulfilled") setHistory(results[1].value || []);
      if (results[2].status === "fulfilled") {
        const latest = results[2].value || null;
        setLatestMetrics(latest);
        if (latest) {
          setCheckInForm((prev) => ({
            ...prev,
            astronaut_id: latest.astronaut_id,
            mission_day: (latest.mission_day || 0) + 1,
          }));
        }
      }
      if (results[3].status === "fulfilled") setTriage(results[3].value || null);
      if (results[4].status === "fulfilled") setForecast(results[4].value || null);
      if (results[5].status === "fulfilled") setActiveAlert(results[5].value || null);
      if (results[6].status === "fulfilled") setAllAlarms(results[6].value || []);
      if (results[7].status === "fulfilled") setChatHistory(results[7].value || []);
    },
    [selectedAstroId, timeScale]
  );

  const handleTimeScaleChange = async (newScale: "DAILY" | "WEEKLY" | "MONTHLY") => {
    setTimeScale(newScale);
    setIsLoadingForecast(true);
    try {
      const horizon = newScale === "DAILY" ? 24 : newScale === "MONTHLY" ? 30 : 7;
      const res = await api.getTrajectoryForecast(selectedAstroId || undefined, horizon, newScale);
      setForecast(res);
    } catch (err) {
      console.error("Failed to load forecast for scale:", newScale, err);
    } finally {
      setIsLoadingForecast(false);
    }
  };

  // Crew Lead Authentication Handlers
  const handleLeadLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLeadFeedback("");
    try {
      const res = await api.loginWithKey(leadLoginForm.username, leadLoginForm.key);
      setLeadToken(res.access_token);
      setLeadProfile({
        username: res.username,
        station_name: res.station_name,
        crew_name: res.crew_name,
        callsign: res.callsign,
        is_lead: res.is_lead,
      });
      setLeadFeedback(`Authenticated as Crew Lead for ${res.crew_name} on ${res.station_name}`);
      await loadAllData();
    } catch (err: any) {
      setLeadFeedback(`Login failed: ${err.message}`);
    }
  };

  const handleLeadRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLeadFeedback("");
    try {
      const res = await api.registerLead(leadRegisterForm);
      setLeadToken(res.access_token);
      setLeadProfile({
        username: res.username,
        station_name: res.station_name,
        crew_name: res.crew_name,
        callsign: res.callsign,
        is_lead: res.is_lead,
      });
      setLeadFeedback(`Station Lead registered: ${res.crew_name} on ${res.station_name}`);
      await loadAllData();
    } catch (err: any) {
      setLeadFeedback(`Registration failed: ${err.message}`);
    }
  };

  const handleProvisionMember = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!leadToken) {
      setLeadFeedback("Must be signed in as Crew Lead to provision members.");
      return;
    }
    setLeadFeedback("");
    try {
      const res = await api.createCrewMember(provisionMemberForm, leadToken);
      setLeadFeedback(`Provisioned crew member '${res.username}' for station '${leadProfile?.station_name}' (${leadProfile?.crew_name})`);
      setProvisionMemberForm({ username: "", key: "", callsign: "" });
      await loadAllData();
    } catch (err: any) {
      setLeadFeedback(`Provisioning failed: ${err.message}`);
    }
  };

  useEffect(() => {
    loadAllData();
  }, [loadAllData]);

  // Submit Unified Daily Check-in Form
  const handleCheckInSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmittingCheckIn(true);
    setCheckInFeedback("");
    try {
      await api.ingestMetrics(checkInForm);
      await loadAllData(checkInForm.astronaut_id);
      setCheckInFeedback(
        `Saved check-in for ${checkInForm.astronaut_id} (Sol ${checkInForm.mission_day}). Triage and Supabase synced.`
      );
    } catch (err: any) {
      setCheckInFeedback(`Error: ${err.message || "Failed to save check-in"}`);
    } finally {
      setIsSubmittingCheckIn(false);
    }
  };

  // Register Crew Member + Emergency Contact
  const handleCrewRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setCrewFeedback("");
    try {
      await api.registerAstronaut(crewForm);
      await loadAllData();
      setCrewFeedback(
        `Registered ${crewForm.callsign} with emergency contact ${crewForm.emergency_contact_callsign}.`
      );
    } catch (err: any) {
      setCrewFeedback(`Notice: ${err.message}`);
    }
  };

  // Send query to AstroDoc AI Flight Surgeon
  const handleSendChat = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim() || isSendingChat) return;
    setIsSendingChat(true);
    setChatError("");
    const q = chatInput.trim();
    setChatInput("");

    // Optimistic append so user sees message immediately
    const target = selectedAstroId || latestMetrics?.astronaut_id || "CM-1 Ibarra";
    const tempUserMsg: ChatHistoryItem = {
      id: Date.now(),
      astronaut_id: target,
      role: "user",
      content: q,
      citations: [],
      timestamp: new Date().toISOString(),
    };
    setChatHistory((prev) => [...prev, tempUserMsg]);

    try {
      const reply = await api.queryFlightSurgeon(q, target);
      const updatedChat = await api.getChatHistory(selectedAstroId || undefined).catch(() => null);
      if (updatedChat && updatedChat.length > 0) {
        setChatHistory(updatedChat);
      } else {
        setChatHistory((prev) => [
          ...prev,
          {
            id: Date.now() + 1,
            astronaut_id: target,
            role: "assistant",
            content: reply.content,
            citations: reply.citations || [],
            timestamp: reply.timestamp || new Date().toISOString(),
          },
        ]);
      }
    } catch (err: any) {
      setChatError(err.message || "Unable to reach AstroDoc backend.");
    } finally {
      setIsSendingChat(false);
    }
  };

  // Dead-Man's Switch Actions
  const handleAnswerAsOwner = async (alertId: string) => {
    await api.answerAlarmAsOwner(alertId, "Confirmed conscious at crew console.");
    await loadAllData();
  };

  const handleAckAsContact = async (alertId: string, contactCallsign: string) => {
    await api.acknowledgeAsEmergencyContact(
      alertId,
      contactCallsign || "CREW-MED",
      "Buddy check initiated; administering NASA protocol."
    );
    await loadAllData();
  };

  const handleCheckTimeout = async () => {
    await api.checkEmergencyTimeout();
    await loadAllData();
  };

  // Compute deltas from real history
  const prevMetrics = history.length >= 2 ? history[history.length - 2] : null;
  const pctDelta = (curr?: number, prev?: number) => {
    if (curr === undefined || curr === null) return "No data";
    if (!prev || prev === 0) return "Baseline";
    const diff = ((curr - prev) / prev) * 100;
    return `${diff >= 0 ? "+" : "−"}${Math.abs(diff).toFixed(1)}%`;
  };

  // Series for the main overview SVG chart
  const chartValues: number[] = history.map((h) =>
    chartMetric === "spo2"
      ? Number(h.spo2)
      : chartMetric === "heart_rate"
      ? Number(h.heart_rate)
      : Number(h.sleep_hours)
  );
  const chartBounds =
    chartMetric === "spo2"
      ? { min: 88, max: 100, labels: ["100%", "97", "94", "91", "88"] }
      : chartMetric === "heart_rate"
      ? { min: 45, max: 145, labels: ["145", "120", "95", "70", "45"] }
      : { min: 0, max: 10, labels: ["10h", "7.5", "5.0", "2.5", "0"] };

  const primaryPath = buildSvgPath(chartValues, chartBounds.min, chartBounds.max);
  const baselinePath =
    chartValues.length > 0
      ? buildSvgPath(
          chartValues.map(() => chartValues[0]),
          chartBounds.min,
          chartBounds.max
        )
      : "";

  // Alerts by system counts (computed purely from real history)
  const systemAlertCounts = React.useMemo(() => {
    let resp = 0,
      sleep = 0,
      rad = 0,
      cardio = 0,
      env = 0,
      sensors = 0;
    for (const row of history) {
      if (row.spo2 < 95) resp++;
      if (row.sleep_hours < 6) sleep++;
      if (row.radiation_msv >= 2.0) rad++;
      if (row.heart_rate > 95 || row.bp_sys > 135) cardio++;
      if ((row.core_temp_c || 36.8) > 37.6) env++;
      if ((row.hrv_rmssd || 45) < 30) sensors++;
    }
    return [
      { label: "Resp.", count: resp, color: "#95A4FC" },
      { label: "Sleep", count: sleep, color: "#96E2D6" },
      { label: "Radiation", count: rad, color: "#A8A8A8" },
      { label: "Cardio", count: cardio, color: "#1CC8FF" },
      { label: "Env.", count: env, color: "#C6A7FF" },
      { label: "Sensors", count: sensors, color: "#A8C5DA" },
    ];
  }, [history]);
  const maxSystemCount = Math.max(6, ...systemAlertCounts.map((s) => s.count));

  const hasData = history.length > 0;
  const avgSleepHrs = hasData
    ? history.reduce((acc, r) => acc + Number(r.sleep_hours || 0), 0) / history.length
    : 0;
  const sleepPct = hasData ? Math.min(50, Math.round((avgSleepHrs / 24) * 1000) / 10) : 0;
  const exercisePct = hasData ? 10.4 : 0;
  const workPct = hasData ? 41.5 : 0;
  const otherPct = hasData
    ? Math.max(0, Number((100 - sleepPct - exercisePct - workPct).toFixed(1)))
    : 0;

  const unackAlertsCount = allAlarms.filter((a) => !a.acknowledged).length;
  const currentMeta = SCREEN_META[activeScreen];

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexWrap: "wrap",
        background: "#1C1C1C",
        color: "#FFFFFF",
        fontFamily: "Inter, 'SF Pro Text', system-ui, sans-serif",
        fontSize: "14px",
        lineHeight: "20px",
        fontVariantNumeric: "tabular-nums",
      }}
    >
      {/* =====================================================================
          LEFT NAVIGATION SIDEBAR (212px, #1C1C1C, border #333333)
      ===================================================================== */}
      {showLeftNav && (
        <div style={{ flex: "0 0 212px", borderRight: "1px solid #333333", position: "relative", zIndex: 20 }}>
          <nav
            aria-label="Main"
            style={{
              width: "100%",
              minHeight: "100%",
              boxSizing: "border-box",
              display: "flex",
              flexDirection: "column",
              gap: "16px",
              padding: "20px 16px",
              background: "#1C1C1C",
              color: "#FFFFFF",
            }}
          >
            {/* Brand Logo */}
            <button
              type="button"
              onClick={() => setActiveScreen("overview")}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                padding: "4px 8px",
                color: "#FFFFFF",
                background: "transparent",
                border: "none",
                cursor: "pointer",
                textAlign: "left",
                width: "100%",
              }}
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path
                  d="M12 2 L21 7 V17 L12 22 L3 17 V7 Z"
                  stroke="#FFFFFF"
                  strokeWidth="1.6"
                  strokeLinejoin="round"
                />
                <path
                  d="M7 12.5 H9.5 L11 9 L13 16 L14.5 12.5 H17"
                  stroke="#7DD3FC"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <span style={{ fontWeight: 600 }}>Aegis-Bio</span>
            </button>

            {/* Pinned */}
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <div style={{ display: "flex", gap: "16px", padding: "4px 8px" }}>
                <span style={{ color: "#A3A3A3" }}>Pinned</span>
                <span style={{ color: "#6B6B6B" }}>Recent</span>
              </div>
              <button
                type="button"
                onClick={() => setActiveScreen("daily-checkin")}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  height: "32px",
                  padding: "0 8px",
                  color: "#FFFFFF",
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  textAlign: "left",
                  width: "100%",
                  whiteSpace: "nowrap",
                }}
              >
                <span
                  style={{
                    width: "6px",
                    height: "6px",
                    borderRadius: "50%",
                    background: "#7DD3FC",
                  }}
                />
                Daily Check-in
              </button>
            </div>

            {/* Dashboards Group */}
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <span style={{ padding: "4px 8px", color: "#A3A3A3" }}>Dashboards</span>

              <button
                type="button"
                onClick={() => setActiveScreen("overview")}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  height: "36px",
                  padding: "0 8px 0 28px",
                  borderRadius: "8px",
                  color: "#FFFFFF",
                  border: "none",
                  cursor: "pointer",
                  width: "100%",
                  textAlign: "left",
                  whiteSpace: "nowrap",
                  background: activeScreen === "overview" ? "rgba(255,255,255,0.1)" : "transparent",
                }}
              >
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                  <path
                    d="M10 2.5 A7.5 7.5 0 1 0 17.5 10 H10 Z"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinejoin="round"
                  />
                  <path d="M12.5 2.9 A7.5 7.5 0 0 1 17.1 7.5 H12.5 Z" fill="currentColor" />
                </svg>
                Overview
              </button>

              <button
                type="button"
                onClick={() => setActiveScreen("daily-checkin")}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  height: "36px",
                  padding: "0 8px 0 28px",
                  borderRadius: "8px",
                  color: "#FFFFFF",
                  border: "none",
                  cursor: "pointer",
                  width: "100%",
                  textAlign: "left",
                  whiteSpace: "nowrap",
                  background:
                    activeScreen === "daily-checkin" ? "rgba(255,255,255,0.1)" : "transparent",
                }}
              >
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                  <rect
                    x="3.5"
                    y="3.5"
                    width="13"
                    height="13"
                    rx="2.5"
                    stroke="currentColor"
                    strokeWidth="1.5"
                  />
                  <path
                    d="M7 10 H13 M10 7 V13"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                  />
                </svg>
                Daily Check-in
              </button>

              <button
                type="button"
                onClick={() => setActiveScreen("crew")}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  height: "36px",
                  padding: "0 8px",
                  borderRadius: "8px",
                  color: "#FFFFFF",
                  border: "none",
                  cursor: "pointer",
                  width: "100%",
                  textAlign: "left",
                  whiteSpace: "nowrap",
                  background: activeScreen === "crew" ? "rgba(255,255,255,0.1)" : "transparent",
                }}
              >
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                  <path
                    d="M3 4.5 L6 7.5 L9 4.5"
                    stroke="#6B6B6B"
                    strokeWidth="1.4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                  <circle cx="7.5" cy="7" r="3" stroke="#FFFFFF" strokeWidth="1.5" />
                  <path
                    d="M2 16.5 C2 13.5 4.5 12 7.5 12 C10.5 12 13 13.5 13 16.5"
                    stroke="#FFFFFF"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                  />
                  <path
                    d="M13 4.2 A2.8 2.8 0 0 1 13 9.8 M15 12.3 C16.8 12.9 18 14.3 18 16.5"
                    stroke="#FFFFFF"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                  />
                </svg>
                Crew
              </button>

              {crew.length > 0 ? (
                crew.map((member) => (
                  <button
                    key={member.id}
                    type="button"
                    onClick={() => {
                      setSelectedAstroId(member.id === selectedAstroId ? "" : member.id);
                    }}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      height: "32px",
                      padding: "0 8px 0 56px",
                      borderRadius: "8px",
                      color: selectedAstroId === member.id ? "#7DD3FC" : "#FFFFFF",
                      background:
                        selectedAstroId === member.id ? "rgba(255,255,255,0.06)" : "transparent",
                      border: "none",
                      cursor: "pointer",
                      textAlign: "left",
                      width: "100%",
                    }}
                  >
                    <span
                      style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                    >
                      {member.id}
                    </span>
                  </button>
                ))
              ) : (
                <span
                  style={{
                    padding: "4px 8px 4px 56px",
                    fontSize: "12px",
                    color: "#6B6B6B",
                  }}
                >
                  No crew logged
                </span>
              )}

              <button
                type="button"
                onClick={() => setActiveScreen("hazards")}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  height: "36px",
                  padding: "0 8px 0 28px",
                  borderRadius: "8px",
                  color: "#FFFFFF",
                  border: "none",
                  cursor: "pointer",
                  width: "100%",
                  textAlign: "left",
                  whiteSpace: "nowrap",
                  background: activeScreen === "hazards" ? "rgba(255,255,255,0.1)" : "transparent",
                }}
              >
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                  <path
                    d="M10 2 L16.5 4.5 V9.5 C16.5 13.5 13.8 16.5 10 18 C6.2 16.5 3.5 13.5 3.5 9.5 V4.5 Z"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinejoin="round"
                  />
                </svg>
                Space Hazards
              </button>
            </div>

            {/* Clinical Group */}
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <span style={{ padding: "4px 8px", color: "#A3A3A3" }}>Clinical</span>

              <button
                type="button"
                onClick={() => setActiveScreen("alerts")}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  height: "36px",
                  padding: "0 8px 0 28px",
                  borderRadius: "8px",
                  color: "#FFFFFF",
                  border: "none",
                  cursor: "pointer",
                  width: "100%",
                  textAlign: "left",
                  whiteSpace: "nowrap",
                  background: activeScreen === "alerts" ? "rgba(255,255,255,0.1)" : "transparent",
                }}
              >
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                  <path
                    d="M5 8 A5 5 0 0 1 15 8 V12 L16.5 14.5 H3.5 L5 12 Z"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinejoin="round"
                  />
                  <path
                    d="M8.2 17 A2 2 0 0 0 11.8 17"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                  />
                </svg>
                Alerts
                {unackAlertsCount > 0 && (
                  <span
                    style={{
                      marginLeft: "auto",
                      minWidth: "20px",
                      height: "20px",
                      padding: "0 6px",
                      borderRadius: "10px",
                      background: "#EF4444",
                      color: "#1C1C1C",
                      fontSize: "12px",
                      fontWeight: 600,
                      lineHeight: "20px",
                      textAlign: "center",
                    }}
                  >
                    {unackAlertsCount}
                  </span>
                )}
              </button>
            </div>

            {/* Mission Group */}
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <span style={{ padding: "4px 8px", color: "#A3A3A3" }}>Mission</span>

              <button
                type="button"
                onClick={() => setActiveScreen("thresholds")}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  height: "36px",
                  padding: "0 8px 0 28px",
                  borderRadius: "8px",
                  color: "#FFFFFF",
                  border: "none",
                  cursor: "pointer",
                  width: "100%",
                  textAlign: "left",
                  whiteSpace: "nowrap",
                  background:
                    activeScreen === "thresholds" ? "rgba(255,255,255,0.1)" : "transparent",
                }}
              >
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                  <circle cx="10" cy="10" r="2.5" stroke="currentColor" strokeWidth="1.5" />
                  <path
                    d="M10 2.5 V4.5 M10 15.5 V17.5 M2.5 10 H4.5 M15.5 10 H17.5 M4.7 4.7 L6.1 6.1 M13.9 13.9 L15.3 15.3 M4.7 15.3 L6.1 13.9 M13.9 6.1 L15.3 4.7"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                  />
                </svg>
                Thresholds
              </button>
            </div>
          </nav>
        </div>
      )}

      {/* =====================================================================
          CENTER MAIN WORKSPACE
      ===================================================================== */}
      <div style={{ flex: "999 1 560px", minWidth: 0, display: "flex", flexDirection: "column" }}>
        {/* Top Header */}
        <header
          style={{
            width: "100%",
            boxSizing: "border-box",
            minHeight: "68px",
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            gap: "8px 16px",
            padding: "12px 28px",
            background: "#1C1C1C",
            borderBottom: "1px solid #333333",
            color: "#FFFFFF",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
            <button
              type="button"
              onClick={() => setShowLeftNav((v) => !v)}
              aria-label="Toggle navigation"
              style={{
                width: "36px",
                height: "36px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                border: "none",
                borderRadius: "8px",
                background: "transparent",
                cursor: "pointer",
              }}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <rect x="3" y="4" width="14" height="12" rx="2" stroke="#FFFFFF" strokeWidth="1.5" />
                <path d="M8 4 V16" stroke="#FFFFFF" strokeWidth="1.5" />
              </svg>
            </button>
            <span style={{ marginLeft: "8px", color: "#A3A3A3" }}>{currentMeta.section}</span>
            <span style={{ color: "#6B6B6B" }}>/</span>
            <span>{currentMeta.title}</span>
            {selectedAstroId && (
              <>
                <span style={{ color: "#6B6B6B" }}>/</span>
                <span style={{ color: "#7DD3FC" }}>{selectedAstroId}</span>
              </>
            )}
          </div>

          <div
            style={{
              marginLeft: "auto",
              display: "flex",
              alignItems: "center",
              gap: "12px",
              flexWrap: "wrap",
            }}
          >
            <span
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                height: "32px",
                padding: "0 12px",
                borderRadius: "8px",
                background: "#282828",
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: "12px",
                color: "#A3A3A3",
              }}
            >
              MET{" "}
              <span style={{ color: "#FFFFFF" }}>
                {String(latestMetrics?.mission_day || 1).padStart(3, "0")}/07:32:18
              </span>{" "}
              · Earth <span style={{ color: "#FFFFFF" }}>+14m 22s</span>
            </span>

            <button
              type="button"
              onClick={() => loadAllData()}
              title="Refresh from backend"
              style={{
                width: "36px",
                height: "36px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                border: "none",
                borderRadius: "8px",
                background: "transparent",
                cursor: "pointer",
              }}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <path
                  d="M3.5 10 A6.5 6.5 0 1 0 5.4 5.4"
                  stroke="#FFFFFF"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
                <path
                  d="M3 3.5 V6.5 H6"
                  stroke="#FFFFFF"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M10 6.5 V10 L12.5 11.5"
                  stroke="#FFFFFF"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              </svg>
            </button>

            <button
              type="button"
              onClick={() => setActiveScreen("alerts")}
              aria-label="Alerts"
              style={{
                position: "relative",
                width: "36px",
                height: "36px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                borderRadius: "8px",
                background: "transparent",
                border: "none",
                cursor: "pointer",
              }}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <path
                  d="M5 8 A5 5 0 0 1 15 8 V12 L16.5 14.5 H3.5 L5 12 Z"
                  stroke="#FFFFFF"
                  strokeWidth="1.5"
                  strokeLinejoin="round"
                />
                <path
                  d="M8.2 17 A2 2 0 0 0 11.8 17"
                  stroke="#FFFFFF"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              </svg>
              {unackAlertsCount > 0 && (
                <span
                  style={{
                    position: "absolute",
                    top: "6px",
                    right: "6px",
                    width: "8px",
                    height: "8px",
                    borderRadius: "50%",
                    background: "#EF4444",
                    boxShadow: "0 0 0 2px #1C1C1C",
                  }}
                />
              )}
            </button>

            <button
              type="button"
              onClick={() => setShowRightPanel((v) => !v)}
              aria-label="Toggle side panel"
              style={{
                width: "36px",
                height: "36px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                border: "none",
                borderRadius: "8px",
                background: "transparent",
                cursor: "pointer",
              }}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <rect x="3" y="4" width="14" height="12" rx="2" stroke="#FFFFFF" strokeWidth="1.5" />
                <path d="M12 4 V16" stroke="#FFFFFF" strokeWidth="1.5" />
              </svg>
            </button>
          </div>
        </header>

        {/* Main Screen Container */}
        <main style={{ display: "flex", flexDirection: "column", gap: "28px", padding: "28px" }}>
          {/* Active Alert Banner */}
          {activeAlert && !activeAlert.acknowledged && (
            <div
              role="alert"
              style={{
                width: "100%",
                boxSizing: "border-box",
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: "12px 16px",
                padding: "12px 12px 12px 16px",
                borderRadius: "16px",
                background: "#3B2323",
                border: "1px solid #EF4444",
                color: "#FFFFFF",
              }}
            >
              <span
                style={{
                  width: "40px",
                  height: "40px",
                  flexShrink: 0,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  borderRadius: "12px",
                  background: "#EF4444",
                }}
              >
                <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
                  <path d="M10 1 L19 10 L10 19 L1 10 Z" fill="#1C1C1C" />
                  <rect x="9" y="5.5" width="2" height="6" rx="1" fill="#EF4444" />
                  <rect x="9" y="13" width="2" height="2" rx="1" fill="#EF4444" />
                </svg>
              </span>
              <div style={{ flex: "999 1 280px", display: "flex", flexDirection: "column" }}>
                <span style={{ fontWeight: 600 }}>
                  Crew warning · {activeAlert.astronaut_id}, {activeAlert.hazard_origin}
                </span>
                <span
                  style={{
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: "12px",
                    lineHeight: "16px",
                    color: "#FCA5A5",
                  }}
                >
                  {activeAlert.status === "SWITCHED_TO_EMERGENCY_CONTACT"
                    ? `Escalated to ${activeAlert.emergency_contact_callsign || "Emergency Contact"}`
                    : `Owner timeout: ${activeAlert.remaining_seconds ?? activeAlert.timeout_seconds}s · Emergency Contact: ${
                        activeAlert.emergency_contact_callsign || "CREW-MED"
                      }`}
                </span>
              </div>
              <div style={{ flex: "1 1 auto", display: "flex", justifyContent: "flex-end", gap: "8px" }}>
                <button
                  type="button"
                  onClick={() => handleAnswerAsOwner(activeAlert.alert_id)}
                  style={{
                    height: "44px",
                    padding: "0 16px",
                    borderRadius: "8px",
                    border: "1px solid #F87171",
                    background: "transparent",
                    color: "#FFFFFF",
                    fontSize: "14px",
                    fontWeight: 500,
                    cursor: "pointer",
                  }}
                >
                  Silence tone (I am OK)
                </button>
                <button
                  type="button"
                  onClick={() => setActiveScreen("alerts")}
                  style={{
                    height: "44px",
                    display: "inline-flex",
                    alignItems: "center",
                    padding: "0 16px",
                    borderRadius: "8px",
                    border: "none",
                    background: "#EF4444",
                    color: "#1C1C1C",
                    fontSize: "14px",
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  Go to Alert
                </button>
              </div>
            </div>
          )}

          {/* =================================================================
              SCREEN 1: OVERVIEW
          ================================================================= */}
          {activeScreen === "overview" && (
            <>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <h1 style={{ margin: 0, fontSize: "14px", lineHeight: "20px", fontWeight: 600 }}>
                  Overview {selectedAstroId ? `· ${selectedAstroId}` : ""}
                </h1>
                <button
                  type="button"
                  onClick={() => setActiveScreen("daily-checkin")}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    height: "32px",
                    padding: "0 12px",
                    border: "1px solid #333333",
                    borderRadius: "8px",
                    background: "#282828",
                    color: "#FFFFFF",
                    fontSize: "13px",
                    cursor: "pointer",
                  }}
                >
                  + Log Daily Check-in
                </button>
              </div>

              {/* 4 KPI Cards (#E3F5FF and #E5ECF6) */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                  gap: "28px",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "8px",
                    padding: "24px",
                    borderRadius: "16px",
                    background: "#E3F5FF",
                    color: "#1C1C1C",
                  }}
                >
                  <span style={{ fontWeight: 600 }}>Heart rate</span>
                  <span
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: "8px",
                    }}
                  >
                    <span style={{ fontSize: "24px", lineHeight: "36px", fontWeight: 600 }}>
                      {latestMetrics ? `${Math.round(latestMetrics.heart_rate)}` : "—"}
                    </span>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "4px", fontSize: "12px" }}>
                      {pctDelta(latestMetrics?.heart_rate, prevMetrics?.heart_rate)}
                    </span>
                  </span>
                </div>

                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "8px",
                    padding: "24px",
                    borderRadius: "16px",
                    background: "#E5ECF6",
                    color: "#1C1C1C",
                  }}
                >
                  <span style={{ fontWeight: 600 }}>SpO₂</span>
                  <span
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: "8px",
                    }}
                  >
                    <span style={{ fontSize: "24px", lineHeight: "36px", fontWeight: 600 }}>
                      {latestMetrics ? `${Number(latestMetrics.spo2).toFixed(1)}%` : "—"}
                    </span>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "4px", fontSize: "12px" }}>
                      {pctDelta(latestMetrics?.spo2, prevMetrics?.spo2)}
                    </span>
                  </span>
                </div>

                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "8px",
                    padding: "24px",
                    borderRadius: "16px",
                    background: "#E3F5FF",
                    color: "#1C1C1C",
                  }}
                >
                  <span style={{ fontWeight: 600 }}>Sleep</span>
                  <span
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: "8px",
                    }}
                  >
                    <span style={{ fontSize: "24px", lineHeight: "36px", fontWeight: 600 }}>
                      {latestMetrics ? `${Number(latestMetrics.sleep_hours).toFixed(1)} h` : "—"}
                    </span>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "4px", fontSize: "12px" }}>
                      {pctDelta(latestMetrics?.sleep_hours, prevMetrics?.sleep_hours)}
                    </span>
                  </span>
                </div>

                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "8px",
                    padding: "24px",
                    borderRadius: "16px",
                    background: "#E5ECF6",
                    color: "#1C1C1C",
                  }}
                >
                  <span style={{ fontWeight: 600 }}>Dose today</span>
                  <span
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: "8px",
                    }}
                  >
                    <span style={{ fontSize: "24px", lineHeight: "36px", fontWeight: 600 }}>
                      {latestMetrics ? `${Number(latestMetrics.radiation_msv).toFixed(2)} mSv` : "—"}
                    </span>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "4px", fontSize: "12px" }}>
                      {pctDelta(latestMetrics?.radiation_msv, prevMetrics?.radiation_msv)}
                    </span>
                  </span>
                </div>
              </div>

              {/* Row 2: Main Line Chart + Crew Vitals in Range */}
              <div style={{ display: "flex", flexWrap: "wrap", gap: "28px" }}>
                <section
                  style={{
                    flex: "3 1 480px",
                    minWidth: 0,
                    display: "flex",
                    flexDirection: "column",
                    gap: "16px",
                    padding: "24px",
                    borderRadius: "16px",
                    background: "#282828",
                  }}
                >
                  <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "16px" }}>
                    <button
                      type="button"
                      onClick={() => setChartMetric("spo2")}
                      style={{
                        background: "transparent",
                        border: "none",
                        cursor: "pointer",
                        padding: 0,
                        fontWeight: chartMetric === "spo2" ? 600 : 400,
                        color: chartMetric === "spo2" ? "#FFFFFF" : "#A3A3A3",
                      }}
                    >
                      SpO₂
                    </button>
                    <button
                      type="button"
                      onClick={() => setChartMetric("heart_rate")}
                      style={{
                        background: "transparent",
                        border: "none",
                        cursor: "pointer",
                        padding: 0,
                        fontWeight: chartMetric === "heart_rate" ? 600 : 400,
                        color: chartMetric === "heart_rate" ? "#FFFFFF" : "#A3A3A3",
                      }}
                    >
                      Heart rate
                    </button>
                    <button
                      type="button"
                      onClick={() => setChartMetric("sleep")}
                      style={{
                        background: "transparent",
                        border: "none",
                        cursor: "pointer",
                        padding: 0,
                        fontWeight: chartMetric === "sleep" ? 600 : 400,
                        color: chartMetric === "sleep" ? "#FFFFFF" : "#A3A3A3",
                      }}
                    >
                      Sleep
                    </button>
                    <span style={{ width: "1px", height: "20px", background: "#444444" }} />
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontSize: "12px" }}>
                      <span
                        style={{
                          width: "6px",
                          height: "6px",
                          borderRadius: "50%",
                          background: "#C6C7F8",
                        }}
                      />
                      Logged series
                    </span>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontSize: "12px" }}>
                      <span
                        style={{
                          width: "6px",
                          height: "6px",
                          borderRadius: "50%",
                          background: "#A8C5DA",
                        }}
                      />
                      Initial baseline
                    </span>
                  </div>

                  {hasData ? (
                    <div style={{ display: "flex", gap: "16px" }}>
                      <div
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          justifyContent: "space-between",
                          height: "232px",
                          paddingBottom: "20px",
                          fontSize: "12px",
                          lineHeight: "16px",
                          color: "#A3A3A3",
                          textAlign: "right",
                        }}
                      >
                        {chartBounds.labels.map((lbl, idx) => (
                          <span key={idx}>{lbl}</span>
                        ))}
                      </div>
                      <div
                        style={{
                          flex: 1,
                          minWidth: 0,
                          display: "flex",
                          flexDirection: "column",
                          gap: "4px",
                        }}
                      >
                        <svg
                          width="100%"
                          height="212"
                          viewBox="0 0 600 200"
                          preserveAspectRatio="none"
                          style={{ display: "block" }}
                        >
                          <path
                            d={baselinePath}
                            fill="none"
                            stroke="#A8C5DA"
                            strokeWidth="2"
                            strokeDasharray="5 5"
                            vectorEffect="non-scaling-stroke"
                          />
                          <path
                            d={primaryPath}
                            fill="none"
                            stroke="#C6C7F8"
                            strokeWidth="3"
                            vectorEffect="non-scaling-stroke"
                          />
                        </svg>
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            fontSize: "12px",
                            lineHeight: "16px",
                            color: "#A3A3A3",
                          }}
                        >
                          {history.slice(-7).map((h, i) => (
                            <span key={i}>Sol {h.mission_day}</span>
                          ))}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div
                      style={{
                        height: "232px",
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: "12px",
                        color: "#A3A3A3",
                        border: "1px dashed #333333",
                        borderRadius: "12px",
                      }}
                    >
                      <span>Database is currently empty. No telemetry records logged yet.</span>
                      <button
                        type="button"
                        onClick={() => setActiveScreen("daily-checkin")}
                        style={{
                          height: "36px",
                          padding: "0 16px",
                          borderRadius: "8px",
                          border: "none",
                          background: "#E3F5FF",
                          color: "#1C1C1C",
                          fontWeight: 600,
                          cursor: "pointer",
                        }}
                      >
                        Open Daily Check-in
                      </button>
                    </div>
                  )}
                </section>

                {/* Crew Vitals in Range */}
                <section
                  style={{
                    flex: "1 1 200px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "16px",
                    padding: "24px",
                    borderRadius: "16px",
                    background: "#282828",
                  }}
                >
                  <h2 style={{ margin: 0, fontSize: "14px", fontWeight: 600 }}>Crew vitals in range</h2>
                  {crew.length > 0 ? (
                    crew.map((m) => (
                      <button
                        key={m.id}
                        type="button"
                        onClick={() => setSelectedAstroId(m.id === selectedAstroId ? "" : m.id)}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          gap: "8px",
                          minHeight: "28px",
                          color: "#FFFFFF",
                          background: "transparent",
                          border: "none",
                          padding: 0,
                          cursor: "pointer",
                        }}
                      >
                        <span>{m.id}</span>
                        <span style={{ display: "flex", gap: "4px" }}>
                          {m.vitals_bars.map((st, idx) => (
                            <span
                              key={idx}
                              style={{
                                width: "14px",
                                height: "3px",
                                borderRadius: "2px",
                                background:
                                  st === "CRITICAL"
                                    ? "#EF4444"
                                    : st === "MEDIUM"
                                    ? "#F59E0B"
                                    : "#FFFFFF",
                              }}
                            />
                          ))}
                        </span>
                      </button>
                    ))
                  ) : (
                    <span style={{ color: "#6B6B6B", fontSize: "13px" }}>
                      No crew vitals recorded yet.
                    </span>
                  )}
                  <span
                    style={{
                      marginTop: "auto",
                      fontSize: "12px",
                      lineHeight: "16px",
                      color: "#A3A3A3",
                    }}
                  >
                    HR · SpO₂ · Sleep · Temp · Dose
                  </span>
                </section>
              </div>

              {/* Multi-Scale Time Series Physiological Forecast Panel */}
              <section
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "20px",
                  padding: "24px",
                  borderRadius: "16px",
                  background: "#282828",
                  border: "1px solid #333333",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: "16px",
                  }}
                >
                  <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span style={{ fontSize: "16px", fontWeight: 600, color: "#FFFFFF" }}>
                        Multi-Scale Time Series Vital Forecast
                      </span>
                      <span
                        style={{
                          fontSize: "11px",
                          fontWeight: 600,
                          padding: "2px 8px",
                          borderRadius: "999px",
                          background:
                            timeScale === "DAILY"
                              ? "rgba(125,211,252,0.15)"
                              : timeScale === "MONTHLY"
                              ? "rgba(233,168,242,0.15)"
                              : "rgba(165,180,252,0.15)",
                          color:
                            timeScale === "DAILY"
                              ? "#7DD3FC"
                              : timeScale === "MONTHLY"
                              ? "#E9A8F2"
                              : "#A5B4FC",
                          border: `1px solid ${
                            timeScale === "DAILY"
                              ? "#7DD3FC"
                              : timeScale === "MONTHLY"
                              ? "#E9A8F2"
                              : "#A5B4FC"
                          }`,
                        }}
                      >
                        {timeScale} HORIZON
                      </span>
                      {isLoadingForecast && (
                        <span style={{ fontSize: "11px", color: "#A3A3A3" }}>Calculating...</span>
                      )}
                    </div>
                    <span style={{ fontSize: "12px", color: "#A3A3A3" }}>
                      {timeScale === "DAILY" &&
                        "24-Hour Intra-Sol Horizon: Damped exponential smoothing with circadian diurnal harmonics (sinusoidal diurnal core temp / sleep cycles)."}
                      {timeScale === "WEEKLY" &&
                        "7-Day Tactical Horizon: Multi-day trend velocity & damped smoothing for clinical stabilization."}
                      {timeScale === "MONTHLY" &&
                        "30-Day Transit Horizon: Long-duration spaceflight adaptation with asymptotic biological plateau damping."}
                    </span>
                  </div>

                  {/* Horizon Switcher Buttons */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      background: "#1C1C1C",
                      padding: "4px",
                      borderRadius: "10px",
                      border: "1px solid #333333",
                      gap: "4px",
                    }}
                  >
                    {(["DAILY", "WEEKLY", "MONTHLY"] as const).map((sc) => (
                      <button
                        key={sc}
                        type="button"
                        onClick={() => handleTimeScaleChange(sc)}
                        style={{
                          border: "none",
                          padding: "6px 14px",
                          borderRadius: "8px",
                          fontSize: "12px",
                          fontWeight: 600,
                          cursor: "pointer",
                          background: timeScale === sc ? "#333333" : "transparent",
                          color: timeScale === sc ? "#FFFFFF" : "#A3A3A3",
                          transition: "all 0.2s ease",
                        }}
                      >
                        {sc === "DAILY" ? "Daily (24h)" : sc === "WEEKLY" ? "Weekly (7d)" : "Monthly (30d)"}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Meta stats bar */}
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                    gap: "12px",
                  }}
                >
                  <div
                    style={{
                      background: "#1C1C1C",
                      padding: "12px 16px",
                      borderRadius: "10px",
                      border: "1px solid #333333",
                    }}
                  >
                    <div style={{ fontSize: "11px", color: "#A3A3A3" }}>FORECAST ENGINE</div>
                    <div style={{ fontSize: "13px", fontWeight: 600, color: "#FFFFFF", marginTop: "4px" }}>
                      {forecast?.model_used || "Holt-Winters Damped (L-BFGS-B)"}
                    </div>
                  </div>

                  <div
                    style={{
                      background: "#1C1C1C",
                      padding: "12px 16px",
                      borderRadius: "10px",
                      border: "1px solid #333333",
                    }}
                  >
                    <div style={{ fontSize: "11px", color: "#A3A3A3" }}>TREND VELOCITY (SLOPE)</div>
                    <div
                      style={{
                        fontSize: "13px",
                        fontWeight: 600,
                        color:
                          (forecast?.trend_velocity || 0) > 0.5
                            ? "#EF4444"
                            : (forecast?.trend_velocity || 0) > 0.1
                            ? "#F59E0B"
                            : "#96E2D6",
                        marginTop: "4px",
                      }}
                    >
                      {forecast?.trend_velocity != null
                        ? `${Number(forecast.trend_velocity).toFixed(3)} units / step`
                        : "0.000 / step"}
                    </div>
                  </div>

                  <div
                    style={{
                      background: "#1C1C1C",
                      padding: "12px 16px",
                      borderRadius: "10px",
                      border: "1px solid #333333",
                    }}
                  >
                    <div style={{ fontSize: "11px", color: "#A3A3A3" }}>PRIMARY STRAIN VITAL</div>
                    <div style={{ fontSize: "13px", fontWeight: 600, color: "#FFFFFF", marginTop: "4px" }}>
                      {forecast?.primary_strain_indicator || "Nominal Vital Envelope"}
                    </div>
                  </div>

                  <div
                    style={{
                      background: "#1C1C1C",
                      padding: "12px 16px",
                      borderRadius: "10px",
                      border: "1px solid #333333",
                    }}
                  >
                    <div style={{ fontSize: "11px", color: "#A3A3A3" }}>ALARM PREDICTION</div>
                    <div
                      style={{
                        fontSize: "13px",
                        fontWeight: 600,
                        color: forecast?.alert_triggered ? "#EF4444" : "#96E2D6",
                        marginTop: "4px",
                      }}
                    >
                      {forecast?.alert_triggered ? "🚨 ESCALATION PREDICTED" : "Nominal (Within Thresholds)"}
                    </div>
                  </div>
                </div>

                {/* Trajectory Timeline Preview */}
                {forecast?.trajectory && forecast.trajectory.length > 0 ? (
                  <div>
                    <div style={{ fontSize: "12px", color: "#A3A3A3", marginBottom: "8px" }}>
                      Projected Trajectory Points ({forecast.trajectory.length} steps):
                    </div>
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
                        gap: "10px",
                      }}
                    >
                      {forecast.trajectory
                        .filter((_, idx) => {
                          const total = forecast.trajectory?.length || 0;
                          if (total <= 8) return true;
                          const step = Math.ceil(total / 8);
                          return idx % step === 0 || idx === total - 1;
                        })
                        .map((pt, idx) => (
                          <div
                            key={idx}
                            style={{
                              padding: "12px",
                              borderRadius: "10px",
                              background: "#1C1C1C",
                              border: "1px solid #333333",
                              display: "flex",
                              flexDirection: "column",
                              gap: "4px",
                            }}
                          >
                            <span style={{ fontSize: "11px", color: "#7DD3FC", fontWeight: 600 }}>
                              {pt.time_label || `Step ${pt.day}`}
                            </span>
                            <div style={{ fontSize: "12px", color: "#FFFFFF" }}>
                              HR: <strong>{Number(pt.heart_rate_predicted).toFixed(0)} bpm</strong>
                            </div>
                            <div style={{ fontSize: "11px", color: "#A3A3A3" }}>
                              SpO₂: {Number(pt.spo2_predicted).toFixed(1)}%
                            </div>
                            {pt.lower_ci_heart_rate != null && pt.upper_ci_heart_rate != null && (
                              <div style={{ fontSize: "10px", color: "#6B6B6B" }}>
                                95% CI: [{Math.round(pt.lower_ci_heart_rate)}-{Math.round(pt.upper_ci_heart_rate)}]
                              </div>
                            )}
                            <div style={{ fontSize: "11px", color: pt.cardiovascular_strain_index > 0.6 ? "#EF4444" : "#96E2D6" }}>
                              CSI: {Number(pt.cardiovascular_strain_index).toFixed(2)}
                            </div>
                          </div>
                        ))}
                    </div>
                  </div>
                ) : (
                  <div style={{ padding: "16px", borderRadius: "10px", background: "#1C1C1C", color: "#A3A3A3", fontSize: "13px" }}>
                    No baseline historical data logged yet to fit the time-series model. Submit a Daily Check-in to initialize the trajectory forecaster.
                  </div>
                )}

                {/* Countermeasure Card */}
                {forecast?.recommended_countermeasure && (
                  <div
                    style={{
                      padding: "14px 18px",
                      borderRadius: "10px",
                      background: "rgba(150, 226, 214, 0.08)",
                      border: "1px solid rgba(150, 226, 214, 0.25)",
                      display: "flex",
                      alignItems: "center",
                      gap: "12px",
                    }}
                  >
                    <span style={{ fontSize: "18px" }}>🩺</span>
                    <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                      <span style={{ fontSize: "11px", color: "#96E2D6", fontWeight: 600 }}>
                        CLINICAL COUNTERMEASURE RECOMMENDATION
                      </span>
                      <span style={{ fontSize: "13px", color: "#FFFFFF" }}>
                        {forecast.recommended_countermeasure}
                      </span>
                    </div>
                  </div>
                )}
              </section>

              {/* Row 3: Alerts by System + Crew Time by Activity */}
              <div style={{ display: "flex", flexWrap: "wrap", gap: "28px" }}>
                <section
                  style={{
                    flex: "1 1 320px",
                    minWidth: 0,
                    display: "flex",
                    flexDirection: "column",
                    gap: "16px",
                    padding: "24px",
                    borderRadius: "16px",
                    background: "#282828",
                  }}
                >
                  <h2 style={{ margin: 0, fontSize: "14px", fontWeight: 600 }}>
                    Alerts by system · logged history
                  </h2>
                  <div style={{ display: "flex", gap: "16px" }}>
                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        justifyContent: "space-between",
                        height: "212px",
                        paddingBottom: "20px",
                        fontSize: "12px",
                        lineHeight: "16px",
                        color: "#A3A3A3",
                        textAlign: "right",
                      }}
                    >
                      <span>{maxSystemCount}</span>
                      <span>{Math.round((maxSystemCount * 2) / 3)}</span>
                      <span>{Math.round(maxSystemCount / 3)}</span>
                      <span>0</span>
                    </div>
                    <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "4px" }}>
                      <div
                        style={{
                          height: "192px",
                          display: "grid",
                          gridTemplateColumns: "repeat(6, minmax(0, 1fr))",
                          gap: "16px",
                          alignItems: "end",
                          justifyItems: "center",
                        }}
                      >
                        {systemAlertCounts.map((item) => {
                          const barH = Math.max(6, Math.round((item.count / maxSystemCount) * 192));
                          return (
                            <div
                              key={item.label}
                              title={`${item.label}: ${item.count}`}
                              style={{
                                width: "28px",
                                height: `${barH}px`,
                                borderRadius: "8px",
                                background: item.color,
                                opacity: item.count === 0 ? 0.25 : 1,
                              }}
                            />
                          );
                        })}
                      </div>
                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns: "repeat(6, minmax(0, 1fr))",
                          gap: "16px",
                          fontSize: "12px",
                          lineHeight: "16px",
                          color: "#A3A3A3",
                          textAlign: "center",
                        }}
                      >
                        {systemAlertCounts.map((item) => (
                          <span key={item.label}>{item.label}</span>
                        ))}
                      </div>
                    </div>
                  </div>
                </section>

                <section
                  style={{
                    flex: "1 1 320px",
                    minWidth: 0,
                    display: "flex",
                    flexDirection: "column",
                    gap: "16px",
                    padding: "24px",
                    borderRadius: "16px",
                    background: "#282828",
                  }}
                >
                  <h2 style={{ margin: 0, fontSize: "14px", fontWeight: 600 }}>
                    Crew time by activity · 24 h
                  </h2>
                  <div
                    style={{
                      flex: 1,
                      display: "flex",
                      flexWrap: "wrap",
                      alignItems: "center",
                      gap: "40px",
                    }}
                  >
                    <svg width="140" height="140" viewBox="0 0 100 100">
                      <circle
                        cx="50"
                        cy="50"
                        r="40"
                        fill="none"
                        stroke="#333333"
                        strokeWidth="14"
                      />
                      {hasData && (
                        <>
                          <circle
                            cx="50"
                            cy="50"
                            r="40"
                            fill="none"
                            stroke="#A8A8A8"
                            strokeWidth="14"
                            strokeDasharray="100.30 151.03"
                            strokeDashoffset="-2.00"
                            transform="rotate(-90 50 50)"
                          />
                          <circle
                            cx="50"
                            cy="50"
                            r="40"
                            fill="none"
                            stroke="#1CC8FF"
                            strokeWidth="14"
                            strokeDasharray="61.35 189.98"
                            strokeDashoffset="-106.30"
                            transform="rotate(-90 50 50)"
                          />
                          <circle
                            cx="50"
                            cy="50"
                            r="40"
                            fill="none"
                            stroke="#96E2D6"
                            strokeWidth="14"
                            strokeDasharray="22.14 229.19"
                            strokeDashoffset="-171.65"
                            transform="rotate(-90 50 50)"
                          />
                          <circle
                            cx="50"
                            cy="50"
                            r="40"
                            fill="none"
                            stroke="#95A4FC"
                            strokeWidth="14"
                            strokeDasharray="51.54 199.78"
                            strokeDashoffset="-197.78"
                            transform="rotate(-90 50 50)"
                          />
                        </>
                      )}
                    </svg>
                    <div
                      style={{
                        flex: 1,
                        minWidth: "160px",
                        display: "flex",
                        flexDirection: "column",
                        gap: "16px",
                        fontSize: "12px",
                        lineHeight: "16px",
                      }}
                    >
                      <span style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
                          <span
                            style={{
                              width: "6px",
                              height: "6px",
                              borderRadius: "50%",
                              background: "#A8A8A8",
                            }}
                          />
                          Work
                        </span>
                        <span>{hasData ? `${workPct}%` : "—"}</span>
                      </span>
                      <span style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
                          <span
                            style={{
                              width: "6px",
                              height: "6px",
                              borderRadius: "50%",
                              background: "#1CC8FF",
                            }}
                          />
                          Sleep
                        </span>
                        <span>{hasData ? `${sleepPct}%` : "—"}</span>
                      </span>
                      <span style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
                          <span
                            style={{
                              width: "6px",
                              height: "6px",
                              borderRadius: "50%",
                              background: "#96E2D6",
                            }}
                          />
                          Exercise
                        </span>
                        <span>{hasData ? `${exercisePct}%` : "—"}</span>
                      </span>
                      <span style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
                          <span
                            style={{
                              width: "6px",
                              height: "6px",
                              borderRadius: "50%",
                              background: "#95A4FC",
                            }}
                          />
                          Other
                        </span>
                        <span>{hasData ? `${otherPct}%` : "—"}</span>
                      </span>
                    </div>
                  </div>
                </section>
              </div>
            </>
          )}

          {/* =================================================================
              SCREEN 2: DAILY CHECK-IN (Unified Single Form, No Tabs)
          ================================================================= */}
          {activeScreen === "daily-checkin" && (
            <section
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "24px",
                padding: "24px",
                borderRadius: "16px",
                background: "#282828",
              }}
            >
              <div>
                <h1 style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>
                  Daily Crew Check-in &amp; Biometric Log
                </h1>
                <p style={{ margin: "4px 0 0", fontSize: "12px", color: "#A3A3A3" }}>
                  Enter all daily check-in parameters on this single screen. Syncs directly to
                  FastAPI &amp; Supabase and runs Dual-Classifier Triage.
                </p>
              </div>

              <form
                onSubmit={handleCheckInSubmit}
                style={{ display: "flex", flexDirection: "column", gap: "20px" }}
              >
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                    gap: "16px",
                  }}
                >
                  <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <span style={{ fontSize: "12px", color: "#A3A3A3" }}>Crew Member ID / Name</span>
                    <input
                      type="text"
                      required
                      value={checkInForm.astronaut_id}
                      onChange={(e) =>
                        setCheckInForm({ ...checkInForm, astronaut_id: e.target.value })
                      }
                      style={{
                        height: "38px",
                        padding: "0 12px",
                        borderRadius: "8px",
                        border: "1px solid #333333",
                        background: "#1C1C1C",
                        color: "#FFFFFF",
                      }}
                    />
                  </label>

                  <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <span style={{ fontSize: "12px", color: "#A3A3A3" }}>Mission Day (Sol)</span>
                    <input
                      type="number"
                      min={1}
                      required
                      value={checkInForm.mission_day}
                      onChange={(e) =>
                        setCheckInForm({
                          ...checkInForm,
                          mission_day: parseInt(e.target.value || "1", 10),
                        })
                      }
                      style={{
                        height: "38px",
                        padding: "0 12px",
                        borderRadius: "8px",
                        border: "1px solid #333333",
                        background: "#1C1C1C",
                        color: "#FFFFFF",
                      }}
                    />
                  </label>

                  <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <span style={{ fontSize: "12px", color: "#A3A3A3" }}>Heart Rate (BPM)</span>
                    <input
                      type="number"
                      step="1"
                      min={30}
                      max={220}
                      required
                      value={checkInForm.heart_rate}
                      onChange={(e) =>
                        setCheckInForm({
                          ...checkInForm,
                          heart_rate: parseFloat(e.target.value || "0"),
                        })
                      }
                      style={{
                        height: "38px",
                        padding: "0 12px",
                        borderRadius: "8px",
                        border: "1px solid #333333",
                        background: "#1C1C1C",
                        color: "#FFFFFF",
                      }}
                    />
                  </label>

                  <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <span style={{ fontSize: "12px", color: "#A3A3A3" }}>SpO₂ (%)</span>
                    <input
                      type="number"
                      step="0.1"
                      min={50}
                      max={100}
                      required
                      value={checkInForm.spo2}
                      onChange={(e) =>
                        setCheckInForm({
                          ...checkInForm,
                          spo2: parseFloat(e.target.value || "0"),
                        })
                      }
                      style={{
                        height: "38px",
                        padding: "0 12px",
                        borderRadius: "8px",
                        border: "1px solid #333333",
                        background: "#1C1C1C",
                        color: "#FFFFFF",
                      }}
                    />
                  </label>

                  <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <span style={{ fontSize: "12px", color: "#A3A3A3" }}>Systolic BP (mmHg)</span>
                    <input
                      type="number"
                      min={60}
                      max={240}
                      required
                      value={checkInForm.bp_sys}
                      onChange={(e) =>
                        setCheckInForm({
                          ...checkInForm,
                          bp_sys: parseFloat(e.target.value || "0"),
                        })
                      }
                      style={{
                        height: "38px",
                        padding: "0 12px",
                        borderRadius: "8px",
                        border: "1px solid #333333",
                        background: "#1C1C1C",
                        color: "#FFFFFF",
                      }}
                    />
                  </label>

                  <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <span style={{ fontSize: "12px", color: "#A3A3A3" }}>Diastolic BP (mmHg)</span>
                    <input
                      type="number"
                      min={40}
                      max={160}
                      required
                      value={checkInForm.bp_dia}
                      onChange={(e) =>
                        setCheckInForm({
                          ...checkInForm,
                          bp_dia: parseFloat(e.target.value || "0"),
                        })
                      }
                      style={{
                        height: "38px",
                        padding: "0 12px",
                        borderRadius: "8px",
                        border: "1px solid #333333",
                        background: "#1C1C1C",
                        color: "#FFFFFF",
                      }}
                    />
                  </label>

                  <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <span style={{ fontSize: "12px", color: "#A3A3A3" }}>
                      Sleep Duration (hours)
                    </span>
                    <input
                      type="number"
                      step="0.1"
                      min={0}
                      max={24}
                      required
                      value={checkInForm.sleep_hours}
                      onChange={(e) =>
                        setCheckInForm({
                          ...checkInForm,
                          sleep_hours: parseFloat(e.target.value || "0"),
                        })
                      }
                      style={{
                        height: "38px",
                        padding: "0 12px",
                        borderRadius: "8px",
                        border: "1px solid #333333",
                        background: "#1C1C1C",
                        color: "#FFFFFF",
                      }}
                    />
                  </label>

                  <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <span style={{ fontSize: "12px", color: "#A3A3A3" }}>
                      Radiation Dose Today (mSv)
                    </span>
                    <input
                      type="number"
                      step="0.05"
                      min={0}
                      required
                      value={checkInForm.radiation_msv}
                      onChange={(e) =>
                        setCheckInForm({
                          ...checkInForm,
                          radiation_msv: parseFloat(e.target.value || "0"),
                        })
                      }
                      style={{
                        height: "38px",
                        padding: "0 12px",
                        borderRadius: "8px",
                        border: "1px solid #333333",
                        background: "#1C1C1C",
                        color: "#FFFFFF",
                      }}
                    />
                  </label>

                  <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <span style={{ fontSize: "12px", color: "#A3A3A3" }}>
                      Core Temperature (°C)
                    </span>
                    <input
                      type="number"
                      step="0.1"
                      min={34}
                      max={42}
                      value={checkInForm.core_temp_c}
                      onChange={(e) =>
                        setCheckInForm({
                          ...checkInForm,
                          core_temp_c: parseFloat(e.target.value || "36.8"),
                        })
                      }
                      style={{
                        height: "38px",
                        padding: "0 12px",
                        borderRadius: "8px",
                        border: "1px solid #333333",
                        background: "#1C1C1C",
                        color: "#FFFFFF",
                      }}
                    />
                  </label>

                  <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <span style={{ fontSize: "12px", color: "#A3A3A3" }}>HRV RMSSD (ms)</span>
                    <input
                      type="number"
                      step="1"
                      min={5}
                      max={200}
                      value={checkInForm.hrv_rmssd}
                      onChange={(e) =>
                        setCheckInForm({
                          ...checkInForm,
                          hrv_rmssd: parseFloat(e.target.value || "45"),
                        })
                      }
                      style={{
                        height: "38px",
                        padding: "0 12px",
                        borderRadius: "8px",
                        border: "1px solid #333333",
                        background: "#1C1C1C",
                        color: "#FFFFFF",
                      }}
                    />
                  </label>

                  <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <span style={{ fontSize: "12px", color: "#A3A3A3" }}>
                      Mood / Morale (1–5)
                    </span>
                    <select
                      value={checkInForm.mood_score}
                      onChange={(e) =>
                        setCheckInForm({
                          ...checkInForm,
                          mood_score: parseInt(e.target.value, 10),
                        })
                      }
                      style={{
                        height: "38px",
                        padding: "0 12px",
                        borderRadius: "8px",
                        border: "1px solid #333333",
                        background: "#1C1C1C",
                        color: "#FFFFFF",
                      }}
                    >
                      <option value={5}>5 — Optimal</option>
                      <option value={4}>4 — Good</option>
                      <option value={3}>3 — Moderate fatigue</option>
                      <option value={2}>2 — Distressed / Low</option>
                      <option value={1}>1 — Severe exhaustion</option>
                    </select>
                  </label>

                  <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <span style={{ fontSize: "12px", color: "#A3A3A3" }}>
                      Blood Glucose (mg/dL)
                    </span>
                    <input
                      type="number"
                      min={40}
                      max={400}
                      value={checkInForm.blood_glucose}
                      onChange={(e) =>
                        setCheckInForm({
                          ...checkInForm,
                          blood_glucose: parseFloat(e.target.value || "92"),
                        })
                      }
                      style={{
                        height: "38px",
                        padding: "0 12px",
                        borderRadius: "8px",
                        border: "1px solid #333333",
                        background: "#1C1C1C",
                        color: "#FFFFFF",
                      }}
                    />
                  </label>
                </div>

                <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                  <span style={{ fontSize: "12px", color: "#A3A3A3" }}>
                    Reported Symptoms &amp; Clinical Notes
                  </span>
                  <textarea
                    rows={3}
                    value={checkInForm.subjective_notes}
                    onChange={(e) =>
                      setCheckInForm({ ...checkInForm, subjective_notes: e.target.value })
                    }
                    placeholder="Optional notes (e.g., post-EVA fatigue, mild headache, vestibular sensation)..."
                    style={{
                      padding: "10px 12px",
                      borderRadius: "8px",
                      border: "1px solid #333333",
                      background: "#1C1C1C",
                      color: "#FFFFFF",
                      resize: "vertical",
                    }}
                  />
                </label>

                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: "16px",
                  }}
                >
                  <span style={{ fontSize: "13px", color: "#7DD3FC" }}>{checkInFeedback}</span>
                  <button
                    type="submit"
                    disabled={isSubmittingCheckIn}
                    style={{
                      height: "40px",
                      padding: "0 20px",
                      borderRadius: "8px",
                      border: "none",
                      background: "#E3F5FF",
                      color: "#1C1C1C",
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
                  >
                    {isSubmittingCheckIn ? "Saving..." : "Submit Daily Check-in"}
                  </button>
                </div>
              </form>
            </section>
          )}

          {/* =================================================================
              SCREEN 3: CREW PROFILES & LEAD PROVISIONING PORTAL
          ================================================================= */}
          {activeScreen === "crew" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "28px" }}>
              {/* Crew Sub-navigation */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "12px",
                  background: "#1C1C1C",
                  padding: "6px",
                  borderRadius: "12px",
                  border: "1px solid #333333",
                  width: "fit-content",
                }}
              >
                <button
                  type="button"
                  onClick={() => setCrewSubTab("roster")}
                  style={{
                    border: "none",
                    padding: "8px 16px",
                    borderRadius: "8px",
                    fontSize: "13px",
                    fontWeight: 600,
                    cursor: "pointer",
                    background: crewSubTab === "roster" ? "#333333" : "transparent",
                    color: crewSubTab === "roster" ? "#FFFFFF" : "#A3A3A3",
                  }}
                >
                  Active Crew Roster
                </button>
                <button
                  type="button"
                  onClick={() => setCrewSubTab("lead-provision")}
                  style={{
                    border: "none",
                    padding: "8px 16px",
                    borderRadius: "8px",
                    fontSize: "13px",
                    fontWeight: 600,
                    cursor: "pointer",
                    background: crewSubTab === "lead-provision" ? "#333333" : "transparent",
                    color: crewSubTab === "lead-provision" ? "#7DD3FC" : "#A3A3A3",
                  }}
                >
                  Crew Lead Provisioning Portal {leadToken ? "🟢 (Lead Active)" : "🔒"}
                </button>
              </div>

              {crewSubTab === "roster" ? (
                <>
                  <section
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "16px",
                      padding: "24px",
                      borderRadius: "16px",
                      background: "#282828",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <h1 style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>Active Crew Roster</h1>
                      <span style={{ fontSize: "12px", color: "#A3A3A3" }}>
                        Strict Crew Isolation Enabled (Proximity routing isolates victims to their crew)
                      </span>
                    </div>

                    {crew.length > 0 ? (
                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
                          gap: "16px",
                        }}
                      >
                        {crew.map((c, idx) => (
                          <div
                            key={c.id}
                            style={{
                              padding: "16px",
                              borderRadius: "12px",
                              background: "#1C1C1C",
                              border: "1px solid #333333",
                              display: "flex",
                              flexDirection: "column",
                              gap: "8px",
                            }}
                          >
                            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                              <span
                                style={{
                                  width: "28px",
                                  height: "28px",
                                  borderRadius: "50%",
                                  background: AVATAR_BG[idx % AVATAR_BG.length],
                                  color: "#1C1C1C",
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                  fontSize: "11px",
                                  fontWeight: 600,
                                }}
                              >
                                {getInitials(c.name || c.id)}
                              </span>
                              <div>
                                <div style={{ fontWeight: 600 }}>{c.id}</div>
                                <div style={{ fontSize: "12px", color: "#A3A3A3" }}>{c.name || c.id}</div>
                              </div>
                              <span
                                style={{
                                  marginLeft: "auto",
                                  fontSize: "12px",
                                  color:
                                    c.status === "CRITICAL"
                                      ? "#EF4444"
                                      : c.status === "MEDIUM"
                                      ? "#F59E0B"
                                      : "#96E2D6",
                                }}
                              >
                                {c.status}
                              </span>
                            </div>
                            <div style={{ fontSize: "12px", color: "#A3A3A3" }}>
                              Emergency Contact:{" "}
                              <span style={{ color: "#FFFFFF" }}>{c.emergency_contact_callsign}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <span style={{ color: "#A3A3A3" }}>
                        No crew registered yet. Use the Crew Lead Provisioning Portal tab above to establish your station crew.
                      </span>
                    )}
                  </section>
                </>
              ) : (
                /* Crew Lead Provisioning Portal */
                <section
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "20px",
                    padding: "24px",
                    borderRadius: "16px",
                    background: "#282828",
                    border: "1px solid #333333",
                  }}
                >
                  {!leadToken ? (
                    <div>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "16px" }}>
                        <div>
                          <h2 style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>
                            {leadAuthMode === "login" ? "Station Lead Key Authentication" : "Establish New Space Station & Crew"}
                          </h2>
                          <p style={{ margin: "4px 0 0", fontSize: "12px", color: "#A3A3A3" }}>
                            Space station credentials rely purely on Username and Key (no email or full name required).
                          </p>
                        </div>
                        <div style={{ display: "flex", gap: "8px" }}>
                          <button
                            type="button"
                            onClick={() => setLeadAuthMode("login")}
                            style={{
                              padding: "6px 12px",
                              borderRadius: "6px",
                              border: "none",
                              background: leadAuthMode === "login" ? "#7DD3FC" : "#1C1C1C",
                              color: leadAuthMode === "login" ? "#1C1C1C" : "#A3A3A3",
                              fontWeight: 600,
                              cursor: "pointer",
                              fontSize: "12px",
                            }}
                          >
                            Lead Login
                          </button>
                          <button
                            type="button"
                            onClick={() => setLeadAuthMode("register")}
                            style={{
                              padding: "6px 12px",
                              borderRadius: "6px",
                              border: "none",
                              background: leadAuthMode === "register" ? "#7DD3FC" : "#1C1C1C",
                              color: leadAuthMode === "register" ? "#1C1C1C" : "#A3A3A3",
                              fontWeight: 600,
                              cursor: "pointer",
                              fontSize: "12px",
                            }}
                          >
                            Register Station Lead
                          </button>
                        </div>
                      </div>

                      {leadAuthMode === "login" ? (
                        <form
                          onSubmit={handleLeadLogin}
                          style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                            gap: "16px",
                          }}
                        >
                          <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                            <span style={{ fontSize: "12px", color: "#A3A3A3" }}>Lead Username</span>
                            <input
                              type="text"
                              required
                              value={leadLoginForm.username}
                              onChange={(e) => setLeadLoginForm({ ...leadLoginForm, username: e.target.value })}
                              style={{
                                height: "36px",
                                padding: "0 12px",
                                borderRadius: "8px",
                                border: "1px solid #333333",
                                background: "#1C1C1C",
                                color: "#FFFFFF",
                              }}
                            />
                          </label>
                          <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                            <span style={{ fontSize: "12px", color: "#A3A3A3" }}>Station Access Key</span>
                            <input
                              type="password"
                              required
                              value={leadLoginForm.key}
                              onChange={(e) => setLeadLoginForm({ ...leadLoginForm, key: e.target.value })}
                              style={{
                                height: "36px",
                                padding: "0 12px",
                                borderRadius: "8px",
                                border: "1px solid #333333",
                                background: "#1C1C1C",
                                color: "#FFFFFF",
                              }}
                            />
                          </label>
                          <div style={{ gridColumn: "1 / -1", display: "flex", alignItems: "center", gap: "12px" }}>
                            <button
                              type="submit"
                              style={{
                                height: "36px",
                                padding: "0 20px",
                                borderRadius: "8px",
                                border: "none",
                                background: "#7DD3FC",
                                color: "#1C1C1C",
                                fontWeight: 600,
                                cursor: "pointer",
                              }}
                            >
                              Sign In as Crew Lead
                            </button>
                            {leadFeedback && (
                              <span style={{ fontSize: "12px", color: "#96E2D6" }}>{leadFeedback}</span>
                            )}
                          </div>
                        </form>
                      ) : (
                        <form
                          onSubmit={handleLeadRegister}
                          style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                            gap: "16px",
                          }}
                        >
                          <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                            <span style={{ fontSize: "12px", color: "#A3A3A3" }}>Station Name</span>
                            <input
                              type="text"
                              required
                              placeholder="e.g. Hermes Orbital Station"
                              value={leadRegisterForm.station_name}
                              onChange={(e) =>
                                setLeadRegisterForm({ ...leadRegisterForm, station_name: e.target.value })
                              }
                              style={{
                                height: "36px",
                                padding: "0 12px",
                                borderRadius: "8px",
                                border: "1px solid #333333",
                                background: "#1C1C1C",
                                color: "#FFFFFF",
                              }}
                            />
                          </label>
                          <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                            <span style={{ fontSize: "12px", color: "#A3A3A3" }}>Crew Name</span>
                            <input
                              type="text"
                              required
                              placeholder="e.g. Crew-Alpha"
                              value={leadRegisterForm.crew_name}
                              onChange={(e) =>
                                setLeadRegisterForm({ ...leadRegisterForm, crew_name: e.target.value })
                              }
                              style={{
                                height: "36px",
                                padding: "0 12px",
                                borderRadius: "8px",
                                border: "1px solid #333333",
                                background: "#1C1C1C",
                                color: "#FFFFFF",
                              }}
                            />
                          </label>
                          <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                            <span style={{ fontSize: "12px", color: "#A3A3A3" }}>Lead Username</span>
                            <input
                              type="text"
                              required
                              value={leadRegisterForm.username}
                              onChange={(e) =>
                                setLeadRegisterForm({ ...leadRegisterForm, username: e.target.value })
                              }
                              style={{
                                height: "36px",
                                padding: "0 12px",
                                borderRadius: "8px",
                                border: "1px solid #333333",
                                background: "#1C1C1C",
                                color: "#FFFFFF",
                              }}
                            />
                          </label>
                          <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                            <span style={{ fontSize: "12px", color: "#A3A3A3" }}>Lead Station Key</span>
                            <input
                              type="password"
                              required
                              value={leadRegisterForm.key}
                              onChange={(e) =>
                                setLeadRegisterForm({ ...leadRegisterForm, key: e.target.value })
                              }
                              style={{
                                height: "36px",
                                padding: "0 12px",
                                borderRadius: "8px",
                                border: "1px solid #333333",
                                background: "#1C1C1C",
                                color: "#FFFFFF",
                              }}
                            />
                          </label>
                          <div style={{ gridColumn: "1 / -1", display: "flex", alignItems: "center", gap: "12px" }}>
                            <button
                              type="submit"
                              style={{
                                height: "36px",
                                padding: "0 20px",
                                borderRadius: "8px",
                                border: "none",
                                background: "#7DD3FC",
                                color: "#1C1C1C",
                                fontWeight: 600,
                                cursor: "pointer",
                              }}
                            >
                              Register &amp; Establish Station Crew
                            </button>
                            {leadFeedback && (
                              <span style={{ fontSize: "12px", color: "#96E2D6" }}>{leadFeedback}</span>
                            )}
                          </div>
                        </form>
                      )}
                    </div>
                  ) : (
                    /* Authenticated Crew Lead Session: Provision Crew Members */
                    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          padding: "16px",
                          borderRadius: "12px",
                          background: "#1C1C1C",
                          border: "1px solid #333333",
                        }}
                      >
                        <div>
                          <div style={{ fontSize: "14px", fontWeight: 600, color: "#FFFFFF" }}>
                            Crew Lead: <span style={{ color: "#7DD3FC" }}>{leadProfile?.username}</span>
                          </div>
                          <div style={{ fontSize: "12px", color: "#A3A3A3", marginTop: "2px" }}>
                            Station: <strong>{leadProfile?.station_name}</strong> | Crew Division:{" "}
                            <strong>{leadProfile?.crew_name}</strong>
                          </div>
                          <div style={{ fontSize: "11px", color: "#96E2D6", marginTop: "4px" }}>
                            🔒 Strict Crew Isolation Active: Proximity alarm search only scans astronauts within {leadProfile?.crew_name}.
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            setLeadToken("");
                            setLeadProfile(null);
                            setLeadFeedback("Lead session ended.");
                          }}
                          style={{
                            padding: "6px 14px",
                            borderRadius: "8px",
                            border: "1px solid #444444",
                            background: "transparent",
                            color: "#A3A3A3",
                            fontSize: "12px",
                            cursor: "pointer",
                          }}
                        >
                          Sign Out
                        </button>
                      </div>

                      <div>
                        <h3 style={{ margin: "0 0 12px 0", fontSize: "14px", fontWeight: 600 }}>
                          Provision New Crew Member for {leadProfile?.crew_name}
                        </h3>
                        <p style={{ margin: "0 0 16px 0", fontSize: "12px", color: "#A3A3A3" }}>
                          No roles or full names needed. Specify username and key to grant secure station bio-telemetry access.
                        </p>

                        <form
                          onSubmit={handleProvisionMember}
                          style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                            gap: "16px",
                          }}
                        >
                          <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                            <span style={{ fontSize: "12px", color: "#A3A3A3" }}>Astronaut Username</span>
                            <input
                              type="text"
                              required
                              placeholder="e.g. astro_cooper"
                              value={provisionMemberForm.username}
                              onChange={(e) =>
                                setProvisionMemberForm({ ...provisionMemberForm, username: e.target.value })
                              }
                              style={{
                                height: "36px",
                                padding: "0 12px",
                                borderRadius: "8px",
                                border: "1px solid #333333",
                                background: "#1C1C1C",
                                color: "#FFFFFF",
                              }}
                            />
                          </label>
                          <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                            <span style={{ fontSize: "12px", color: "#A3A3A3" }}>Station Key</span>
                            <input
                              type="password"
                              required
                              placeholder="Station access key"
                              value={provisionMemberForm.key}
                              onChange={(e) =>
                                setProvisionMemberForm({ ...provisionMemberForm, key: e.target.value })
                              }
                              style={{
                                height: "36px",
                                padding: "0 12px",
                                borderRadius: "8px",
                                border: "1px solid #333333",
                                background: "#1C1C1C",
                                color: "#FFFFFF",
                              }}
                            />
                          </label>
                          <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                            <span style={{ fontSize: "12px", color: "#A3A3A3" }}>Callsign (Optional)</span>
                            <input
                              type="text"
                              placeholder="e.g. ASTRO-09"
                              value={provisionMemberForm.callsign}
                              onChange={(e) =>
                                setProvisionMemberForm({ ...provisionMemberForm, callsign: e.target.value })
                              }
                              style={{
                                height: "36px",
                                padding: "0 12px",
                                borderRadius: "8px",
                                border: "1px solid #333333",
                                background: "#1C1C1C",
                                color: "#FFFFFF",
                              }}
                            />
                          </label>
                          <div style={{ gridColumn: "1 / -1", display: "flex", alignItems: "center", gap: "12px" }}>
                            <button
                              type="submit"
                              style={{
                                height: "36px",
                                padding: "0 20px",
                                borderRadius: "8px",
                                border: "none",
                                background: "#7DD3FC",
                                color: "#1C1C1C",
                                fontWeight: 600,
                                cursor: "pointer",
                              }}
                            >
                              + Provision Member for {leadProfile?.crew_name}
                            </button>
                            {leadFeedback && (
                              <span style={{ fontSize: "12px", color: "#96E2D6" }}>{leadFeedback}</span>
                            )}
                          </div>
                        </form>
                      </div>
                    </div>
                  )}
                </section>
              )}
            </div>
          )}

          {/* =================================================================
              SCREEN 4: SPACE HAZARDS (Dual-Classifier Triage Engine)
          ================================================================= */}
          {activeScreen === "hazards" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "28px" }}>
              {triage ? (
                <>
                  <section
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "16px",
                      padding: "24px",
                      borderRadius: "16px",
                      background: "#282828",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                      }}
                    >
                      <h1 style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>
                        NASA 5 Spaceflight Hazards · {triage.astronaut_id} (Sol {triage.mission_day})
                      </h1>
                      <span
                        style={{
                          padding: "4px 10px",
                          borderRadius: "8px",
                          background: "#1C1C1C",
                          color:
                            triage.overall_status === "CRITICAL"
                              ? "#EF4444"
                              : triage.overall_status === "NOMINAL"
                              ? "#96E2D6"
                              : "#F59E0B",
                          fontWeight: 600,
                          fontSize: "12px",
                        }}
                      >
                        {triage.overall_status} · Risk {triage.overall_risk_score}/100
                      </span>
                    </div>

                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                        gap: "16px",
                      }}
                    >
                      {[
                        {
                          label: "Space Radiation",
                          score: triage.hazards.radiation_score,
                          color: "#C6C7F8",
                        },
                        {
                          label: "Microgravity Strain",
                          score: triage.hazards.microgravity_score,
                          color: "#1CC8FF",
                        },
                        {
                          label: "Isolation & Circadian",
                          score: triage.hazards.isolation_score,
                          color: "#96E2D6",
                        },
                        {
                          label: "Hostile Habitat",
                          score: triage.hazards.hostile_env_score,
                          color: "#95A4FC",
                        },
                        {
                          label: "Earth Distance",
                          score: triage.hazards.distance_score,
                          color: "#A8C5DA",
                        },
                      ].map((hz) => (
                        <div
                          key={hz.label}
                          style={{
                            padding: "16px",
                            borderRadius: "12px",
                            background: "#1C1C1C",
                            border: "1px solid #333333",
                            display: "flex",
                            flexDirection: "column",
                            gap: "8px",
                          }}
                        >
                          <span style={{ fontSize: "12px", color: "#A3A3A3" }}>{hz.label}</span>
                          <span style={{ fontSize: "20px", fontWeight: 600 }}>{hz.score}%</span>
                          <div style={{ height: "4px", borderRadius: "2px", background: "#333333" }}>
                            <div
                              style={{
                                width: `${Math.min(100, hz.score)}%`,
                                height: "100%",
                                borderRadius: "2px",
                                background: hz.color,
                              }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>

                  <section
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "16px",
                      padding: "24px",
                      borderRadius: "16px",
                      background: "#282828",
                    }}
                  >
                    <h2 style={{ margin: 0, fontSize: "14px", fontWeight: 600 }}>
                      Classifier 1 · Individual Metric Severity (NASA-STD-3001)
                    </h2>
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                        gap: "12px",
                      }}
                    >
                      {Object.values(triage.metric_evaluations || {}).map((ev: any) => (
                        <div
                          key={ev.metric_name}
                          style={{
                            padding: "14px",
                            borderRadius: "12px",
                            background: "#1C1C1C",
                            border: "1px solid #333333",
                            display: "flex",
                            flexDirection: "column",
                            gap: "4px",
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between" }}>
                            <span style={{ fontWeight: 600 }}>{ev.label}</span>
                            <span
                              style={{
                                fontSize: "12px",
                                color:
                                  ev.status === "CRITICAL"
                                    ? "#EF4444"
                                    : ev.status === "MEDIUM"
                                    ? "#F59E0B"
                                    : "#96E2D6",
                              }}
                            >
                              {ev.status}
                            </span>
                          </div>
                          <span style={{ fontSize: "18px", fontWeight: 600 }}>
                            {ev.value} {ev.unit}
                          </span>
                          <span style={{ fontSize: "12px", color: "#A3A3A3" }}>
                            Nominal: {ev.nominal_range}
                          </span>
                        </div>
                      ))}
                    </div>
                  </section>
                </>
              ) : (
                <section
                  style={{
                    padding: "24px",
                    borderRadius: "16px",
                    background: "#282828",
                    color: "#A3A3A3",
                  }}
                >
                  No telemetry logged yet. Submit a Daily Check-in to run Dual-Classifier Space
                  Hazard Triage.
                </section>
              )}
            </div>
          )}

          {/* =================================================================
              SCREEN 5: ALERTS & DEAD-MAN'S SWITCH ESCALATION
          ================================================================= */}
          {activeScreen === "alerts" && (
            <section
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "16px",
                padding: "24px",
                borderRadius: "16px",
                background: "#282828",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <h1 style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>
                  Clinical Alerts &amp; Intra-Crew Dead-Man&apos;s Switch
                </h1>
                <button
                  type="button"
                  onClick={handleCheckTimeout}
                  style={{
                    height: "32px",
                    padding: "0 12px",
                    borderRadius: "8px",
                    border: "1px solid #333333",
                    background: "#1C1C1C",
                    color: "#FFFFFF",
                    fontSize: "12px",
                    cursor: "pointer",
                  }}
                >
                  Evaluate Timeouts
                </button>
              </div>

              {allAlarms.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                  {allAlarms.map((al) => (
                    <div
                      key={al.alert_id}
                      style={{
                        padding: "16px",
                        borderRadius: "12px",
                        background: al.acknowledged ? "#1C1C1C" : "#3B2323",
                        border: `1px solid ${al.acknowledged ? "#333333" : "#EF4444"}`,
                        display: "flex",
                        flexDirection: "column",
                        gap: "8px",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                        }}
                      >
                        <span style={{ fontWeight: 600 }}>
                          {al.astronaut_id} · {al.hazard_origin}
                        </span>
                        <span
                          style={{
                            fontFamily: "'JetBrains Mono', monospace",
                            fontSize: "12px",
                            color: al.acknowledged ? "#96E2D6" : "#FCA5A5",
                          }}
                        >
                          {al.status}
                        </span>
                      </div>
                      <div style={{ fontSize: "13px", color: "#A3A3A3" }}>{al.message}</div>
                      <div style={{ fontSize: "12px", color: "#A3A3A3" }}>
                        Designated Emergency Contact:{" "}
                        <span style={{ color: "#FFFFFF" }}>
                          {al.emergency_contact_callsign || "CREW-MED"} (
                          {al.emergency_contact_name || "Medical Officer"})
                        </span>
                      </div>
                      {!al.acknowledged && (
                        <div style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
                          <button
                            type="button"
                            onClick={() => handleAnswerAsOwner(al.alert_id)}
                            style={{
                              height: "34px",
                              padding: "0 14px",
                              borderRadius: "8px",
                              border: "1px solid #F87171",
                              background: "transparent",
                              color: "#FFFFFF",
                              fontSize: "13px",
                              cursor: "pointer",
                            }}
                          >
                            Answer as Owner
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              handleAckAsContact(
                                al.alert_id,
                                al.emergency_contact_callsign || "CREW-MED"
                              )
                            }
                            style={{
                              height: "34px",
                              padding: "0 14px",
                              borderRadius: "8px",
                              border: "none",
                              background: "#EF4444",
                              color: "#1C1C1C",
                              fontWeight: 600,
                              fontSize: "13px",
                              cursor: "pointer",
                            }}
                          >
                            Acknowledge as Emergency Contact
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <span style={{ color: "#A3A3A3" }}>
                  No alerts recorded in the database. Alerts trigger automatically when a Daily
                  Check-in or forecast crosses NASA clinical thresholds.
                </span>
              )}
            </section>
          )}

          {/* =================================================================
              SCREEN 6: THRESHOLDS (NASA-STD-3001 Reference)
          ================================================================= */}
          {activeScreen === "thresholds" && (
            <section
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "16px",
                padding: "24px",
                borderRadius: "16px",
                background: "#282828",
              }}
            >
              <h1 style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>
                NASA-STD-3001 Clinical Thresholds
              </h1>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                  gap: "12px",
                }}
              >
                {[
                  { name: "Heart rate", nominal: "50 – 90 BPM", critical: "≥ 115 or ≤ 45 BPM" },
                  { name: "SpO₂", nominal: "96.0 – 100.0%", critical: "< 93.0%" },
                  { name: "Sleep duration", nominal: "6.5 – 9.0 h", critical: "< 4.5 h" },
                  {
                    name: "Radiation dose",
                    nominal: "0.0 – 2.0 mSv/d",
                    critical: "≥ 20.0 mSv/d (SPE)",
                  },
                  {
                    name: "Systolic BP",
                    nominal: "90 – 130 mmHg",
                    critical: "≥ 140 or ≤ 85 mmHg",
                  },
                  {
                    name: "Core temperature",
                    nominal: "36.5 – 37.5 °C",
                    critical: "≥ 38.2 or ≤ 35.5 °C",
                  },
                ].map((t) => (
                  <div
                    key={t.name}
                    style={{
                      padding: "14px",
                      borderRadius: "12px",
                      background: "#1C1C1C",
                      border: "1px solid #333333",
                    }}
                  >
                    <div style={{ fontWeight: 600 }}>{t.name}</div>
                    <div style={{ fontSize: "12px", color: "#96E2D6", marginTop: "4px" }}>
                      Nominal: {t.nominal}
                    </div>
                    <div style={{ fontSize: "12px", color: "#FCA5A5" }}>Critical: {t.critical}</div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </main>
      </div>

      {/* =====================================================================
          RIGHT SIDEBAR (280px, #1C1C1C, border #333333)
      ===================================================================== */}
      {showRightPanel && (
        <div style={{ flex: "0 0 280px", borderLeft: "1px solid #333333" }}>
          <aside
            aria-label="Alerts and crew"
            style={{
              width: "100%",
              minHeight: "100%",
              boxSizing: "border-box",
              display: "flex",
              flexDirection: "column",
              gap: "24px",
              padding: "20px",
              background: "#1C1C1C",
              color: "#FFFFFF",
            }}
          >
            {/* Alerts Feed */}
            <section style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              <h2 style={{ margin: 0, padding: "8px 4px", fontSize: "14px", fontWeight: 600 }}>
                Alerts
              </h2>
              {allAlarms.length > 0 ? (
                allAlarms.slice(0, 4).map((al) => (
                  <button
                    key={al.alert_id}
                    type="button"
                    onClick={() => setActiveScreen("alerts")}
                    style={{
                      display: "flex",
                      gap: "8px",
                      padding: "8px 4px",
                      borderRadius: "8px",
                      color: "#FFFFFF",
                      background: "transparent",
                      border: "none",
                      cursor: "pointer",
                      textAlign: "left",
                    }}
                  >
                    <span
                      style={{
                        width: "24px",
                        height: "24px",
                        flexShrink: 0,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        borderRadius: "8px",
                        background: al.severity.includes("CRITICAL") ? "#EF4444" : "#F59E0B",
                      }}
                    >
                      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
                        <path d="M6 0.5 L11.5 6 L6 11.5 L0.5 6 Z" fill="#1C1C1C" />
                      </svg>
                    </span>
                    <span style={{ display: "flex", flexDirection: "column" }}>
                      <span>
                        {al.astronaut_id} · {al.severity}
                      </span>
                      <span style={{ fontSize: "12px", lineHeight: "16px", color: "#A3A3A3" }}>
                        {al.status}
                      </span>
                    </span>
                  </button>
                ))
              ) : (
                <span style={{ padding: "4px", fontSize: "12px", color: "#6B6B6B" }}>
                  No alerts recorded
                </span>
              )}
            </section>

            {/* Crew Status List */}
            <section style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <h2 style={{ margin: 0, padding: "8px 4px", fontSize: "14px", fontWeight: 600 }}>
                Crew
              </h2>
              {crew.length > 0 ? (
                crew.map((m, idx) => (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => setSelectedAstroId(m.id === selectedAstroId ? "" : m.id)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      height: "40px",
                      padding: "0 4px",
                      color: "#FFFFFF",
                      background: "transparent",
                      border: "none",
                      cursor: "pointer",
                      textAlign: "left",
                    }}
                  >
                    <span
                      style={{
                        width: "24px",
                        height: "24px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        borderRadius: "50%",
                        background: AVATAR_BG[idx % AVATAR_BG.length],
                        color: "#1C1C1C",
                        fontSize: "10px",
                        fontWeight: 600,
                      }}
                    >
                      {getInitials(m.name)}
                    </span>
                    <span>{m.name}</span>
                    <span
                      style={{
                        marginLeft: "auto",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "4px",
                        fontSize: "12px",
                        color:
                          m.status === "CRITICAL"
                            ? "#F87171"
                            : m.status === "MEDIUM"
                            ? "#F59E0B"
                            : "#96E2D6",
                      }}
                    >
                      {m.status === "CRITICAL"
                        ? "Warning"
                        : m.status === "MEDIUM"
                        ? "Caution"
                        : "Nominal"}
                    </span>
                  </button>
                ))
              ) : (
                <span style={{ padding: "4px", fontSize: "12px", color: "#6B6B6B" }}>
                  No crew in database
                </span>
              )}
            </section>
          </aside>
        </div>
      )}

      {/* =====================================================================
          FLOATING CIRCULAR BOT ICON + INTERACTIVE EXPANDABLE CHAT DIALOG
      ===================================================================== */}
      {!isChatOpen && (
        <button
          type="button"
          onClick={() => setIsChatOpen(true)}
          aria-label="Open AstroDoc AI Flight Surgeon"
          title="Open AstroDoc AI Flight Surgeon"
          style={{
            position: "fixed",
            bottom: "24px",
            right: "24px",
            zIndex: 60,
            width: "52px",
            height: "52px",
            borderRadius: "50%",
            background: "#E3F5FF",
            color: "#1C1C1C",
            border: "1px solid #333333",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
            boxShadow: "0 8px 24px rgba(0,0,0,0.45)",
          }}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <rect x="4" y="6" width="16" height="12" rx="4" stroke="#1C1C1C" strokeWidth="1.8" />
            <path d="M12 3 V6" stroke="#1C1C1C" strokeWidth="1.8" strokeLinecap="round" />
            <circle cx="9.5" cy="12" r="1.3" fill="#1C1C1C" />
            <circle cx="14.5" cy="12" r="1.3" fill="#1C1C1C" />
          </svg>
        </button>
      )}

      {isChatOpen && (
        <div
          role="dialog"
          aria-label="AstroDoc AI Flight Surgeon"
          style={{
            position: "fixed",
            bottom: "24px",
            right: "24px",
            zIndex: 60,
            width: isChatExpanded ? "min(840px, calc(100vw - 32px))" : "min(400px, calc(100vw - 32px))",
            height: isChatExpanded ? "min(720px, calc(100vh - 48px))" : "min(540px, calc(100vh - 48px))",
            background: "#282828",
            border: "1px solid #333333",
            borderRadius: "16px",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            boxShadow: "0 16px 48px rgba(0,0,0,0.65)",
            transition: "width 0.18s ease, height 0.18s ease",
          }}
        >
          {/* Dialog Header */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "14px 16px",
              background: "#1C1C1C",
              borderBottom: "1px solid #333333",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <span
                style={{
                  width: "28px",
                  height: "28px",
                  borderRadius: "50%",
                  background: "#E3F5FF",
                  color: "#1C1C1C",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <rect
                    x="4"
                    y="6"
                    width="16"
                    height="12"
                    rx="4"
                    stroke="#1C1C1C"
                    strokeWidth="2"
                  />
                  <circle cx="9.5" cy="12" r="1.4" fill="#1C1C1C" />
                  <circle cx="14.5" cy="12" r="1.4" fill="#1C1C1C" />
                </svg>
              </span>
              <div>
                <div style={{ fontWeight: 600, fontSize: "14px", color: "#FFFFFF" }}>
                  AstroDoc Flight Surgeon
                </div>
                <div style={{ fontSize: "11px", color: "#A3A3A3" }}>
                  NASA RAG Clinical Assistant
                </div>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              {/* Expand / Collapse Icon Button */}
              <button
                type="button"
                onClick={() => setIsChatExpanded((v) => !v)}
                aria-label={isChatExpanded ? "Collapse chat" : "Expand chat"}
                title={isChatExpanded ? "Collapse" : "Expand"}
                style={{
                  width: "32px",
                  height: "32px",
                  borderRadius: "8px",
                  border: "none",
                  background: "transparent",
                  color: "#A3A3A3",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  cursor: "pointer",
                }}
              >
                {isChatExpanded ? (
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <path
                      d="M6 2 V6 H2 M10 14 V10 H14 M14 6 H10 V2 M2 10 H6 V14"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                ) : (
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <path
                      d="M10 2 H14 V6 M6 14 H2 V10 M14 2 L9.5 6.5 M2 14 L6.5 9.5"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                )}
              </button>

              {/* Close Button */}
              <button
                type="button"
                onClick={() => setIsChatOpen(false)}
                aria-label="Close chat"
                title="Close"
                style={{
                  width: "32px",
                  height: "32px",
                  borderRadius: "8px",
                  border: "none",
                  background: "transparent",
                  color: "#A3A3A3",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  cursor: "pointer",
                }}
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <path
                    d="M4 4 L12 12 M12 4 L4 12"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                  />
                </svg>
              </button>
            </div>
          </div>

          {/* Messages List */}
          <div
            style={{
              flex: 1,
              overflowY: "auto",
              padding: "16px",
              display: "flex",
              flexDirection: "column",
              gap: "12px",
              background: "#1C1C1C",
            }}
          >
            {chatHistory.length > 0 ? (
              chatHistory.map((msg) => (
                <div
                  key={msg.id}
                  style={{
                    alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
                    maxWidth: "85%",
                    padding: "10px 14px",
                    borderRadius: "12px",
                    background: msg.role === "user" ? "#E3F5FF" : "#282828",
                    color: msg.role === "user" ? "#1C1C1C" : "#FFFFFF",
                    fontSize: "13px",
                    lineHeight: "19px",
                  }}
                >
                  <div style={{ whiteSpace: "pre-wrap" }}>{msg.content}</div>
                  {msg.citations && msg.citations.length > 0 && (
                    <div style={{ marginTop: "6px", fontSize: "11px", color: "#A3A3A3" }}>
                      Refs: {msg.citations.join(" · ")}
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div
                style={{
                  margin: "auto",
                  textAlign: "center",
                  color: "#6B6B6B",
                  fontSize: "13px",
                  maxWidth: "260px",
                }}
              >
                Ask AstroDoc about crew vitals, radiation protocols, SpO₂ drops, or countermeasures.
              </div>
            )}
            {chatError && (
              <div style={{ fontSize: "12px", color: "#FCA5A5", textAlign: "center" }}>
                {chatError}
              </div>
            )}
          </div>

          {/* Input Bar */}
          <form
            onSubmit={handleSendChat}
            style={{
              display: "flex",
              gap: "8px",
              padding: "12px 16px",
              background: "#282828",
              borderTop: "1px solid #333333",
            }}
          >
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder="Ask AstroDoc..."
              style={{
                flex: 1,
                height: "38px",
                padding: "0 12px",
                borderRadius: "8px",
                border: "1px solid #333333",
                background: "#1C1C1C",
                color: "#FFFFFF",
                fontSize: "13px",
                outline: "none",
              }}
            />
            <button
              type="submit"
              disabled={isSendingChat}
              style={{
                height: "38px",
                padding: "0 16px",
                borderRadius: "8px",
                border: "none",
                background: "#E3F5FF",
                color: "#1C1C1C",
                fontWeight: 600,
                fontSize: "13px",
                cursor: "pointer",
              }}
            >
              {isSendingChat ? "..." : "Send"}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
