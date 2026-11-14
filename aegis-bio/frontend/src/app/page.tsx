"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import {
  Activity,
  Heart,
  Shield,
  Moon,
  Radio,
  Cpu,
  TrendingUp,
  AlertOctagon,
  ChevronLeft,
  ChevronRight,
  User,
  Zap,
  RefreshCw,
  Wind,
} from "lucide-react";

import {
  CrewMember,
  WeeklyTelemetryResponse,
  PredictorResponse,
  EmergencyAlert,
} from "@/lib/types";
import { api } from "@/lib/api";
import { EmergencyBanner } from "@/components/EmergencyBanner";
import { ProactiveChatDrawer } from "@/components/ProactiveChatDrawer";

export default function MissionDashboard() {
  const [crew, setCrew] = useState<CrewMember[]>([]);
  const [selectedAstronautId, setSelectedAstronautId] = useState<string>("ASTRO-01");
  const [currentWeek, setCurrentWeek] = useState<number>(1);
  const [weeklyData, setWeeklyData] = useState<WeeklyTelemetryResponse | null>(null);
  const [prediction, setPrediction] = useState<PredictorResponse | null>(null);
  const [emergencyAlert, setEmergencyAlert] = useState<EmergencyAlert | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isChatOpen, setIsChatOpen] = useState<boolean>(false);

  // Load crew list once on mount
  useEffect(() => {
    api
      .getCrewMembers()
      .then((res) => {
        if (res.crew && res.crew.length > 0) {
          setCrew(res.crew);
        }
      })
      .catch((err) => console.error("Crew load failed:", err));
  }, []);

  // Fetch weekly telemetry and run predictor agent
  const loadWeekData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [telemetryRes, predRes, emerRes] = await Promise.all([
        api.getWeeklyTelemetry(selectedAstronautId, currentWeek),
        api.predictUpcomingHealth(selectedAstronautId, currentWeek, 7),
        api.getEmergencyStatus(selectedAstronautId),
      ]);
      setWeeklyData(telemetryRes);
      setPrediction(predRes);
      setEmergencyAlert(emerRes);
    } catch (err) {
      console.error("Failed to load telemetry:", err);
    } finally {
      setIsLoading(false);
    }
  }, [selectedAstronautId, currentWeek]);

  useEffect(() => {
    loadWeekData();
  }, [loadWeekData]);

  const handlePrevWeek = () => {
    if (currentWeek > 1) setCurrentWeek((w) => w - 1);
  };

  const handleNextWeek = () => {
    const maxWeeks = weeklyData?.astronaut.max_available_weeks || 25;
    if (currentWeek < maxWeeks) setCurrentWeek((w) => w + 1);
  };

  const handleEmergencyAck = async (alertId: string, callsign: string) => {
    await api.acknowledgeEmergency({ alert_id: alertId, crew_member_callsign: callsign });
    const updated = await api.getEmergencyStatus(selectedAstronautId);
    setEmergencyAlert(updated);
  };

  const handleTriggerDrill = async () => {
    const drill = await api.triggerEmergencyDrill();
    setEmergencyAlert(drill);
  };

  const kpis = weeklyData?.summary_kpis;
  const astro = weeklyData?.astronaut;
  const maxWeeks = astro?.max_available_weeks || 25;

  return (
    <div className="min-h-screen bg-space-950 text-slate-100 font-mono pb-12 selection:bg-cyan-500 selection:text-black">
      {/* -------------------------------------------------------------
          TOP AEROSPACE COCKPIT BAR (MINIMAL)
      -------------------------------------------------------------- */}
      <header className="sticky top-0 z-40 border-b border-slate-800 bg-space-950/95 backdrop-blur-md px-4 lg:px-6 py-2.5">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          {/* Logo & Subsystem Header */}
          <div className="flex items-center space-x-3">
            <div className="flex items-center justify-center w-7 h-7 rounded bg-cyan-950 border border-cyan-500/80 text-hud-cyan shadow-[0_0_12px_rgba(0,240,255,0.4)]">
              <Zap className="w-4 h-4 animate-pulse" />
            </div>
            <div className="flex items-center space-x-2">
              <span className="font-bold tracking-wider text-sm text-white">AEGIS-BIO</span>
              <span className="text-[10px] text-slate-500">|</span>
              <span className="text-[11px] text-slate-400">TELEMETRY COCKPIT</span>
              {/* OpenTelemetry status pill */}
              <span className="inline-flex items-center space-x-1 px-1.5 py-0.5 rounded text-[10px] bg-slate-900 border border-cyan-800/80 text-hud-cyan">
                <Radio className="w-2.5 h-2.5 animate-pulse text-hud-cyan" />
                <span>OTEL v1.2</span>
              </span>
            </div>
          </div>

          {/* Controls: Astronaut & Weekly Cycle Selector */}
          <div className="flex items-center flex-wrap gap-2">
            {/* Astronaut Selector */}
            <div className="flex items-center space-x-1.5 px-2 py-1 rounded bg-space-900 border border-slate-800 text-xs">
              <User className="w-3.5 h-3.5 text-slate-400" />
              <select
                value={selectedAstronautId}
                onChange={(e) => setSelectedAstronautId(e.target.value)}
                className="bg-transparent text-white font-mono text-xs focus:outline-none cursor-pointer"
              >
                {crew.map((c) => (
                  <option key={c.id} value={c.id} className="bg-space-900 text-white">
                    {c.id} • {c.name} ({c.age}{c.sex})
                  </option>
                ))}
              </select>
            </div>

            {/* Weekly Sliding Window Selector */}
            <div className="flex items-center rounded bg-space-900 border border-slate-800 text-xs">
              <button
                onClick={handlePrevWeek}
                disabled={currentWeek <= 1}
                className="p-1.5 text-slate-400 hover:text-white disabled:opacity-30 transition-colors"
                title="Previous Week"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <div className="px-2.5 py-1 text-center min-w-[130px] border-x border-slate-800">
                <span className="text-hud-cyan font-bold">WEEK {currentWeek}</span>
                <span className="text-slate-500 text-[10px] block">
                  Sol {astro?.start_sol || 1} – {astro?.end_sol || 7} (7-Day Reset)
                </span>
              </div>
              <button
                onClick={handleNextWeek}
                disabled={currentWeek >= maxWeeks}
                className="p-1.5 text-slate-400 hover:text-white disabled:opacity-30 transition-colors"
                title="Next Week"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>

            {/* AI Clinical Agent Drawer Button */}
            <button
              onClick={() => setIsChatOpen(true)}
              className="flex items-center space-x-1 px-2.5 py-1 rounded bg-cyan-950 hover:bg-cyan-900 text-hud-cyan border border-cyan-700/60 text-xs font-bold transition-colors"
            >
              <Cpu className="w-3.5 h-3.5" />
              <span>AGENT</span>
            </button>

            {/* Refresh */}
            <button
              onClick={loadWeekData}
              disabled={isLoading}
              className="p-1.5 rounded bg-space-900 hover:bg-space-850 border border-slate-800 text-slate-300 hover:text-white transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
            </button>
          </div>
        </div>
      </header>

      {/* -------------------------------------------------------------
          MAIN TELEMETRY WORKSPACE
      -------------------------------------------------------------- */}
      <main className="max-w-[1560px] mx-auto px-4 lg:px-6 mt-4 space-y-4">
        {/* Emergency Alert Banner (Shown only if active/unacknowledged) */}
        <EmergencyBanner
          alert={emergencyAlert}
          onAcknowledge={handleEmergencyAck}
          onTriggerDrill={handleTriggerDrill}
          onRefresh={loadDashboardData}
        />

        {/* -------------------------------------------------------------
            ROW 1: SUMMARY KPI TILES (NON-REPEATING KEY METRICS)
        -------------------------------------------------------------- */}
        <section className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {/* Tile 1: Heart Rate */}
          <div className="rounded-lg border border-slate-800/80 bg-space-900/80 p-3">
            <div className="flex items-center justify-between text-slate-400 text-[11px] mb-1">
              <span>HEART RATE</span>
              <Heart className="w-3.5 h-3.5 text-hud-cyan" />
            </div>
            <div className="flex items-baseline space-x-1">
              <span className="text-xl font-bold text-white">{kpis?.avg_heart_rate ?? "--"}</span>
              <span className="text-[10px] text-slate-500">BPM</span>
            </div>
            <div className="text-[10px] text-slate-500 mt-1">
              Min {kpis?.min_heart_rate} • Max {kpis?.max_heart_rate}
            </div>
          </div>

          {/* Tile 2: SpO2 */}
          <div className="rounded-lg border border-slate-800/80 bg-space-900/80 p-3">
            <div className="flex items-center justify-between text-slate-400 text-[11px] mb-1">
              <span>PULSE OXIMETRY</span>
              <Activity className="w-3.5 h-3.5 text-hud-green" />
            </div>
            <div className="flex items-baseline space-x-1">
              <span className="text-xl font-bold text-white">{kpis?.avg_spo2 ?? "--"}</span>
              <span className="text-[10px] text-slate-500">% SpO2</span>
            </div>
            <div className="text-[10px] text-slate-500 mt-1">
              Floor {kpis?.min_spo2}%
            </div>
          </div>

          {/* Tile 3: Autonomic Stress (HRV RMSSD) */}
          <div className="rounded-lg border border-slate-800/80 bg-space-900/80 p-3">
            <div className="flex items-center justify-between text-slate-400 text-[11px] mb-1">
              <span>STRESS (HRV)</span>
              <TrendingUp className="w-3.5 h-3.5 text-hud-purple" />
            </div>
            <div className="flex items-baseline space-x-1">
              <span className="text-xl font-bold text-white">{kpis?.avg_hrv_rmssd ?? "--"}</span>
              <span className="text-[10px] text-slate-500">ms</span>
            </div>
            <div className="text-[10px] text-slate-500 mt-1">
              Base: {crew.find((c) => c.id === selectedAstronautId)?.hrv_baseline || 50} ms
            </div>
          </div>

          {/* Tile 4: Sleep Duration */}
          <div className="rounded-lg border border-slate-800/80 bg-space-900/80 p-3">
            <div className="flex items-center justify-between text-slate-400 text-[11px] mb-1">
              <span>SLEEP REST</span>
              <Moon className="w-3.5 h-3.5 text-hud-blue" />
            </div>
            <div className="flex items-baseline space-x-1">
              <span className="text-xl font-bold text-white">{kpis?.avg_sleep_hours ?? "--"}</span>
              <span className="text-[10px] text-slate-500">hrs/sol</span>
            </div>
            <div className="text-[10px] text-slate-500 mt-1">
              Weekly Avg
            </div>
          </div>

          {/* Tile 5: Cabin CO2 */}
          <div className="rounded-lg border border-slate-800/80 bg-space-900/80 p-3">
            <div className="flex items-center justify-between text-slate-400 text-[11px] mb-1">
              <span>CABIN CO2</span>
              <Wind className="w-3.5 h-3.5 text-hud-amber" />
            </div>
            <div className="flex items-baseline space-x-1">
              <span className="text-xl font-bold text-white">{kpis?.peak_cabin_co2 ?? "--"}</span>
              <span className="text-[10px] text-slate-500">mmHg</span>
            </div>
            <div className="text-[10px] text-slate-500 mt-1">
              Limit: 3.5 mmHg
            </div>
          </div>

          {/* Tile 6: Radiation Flux */}
          <div className="rounded-lg border border-slate-800/80 bg-space-900/80 p-3">
            <div className="flex items-center justify-between text-slate-400 text-[11px] mb-1">
              <span>RADIATION</span>
              <Shield className="w-3.5 h-3.5 text-hud-red" />
            </div>
            <div className="flex items-baseline space-x-1">
              <span className="text-xl font-bold text-white">{kpis?.peak_radiation_rate ?? "--"}</span>
              <span className="text-[10px] text-slate-500">µSv/h</span>
            </div>
            <div className="text-[10px] text-slate-500 mt-1">
              Total {kpis?.cumulative_radiation_msv} mSv
            </div>
          </div>
        </section>

        {/* -------------------------------------------------------------
            ROW 2: VISUALIZATION GRIDS (DISTINCT CHART TYPES, NO REPETITION)
            - DIAGRAM 1: LINE CHART (Physiological Vitals)
            - DIAGRAM 2: AREA CHART (Ship & Habitat Environment)
        -------------------------------------------------------------- */}
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* DIAGRAM 1: LINE CHART - Continuous Vitals */}
          <div className="rounded-xl border border-slate-800 bg-space-900/90 p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center space-x-2">
                <span className="w-2 h-2 rounded-full bg-hud-cyan animate-pulse"></span>
                <h3 className="text-xs font-bold uppercase tracking-wider text-white">
                  Continuous Vitals Time-Series (Sol {astro?.start_sol}–{astro?.end_sol})
                </h3>
              </div>
              <span className="text-[10px] text-slate-500 font-mono">168-HR STREAM</span>
            </div>
            <div className="h-[250px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={weeklyData?.hourly_vitals || []} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
                  <XAxis dataKey="label" stroke="#64748b" fontSize={10} interval={23} tickLine={false} />
                  <YAxis stroke="#64748b" fontSize={10} tickLine={false} domain={["auto", "auto"]} />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#0b0f19", borderColor: "#374151", fontSize: "11px" }}
                  />
                  <Legend wrapperStyle={{ fontSize: "10px", paddingTop: "6px" }} />
                  <Line type="monotone" dataKey="heart_rate" name="Heart Rate (BPM)" stroke="#00F0FF" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                  <Line type="monotone" dataKey="systolic_bp" name="Systolic BP (mmHg)" stroke="#F59E0B" strokeWidth={1.2} dot={false} isAnimationActive={false} />
                  <Line type="monotone" dataKey="diastolic_bp" name="Diastolic BP (mmHg)" stroke="#38BDF8" strokeWidth={1.2} dot={false} isAnimationActive={false} />
                  <Line type="monotone" dataKey="respiratory_rate" name="Respiration (BPM)" stroke="#A855F7" strokeWidth={1.2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* DIAGRAM 2: AREA CHART - Ship Environment & Life Support */}
          <div className="rounded-xl border border-slate-800 bg-space-900/90 p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center space-x-2">
                <span className="w-2 h-2 rounded-full bg-hud-amber animate-pulse"></span>
                <h3 className="text-xs font-bold uppercase tracking-wider text-white">
                  Spacecraft Environment & ECLSS (Sol {astro?.start_sol}–{astro?.end_sol})
                </h3>
              </div>
              <span className="text-[10px] text-slate-500 font-mono">HABITAT LIFE SUPPORT</span>
            </div>
            <div className="h-[250px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={weeklyData?.ship_environment || []} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="co2Grad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#F59E0B" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#F59E0B" stopOpacity={0.0} />
                    </linearGradient>
                    <linearGradient id="radGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#EF4444" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#EF4444" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
                  <XAxis dataKey="label" stroke="#64748b" fontSize={10} interval={23} tickLine={false} />
                  <YAxis stroke="#64748b" fontSize={10} tickLine={false} domain={["auto", "auto"]} />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#0b0f19", borderColor: "#374151", fontSize: "11px" }}
                  />
                  <Legend wrapperStyle={{ fontSize: "10px", paddingTop: "6px" }} />
                  <Area type="monotone" dataKey="cabin_co2" name="Cabin CO2 (mmHg)" stroke="#F59E0B" fill="url(#co2Grad)" strokeWidth={1.5} isAnimationActive={false} />
                  <Area type="monotone" dataKey="radiation_rate_usv" name="Radiation (µSv/h)" stroke="#EF4444" fill="url(#radGrad)" strokeWidth={1.5} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </section>

        {/* -------------------------------------------------------------
            ROW 3: STATUS PIE CHART & STRESS/RECOVERY BAR CHART
            - DIAGRAM 3: DONUT / PIE CHART (Metric Status Distribution)
            - DIAGRAM 4: GROUPED BAR CHART (Autonomic Stress vs Sleep)
        -------------------------------------------------------------- */}
        <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* DIAGRAM 3: DONUT / PIE CHART - Status Distribution */}
          <div className="rounded-xl border border-slate-800 bg-space-900/90 p-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-white">
                Weekly Health Triage Breakdown
              </h3>
              <span className="text-[10px] text-slate-500 font-mono">168 HRS</span>
            </div>
            <div className="h-[210px] w-full flex items-center justify-center">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={weeklyData?.status_distribution || []}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={50}
                    outerRadius={75}
                    paddingAngle={3}
                  >
                    {(weeklyData?.status_distribution || []).map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ backgroundColor: "#0b0f19", borderColor: "#374151", fontSize: "11px" }} />
                  <Legend wrapperStyle={{ fontSize: "10px", paddingTop: "4px" }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="text-[10px] text-slate-400 text-center mt-1">
              Primary Driver: <span className="text-hud-amber font-bold">{kpis?.dominant_driver || "NOMINAL"}</span>
            </div>
          </div>

          {/* DIAGRAM 4: GROUPED BAR CHART - Daily Stress vs Sleep Recovery */}
          <div className="md:col-span-2 rounded-xl border border-slate-800 bg-space-900/90 p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center space-x-2">
                <span className="w-2 h-2 rounded-full bg-hud-purple animate-pulse"></span>
                <h3 className="text-xs font-bold uppercase tracking-wider text-white">
                  Autonomic Stress (HRV RMSSD) vs. Sleep Recovery (Per Sol)
                </h3>
              </div>
              <span className="text-[10px] text-slate-500 font-mono">7-DAY SLIDING CYCLE</span>
            </div>
            <div className="h-[210px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={weeklyData?.stress_recovery_daily || []} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
                  <XAxis dataKey="sol_label" stroke="#64748b" fontSize={10} tickLine={false} />
                  <YAxis stroke="#64748b" fontSize={10} tickLine={false} domain={[0, "auto"]} />
                  <Tooltip contentStyle={{ backgroundColor: "#0b0f19", borderColor: "#374151", fontSize: "11px" }} />
                  <Legend wrapperStyle={{ fontSize: "10px", paddingTop: "4px" }} />
                  <Bar dataKey="stress_hrv_rmssd" name="HRV RMSSD (ms)" fill="#A855F7" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="sleep_hours" name="Sleep Hours (h)" fill="#38BDF8" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </section>

        {/* -------------------------------------------------------------
            ROW 4: PREDICTOR AGENT (7-DAY FORWARD HEALTH FORECAST)
        -------------------------------------------------------------- */}
        <section className="rounded-xl border border-cyan-900/60 bg-space-900/90 p-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-4 border-b border-slate-800 pb-3">
            <div className="flex items-center space-x-2.5">
              <div className="p-1.5 rounded bg-cyan-950 border border-cyan-600 text-hud-cyan">
                <Cpu className="w-4 h-4 animate-pulse" />
              </div>
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-white">
                  Autonomous Health Predictor Agent (Upcoming 7-Day Forecast)
                </h3>
                <p className="text-[10px] text-slate-400">
                  Multivariate regression coupled with spacecraft environment metrics (Stress, O2, Cabin CO2, Radiation)
                </p>
              </div>
            </div>
            <div className="flex items-center space-x-2 text-xs">
              <span className="text-slate-400 text-[11px]">PROJECTED OUTLOOK:</span>
              <span
                className={`px-2 py-0.5 rounded font-bold text-[10px] uppercase border ${
                  prediction?.health_outlook === "CRITICAL_DRIFT"
                    ? "bg-red-950 text-red-400 border-red-800"
                    : prediction?.health_outlook === "ELEVATED_STRAIN"
                    ? "bg-amber-950 text-amber-400 border-amber-800"
                    : "bg-emerald-950 text-emerald-400 border-emerald-800"
                }`}
              >
                {prediction?.health_outlook || "CALCULATING..."}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
            {/* Predictor Risk Gauges */}
            <div className="space-y-3 font-mono text-xs">
              {/* Gauge 1: Cardiovascular Strain */}
              <div>
                <div className="flex justify-between text-slate-300 text-[11px] mb-1">
                  <span>Cardiovascular Strain</span>
                  <span className="text-hud-cyan font-bold">{prediction?.cardiovascular_strain_score || 0}%</span>
                </div>
                <div className="w-full h-1.5 rounded-full bg-space-800 overflow-hidden">
                  <div
                    className="h-full bg-hud-cyan rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(100, prediction?.cardiovascular_strain_score || 0)}%` }}
                  />
                </div>
              </div>

              {/* Gauge 2: Cognitive Fatigue Risk */}
              <div>
                <div className="flex justify-between text-slate-300 text-[11px] mb-1">
                  <span>Cognitive Fatigue Risk</span>
                  <span className="text-hud-purple font-bold">{prediction?.cognitive_fatigue_risk || 0}%</span>
                </div>
                <div className="w-full h-1.5 rounded-full bg-space-800 overflow-hidden">
                  <div
                    className="h-full bg-hud-purple rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(100, prediction?.cognitive_fatigue_risk || 0)}%` }}
                  />
                </div>
              </div>

              {/* Gauge 3: Hypoxia / ECLSS Risk */}
              <div>
                <div className="flex justify-between text-slate-300 text-[11px] mb-1">
                  <span>Hypoxia / ECLSS Strain</span>
                  <span className="text-hud-amber font-bold">{prediction?.hypoxia_eclss_risk || 0}%</span>
                </div>
                <div className="w-full h-1.5 rounded-full bg-space-800 overflow-hidden">
                  <div
                    className="h-full bg-hud-amber rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(100, prediction?.hypoxia_eclss_risk || 0)}%` }}
                  />
                </div>
              </div>

              {/* Gauge 4: Radiation Hazard Index */}
              <div>
                <div className="flex justify-between text-slate-300 text-[11px] mb-1">
                  <span>Radiation Hazard Index</span>
                  <span className="text-hud-red font-bold">{prediction?.radiation_hazard_index || 0}%</span>
                </div>
                <div className="w-full h-1.5 rounded-full bg-space-800 overflow-hidden">
                  <div
                    className="h-full bg-hud-red rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(100, prediction?.radiation_hazard_index || 0)}%` }}
                  />
                </div>
              </div>

              {/* Clinical Directives */}
              <div className="pt-2 border-t border-slate-800 text-[10px] space-y-1.5">
                <span className="text-slate-400 font-bold block uppercase">PREDICTED ACTION DIRECTIVES:</span>
                {(prediction?.clinical_directives || []).map((dir, i) => (
                  <div key={i} className="p-1.5 rounded bg-space-850 border border-slate-800">
                    <div className="flex items-center justify-between text-hud-cyan font-semibold">
                      <span>{dir.category}</span>
                      <span className="text-hud-amber">{dir.urgency}</span>
                    </div>
                    <p className="text-slate-300 mt-0.5">{dir.action}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Projected Trajectory Chart (7 Future Sols) */}
            <div className="lg:col-span-3 h-[240px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={prediction?.projected_trajectory || []} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
                  <XAxis dataKey="sol_label" stroke="#64748b" fontSize={10} tickLine={false} />
                  <YAxis stroke="#64748b" fontSize={10} tickLine={false} domain={[0, 100]} />
                  <Tooltip contentStyle={{ backgroundColor: "#0b0f19", borderColor: "#374151", fontSize: "11px" }} />
                  <Legend wrapperStyle={{ fontSize: "10px", paddingTop: "4px" }} />
                  <Line type="monotone" dataKey="cardiovascular_strain" name="Predicted CV Strain (%)" stroke="#00F0FF" strokeWidth={2} strokeDasharray="5 5" dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="cognitive_fatigue" name="Predicted Cognitive Fatigue (%)" stroke="#A855F7" strokeWidth={2} strokeDasharray="5 5" dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="predicted_heart_rate" name="Predicted Heart Rate (BPM)" stroke="#F59E0B" strokeWidth={1.5} dot={{ r: 2 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </section>
      </main>

      {/* Slide-Over Proactive Chat Drawer */}
      <ProactiveChatDrawer
        isOpen={isChatOpen}
        onClose={() => setIsChatOpen(false)}
        latestMetrics={null}
      />
    </div>
  );
}
