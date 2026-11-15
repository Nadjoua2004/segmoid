"use client";

import React, { useState, useEffect, useCallback } from "react";
import { api, CrewSummaryItem, ChatHistoryItem } from "@/lib/api";
import {
  HealthMetrics,
  EmergencyAlert,
  TriageResult,
  PredictionResult,
  DailyCheckInPayload,
  GlucoseContext,
  SymptomKey,
} from "@/lib/types";
import { SYMPTOMS, GLUCOSE_CONTEXT, RATINGS } from "@/lib/healthIndicators";
import { DailyCheckInModal } from "@/components/DailyCheckInModal";
import { StationLoginPage } from "@/components/StationLoginPage";
import { HologramModel3D } from "@/components/HologramModel3D";
import {
  Button,
  EmptyState,
  InlineError,
  MetricCard,
  Panel,
  PanelHeader,
  SegmentedTabs,
  Spinner,
  StatusBadge,
  toStatus,
  type StatusKey,
} from "@/components/bio";

type ChartMetric = "spo2" | "heart_rate" | "sleep";

const VITAL_RANGES = {
  heart_rate: "50–90 bpm",
  spo2: "96.0–100.0%",
  sleep_hours: "6.5–9.0 h",
  radiation_msv: "0.0–2.0 mSv/d",
} as const;

const VITAL_LABELS = ["Heart rate", "SpO₂", "Sleep", "Core temp", "Radiation dose"] as const;

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

function renderFormattedChatText(content: string): React.ReactNode {
  return content.split("\n").map((line, lineIdx, arr) => {
    const parts = line.split(/(\*\*[^*]+\*\*)/g);
    return (
      <React.Fragment key={lineIdx}>
        {parts.map((part, pIdx) =>
          part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
            <strong key={pIdx} style={{ fontWeight: 700 }}>
              {part.slice(2, -2)}
            </strong>
          ) : (
            <React.Fragment key={pIdx}>{part}</React.Fragment>
          )
        )}
        {lineIdx < arr.length - 1 && <br />}
      </React.Fragment>
    );
  });
}

export default function AegisBioApp() {
  const [activeScreen, setActiveScreen] = useState<ScreenId>("overview");
  const [selectedAstroId, setSelectedAstroId] = useState<string>("");
  const [showLeftNav, setShowLeftNav] = useState<boolean>(true);
  const [showRightPanel, setShowRightPanel] = useState<boolean>(false);
  const [chartMetric, setChartMetric] = useState<ChartMetric>("spo2");

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
  const [forecastError, setForecastError] = useState<string>("");

  // Crew Lead Authentication & Provisioning State
  const [crewSubTab, setCrewSubTab] = useState<"roster" | "lead-provision">("roster");
  const [isAuthChecked, setIsAuthChecked] = useState<boolean>(false);
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
    environment: "LUNAR",
  });
  const [provisionMemberForm, setProvisionMemberForm] = useState({
    username: "astro_01",
    key: "astro_01_key",
    callsign: "ASTRO-01",
  });
  const [leadFeedback, setLeadFeedback] = useState<string>("");
  const [isModalCheckInOpen, setIsModalCheckInOpen] = useState<boolean>(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState<boolean>(false);
  const [justCheckedInAstroIds, setJustCheckedInAstroIds] = useState<string[]>([]);
  const [nowTick, setNowTick] = useState<number>(() => Date.now());

  // Periodic daytime check (every 60s) to automatically surface / unsnooze daily check-in reminders
  useEffect(() => {
    const id = setInterval(() => {
      setNowTick(Date.now());
    }, 60_000);
    return () => clearInterval(id);
  }, []);

  // Restore Station Session from LocalStorage (keeps user signed in across reloads)
  useEffect(() => {
    let cancelled = false;
    const restoreSession = async () => {
      try {
        const savedToken = localStorage.getItem("aegis_station_token");
        const savedProfileRaw = localStorage.getItem("aegis_station_profile");
        if (savedToken) {
          setLeadToken(savedToken);
          let parsedProfile: any = null;
          if (savedProfileRaw && savedProfileRaw !== "undefined") {
            try {
              parsedProfile = JSON.parse(savedProfileRaw);
            } catch {
              parsedProfile = null;
            }
          }
          if (parsedProfile) {
            setLeadProfile(parsedProfile);
            const astroId = parsedProfile.callsign || parsedProfile.username;
            if (astroId) {
              setSelectedAstroId((prev) => prev || astroId);
              setCheckInForm((prev) => ({ ...prev, astronaut_id: astroId }));
            }
          }
          // Silently refresh profile from backend; only sign out on explicit 401/403
          try {
            const fresh = await api.getMyProfile(savedToken);
            if (!cancelled && fresh) {
              setLeadProfile(fresh);
              localStorage.setItem("aegis_station_profile", JSON.stringify(fresh));
              const astroId = fresh.callsign || fresh.username;
              if (astroId) {
                setSelectedAstroId((prev) => prev || astroId);
                setCheckInForm((prev) => ({ ...prev, astronaut_id: astroId }));
              }
            }
          } catch (err: any) {
            if (!cancelled && err?.status === 401) {
              localStorage.removeItem("aegis_station_token");
              localStorage.removeItem("aegis_station_profile");
              setLeadToken("");
              setLeadProfile(null);
              setChatHistory([]);
            }
          }
        }
      } catch {
        // ignore storage access issues
      } finally {
        if (!cancelled) setIsAuthChecked(true);
      }
    };
    restoreSession();
    return () => {
      cancelled = true;
    };
  }, []);

  // Unified Daily Check-in Form State (All 44 Classifier Metrics)
  const [checkInForm, setCheckInForm] = useState<HealthMetrics>({
    astronaut_id: "ASTRO-7702-HELENA",
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
  const [checkInExtras, setCheckInExtras] = useState<{
    glucose_context: GlucoseContext;
    bedtime: string;
    wake_time: string;
    sleep_quality: number;
    sleep_medication: boolean;
    energy_level: number;
    stress_level: number;
    cardio_minutes: number;
    resistance_minutes: number;
    calories_kcal: number;
    water_liters: number;
    breakfast: boolean;
    lunch: boolean;
    dinner: boolean;
    vitamin_d_taken: boolean;
    radiation_badge_worn: boolean;
    cabin_temp_c: number;
    ear_protection_used: boolean;
    symptoms: SymptomKey[];
  }>({
    glucose_context: "fasting",
    bedtime: "22:30",
    wake_time: "06:30",
    sleep_quality: 4,
    sleep_medication: false,
    energy_level: 4,
    stress_level: 4,
    cardio_minutes: 70,
    resistance_minutes: 60,
    calories_kcal: 2600,
    water_liters: 2.4,
    breakfast: true,
    lunch: true,
    dinner: true,
    vitamin_d_taken: true,
    radiation_badge_worn: true,
    cabin_temp_c: 22.5,
    ear_protection_used: true,
    symptoms: [],
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

  const myChatAstroId = leadProfile?.callsign || leadProfile?.username || "";

  const loadAllData = useCallback(
    async (astroFilter?: string, customScale?: "DAILY" | "WEEKLY" | "MONTHLY") => {
      if (!leadToken) return;
      const myId = leadProfile?.callsign || leadProfile?.username;
      const targetAstro = leadProfile?.is_lead
        ? (astroFilter !== undefined ? astroFilter : selectedAstroId || undefined)
        : (myId || undefined);
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
        myId ? api.getChatHistory(myId) : Promise.resolve([]),
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
    [selectedAstroId, timeScale, leadProfile, leadToken]
  );

  const handleTimeScaleChange = async (newScale: "DAILY" | "WEEKLY" | "MONTHLY") => {
    setTimeScale(newScale);
    setIsLoadingForecast(true);
    setForecastError("");
    try {
      const horizon = newScale === "DAILY" ? 24 : newScale === "MONTHLY" ? 30 : 7;
      const res = await api.getTrajectoryForecast(selectedAstroId || undefined, horizon, newScale);
      setForecast(res);
    } catch (err: any) {
      console.error("Failed to load forecast for scale:", newScale, err);
      setForecastError(err?.message || "Unable to calculate trajectory forecast.");
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
      const u = res.user || res;
      const prof = {
        username: u.username,
        station_name: u.station_name,
        crew_name: u.crew_name,
        callsign: u.callsign,
        is_lead: u.is_lead,
      };
      setChatHistory([]);
      setLeadToken(res.access_token);
      setLeadProfile(prof);
      try {
        localStorage.setItem("aegis_station_token", res.access_token);
        localStorage.setItem("aegis_station_profile", JSON.stringify(prof));
      } catch {
        // ignore
      }
      setLeadFeedback(`Authenticated as Crew Lead for ${prof.crew_name} on ${prof.station_name}`);
      setIsAuthModalOpen(false);
    } catch (err: any) {
      setLeadFeedback(`Login failed: ${err.message}`);
    }
  };

  const handleLeadRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLeadFeedback("");
    try {
      const res = await api.registerLead(leadRegisterForm);
      const u = res.user || res;
      const prof = {
        username: u.username,
        station_name: u.station_name,
        crew_name: u.crew_name,
        callsign: u.callsign,
        is_lead: u.is_lead,
      };
      setChatHistory([]);
      setLeadToken(res.access_token);
      setLeadProfile(prof);
      try {
        localStorage.setItem("aegis_station_token", res.access_token);
        localStorage.setItem("aegis_station_profile", JSON.stringify(prof));
      } catch {
        // ignore
      }
      setLeadFeedback(`Station Lead registered: ${prof.crew_name} on ${prof.station_name}`);
      setIsAuthModalOpen(false);
    } catch (err: any) {
      setLeadFeedback(`Registration failed: ${err.message}`);
    }
  };

  const handleSignOut = () => {
    setLeadToken("");
    setLeadProfile(null);
    setSelectedAstroId("");
    setChatHistory([]);
    setChatError("");
    setIsChatOpen(false);
    setCrew([]);
    setHistory([]);
    setLatestMetrics(null);
    setTriage(null);
    setForecast(null);
    setActiveAlert(null);
    setAllAlarms([]);
    setJustCheckedInAstroIds([]);
    try {
      localStorage.removeItem("aegis_station_token");
      localStorage.removeItem("aegis_station_profile");
    } catch {
      // ignore
    }
    setLeadFeedback("Signed out of station console.");
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

  // Helper to send classifier results directly to AstroDoc chatbot and auto-open interface
  const dispatchClassifierResultsToChatbot = async (
    astroId: string,
    prompt: string
  ) => {
    const chatOwner = myChatAstroId || astroId;
    // 1. Immediately open and expand the chatbot interface
    setIsChatOpen(true);
    setIsChatExpanded(true);

    // 2. Append optimistic user turn so prompt appears immediately
    const userTurn: ChatHistoryItem = {
      id: Date.now(),
      astronaut_id: chatOwner,
      role: "user",
      content: prompt,
      citations: [],
      timestamp: new Date().toISOString(),
    };
    setChatHistory((prev) => [...prev, userTurn]);

    // 3. Query the flight surgeon model for clinical directives & what to do next
    try {
      const reply = await api.queryFlightSurgeon(prompt, astroId);
      const assistantTurn: ChatHistoryItem = {
        id: Date.now() + 1,
        astronaut_id: chatOwner,
        role: "assistant",
        content: reply.content,
        citations: reply.citations || [],
        timestamp: reply.timestamp || new Date().toISOString(),
      };
      setChatHistory((prev) => [...prev, assistantTurn]);
    } catch (err: any) {
      console.error("Failed to query chatbot with classifier results:", err);
      setChatError("Could not retrieve autonomous recommendations from AstroDoc.");
    }
  };

  // Submit Unified Daily Check-in Form
  const handleCheckInSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmittingCheckIn(true);
    setCheckInFeedback("");
    try {
      const rawAstroId = !leadProfile?.is_lead
        ? leadProfile?.callsign || leadProfile?.username || checkInForm.astronaut_id || "ASTRO-01"
        : checkInForm.astronaut_id || selectedAstroId || "ASTRO-01";
      const sanitizedAstroId = rawAstroId.trim().replace(/\s+/g, "-");
      const checkinPayload: DailyCheckInPayload = {
        astronaut_id: sanitizedAstroId,
        mission_day: Number(checkInForm.mission_day) || 1,
        checkin_date: new Date().toISOString().slice(0, 10),
        vitals: {
          heart_rate: Number(checkInForm.heart_rate),
          bp_sys: Number(checkInForm.bp_sys),
          bp_dia: Number(checkInForm.bp_dia),
          spo2: Number(checkInForm.spo2),
          core_temp_c: Number(checkInForm.core_temp_c ?? 36.8),
          blood_glucose: Number(checkInForm.blood_glucose ?? 92),
          glucose_context: checkInExtras.glucose_context,
          hrv_rmssd: Number(checkInForm.hrv_rmssd ?? 48),
        },
        sleep: {
          bedtime: checkInExtras.bedtime,
          wake_time: checkInExtras.wake_time,
          sleep_hours: Number(checkInForm.sleep_hours ?? 7.0),
          sleep_quality: checkInExtras.sleep_quality,
          sleep_medication: checkInExtras.sleep_medication,
        },
        wellbeing: {
          mood_score: Math.min(5, Math.max(1, Math.round(Number(checkInForm.mood_score || 4)))),
          energy_level: checkInExtras.energy_level,
          stress_level: checkInExtras.stress_level,
        },
        exercise: {
          cardio_minutes: Number(checkInExtras.cardio_minutes),
          resistance_minutes: Number(checkInExtras.resistance_minutes),
        },
        nutrition: {
          calories_kcal: Number(checkInExtras.calories_kcal),
          water_liters: Number(checkInExtras.water_liters),
          breakfast: checkInExtras.breakfast,
          lunch: checkInExtras.lunch,
          dinner: checkInExtras.dinner,
          vitamin_d_taken: checkInExtras.vitamin_d_taken,
        },
        environment: {
          radiation_msv: Number(checkInForm.radiation_msv ?? 0.85),
          radiation_badge_worn: checkInExtras.radiation_badge_worn,
          cabin_temp_c: Number(checkInExtras.cabin_temp_c),
          cabin_co2_mmhg: Number(checkInForm.cabin_co2_mmhg ?? 2.6),
          ear_protection_used: checkInExtras.ear_protection_used,
        },
        symptoms: checkInExtras.symptoms,
      };

      let record;
      try {
        record = await api.submitDailyCheckIn(checkinPayload);
      } catch (submitErr: any) {
        if (submitErr?.status === 409) {
          // If already checked in today on this sol, ingest latest telemetry
          await api.ingestMetrics({ ...checkInForm, astronaut_id: sanitizedAstroId });
        } else {
          throw submitErr;
        }
      }

      setJustCheckedInAstroIds((prev) =>
        prev.includes(sanitizedAstroId) ? prev : [...prev, sanitizedAstroId]
      );
      setSelectedAstroId(sanitizedAstroId);
      setLatestMetrics({
        astronaut_id: sanitizedAstroId,
        mission_day: checkinPayload.mission_day,
        heart_rate: checkinPayload.vitals.heart_rate,
        bp_sys: checkinPayload.vitals.bp_sys,
        bp_dia: checkinPayload.vitals.bp_dia,
        spo2: checkinPayload.vitals.spo2,
        core_temp_c: checkinPayload.vitals.core_temp_c,
        blood_glucose: checkinPayload.vitals.blood_glucose,
        hrv_rmssd: checkinPayload.vitals.hrv_rmssd,
        sleep_hours: checkinPayload.sleep.sleep_hours,
        mood_score: checkinPayload.wellbeing.mood_score,
        radiation_msv: checkinPayload.environment.radiation_msv,
        created_at: new Date().toISOString(),
      });
      await loadAllData(sanitizedAstroId);

      const assessment = record?.assessment;
      const status = assessment?.status || "NOMINAL";
      const hazard = assessment?.hazard || "Spaceflight Adaptation";
      const concern = assessment?.concern_label || assessment?.primary_concern || "Routine Telemetry";
      const reasons = assessment?.safety_reasons?.join("; ") || "Nominal thresholds maintained";
      const factors =
        assessment?.key_factors?.map((f: any) => `${f.factor}: ${f.value}`).join(", ") ||
        "All parameters within nominal operational limits";
      const symptomLabels =
        checkInExtras.symptoms.length > 0
          ? checkInExtras.symptoms.map((s) => SYMPTOMS.find((x) => x.key === s)?.label || s).join(", ")
          : "None reported";

      setCheckInFeedback(
        `Check-in complete for ${sanitizedAstroId} (Sol ${checkInForm.mission_day}). Classifier status: ${status}. Opening AstroDoc for next steps...`
      );

      const prompt = `**DAILY HEALTH CHECK-IN CLASSIFICATION REPORT**
**Astronaut:** ${sanitizedAstroId} (Sol ${checkInForm.mission_day})
**Classification Status:** ${status}
**Primary Hazard:** ${hazard}
**Primary Concern:** ${concern}
**Safety Floor Directives:** ${reasons}
**Key Predictive Factors:** ${factors}
**Vitals & Environment Logged:** HR ${checkInForm.heart_rate} bpm, SpO2 ${checkInForm.spo2}%, BP ${checkInForm.bp_sys}/${checkInForm.bp_dia} mmHg, Sleep ${checkInForm.sleep_hours}h, Radiation ${checkInForm.radiation_msv} mSv, Cabin CO2 ${checkInForm.cabin_co2_mmhg} mmHg, Temp ${checkInForm.core_temp_c}°C, HRV ${checkInForm.hrv_rmssd} ms, Glucose ${checkInForm.blood_glucose} mg/dL (${checkInExtras.glucose_context})
**Symptoms:** ${symptomLabels}

Classifier results are ready. What is your clinical evaluation, what specific countermeasures should I apply, and what should I do next?`;

      // Dispatch directly to chatbot and open interface
      await dispatchClassifierResultsToChatbot(sanitizedAstroId, prompt);
    } catch (err: any) {
      setCheckInFeedback(`Error: ${err.message || "Failed to save check-in"}`);
    } finally {
      setIsSubmittingCheckIn(false);
    }
  };

  // Handle astronaut daily check-in modal submission (ISS-grade multi-step form)
  const handleModalCheckInSubmit = async (payload: DailyCheckInPayload) => {
    const record = await api.submitDailyCheckIn(payload);
    setJustCheckedInAstroIds((prev) =>
      prev.includes(payload.astronaut_id) ? prev : [...prev, payload.astronaut_id]
    );
    await loadAllData(payload.astronaut_id);
    setIsModalCheckInOpen(false);

    const assessment = record.assessment;
    const astroId = payload.astronaut_id;
    const sol = payload.mission_day;
    const status = assessment?.status || "NOMINAL";
    const hazard = assessment?.hazard || "Spaceflight Adaptation";
    const concern = assessment?.concern_label || assessment?.primary_concern || "Routine Telemetry";
    const reasons = assessment?.safety_reasons?.join("; ") || "Nominal thresholds maintained";
    const factors =
      assessment?.key_factors?.map((f) => `${f.factor}: ${f.value}`).join(", ") ||
      "All parameters logged";

    setCheckInFeedback(
      `Submitted guided check-in for ${astroId}. Classifier status: ${status}. Opening AstroDoc for clinical guidance...`
    );

    const prompt = `**DAILY HEALTH CHECK-IN CLASSIFICATION REPORT**
**Astronaut:** ${astroId} (Sol ${sol})
**Classification Status:** ${status}
**Primary Hazard:** ${hazard}
**Primary Concern:** ${concern}
**Safety Floor Directives:** ${reasons}
**Key Predictive Factors:** ${factors}

Classifier results are ready. What is your clinical evaluation, what specific countermeasures should I apply, and what should I do next?`;

    // Dispatch directly to chatbot and open interface
    await dispatchClassifierResultsToChatbot(astroId, prompt);
    return record;
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

  // Send query to AstroDoc AI Flight Surgeon (strictly scoped to signed-in member)
  const handleSendChat = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim() || isSendingChat) return;
    const chatOwner = myChatAstroId || selectedAstroId;
    if (!chatOwner) {
      setChatError("Sign in to chat with AstroDoc.");
      return;
    }
    setIsSendingChat(true);
    setChatError("");
    const q = chatInput.trim();
    setChatInput("");

    // Optimistic append so user sees message immediately
    const tempUserMsg: ChatHistoryItem = {
      id: Date.now(),
      astronaut_id: chatOwner,
      role: "user",
      content: q,
      citations: [],
      timestamp: new Date().toISOString(),
    };
    setChatHistory((prev) => [...prev, tempUserMsg]);

    try {
      const reply = await api.queryFlightSurgeon(q, chatOwner);
      const updatedChat = await api.getChatHistory(chatOwner).catch(() => null);
      if (updatedChat && updatedChat.length > 0) {
        setChatHistory(updatedChat);
      } else {
        setChatHistory((prev) => [
          ...prev,
          {
            id: Date.now() + 1,
            astronaut_id: chatOwner,
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

  // Compute deltas & overview telemetry status (single source of truth from backend classifier)
  const prevMetrics = history.length >= 2 ? history[history.length - 2] : null;
  const deltaLabel = (curr?: number, prev?: number): string | null => {
    if (curr === undefined || curr === null) return null;
    if (!prev || prev === 0) return "Baseline";
    const diff = ((curr - prev) / prev) * 100;
    return `${diff >= 0 ? "+" : "−"}${Math.abs(diff).toFixed(1)}% vs prev`;
  };

  const vitalStatus = (barIdx: number): StatusKey => {
    if (!latestMetrics) return "NODATA";
    const targetId = selectedAstroId || latestMetrics.astronaut_id;
    const member =
      crew.find((m) => m.id.toLowerCase() === String(targetId || "").toLowerCase()) ??
      (!selectedAstroId ? crew[0] : undefined);
    if (member?.has_telemetry && member.vitals_bars?.[barIdx]) {
      return toStatus(member.vitals_bars[barIdx]);
    }
    if (barIdx === 0) {
      const hr = Number(latestMetrics.heart_rate);
      if (hr < 45 || hr >= 115) return "CRITICAL";
      if (hr < 50 || hr > 90) return "MEDIUM";
      return "NORMAL";
    }
    if (barIdx === 1) {
      const spo2 = Number(latestMetrics.spo2);
      if (spo2 < 93) return "CRITICAL";
      if (spo2 < 96) return "MEDIUM";
      return "NORMAL";
    }
    if (barIdx === 2) {
      const sleep = Number(latestMetrics.sleep_hours);
      if (sleep < 4.5) return "CRITICAL";
      if (sleep < 6.5 || sleep > 9.0) return "MEDIUM";
      return "NORMAL";
    }
    if (barIdx === 4) {
      const rad = Number(latestMetrics.radiation_msv);
      if (rad >= 20) return "CRITICAL";
      if (rad > 2.0) return "MEDIUM";
      return "NORMAL";
    }
    return "UNCLASSIFIED";
  };

  const overallBodyStatus: StatusKey = !latestMetrics
    ? "NODATA"
    : [0, 1, 2, 4].some((i) => vitalStatus(i) === "CRITICAL")
    ? "CRITICAL"
    : [0, 1, 2, 4].some((i) => vitalStatus(i) === "MEDIUM")
    ? "MEDIUM"
    : "NORMAL";

  // Series for the main overview SVG chart (aligned 1:1 with the last 7 logged Sols)
  const chartHistory = history.slice(-7);
  const chartValues: number[] = chartHistory.map((h) =>
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

  const chartMetricLabel =
    chartMetric === "spo2"
      ? "Blood oxygen (SpO₂)"
      : chartMetric === "heart_rate"
      ? "Heart rate"
      : "Sleep";

  const normalRange =
    chartMetric === "spo2"
      ? { low: 96, high: 100 }
      : chartMetric === "heart_rate"
      ? { low: 50, high: 90 }
      : { low: 6.5, high: 9.0 };
  const rangeSpan = Math.max(0.1, chartBounds.max - chartBounds.min);
  const bandTop = 200 - ((normalRange.high - chartBounds.min) / rangeSpan) * 160 - 20;
  const bandBottom = 200 - ((normalRange.low - chartBounds.min) / rangeSpan) * 160 - 20;
  const chartBand = {
    y: Math.max(20, Math.min(180, bandTop)),
    height: Math.max(0, Math.min(180, bandBottom) - Math.max(20, bandTop)),
  };

  const primaryPath = buildSvgPath(chartValues, chartBounds.min, chartBounds.max);
  const baselinePath =
    chartValues.length > 0
      ? buildSvgPath(
          chartValues.map(() => chartValues[0]),
          chartBounds.min,
          chartBounds.max
        )
      : "";

  const velocityAbs = Math.abs(Number(forecast?.trend_velocity || 0));
  const trendTone =
    velocityAbs > 0.5
      ? "text-bio-critical"
      : velocityAbs > 0.1
      ? "text-bio-warning"
      : "text-bio-nominal";
  const trendWord =
    velocityAbs > 0.5 ? "(rising fast)" : velocityAbs > 0.1 ? "(drifting)" : "(stable)";

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
      { label: "Resp.", count: resp },
      { label: "Sleep", count: sleep },
      { label: "Radiation", count: rad },
      { label: "Cardio", count: cardio },
      { label: "Env.", count: env },
      { label: "Sensors", count: sensors },
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

  const DONUT_CIRCUMFERENCE = 2 * Math.PI * 40;
  const activityRaw = [
    { label: "Work", pct: workPct, stroke: "stroke-bio-primary", dot: "bg-bio-primary" },
    { label: "Sleep", pct: sleepPct, stroke: "stroke-bio-accent", dot: "bg-bio-accent" },
    { label: "Exercise", pct: exercisePct, stroke: "stroke-bio-nominal", dot: "bg-bio-nominal" },
    { label: "Other", pct: otherPct, stroke: "stroke-bio-warning", dot: "bg-bio-warning" },
  ];
  let runningOffset = 0;
  const activitySegments = activityRaw.map((item) => {
    const len = (item.pct / 100) * DONUT_CIRCUMFERENCE;
    const seg = { ...item, len, offset: runningOffset };
    runningOffset += len;
    return seg;
  });

  const activeAstroId =
    selectedAstroId || leadProfile?.callsign || leadProfile?.username || checkInForm.astronaut_id;

  const hasCheckedInToday = React.useMemo(() => {
    if (justCheckedInAstroIds.includes(activeAstroId)) return true;
    const todayIso = new Date(nowTick).toISOString().slice(0, 10);
    const todayLocal = new Date(nowTick).toLocaleDateString("en-CA");
    const crewMatch = crew.find(
      (c) => c.id.toLowerCase() === activeAstroId.toLowerCase() || c.name.toLowerCase() === activeAstroId.toLowerCase()
    );
    if (crewMatch?.checked_in_today) return true;
    const tsRaw = latestMetrics?.created_at || latestMetrics?.timestamp;
    if (tsRaw && (!latestMetrics?.astronaut_id || latestMetrics.astronaut_id === activeAstroId)) {
      const dStr = String(tsRaw).slice(0, 10);
      if (dStr === todayIso || dStr === todayLocal) return true;
    }
    return false;
  }, [activeAstroId, justCheckedInAstroIds, crew, latestMetrics, nowTick]);

  const isReminderPending = !hasCheckedInToday;
  const unackAlertsCount = allAlarms.filter((a) => !a.acknowledged).length;
  const totalNotifCount = unackAlertsCount + (isReminderPending ? 1 : 0);

  // Wait for LocalStorage session check before deciding auth screen (avoids reload sign-out flash)
  if (!isAuthChecked) {
    return (
      <div
        style={{
          minHeight: "100vh",
          width: "100vw",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0C0E12",
          color: "#94A3B8",
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: "12px",
          letterSpacing: "0.14em",
          textTransform: "uppercase",
        }}
      >
        Restoring Station Session...
      </div>
    );
  }

  // FIRST PAGE: Dedicated Station Login Page if not authenticated
  if (!leadToken) {
    return (
      <StationLoginPage
        onLoginSuccess={(token, profile) => {
          setChatHistory([]);
          try {
            localStorage.setItem("aegis_station_token", token);
            localStorage.setItem("aegis_station_profile", JSON.stringify(profile));
          } catch {
            // ignore
          }
          setLeadToken(token);
          setLeadProfile(profile);
          if (profile?.callsign || profile?.username) {
            const astroId = profile.callsign || profile.username;
            setSelectedAstroId(astroId);
            setCheckInForm((prev) => ({ ...prev, astronaut_id: astroId }));
          }
        }}
      />
    );
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexWrap: "wrap",
        background: "var(--bio-canvas)",
        color: "var(--bio-text-primary)",
        fontFamily: "var(--font-inter), Inter, 'SF Pro Text', system-ui, sans-serif",
        fontSize: "14px",
        lineHeight: "20px",
        fontVariantNumeric: "tabular-nums",
      }}
    >
      {/* =====================================================================
          LEFT NAVIGATION SIDEBAR (212px, var(--bio-surface), border var(--bio-border-subtle))
      ===================================================================== */}
      {showLeftNav && (
        <div
          style={{
            flex: "0 0 212px",
            borderRight: "1px solid var(--bio-border-subtle)",
            position: "sticky",
            top: 0,
            height: "100vh",
            overflowY: "auto",
            alignSelf: "flex-start",
            zIndex: 20,
            background: "var(--bio-surface)",
          }}
        >
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
              background: "var(--bio-surface)",
              color: "var(--bio-text-primary)",
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
              <span style={{ fontWeight: 600 }}>Apex</span>
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

              {leadProfile?.is_lead && (
                <button
                  type="button"
                  onClick={() => setActiveScreen("crew")}
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
                    background: activeScreen === "crew" ? "rgba(255,255,255,0.1)" : "transparent",
                  }}
                >
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
                  <span style={{ flex: 1 }}>Manage Crew</span>
                  <span
                    style={{
                      fontSize: "10px",
                      padding: "2px 6px",
                      borderRadius: "4px",
                      background: "#7DD3FC",
                      color: "#1C1C1C",
                      fontWeight: 700,
                    }}
                  >
                    LEAD
                  </span>
                </button>
              )}

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
            background: "var(--bio-surface)",
            borderBottom: "1px solid var(--bio-border-subtle)",
            color: "var(--bio-text-primary)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
            <button
              type="button"
              onClick={() => setShowLeftNav((v) => !v)}
              aria-label="Toggle navigation"
              title={showLeftNav ? "Hide sidebar" : "Show sidebar"}
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
              onClick={() => setShowRightPanel((v) => !v)}
              aria-label="Notifications"
              aria-expanded={showRightPanel}
              title="Notifications & Alerts"
              style={{
                position: "relative",
                width: "36px",
                height: "36px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                borderRadius: "8px",
                background: showRightPanel ? "#282828" : "transparent",
                border: isReminderPending ? "1px solid rgba(245, 158, 11, 0.45)" : "none",
                cursor: "pointer",
              }}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <path
                  d="M5 8 A5 5 0 0 1 15 8 V12 L16.5 14.5 H3.5 L5 12 Z"
                  stroke={isReminderPending ? "#FBBF24" : "#FFFFFF"}
                  strokeWidth="1.5"
                  strokeLinejoin="round"
                />
                <path
                  d="M8.2 17 A2 2 0 0 0 11.8 17"
                  stroke={isReminderPending ? "#FBBF24" : "#FFFFFF"}
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              </svg>
              {totalNotifCount > 0 && (
                <span
                  style={{
                    position: "absolute",
                    top: "3px",
                    right: "3px",
                    minWidth: "16px",
                    height: "16px",
                    padding: "0 4px",
                    borderRadius: "999px",
                    background: unackAlertsCount > 0 ? "#EF4444" : "#F59E0B",
                    color: "#1C1C1C",
                    fontSize: "10px",
                    fontWeight: 700,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    boxShadow: "0 0 0 2px #1C1C1C",
                  }}
                >
                  {totalNotifCount}
                </span>
              )}
            </button>

            {/* Station User Authentication Status & Sign Out */}
            {leadProfile ? (
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    height: "32px",
                    padding: "0 10px",
                    borderRadius: "8px",
                    background: "rgba(125,211,252,0.12)",
                    border: "1px solid rgba(125,211,252,0.3)",
                    fontSize: "12px",
                    color: "#7DD3FC",
                  }}
                >
                  <span style={{ fontWeight: 600 }}>{leadProfile.callsign || leadProfile.username}</span>
                  <span style={{ color: "#A3A3A3", fontSize: "11px" }}>({leadProfile.crew_name})</span>
                </div>
                <button
                  type="button"
                  onClick={handleSignOut}
                  title="Sign Out of Station Console"
                  style={{
                    height: "32px",
                    padding: "0 12px",
                    borderRadius: "8px",
                    border: "1px solid #444444",
                    background: "#282828",
                    color: "#EF4444",
                    fontSize: "12px",
                    fontWeight: 600,
                    cursor: "pointer",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "4px",
                  }}
                >
                  Sign Out
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setIsAuthModalOpen(true)}
                style={{
                  height: "32px",
                  padding: "0 12px",
                  borderRadius: "8px",
                  border: "1px solid #7DD3FC",
                  background: "transparent",
                  color: "#7DD3FC",
                  fontSize: "12px",
                  fontWeight: 600,
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                }}
              >
                🔑 Station Login
              </button>
            )}
          </div>
        </header>

        {/* Main Screen Container */}
        <main style={{ display: "flex", flexDirection: "column", gap: "28px", padding: "28px" }}>
          {/* =================================================================
              SCREEN 1: OVERVIEW
          ================================================================= */}
          {activeScreen === "overview" && (
            <div className="flex flex-col gap-bio-5">
              {/* Page header: one primary action for the view */}
              <header className="flex flex-wrap items-center justify-between gap-bio-3">
                <div className="flex flex-col gap-bio-1">
                  <h1 className="text-bio-lg font-semibold text-bio-text">Overview</h1>
                  <p className="text-bio-sm text-bio-text-secondary">
                    {latestMetrics
                      ? `Latest reading: ${latestMetrics.astronaut_id}, Sol ${latestMetrics.mission_day}`
                      : "No readings logged yet."}
                  </p>
                </div>
                <Button variant="primary" onClick={() => setActiveScreen("daily-checkin")}>
                  Log daily check-in
                </Button>
              </header>

              {/* 3-Column Biometric Stage: Left Metrics/Diagrams | Center 3D Rotating Model | Right Metrics/Diagrams */}
              <div className="grid grid-cols-1 items-stretch gap-bio-4 xl:grid-cols-[minmax(260px,1fr)_minmax(360px,460px)_minmax(260px,1fr)]">
                {/* LEFT WING: Cardio/Oxygen Metrics + Trend + Out-of-Range Systems */}
                <div className="order-2 flex flex-col gap-bio-4 xl:order-1 xl:h-full">
                  <div className="grid grid-cols-1 gap-bio-4 min-[520px]:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
                    <MetricCard
                      label="Heart rate"
                      value={latestMetrics ? String(Math.round(latestMetrics.heart_rate)) : null}
                      unit="bpm"
                      status={vitalStatus(0)}
                      delta={deltaLabel(latestMetrics?.heart_rate, prevMetrics?.heart_rate)}
                      range={VITAL_RANGES.heart_rate}
                    />
                    <MetricCard
                      label="Blood oxygen (SpO₂)"
                      value={latestMetrics ? Number(latestMetrics.spo2).toFixed(1) : null}
                      unit="%"
                      status={vitalStatus(1)}
                      delta={deltaLabel(latestMetrics?.spo2, prevMetrics?.spo2)}
                      range={VITAL_RANGES.spo2}
                    />
                  </div>

                  <Panel aria-labelledby="trend-title">
                    <PanelHeader
                      titleId="trend-title"
                      title="Trend"
                      description="Last seven logged readings. The shaded band is the normal range."
                      actions={
                        <SegmentedTabs<ChartMetric>
                          label="Metric"
                          value={chartMetric}
                          onChange={setChartMetric}
                          options={[
                            { value: "spo2", label: "SpO₂" },
                            { value: "heart_rate", label: "Heart rate" },
                            { value: "sleep", label: "Sleep" },
                          ]}
                        />
                      }
                    />

                    {hasData ? (
                      <>
                        <ul className="flex flex-wrap gap-x-bio-4 gap-y-bio-2 text-bio-xs text-bio-text-secondary">
                          <li className="inline-flex items-center gap-bio-2">
                            <span className="h-0.5 w-bio-4 rounded-full bg-bio-primary" aria-hidden="true" />
                            Logged readings
                          </li>
                          <li className="inline-flex items-center gap-bio-2">
                            <span className="w-bio-4 border-t-2 border-dashed border-bio-text-muted" aria-hidden="true" />
                            First reading
                          </li>
                          <li className="inline-flex items-center gap-bio-2">
                            <span
                              className="h-bio-3 w-bio-4 rounded-bio-sm border border-bio-nominal-border bg-bio-nominal-bg"
                              aria-hidden="true"
                            />
                            Normal range
                          </li>
                        </ul>

                        <div className="flex gap-bio-3">
                          <div
                            className="flex h-48 flex-col justify-between py-5 text-right font-mono text-bio-xs text-bio-text-muted"
                            aria-hidden="true"
                          >
                            {chartBounds.labels.map((lbl, idx) => (
                              <span key={idx}>{lbl}</span>
                            ))}
                          </div>
                          <div className="flex min-w-0 flex-1 flex-col gap-bio-2">
                            <svg
                              role="img"
                              aria-label={`${chartMetricLabel} over the last ${chartValues.length} readings. Latest: ${chartValues[chartValues.length - 1]}.`}
                              className="block h-48 w-full"
                              viewBox="0 0 600 200"
                              preserveAspectRatio="none"
                            >
                              {[0, 1, 2, 3, 4].map((i) => (
                                <line
                                  key={i}
                                  x1="0"
                                  x2="600"
                                  y1={20 + i * 40}
                                  y2={20 + i * 40}
                                  className="stroke-bio-border-subtle"
                                  strokeWidth="1"
                                  vectorEffect="non-scaling-stroke"
                                />
                              ))}
                              <rect
                                x="0"
                                width="600"
                                y={chartBand.y}
                                height={chartBand.height}
                                className="fill-bio-nominal-bg"
                              />
                              <path
                                d={baselinePath}
                                fill="none"
                                className="stroke-bio-text-muted"
                                strokeWidth="1.5"
                                strokeDasharray="5 5"
                                vectorEffect="non-scaling-stroke"
                              />
                              <path
                                d={primaryPath}
                                fill="none"
                                className="stroke-bio-primary"
                                strokeWidth="2.5"
                                strokeLinejoin="round"
                                strokeLinecap="round"
                                vectorEffect="non-scaling-stroke"
                              />
                            </svg>
                            <div className="flex justify-between font-mono text-bio-xs text-bio-text-muted">
                              {chartHistory.map((h, i) => (
                                <span key={i}>Sol {h.mission_day}</span>
                              ))}
                            </div>
                          </div>
                        </div>
                      </>
                    ) : (
                      <EmptyState
                        className="min-h-48"
                        title="No readings logged yet"
                        body="Log a daily check-in to start the trend line and the vital forecast."
                        action={
                          <Button onClick={() => setActiveScreen("daily-checkin")}>Open daily check-in</Button>
                        }
                      />
                    )}
                  </Panel>

                  <Panel aria-labelledby="system-title" className="flex-1">
                    <PanelHeader
                      titleId="system-title"
                      title="Out-of-range readings by system"
                      description="How many logged readings fell outside expected limits, per body system."
                    />
                    <div className="flex flex-col gap-bio-2">
                      <div className="flex h-44 items-end gap-bio-2 border-b border-bio-border-strong">
                        {systemAlertCounts.map((item) => (
                          <div
                            key={item.label}
                            className="flex flex-1 flex-col items-center justify-end gap-bio-1"
                          >
                            <span className="font-mono text-bio-xs text-bio-text-secondary">{item.count}</span>
                            <div
                              className="w-bio-5 rounded-t-bio-sm bg-gradient-to-t from-bio-primary to-bio-accent"
                              style={{
                                height: `${
                                  item.count === 0 ? 0 : Math.max(8, Math.round((item.count / maxSystemCount) * 136))
                                }px`,
                              }}
                            />
                          </div>
                        ))}
                      </div>
                      <div className="flex gap-bio-2 text-center text-bio-xs text-bio-text-secondary">
                        {systemAlertCounts.map((item) => (
                          <span key={item.label} className="flex-1 truncate">
                            {item.label}
                          </span>
                        ))}
                      </div>
                    </div>
                  </Panel>
                </div>

                {/* CENTER STAGE: Rotating 3D Holographic Body Model + Biometric Envelope Bar Chart */}
                <div className="order-1 flex flex-col gap-bio-4 xl:order-2 xl:h-full">
                  <HologramModel3D
                    astronautId={latestMetrics?.astronaut_id || selectedAstroId || leadProfile?.callsign}
                    missionDay={latestMetrics?.mission_day}
                    status={overallBodyStatus}
                    heartRate={latestMetrics?.heart_rate ?? null}
                    spo2={latestMetrics?.spo2 ?? null}
                    sleepHours={latestMetrics?.sleep_hours ?? null}
                    radiationMsv={latestMetrics?.radiation_msv ?? null}
                  />

                  <Panel aria-labelledby="envelope-title" className="flex-1">
                    <PanelHeader
                      titleId="envelope-title"
                      title="Biometric envelope"
                      description="Latest telemetry levels relative to mission safety limits."
                    />
                    <div className="flex flex-col gap-bio-3">
                      {[
                        {
                          label: "Heart rate",
                          pct: latestMetrics ? Math.min(100, Math.max(8, (Number(latestMetrics.heart_rate) / 140) * 100)) : 0,
                          readout: latestMetrics ? `${Math.round(latestMetrics.heart_rate)} bpm` : "—",
                          st: vitalStatus(0),
                        },
                        {
                          label: "SpO₂ saturation",
                          pct: latestMetrics ? Math.min(100, Math.max(8, Number(latestMetrics.spo2))) : 0,
                          readout: latestMetrics ? `${Number(latestMetrics.spo2).toFixed(1)}%` : "—",
                          st: vitalStatus(1),
                        },
                        {
                          label: "Sleep cycle",
                          pct: latestMetrics ? Math.min(100, Math.max(8, (Number(latestMetrics.sleep_hours) / 10) * 100)) : 0,
                          readout: latestMetrics ? `${Number(latestMetrics.sleep_hours).toFixed(1)} h` : "—",
                          st: vitalStatus(2),
                        },
                        {
                          label: "Core temp",
                          pct: latestMetrics
                            ? Math.min(100, Math.max(8, ((Number(latestMetrics.core_temp_c ?? 36.8) - 35) / 4) * 100))
                            : 0,
                          readout: latestMetrics ? `${Number(latestMetrics.core_temp_c ?? 36.8).toFixed(1)} °C` : "—",
                          st: vitalStatus(3),
                        },
                        {
                          label: "Radiation load",
                          pct: latestMetrics ? Math.min(100, Math.max(6, (Number(latestMetrics.radiation_msv) / 2.5) * 100)) : 0,
                          readout: latestMetrics ? `${Number(latestMetrics.radiation_msv).toFixed(2)} mSv` : "—",
                          st: vitalStatus(4),
                        },
                      ].map((bar) => (
                        <div key={bar.label} className="flex flex-col gap-bio-1">
                          <div className="flex items-center justify-between text-bio-xs">
                            <span className="text-bio-text-secondary">{bar.label}</span>
                            <span className="font-mono font-medium text-bio-text">{bar.readout}</span>
                          </div>
                          <div className="h-2 w-full overflow-hidden rounded-full bg-bio-surface-elevated">
                            <div
                              className={`h-full rounded-full transition-all duration-300 ${
                                bar.st === "CRITICAL"
                                  ? "bg-bio-critical-bold"
                                  : bar.st === "MEDIUM"
                                  ? "bg-bio-warning"
                                  : "bg-gradient-to-r from-bio-primary to-bio-accent"
                              }`}
                              style={{ width: `${bar.pct}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </Panel>
                </div>

                {/* RIGHT WING: Sleep/Radiation Metrics + Activity Donut + Crew Vitals */}
                <div className="order-3 flex flex-col gap-bio-4 xl:h-full">
                  <div className="grid grid-cols-1 gap-bio-4 min-[520px]:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
                    <MetricCard
                      label="Sleep"
                      value={latestMetrics ? Number(latestMetrics.sleep_hours).toFixed(1) : null}
                      unit="h"
                      status={vitalStatus(2)}
                      delta={deltaLabel(latestMetrics?.sleep_hours, prevMetrics?.sleep_hours)}
                      range={VITAL_RANGES.sleep_hours}
                    />
                    <MetricCard
                      label="Radiation dose today"
                      value={latestMetrics ? Number(latestMetrics.radiation_msv).toFixed(2) : null}
                      unit="mSv"
                      status={vitalStatus(4)}
                      delta={deltaLabel(latestMetrics?.radiation_msv, prevMetrics?.radiation_msv)}
                      range={VITAL_RANGES.radiation_msv}
                    />
                  </div>

                  <Panel aria-labelledby="activity-title">
                    <PanelHeader
                      titleId="activity-title"
                      title="Crew time by activity"
                      description="Share of a 24-hour sol."
                    />
                    <div className="flex flex-wrap items-center gap-bio-5">
                      <svg
                        className="h-32 w-32 shrink-0"
                        viewBox="0 0 100 100"
                        role="img"
                        aria-label="Donut chart of crew time by activity. Values are listed beside it."
                      >
                        <circle cx="50" cy="50" r="40" fill="none" className="stroke-bio-border-strong" strokeWidth="14" />
                        {hasData &&
                          activitySegments.map((seg) => (
                            <circle
                              key={seg.label}
                              cx="50"
                              cy="50"
                              r="40"
                              fill="none"
                              className={seg.stroke}
                              strokeWidth="14"
                              strokeDasharray={`${seg.len} ${DONUT_CIRCUMFERENCE - seg.len}`}
                              strokeDashoffset={-seg.offset}
                              transform="rotate(-90 50 50)"
                            />
                          ))}
                      </svg>
                      <ul className="flex min-w-36 flex-1 flex-col gap-bio-2 text-bio-sm">
                        {activitySegments.map((seg) => (
                          <li key={seg.label} className="flex items-center justify-between gap-bio-3">
                            <span className="inline-flex items-center gap-bio-2 text-bio-text-secondary">
                              <span className={`h-2 w-2 rounded-full ${seg.dot}`} aria-hidden="true" />
                              {seg.label}
                            </span>
                            <span className="font-mono text-bio-text">{hasData ? `${seg.pct}%` : "—"}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </Panel>

                  <Panel aria-labelledby="crew-vitals-title" className="flex-1">
                    <PanelHeader
                      titleId="crew-vitals-title"
                      title="Crew vitals"
                      description="Select a crew member to filter this page. Bars show heart rate, SpO₂, sleep, temperature and dose."
                    />
                    {crew.length > 0 ? (
                      <ul className="flex flex-col gap-bio-1">
                        {crew.map((m) => {
                          const selected = m.id === selectedAstroId;
                          return (
                            <li key={m.id}>
                              <button
                                type="button"
                                aria-pressed={selected}
                                onClick={() => setSelectedAstroId(selected ? "" : m.id)}
                                className={`bio-focus flex w-full items-center justify-between gap-bio-3 rounded-bio-md border px-bio-3 py-bio-2 text-left transition-colors duration-150 hover:bg-bio-surface-hover active:bg-bio-surface-active ${
                                  selected
                                    ? "border-bio-border-control bg-bio-surface-elevated"
                                    : "border-transparent"
                                }`}
                              >
                                <span className="flex min-w-0 flex-col gap-bio-2">
                                  <span className="truncate text-bio-sm font-medium text-bio-text">{m.id}</span>
                                  <span className="flex gap-bio-1" aria-hidden="true">
                                    {m.vitals_bars.map((st, idx) => {
                                      const k = m.has_telemetry ? toStatus(st) : "NODATA";
                                      return (
                                        <span
                                          key={idx}
                                          className={`h-1 w-bio-4 rounded-full ${
                                            k === "CRITICAL"
                                              ? "bg-bio-critical"
                                              : k === "MEDIUM"
                                              ? "bg-bio-warning"
                                              : k === "NORMAL"
                                              ? "bg-bio-text-muted"
                                              : "bg-bio-border-strong"
                                          }`}
                                        />
                                      );
                                    })}
                                  </span>
                                  <span className="sr-only">
                                    {m.has_telemetry
                                      ? m.vitals_bars
                                          .map((st, idx) => `${VITAL_LABELS[idx] ?? "Vital"}: ${toStatus(st).toLowerCase()}`)
                                          .join(", ")
                                      : "No readings logged"}
                                  </span>
                                </span>
                                <StatusBadge status={m.has_telemetry ? toStatus(m.status) : "NODATA"} />
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    ) : (
                      <EmptyState
                        title="No crew vitals yet"
                        body="Vitals appear here once a crew member logs a daily check-in."
                      />
                    )}
                  </Panel>
                </div>
              </div>

              {/* Vital forecast (full-width below the 3-column biometric stage) */}
              <Panel aria-labelledby="forecast-title" aria-busy={isLoadingForecast}>
                <PanelHeader
                  titleId="forecast-title"
                  title="Vital forecast"
                  description={
                    timeScale === "DAILY"
                      ? "Next 24 hours: damped exponential smoothing with circadian harmonics for core temperature and sleep."
                      : timeScale === "WEEKLY"
                      ? "Next 7 days: multi-day trend velocity with damped smoothing."
                      : "Next 30 days: long-duration spaceflight adaptation with asymptotic plateau damping."
                  }
                  actions={
                    <div className="flex items-center gap-bio-3">
                      {isLoadingForecast && <Spinner label="Calculating forecast…" />}
                      <SegmentedTabs<"DAILY" | "WEEKLY" | "MONTHLY">
                        label="Forecast horizon"
                        value={timeScale}
                        onChange={handleTimeScaleChange}
                        options={[
                          { value: "DAILY", label: "24 hours" },
                          { value: "WEEKLY", label: "7 days" },
                          { value: "MONTHLY", label: "30 days" },
                        ]}
                      />
                    </div>
                  }
                />

                {forecastError && (
                  <InlineError
                    title="Forecast didn't load"
                    body={forecastError}
                    action={<Button onClick={() => handleTimeScaleChange(timeScale)}>Retry</Button>}
                  />
                )}

                <dl className="grid grid-cols-1 gap-bio-3 min-[520px]:grid-cols-2 xl:grid-cols-4">
                  <div className="rounded-bio-md border border-bio-border bg-bio-surface-elevated p-bio-3">
                    <dt className="text-bio-xs text-bio-text-muted">Forecast model</dt>
                    <dd className="mt-bio-1 text-bio-sm font-semibold text-bio-text">
                      {forecast?.model_used || "Holt-Winters damped"}
                    </dd>
                  </div>
                  <div className="rounded-bio-md border border-bio-border bg-bio-surface-elevated p-bio-3">
                    <dt className="text-bio-xs text-bio-text-muted">Trend velocity</dt>
                    <dd className={`mt-bio-1 text-bio-sm font-semibold ${trendTone}`}>
                      <span className="font-mono">
                        {forecast?.trend_velocity != null
                          ? `${Number(forecast.trend_velocity).toFixed(3)} per step`
                          : "—"}
                      </span>
                      {forecast?.trend_velocity != null && (
                        <span className="ml-bio-2 font-normal">{trendWord}</span>
                      )}
                    </dd>
                  </div>
                  <div className="rounded-bio-md border border-bio-border bg-bio-surface-elevated p-bio-3">
                    <dt className="text-bio-xs text-bio-text-muted">Main strain</dt>
                    <dd className="mt-bio-1 text-bio-sm font-semibold text-bio-text">
                      {forecast?.primary_strain_indicator || "Nominal vital envelope"}
                    </dd>
                  </div>
                  <div className="rounded-bio-md border border-bio-border bg-bio-surface-elevated p-bio-3">
                    <dt className="text-bio-xs text-bio-text-muted">Alarm outlook</dt>
                    <dd className="mt-bio-1">
                      <StatusBadge
                        status={forecast?.alert_triggered ? "CRITICAL" : "NORMAL"}
                        label={forecast?.alert_triggered ? "Escalation predicted" : "Within thresholds"}
                      />
                    </dd>
                  </div>
                </dl>

                {forecast?.trajectory && forecast.trajectory.length > 0 ? (
                  <div className="flex flex-col gap-bio-3">
                    <h3 className="text-bio-sm font-medium text-bio-text-secondary">
                      Projected points ({forecast.trajectory.length} steps, up to 8 shown)
                    </h3>
                    <ul className="grid grid-cols-2 gap-bio-3 min-[520px]:grid-cols-3 xl:grid-cols-4">
                      {forecast.trajectory
                        .filter((_, idx) => {
                          const total = forecast.trajectory?.length || 0;
                          if (total <= 8) return true;
                          const step = Math.ceil(total / 8);
                          return idx % step === 0 || idx === total - 1;
                        })
                        .map((pt, idx) => (
                          <li
                            key={idx}
                            className="flex flex-col gap-bio-1 rounded-bio-md border border-bio-border bg-bio-surface-elevated p-bio-3"
                          >
                            <span className="text-bio-xs font-semibold text-bio-accent">
                              {pt.time_label || `Step ${pt.day}`}
                            </span>
                            <span className="font-mono text-bio-sm font-semibold text-bio-text">
                              {Number(pt.heart_rate_predicted).toFixed(0)} bpm
                            </span>
                            <span className="font-mono text-bio-xs text-bio-text-secondary">
                              SpO₂ {Number(pt.spo2_predicted).toFixed(1)}%
                            </span>
                            {pt.lower_ci_heart_rate != null && pt.upper_ci_heart_rate != null && (
                              <span className="font-mono text-bio-xs text-bio-text-muted">
                                95% CI {Math.round(pt.lower_ci_heart_rate)}–{Math.round(pt.upper_ci_heart_rate)}
                              </span>
                            )}
                            <span
                              className={`font-mono text-bio-xs ${
                                pt.cardiovascular_strain_index > 0.6 ? "text-bio-critical" : "text-bio-nominal"
                              }`}
                            >
                              Strain {Number(pt.cardiovascular_strain_index).toFixed(2)}
                              {pt.cardiovascular_strain_index > 0.6 ? " (high)" : ""}
                            </span>
                          </li>
                        ))}
                    </ul>
                  </div>
                ) : (
                  <EmptyState
                    title="Not enough history to forecast"
                    body="The time-series model needs logged readings to fit. Submit a daily check-in to initialise it."
                  />
                )}

                {forecast?.recommended_countermeasure && (
                  <div className="flex items-start gap-bio-3 rounded-bio-md border border-bio-primary-glow bg-bio-primary-subtle p-bio-4">
                    <svg
                      className="mt-bio-1 h-4 w-4 shrink-0 text-bio-primary"
                      viewBox="0 0 16 16"
                      fill="currentColor"
                      aria-hidden="true"
                    >
                      <path d="M6 1h4v5h5v4h-5v5H6v-5H1V6h5z" />
                    </svg>
                    <div className="flex flex-col gap-bio-1">
                      <h3 className="text-bio-xs font-semibold text-bio-primary">Recommended countermeasure</h3>
                      <p className="max-w-[65ch] text-bio-sm text-bio-text">{forecast.recommended_countermeasure}</p>
                    </div>
                  </div>
                )}
              </Panel>
            </div>
          )}

          {/* =================================================================
              SCREEN 2: DAILY CHECK-IN (All 44 Classifier Metrics + Holographic HUD Design)
          ================================================================= */}
          {activeScreen === "daily-checkin" && (
            <section
              style={{
                position: "relative",
                display: "flex",
                flexDirection: "column",
                gap: "22px",
                padding: "24px",
                borderRadius: "16px",
                background: "#0F131C",
                border: "1px solid #232B3B",
              }}
            >
              {/* Animated ASTRO Holographic HUD Loader Overlay during submission */}
              {isSubmittingCheckIn && (
                <div
                  role="status"
                  aria-live="assertive"
                  style={{
                    position: "fixed",
                    inset: 0,
                    zIndex: 9998,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "20px",
                    background: "rgba(8, 11, 16, 0.86)",
                    backdropFilter: "blur(8px)",
                  }}
                >
                  <div style={{ position: "relative", width: "260px", height: "260px", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    {/* Outer glowing telemetry arc ring */}
                    <svg
                      width="260"
                      height="260"
                      viewBox="0 0 260 260"
                      style={{ position: "absolute", inset: 0, animation: "astroSpinCW 9s linear infinite" }}
                      aria-hidden="true"
                    >
                      <circle cx="130" cy="130" r="122" fill="none" stroke="rgba(45, 212, 191, 0.22)" strokeWidth="1.5" />
                      <circle
                        cx="130"
                        cy="130"
                        r="122"
                        fill="none"
                        stroke="#2DD4BF"
                        strokeWidth="4"
                        strokeDasharray="68 95 28 110"
                        strokeLinecap="round"
                      />
                      <circle
                        cx="130"
                        cy="130"
                        r="112"
                        fill="none"
                        stroke="rgba(94, 234, 212, 0.45)"
                        strokeWidth="2"
                        strokeDasharray="4 10"
                      />
                    </svg>

                    {/* Middle counter-rotating tick / capsule gauge ring */}
                    <svg
                      width="210"
                      height="210"
                      viewBox="0 0 210 210"
                      style={{ position: "absolute", animation: "astroSpinCCW 7s linear infinite" }}
                      aria-hidden="true"
                    >
                      <circle
                        cx="105"
                        cy="105"
                        r="94"
                        fill="none"
                        stroke="rgba(45, 212, 191, 0.55)"
                        strokeWidth="7"
                        strokeDasharray="3 7"
                      />
                      <circle
                        cx="105"
                        cy="105"
                        r="82"
                        fill="none"
                        stroke="#5EEAD4"
                        strokeWidth="2"
                        strokeDasharray="45 35 15 45"
                        strokeLinecap="round"
                      />
                    </svg>

                    {/* Inner pulsing core ring */}
                    <svg
                      width="148"
                      height="148"
                      viewBox="0 0 148 148"
                      style={{ position: "absolute", animation: "astroSpinCW 4.5s linear infinite, astroPulseGlow 2s ease-in-out infinite" }}
                      aria-hidden="true"
                    >
                      <circle cx="74" cy="74" r="66" fill="rgba(45, 212, 191, 0.05)" stroke="rgba(45, 212, 191, 0.3)" strokeWidth="1" />
                      <circle
                        cx="74"
                        cy="74"
                        r="62"
                        fill="none"
                        stroke="#2DD4BF"
                        strokeWidth="4.5"
                        strokeDasharray="90 35 45 25"
                        strokeLinecap="round"
                      />
                    </svg>

                    {/* Center Label: ASTRO */}
                    <div
                      style={{
                        position: "relative",
                        zIndex: 2,
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        gap: "2px",
                      }}
                    >
                      <span
                        style={{
                          fontFamily: "'JetBrains Mono', monospace",
                          fontSize: "20px",
                          fontWeight: 700,
                          letterSpacing: "0.28em",
                          paddingLeft: "0.28em",
                          color: "#F1F5F9",
                          textShadow: "0 0 14px rgba(45, 212, 191, 0.85)",
                        }}
                      >
                        ASTRO
                      </span>
                    </div>
                  </div>
                  <div
                    style={{
                      fontFamily: "'JetBrains Mono', monospace",
                      fontSize: "12px",
                      letterSpacing: "0.14em",
                      color: "#5EEAD4",
                      textTransform: "uppercase",
                    }}
                  >
                    Classifying Biometrics &amp; Updating Telemetry...
                  </div>
                </div>
              )}

              {/* Header */}
              <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "12px", borderBottom: "1px solid rgba(45, 212, 191, 0.16)", paddingBottom: "14px" }}>
                <div>
                  <h1 style={{ margin: 0, fontSize: "16px", fontWeight: 600, color: "#F1F5F9" }}>
                    Daily Crew Check-in
                  </h1>
                  <p style={{ margin: "4px 0 0", fontSize: "12px", color: "#94A3B8" }}>
                    Complete all 5 operational panels below to run the ML health classifier and update station telemetry.
                  </p>
                </div>
                <span
                  style={{
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: "11px",
                    padding: "4px 10px",
                    borderRadius: "999px",
                    border: "1px solid rgba(45, 212, 191, 0.35)",
                    background: "rgba(45, 212, 191, 0.1)",
                    color: "#2DD4BF",
                  }}
                >
                  44-FEATURE CLASSIFIER READY
                </span>
              </div>

              <form
                onSubmit={handleCheckInSubmit}
                style={{ display: "flex", flexDirection: "column", gap: "20px" }}
              >
                {/* SECTION 1: Identity & Physiological Vitals */}
                <div style={{ padding: "16px", borderRadius: "12px", background: "#131720", border: "1px solid #232B3B", display: "flex", flexDirection: "column", gap: "14px" }}>
                  <div style={{ fontSize: "11px", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "#2DD4BF", fontFamily: "'JetBrains Mono', monospace" }}>
                    01 · Identity &amp; Physiological Vitals
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(185px, 1fr))", gap: "14px" }}>
                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Crew Member ID / Callsign</span>
                      <input
                        type="text"
                        required
                        value={checkInForm.astronaut_id}
                        onChange={(e) => setCheckInForm({ ...checkInForm, astronaut_id: e.target.value })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      />
                    </label>

                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Mission Day (Sol)</span>
                      <input
                        type="number"
                        min={1}
                        required
                        value={checkInForm.mission_day}
                        onChange={(e) => setCheckInForm({ ...checkInForm, mission_day: parseInt(e.target.value || "1", 10) })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      />
                    </label>

                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Heart Rate (BPM)</span>
                      <input
                        type="number"
                        step="1"
                        min={30}
                        max={240}
                        required
                        value={checkInForm.heart_rate}
                        onChange={(e) => setCheckInForm({ ...checkInForm, heart_rate: parseFloat(e.target.value || "0") })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      />
                    </label>

                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>SpO₂ (%)</span>
                      <input
                        type="number"
                        step="0.1"
                        min={50}
                        max={100}
                        required
                        value={checkInForm.spo2}
                        onChange={(e) => setCheckInForm({ ...checkInForm, spo2: parseFloat(e.target.value || "0") })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      />
                    </label>

                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Systolic BP (mmHg)</span>
                      <input
                        type="number"
                        min={60}
                        max={250}
                        required
                        value={checkInForm.bp_sys}
                        onChange={(e) => setCheckInForm({ ...checkInForm, bp_sys: parseFloat(e.target.value || "0") })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      />
                    </label>

                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Diastolic BP (mmHg)</span>
                      <input
                        type="number"
                        min={40}
                        max={160}
                        required
                        value={checkInForm.bp_dia}
                        onChange={(e) => setCheckInForm({ ...checkInForm, bp_dia: parseFloat(e.target.value || "0") })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      />
                    </label>

                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Core Temperature (°C)</span>
                      <input
                        type="number"
                        step="0.1"
                        min={34}
                        max={42}
                        required
                        value={checkInForm.core_temp_c}
                        onChange={(e) => setCheckInForm({ ...checkInForm, core_temp_c: parseFloat(e.target.value || "36.8") })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      />
                    </label>

                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>HRV RMSSD (ms)</span>
                      <input
                        type="number"
                        step="1"
                        min={5}
                        max={200}
                        required
                        value={checkInForm.hrv_rmssd}
                        onChange={(e) => setCheckInForm({ ...checkInForm, hrv_rmssd: parseFloat(e.target.value || "48") })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      />
                    </label>

                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Blood Glucose (mg/dL)</span>
                      <input
                        type="number"
                        min={40}
                        max={400}
                        required
                        value={checkInForm.blood_glucose}
                        onChange={(e) => setCheckInForm({ ...checkInForm, blood_glucose: parseFloat(e.target.value || "92") })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      />
                    </label>

                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Glucose Timing Context</span>
                      <select
                        value={checkInExtras.glucose_context}
                        onChange={(e) => setCheckInExtras({ ...checkInExtras, glucose_context: e.target.value as GlucoseContext })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      >
                        {GLUCOSE_CONTEXT.map((g) => (
                          <option key={g.value} value={g.value}>{g.label}</option>
                        ))}
                      </select>
                    </label>
                  </div>
                </div>

                {/* SECTION 2: Sleep & Psychological Wellbeing */}
                <div style={{ padding: "16px", borderRadius: "12px", background: "#131720", border: "1px solid #232B3B", display: "flex", flexDirection: "column", gap: "14px" }}>
                  <div style={{ fontSize: "11px", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "#2DD4BF", fontFamily: "'JetBrains Mono', monospace" }}>
                    02 · Sleep &amp; Psychological Wellbeing
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(185px, 1fr))", gap: "14px" }}>
                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Bedtime (HH:MM)</span>
                      <input
                        type="time"
                        required
                        value={checkInExtras.bedtime}
                        onChange={(e) => setCheckInExtras({ ...checkInExtras, bedtime: e.target.value })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      />
                    </label>

                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Wake Time (HH:MM)</span>
                      <input
                        type="time"
                        required
                        value={checkInExtras.wake_time}
                        onChange={(e) => setCheckInExtras({ ...checkInExtras, wake_time: e.target.value })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      />
                    </label>

                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Sleep Duration (hours)</span>
                      <input
                        type="number"
                        step="0.1"
                        min={0}
                        max={24}
                        required
                        value={checkInForm.sleep_hours}
                        onChange={(e) => setCheckInForm({ ...checkInForm, sleep_hours: parseFloat(e.target.value || "0") })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      />
                    </label>

                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Sleep Quality (1–5)</span>
                      <select
                        value={checkInExtras.sleep_quality}
                        onChange={(e) => setCheckInExtras({ ...checkInExtras, sleep_quality: parseInt(e.target.value, 10) })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      >
                        {RATINGS.sleep_quality.options.map((o) => (
                          <option key={o.value} value={o.value}>{o.value} — {o.label}</option>
                        ))}
                      </select>
                    </label>

                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Mood / Morale (1–5)</span>
                      <select
                        value={checkInForm.mood_score}
                        onChange={(e) => setCheckInForm({ ...checkInForm, mood_score: parseInt(e.target.value, 10) })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      >
                        {RATINGS.mood.options.map((o) => (
                          <option key={o.value} value={o.value}>{o.value} — {o.label}</option>
                        ))}
                      </select>
                    </label>

                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Energy Level (1–5)</span>
                      <select
                        value={checkInExtras.energy_level}
                        onChange={(e) => setCheckInExtras({ ...checkInExtras, energy_level: parseInt(e.target.value, 10) })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      >
                        {RATINGS.energy.options.map((o) => (
                          <option key={o.value} value={o.value}>{o.value} — {o.label}</option>
                        ))}
                      </select>
                    </label>

                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Stress / Calmness (1–5)</span>
                      <select
                        value={checkInExtras.stress_level}
                        onChange={(e) => setCheckInExtras({ ...checkInExtras, stress_level: parseInt(e.target.value, 10) })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      >
                        {RATINGS.stress.options.map((o) => (
                          <option key={o.value} value={o.value}>{o.value} — {o.label}</option>
                        ))}
                      </select>
                    </label>

                    <label style={{ display: "flex", alignItems: "center", gap: "10px", marginTop: "22px", cursor: "pointer", padding: "0 10px", height: "38px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12" }}>
                      <input
                        type="checkbox"
                        checked={checkInExtras.sleep_medication}
                        onChange={(e) => setCheckInExtras({ ...checkInExtras, sleep_medication: e.target.checked })}
                        style={{ accentColor: "#2DD4BF", width: "15px", height: "15px" }}
                      />
                      <span style={{ fontSize: "12px", color: "#F1F5F9" }}>Sleep Medication Used</span>
                    </label>
                  </div>
                </div>

                {/* SECTION 3: Exercise & Nutrition Countermeasures */}
                <div style={{ padding: "16px", borderRadius: "12px", background: "#131720", border: "1px solid #232B3B", display: "flex", flexDirection: "column", gap: "14px" }}>
                  <div style={{ fontSize: "11px", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "#2DD4BF", fontFamily: "'JetBrains Mono', monospace" }}>
                    03 · Exercise &amp; Nutrition Countermeasures
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(185px, 1fr))", gap: "14px" }}>
                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Cardio Exercise (min)</span>
                      <input
                        type="number"
                        min={0}
                        max={600}
                        required
                        value={checkInExtras.cardio_minutes}
                        onChange={(e) => setCheckInExtras({ ...checkInExtras, cardio_minutes: parseInt(e.target.value || "0", 10) })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      />
                    </label>

                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Resistance / ARED (min)</span>
                      <input
                        type="number"
                        min={0}
                        max={600}
                        required
                        value={checkInExtras.resistance_minutes}
                        onChange={(e) => setCheckInExtras({ ...checkInExtras, resistance_minutes: parseInt(e.target.value || "0", 10) })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      />
                    </label>

                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Calories Eaten (kcal)</span>
                      <input
                        type="number"
                        min={0}
                        max={8000}
                        required
                        value={checkInExtras.calories_kcal}
                        onChange={(e) => setCheckInExtras({ ...checkInExtras, calories_kcal: parseInt(e.target.value || "0", 10) })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      />
                    </label>

                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Water Intake (L)</span>
                      <input
                        type="number"
                        step="0.1"
                        min={0}
                        max={10}
                        required
                        value={checkInExtras.water_liters}
                        onChange={(e) => setCheckInExtras({ ...checkInExtras, water_liters: parseFloat(e.target.value || "0") })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      />
                    </label>
                  </div>

                  <div style={{ display: "flex", flexWrap: "wrap", gap: "10px" }}>
                    {[
                      { key: "breakfast" as const, label: "Breakfast" },
                      { key: "lunch" as const, label: "Lunch" },
                      { key: "dinner" as const, label: "Dinner" },
                      { key: "vitamin_d_taken" as const, label: "Vitamin D Supplement" },
                    ].map((item) => (
                      <label
                        key={item.key}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "8px",
                          padding: "8px 12px",
                          borderRadius: "8px",
                          border: `1px solid ${checkInExtras[item.key] ? "rgba(45, 212, 191, 0.5)" : "#232B3B"}`,
                          background: checkInExtras[item.key] ? "rgba(45, 212, 191, 0.1)" : "#0C0E12",
                          cursor: "pointer",
                          fontSize: "12px",
                          color: "#F1F5F9",
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={checkInExtras[item.key]}
                          onChange={(e) => setCheckInExtras({ ...checkInExtras, [item.key]: e.target.checked })}
                          style={{ accentColor: "#2DD4BF", width: "14px", height: "14px" }}
                        />
                        {item.label}
                      </label>
                    ))}
                  </div>
                </div>

                {/* SECTION 4: Habitat & Radiation Environment */}
                <div style={{ padding: "16px", borderRadius: "12px", background: "#131720", border: "1px solid #232B3B", display: "flex", flexDirection: "column", gap: "14px" }}>
                  <div style={{ fontSize: "11px", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "#2DD4BF", fontFamily: "'JetBrains Mono', monospace" }}>
                    04 · Habitat &amp; Radiation Environment
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(185px, 1fr))", gap: "14px" }}>
                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Radiation Dose Today (mSv)</span>
                      <input
                        type="number"
                        step="0.05"
                        min={0}
                        max={500}
                        required
                        value={checkInForm.radiation_msv}
                        onChange={(e) => setCheckInForm({ ...checkInForm, radiation_msv: parseFloat(e.target.value || "0") })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      />
                    </label>

                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Cabin Temperature (°C)</span>
                      <input
                        type="number"
                        step="0.1"
                        min={0}
                        max={50}
                        required
                        value={checkInExtras.cabin_temp_c}
                        onChange={(e) => setCheckInExtras({ ...checkInExtras, cabin_temp_c: parseFloat(e.target.value || "22.5") })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      />
                    </label>

                    <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                      <span style={{ fontSize: "12px", color: "#94A3B8" }}>Cabin Ambient CO₂ (mmHg)</span>
                      <input
                        type="number"
                        step="0.1"
                        min={0}
                        max={15}
                        required
                        value={checkInForm.cabin_co2_mmhg}
                        onChange={(e) => setCheckInForm({ ...checkInForm, cabin_co2_mmhg: parseFloat(e.target.value || "2.6") })}
                        style={{ height: "38px", padding: "0 12px", borderRadius: "8px", border: "1px solid #232B3B", background: "#0C0E12", color: "#F1F5F9" }}
                      />
                    </label>
                  </div>

                  <div style={{ display: "flex", flexWrap: "wrap", gap: "10px" }}>
                    {[
                      { key: "radiation_badge_worn" as const, label: "Dosimeter Badge Worn All Day" },
                      { key: "ear_protection_used" as const, label: "Ear Protection Used in Noisy Areas" },
                    ].map((item) => (
                      <label
                        key={item.key}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "8px",
                          padding: "8px 12px",
                          borderRadius: "8px",
                          border: `1px solid ${checkInExtras[item.key] ? "rgba(45, 212, 191, 0.5)" : "#232B3B"}`,
                          background: checkInExtras[item.key] ? "rgba(45, 212, 191, 0.1)" : "#0C0E12",
                          cursor: "pointer",
                          fontSize: "12px",
                          color: "#F1F5F9",
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={checkInExtras[item.key]}
                          onChange={(e) => setCheckInExtras({ ...checkInExtras, [item.key]: e.target.checked })}
                          style={{ accentColor: "#2DD4BF", width: "14px", height: "14px" }}
                        />
                        {item.label}
                      </label>
                    ))}
                  </div>
                </div>

                {/* SECTION 5: Spaceflight Symptoms Checklist (12 discrete indicators) */}
                <div style={{ padding: "16px", borderRadius: "12px", background: "#131720", border: "1px solid #232B3B", display: "flex", flexDirection: "column", gap: "12px" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "8px" }}>
                    <div style={{ fontSize: "11px", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "#2DD4BF", fontFamily: "'JetBrains Mono', monospace" }}>
                      05 · Spaceflight Symptoms Checklist ({checkInExtras.symptoms.length} selected)
                    </div>
                    {checkInExtras.symptoms.length > 0 && (
                      <button
                        type="button"
                        onClick={() => setCheckInExtras({ ...checkInExtras, symptoms: [] })}
                        style={{ background: "transparent", border: "none", color: "#94A3B8", fontSize: "11px", cursor: "pointer" }}
                      >
                        Clear symptoms
                      </button>
                    )}
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "8px" }}>
                    {SYMPTOMS.map((sym) => {
                      const active = checkInExtras.symptoms.includes(sym.key);
                      return (
                        <label
                          key={sym.key}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "8px",
                            padding: "8px 10px",
                            borderRadius: "8px",
                            border: `1px solid ${active ? "rgba(45, 212, 191, 0.55)" : "#232B3B"}`,
                            background: active ? "rgba(45, 212, 191, 0.12)" : "#0C0E12",
                            color: active ? "#5EEAD4" : "#94A3B8",
                            fontSize: "12px",
                            cursor: "pointer",
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={active}
                            onChange={(e) => {
                              const next = e.target.checked
                                ? [...checkInExtras.symptoms, sym.key]
                                : checkInExtras.symptoms.filter((s) => s !== sym.key);
                              setCheckInExtras({ ...checkInExtras, symptoms: next });
                            }}
                            style={{ accentColor: "#2DD4BF", width: "14px", height: "14px" }}
                          />
                          {sym.label}
                        </label>
                      );
                    })}
                  </div>
                </div>

                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: "16px",
                    flexWrap: "wrap",
                  }}
                >
                  <span style={{ fontSize: "13px", color: "#5EEAD4" }}>{checkInFeedback}</span>
                  <button
                    type="submit"
                    disabled={isSubmittingCheckIn}
                    style={{
                      height: "42px",
                      padding: "0 24px",
                      borderRadius: "10px",
                      border: "1px solid rgba(45, 212, 191, 0.4)",
                      background: "#2DD4BF",
                      color: "#061312",
                      fontWeight: 700,
                      fontSize: "13px",
                      cursor: isSubmittingCheckIn ? "wait" : "pointer",
                    }}
                  >
                    Submit Daily Check-in
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
                {leadProfile?.is_lead && (
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
                    Crew Lead Provisioning Portal 🟢 (Lead Active)
                  </button>
                )}
              </div>

              {crewSubTab === "roster" || !leadProfile?.is_lead ? (
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
                            <span style={{ fontSize: "12px", color: "#A3A3A3" }}>Operating Location (applies to every crew member)</span>
                            <select
                              required
                              value={leadRegisterForm.environment}
                              onChange={(e) => setLeadRegisterForm({ ...leadRegisterForm, environment: e.target.value })}
                              style={{ height: "36px", padding: "0 12px", borderRadius: "8px", border: "1px solid #333333", background: "#1C1C1C", color: "#FFFFFF" }}
                            >
                              <option value="LUNAR">Moon (Lunar surface / orbit)</option>
                              <option value="MARS">Mars (surface / orbit)</option>
                              <option value="LEO">Low Earth Orbit (ISS-type)</option>
                              <option value="DEEP_SPACE">Deep-space transit</option>
                            </select>
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
                          onClick={handleSignOut}
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
          RIGHT SIDEBAR (280px, var(--bio-surface), border var(--bio-border-subtle))
      ===================================================================== */}
      {showRightPanel && (
        <div
          style={{
            flex: "0 0 280px",
            borderLeft: "1px solid var(--bio-border-subtle)",
            position: "sticky",
            top: 0,
            height: "100vh",
            overflowY: "auto",
            alignSelf: "flex-start",
            background: "var(--bio-surface)",
          }}
        >
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
              background: "var(--bio-surface)",
              color: "var(--bio-text-primary)",
            }}
          >
            {/* Alerts Feed */}
            <section style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 4px" }}>
                <h2 style={{ margin: 0, fontSize: "14px", fontWeight: 600 }}>Notifications &amp; Alerts</h2>
                {activeAlert && !activeAlert.acknowledged && (
                  <span
                    style={{
                      fontSize: "11px",
                      padding: "2px 6px",
                      borderRadius: "4px",
                      background: "#EF4444",
                      color: "#1C1C1C",
                      fontWeight: 700,
                      animation: "pulse 1.5s infinite",
                    }}
                  >
                    ACTIVE
                  </span>
                )}
              </div>

              {/* Automatic Daily Check-in Reminder in Notifications Feed */}
              {isReminderPending && (
                <div
                  role="status"
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "8px",
                    padding: "12px",
                    borderRadius: "12px",
                    background: "linear-gradient(145deg, rgba(245, 158, 11, 0.16), rgba(28, 28, 28, 0.95))",
                    border: "1px solid rgba(245, 158, 11, 0.55)",
                    boxShadow: "0 0 14px rgba(245, 158, 11, 0.15)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "6px" }}>
                    <span style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", fontWeight: 700, color: "#FBBF24" }}>
                      <span
                        style={{
                          width: "8px",
                          height: "8px",
                          borderRadius: "50%",
                          background: "#F59E0B",
                          boxShadow: "0 0 8px #F59E0B",
                        }}
                      />
                      Daily Check-in Due
                    </span>
                  </div>
                  <div style={{ fontSize: "11px", color: "#E5E5E5", lineHeight: "15px" }}>
                    <strong>{activeAstroId}</strong> has not logged today&apos;s daily biometric check-in yet.
                  </div>
                  <div style={{ display: "flex", gap: "6px", marginTop: "2px" }}>
                    <button
                      type="button"
                      onClick={() => setActiveScreen("daily-checkin")}
                      style={{
                        flex: 1,
                        height: "28px",
                        borderRadius: "6px",
                        border: "none",
                        background: "#F59E0B",
                        color: "#1C1C1C",
                        fontSize: "11px",
                        fontWeight: 700,
                        cursor: "pointer",
                      }}
                    >
                      Check in Now
                    </button>
                    <button
                      type="button"
                      onClick={() => setIsModalCheckInOpen(true)}
                      style={{
                        height: "28px",
                        padding: "0 8px",
                        borderRadius: "6px",
                        border: "1px solid rgba(125,211,252,0.45)",
                        background: "transparent",
                        color: "#7DD3FC",
                        fontSize: "11px",
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                    >
                      Guided
                    </button>
                  </div>
                </div>
              )}

              {/* Active Emergency Card Docked in Alerts Panel */}
              {activeAlert && !activeAlert.acknowledged && (
                <div
                  role="alert"
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "8px",
                    padding: "12px",
                    borderRadius: "12px",
                    background: "#3B2323",
                    border: "1px solid #EF4444",
                    boxShadow: "0 0 12px rgba(239, 68, 68, 0.25)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span
                      style={{
                        width: "8px",
                        height: "8px",
                        borderRadius: "50%",
                        background: "#EF4444",
                        boxShadow: "0 0 8px #EF4444",
                      }}
                    />
                    <span style={{ fontSize: "12px", fontWeight: 700, color: "#FCA5A5" }}>
                      {activeAlert.astronaut_id} · {activeAlert.hazard_origin}
                    </span>
                  </div>
                  <div style={{ fontSize: "11px", color: "#FCA5A5", lineHeight: "15px" }}>
                    {activeAlert.status === "SWITCHED_TO_EMERGENCY_CONTACT"
                      ? `Escalated to ${activeAlert.emergency_contact_callsign || "Emergency Contact"}`
                      : `Timeout: ${activeAlert.remaining_seconds ?? activeAlert.timeout_seconds}s · Contact: ${
                          activeAlert.emergency_contact_callsign || "CREW-MED"
                        }`}
                  </div>
                  <div style={{ display: "flex", gap: "6px", marginTop: "4px" }}>
                    <button
                      type="button"
                      onClick={() => handleAnswerAsOwner(activeAlert.alert_id)}
                      style={{
                        flex: 1,
                        height: "30px",
                        borderRadius: "6px",
                        border: "1px solid #F87171",
                        background: "transparent",
                        color: "#FFFFFF",
                        fontSize: "11px",
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                    >
                      Silence tone (I am OK)
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveScreen("alerts")}
                      style={{
                        height: "30px",
                        padding: "0 10px",
                        borderRadius: "6px",
                        border: "none",
                        background: "#EF4444",
                        color: "#1C1C1C",
                        fontSize: "11px",
                        fontWeight: 700,
                        cursor: "pointer",
                      }}
                    >
                      View
                    </button>
                  </div>
                </div>
              )}
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
              ) : !(activeAlert && !activeAlert.acknowledged) ? (
                <span style={{ padding: "4px", fontSize: "12px", color: "#6B6B6B" }}>
                  No alerts recorded
                </span>
              ) : null}
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
            right: showRightPanel ? "304px" : "24px",
            zIndex: 60,
            width: "52px",
            height: "52px",
            borderRadius: "50%",
            background: "#131720",
            color: "#5EEAD4",
            border: "1px solid #232B3B",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
            boxShadow: "0 8px 24px rgba(0,0,0,0.45)",
          }}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <rect x="4" y="6" width="16" height="12" rx="4" stroke="#5EEAD4" strokeWidth="1.8" />
            <path d="M12 3 V6" stroke="#5EEAD4" strokeWidth="1.8" strokeLinecap="round" />
            <circle cx="9.5" cy="12" r="1.3" fill="#2DD4BF" />
            <circle cx="14.5" cy="12" r="1.3" fill="#2DD4BF" />
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
            right: showRightPanel ? "304px" : "24px",
            zIndex: 60,
            width: isChatExpanded ? "min(840px, calc(100vw - 32px))" : "min(400px, calc(100vw - 32px))",
            height: isChatExpanded ? "min(720px, calc(100vh - 48px))" : "min(540px, calc(100vh - 48px))",
            background: "#131720",
            border: "1px solid #232B3B",
            borderRadius: "14px",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            boxShadow: "0 16px 40px rgba(0,0,0,0.55)",
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
              background: "#0C0E12",
              borderBottom: "1px solid #232B3B",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <span
                style={{
                  width: "28px",
                  height: "28px",
                  borderRadius: "50%",
                  background: "rgba(45, 212, 191, 0.12)",
                  border: "1px solid rgba(45, 212, 191, 0.3)",
                  color: "#5EEAD4",
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
                    stroke="currentColor"
                    strokeWidth="2"
                  />
                  <circle cx="9.5" cy="12" r="1.4" fill="currentColor" />
                  <circle cx="14.5" cy="12" r="1.4" fill="currentColor" />
                </svg>
              </span>
              <div>
                <div style={{ fontWeight: 600, fontSize: "14px", color: "#F1F5F9" }}>
                  AstroDoc Flight Surgeon
                </div>
                <div style={{ fontSize: "11px", color: "#94A3B8" }}>
                  NASA RAG Clinical Assistant{myChatAstroId ? ` · ${myChatAstroId}` : ""}
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
              background: "#0C0E12",
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
                    border: msg.role === "user" ? "1px solid rgba(45, 212, 191, 0.3)" : "1px solid #232B3B",
                    background: msg.role === "user" ? "rgba(45, 212, 191, 0.12)" : "#131720",
                    color: "#E2E8F0",
                    fontSize: "13px",
                    lineHeight: "19px",
                  }}
                >
                  <div style={{ whiteSpace: "pre-wrap" }}>{renderFormattedChatText(msg.content)}</div>
                  {msg.citations && msg.citations.length > 0 && (
                    <div style={{ marginTop: "6px", fontSize: "11px", color: "#94A3B8" }}>
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
                  color: "#64748B",
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
              background: "#131720",
              borderTop: "1px solid #232B3B",
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
                border: "1px solid #232B3B",
                background: "#0C0E12",
                color: "#F1F5F9",
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
                border: "1px solid rgba(45, 212, 191, 0.35)",
                background: "#2DD4BF",
                color: "#061312",
                fontWeight: 700,
                fontSize: "13px",
                cursor: "pointer",
              }}
            >
              {isSendingChat ? "..." : "Send"}
            </button>
          </form>
        </div>
      )}

      {/* Guided ISS-Grade Multi-Step Check-in Modal */}
      <DailyCheckInModal
        isOpen={isModalCheckInOpen}
        onClose={() => setIsModalCheckInOpen(false)}
        onSubmit={handleModalCheckInSubmit}
        currentMissionDay={latestMetrics?.mission_day || 1}
        previousMetrics={latestMetrics}
      />

      {/* Quick Station Key Login Modal */}
      {isAuthModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0, 0, 0, 0.75)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999,
            padding: "20px",
          }}
        >
          <div
            style={{
              width: "100%",
              maxWidth: "460px",
              background: "#1C1C1C",
              border: "1px solid #333333",
              borderRadius: "16px",
              padding: "28px",
              display: "flex",
              flexDirection: "column",
              gap: "20px",
              boxShadow: "0 20px 40px rgba(0, 0, 0, 0.6)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <span style={{ fontSize: "20px" }}>🔑</span>
                <div>
                  <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 600, color: "#FFFFFF" }}>
                    {leadAuthMode === "login" ? "Station Key Authentication" : "Register Station Crew Lead"}
                  </h3>
                  <p style={{ margin: "2px 0 0", fontSize: "12px", color: "#A3A3A3" }}>
                    Username and secret access key (no passwords/emails).
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsAuthModalOpen(false)}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "#A3A3A3",
                  fontSize: "18px",
                  cursor: "pointer",
                  padding: "4px 8px",
                }}
              >
                ✕
              </button>
            </div>

            <div style={{ display: "flex", gap: "8px", background: "#282828", padding: "4px", borderRadius: "8px" }}>
              <button
                type="button"
                onClick={() => setLeadAuthMode("login")}
                style={{
                  flex: 1,
                  padding: "6px 12px",
                  borderRadius: "6px",
                  border: "none",
                  background: leadAuthMode === "login" ? "#7DD3FC" : "transparent",
                  color: leadAuthMode === "login" ? "#1C1C1C" : "#A3A3A3",
                  fontWeight: 600,
                  fontSize: "12px",
                  cursor: "pointer",
                }}
              >
                Sign In
              </button>
              <button
                type="button"
                onClick={() => setLeadAuthMode("register")}
                style={{
                  flex: 1,
                  padding: "6px 12px",
                  borderRadius: "6px",
                  border: "none",
                  background: leadAuthMode === "register" ? "#7DD3FC" : "transparent",
                  color: leadAuthMode === "register" ? "#1C1C1C" : "#A3A3A3",
                  fontWeight: 600,
                  fontSize: "12px",
                  cursor: "pointer",
                }}
              >
                Register Lead
              </button>
            </div>

            {leadAuthMode === "login" ? (
              <form onSubmit={handleLeadLogin} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                  <span style={{ fontSize: "12px", color: "#A3A3A3" }}>Username</span>
                  <input
                    type="text"
                    required
                    value={leadLoginForm.username}
                    onChange={(e) => setLeadLoginForm({ ...leadLoginForm, username: e.target.value })}
                    style={{
                      height: "38px",
                      padding: "0 12px",
                      borderRadius: "8px",
                      border: "1px solid #333333",
                      background: "#282828",
                      color: "#FFFFFF",
                    }}
                  />
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                  <span style={{ fontSize: "12px", color: "#A3A3A3" }}>Station Key</span>
                  <input
                    type="password"
                    required
                    value={leadLoginForm.key}
                    onChange={(e) => setLeadLoginForm({ ...leadLoginForm, key: e.target.value })}
                    style={{
                      height: "38px",
                      padding: "0 12px",
                      borderRadius: "8px",
                      border: "1px solid #333333",
                      background: "#282828",
                      color: "#FFFFFF",
                    }}
                  />
                </label>
                <button
                  type="submit"
                  style={{
                    height: "40px",
                    borderRadius: "8px",
                    border: "none",
                    background: "#7DD3FC",
                    color: "#1C1C1C",
                    fontWeight: 600,
                    cursor: "pointer",
                    fontSize: "13px",
                  }}
                >
                  Authenticate Station Access
                </button>
              </form>
            ) : (
              <form onSubmit={handleLeadRegister} style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
                <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                  <span style={{ fontSize: "12px", color: "#A3A3A3" }}>Station Name</span>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Hermes Lunar Orbit"
                    value={leadRegisterForm.station_name}
                    onChange={(e) => setLeadRegisterForm({ ...leadRegisterForm, station_name: e.target.value })}
                    style={{
                      height: "36px",
                      padding: "0 12px",
                      borderRadius: "8px",
                      border: "1px solid #333333",
                      background: "#282828",
                      color: "#FFFFFF",
                    }}
                  />
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                  <span style={{ fontSize: "12px", color: "#A3A3A3" }}>Operating Location (applies to every crew member)</span>
                  <select
                    required
                    value={leadRegisterForm.environment}
                    onChange={(e) => setLeadRegisterForm({ ...leadRegisterForm, environment: e.target.value })}
                    style={{ height: "36px", padding: "0 12px", borderRadius: "8px", border: "1px solid #333333", background: "#1C1C1C", color: "#FFFFFF" }}
                  >
                    <option value="LUNAR">Moon (Lunar surface / orbit)</option>
                    <option value="MARS">Mars (surface / orbit)</option>
                    <option value="LEO">Low Earth Orbit (ISS-type)</option>
                    <option value="DEEP_SPACE">Deep-space transit</option>
                  </select>
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                  <span style={{ fontSize: "12px", color: "#A3A3A3" }}>Crew Division Name</span>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Crew-Alpha"
                    value={leadRegisterForm.crew_name}
                    onChange={(e) => setLeadRegisterForm({ ...leadRegisterForm, crew_name: e.target.value })}
                    style={{
                      height: "36px",
                      padding: "0 12px",
                      borderRadius: "8px",
                      border: "1px solid #333333",
                      background: "#282828",
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
                    onChange={(e) => setLeadRegisterForm({ ...leadRegisterForm, username: e.target.value })}
                    style={{
                      height: "36px",
                      padding: "0 12px",
                      borderRadius: "8px",
                      border: "1px solid #333333",
                      background: "#282828",
                      color: "#FFFFFF",
                    }}
                  />
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                  <span style={{ fontSize: "12px", color: "#A3A3A3" }}>Station Secret Key</span>
                  <input
                    type="password"
                    required
                    value={leadRegisterForm.key}
                    onChange={(e) => setLeadRegisterForm({ ...leadRegisterForm, key: e.target.value })}
                    style={{
                      height: "36px",
                      padding: "0 12px",
                      borderRadius: "8px",
                      border: "1px solid #333333",
                      background: "#282828",
                      color: "#FFFFFF",
                    }}
                  />
                </label>
                <button
                  type="submit"
                  style={{
                    height: "40px",
                    borderRadius: "8px",
                    border: "none",
                    background: "#7DD3FC",
                    color: "#1C1C1C",
                    fontWeight: 600,
                    cursor: "pointer",
                    fontSize: "13px",
                  }}
                >
                  Establish Station &amp; Crew
                </button>
              </form>
            )}

            {leadFeedback && (
              <span style={{ fontSize: "12px", color: "#96E2D6", textAlign: "center" }}>{leadFeedback}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
