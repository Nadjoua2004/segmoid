"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Heart,
  Activity,
  ShieldAlert,
  Moon,
  Radio,
  Thermometer,
  Bot,
  PlusCircle,
  RefreshCw,
  AlertTriangle,
  FileText,
  Clock,
  Compass,
  Zap,
} from "lucide-react";

import {
  HealthMetricsResponse,
  TriageResult,
  PredictionResult,
  EmergencyAlert,
  DailyCheckInPayload,
} from "@/lib/types";
import { api } from "@/lib/api";

import { TelemetryCard } from "@/components/TelemetryCard";
import { VitalsChart } from "@/components/VitalsChart";
import { DailyCheckInModal } from "@/components/DailyCheckInModal";
import { ProactiveChatDrawer } from "@/components/ProactiveChatDrawer";
import { EmergencyBanner } from "@/components/EmergencyBanner";

export default function MissionDashboard() {
  const [history, setHistory] = useState<HealthMetricsResponse[]>([]);
  const [latestMetrics, setLatestMetrics] = useState<HealthMetricsResponse | null>(null);
  const [triage, setTriage] = useState<TriageResult | null>(null);
  const [prediction, setPrediction] = useState<PredictionResult | null>(null);
  const [emergencyAlert, setEmergencyAlert] = useState<EmergencyAlert | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [isCheckInOpen, setIsCheckInOpen] = useState(false);
  const [isChatOpen, setIsChatOpen] = useState(false);

  const loadDashboardData = useCallback(async () => {
    setIsLoading(true);
    try {
      // 1. Fetch History
      const histData = await api.getMetricsHistory();
      setHistory(histData);

      // 2. Fetch Latest Metrics
      if (histData.length > 0) {
        setLatestMetrics(histData[histData.length - 1]);
      }

      // 3. Fetch Triage Assessment
      const triageData = await api.getCurrentTriage();
      setTriage(triageData);

      // 4. Fetch 7-Day Forecast Trajectory
      const predData = await api.getPredictedTrajectory();
      setPrediction(predData);

      // 5. Fetch Emergency Status
      const emerData = await api.getEmergencyStatus();
      setEmergencyAlert(emerData);
    } catch (err) {
      console.error("Dashboard data load error:", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  // Handle astronaut daily check-in submission
  // Returns the saved record (with advice flags) so the modal can show the result;
  // the dashboard refresh runs in the background.
  const handleCheckInSubmit = async (payload: DailyCheckInPayload) => {
    const record = await api.submitDailyCheckIn(payload);
    void loadDashboardData();
    return record;
  };

  // Handle intra-crew emergency acknowledgment
  const handleEmergencyAck = async (alertId: string, callsign: string) => {
    await api.acknowledgeEmergency({ alert_id: alertId, crew_member_callsign: callsign });
    const updated = await api.getEmergencyStatus();
    setEmergencyAlert(updated);
  };

  // Handle emergency simulation drill
  const handleTriggerDrill = async () => {
    const drillAlert = await api.triggerEmergencyDrill();
    setEmergencyAlert(drillAlert);
  };

  const currentMissionDay = latestMetrics ? latestMetrics.mission_day : 30;

  // Generate sparkline values for core cards
  const hrSparkline = history.slice(-8).map((h) => ({ val: h.heart_rate }));
  const spo2Sparkline = history.slice(-8).map((h) => ({ val: h.spo2 }));
  const radSparkline = history.slice(-8).map((h) => ({ val: h.radiation_msv }));
  const sleepSparkline = history.slice(-8).map((h) => ({ val: h.sleep_hours }));

  return (
    <div className="min-h-screen text-slate-100 pb-16">
      {/* -------------------------------------------------------------
          TOP AEROSPACE COCKPIT BAR
      -------------------------------------------------------------- */}
      <header className="sticky top-0 z-40 border-b border-cyan-900/50 bg-space-950/90 backdrop-blur-md px-4 lg:px-8 py-3">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          {/* Project Title & Mission Breadcrumb */}
          <div className="flex items-center space-x-3">
            <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-cyan-950 border border-cyan-500/60 shadow-[0_0_15px_rgba(0,240,255,0.4)]">
              <Zap className="w-5 h-5 text-hud-cyan animate-pulse" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-base font-mono font-bold tracking-wider text-white">
                  AEGIS-BIO
                </h1>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-cyan-900/50 text-hud-cyan border border-cyan-700/60 uppercase">
                  Flight Surgeon Core v1.0
                </span>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                  Team Sigmoid
                </span>
              </div>
              <p className="text-xs font-mono text-slate-400">
                Artemis Base Alpha • Astronaut Helena [ASTRO-7702] • Sol {currentMissionDay}
              </p>
            </div>
          </div>

          {/* Deep Space Comm Delay & Action Controls */}
          <div className="flex items-center flex-wrap gap-2.5">
            {/* 18.5 Min Comm Delay Badge */}
            <div className="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-space-900 border border-amber-800/60 text-amber-300 text-xs font-mono">
              <Radio className="w-3.5 h-3.5 text-hud-amber animate-pulse" />
              <span>Latency: 18.5 min to MCC</span>
              <span className="text-[10px] text-slate-400 border-l border-amber-900/60 pl-1.5">
                AUTONOMOUS MODE
              </span>
            </div>

            {/* Daily Check-in Button */}
            <button
              onClick={() => setIsCheckInOpen(true)}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-mono font-bold uppercase tracking-wider transition-all shadow-[0_0_15px_rgba(0,240,255,0.25)]"
            >
              <PlusCircle className="w-3.5 h-3.5" />
              <span>Log Check-in</span>
            </button>

            {/* AI Flight Surgeon Drawer Toggle */}
            <button
              onClick={() => setIsChatOpen(true)}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-space-850 hover:bg-space-800 border border-cyan-800/70 text-hud-cyan text-xs font-mono font-bold uppercase tracking-wider transition-all"
            >
              <Bot className="w-3.5 h-3.5" />
              <span>AI Surgeon (RAG)</span>
            </button>

            {/* Refresh Button */}
            <button
              onClick={loadDashboardData}
              disabled={isLoading}
              title="Refresh telemetry"
              className="p-2 rounded-lg bg-space-900 hover:bg-space-850 border border-slate-700 text-slate-300 hover:text-white transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
            </button>
          </div>
        </div>
      </header>

      {/* -------------------------------------------------------------
          MAIN CONTENT CONTAINER
      -------------------------------------------------------------- */}
      <main className="max-w-7xl mx-auto px-4 lg:px-8 mt-5 space-y-6">
        {/* Intra-Crew Emergency Alert Banner */}
        <EmergencyBanner
          alert={emergencyAlert}
          onAcknowledge={handleEmergencyAck}
          onTriggerDrill={handleTriggerDrill}
        />

        {/* -------------------------------------------------------------
            ROW 1: CORE TELEMETRY VITALS GRID
        -------------------------------------------------------------- */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-mono uppercase tracking-widest text-slate-400 flex items-center space-x-2">
              <Activity className="w-4 h-4 text-hud-cyan" />
              <span>Continuous Physiological Telemetry & Biometrics</span>
            </h2>
            <span className="text-[11px] font-mono text-slate-500">
              Sensors: Biosensor Patch Array 4B • Telemetry Stream 1 Hz
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Heart Rate */}
            <TelemetryCard
              title="Resting Heart Rate"
              hazardLabel="Microgravity Hazard"
              value={latestMetrics ? latestMetrics.heart_rate : 76}
              unit="BPM"
              icon={Heart}
              status={
                latestMetrics && latestMetrics.heart_rate > 115
                  ? "critical"
                  : latestMetrics && latestMetrics.heart_rate > 95
                  ? "warning"
                  : "nominal"
              }
              sparklineData={hrSparkline}
              trend={latestMetrics && latestMetrics.heart_rate > 85 ? "up" : "flat"}
              trendValue="+12% from baseline"
              subtitle="Fluid cephalad shift index"
            />

            {/* SpO2 */}
            <TelemetryCard
              title="Pulse Oximetry"
              hazardLabel="Closed Habitat"
              value={latestMetrics ? latestMetrics.spo2 : 98}
              unit="%"
              icon={Activity}
              status={
                latestMetrics && latestMetrics.spo2 < 93
                  ? "critical"
                  : latestMetrics && latestMetrics.spo2 < 96
                  ? "warning"
                  : "nominal"
              }
              sparklineData={spo2Sparkline}
              trend="flat"
              trendValue="98.2% nominal"
              subtitle="Habitat cabin ppO2 sync"
            />

            {/* Radiation Dose */}
            <TelemetryCard
              title="Daily Radiation Dose"
              hazardLabel="Space Radiation"
              value={latestMetrics ? latestMetrics.radiation_msv : 1.2}
              unit="mSv/day"
              icon={ShieldAlert}
              status={
                latestMetrics && latestMetrics.radiation_msv >= 20.0
                  ? "critical"
                  : latestMetrics && latestMetrics.radiation_msv >= 5.0
                  ? "warning"
                  : "nominal"
              }
              sparklineData={radSparkline}
              trend={latestMetrics && latestMetrics.radiation_msv > 3.0 ? "up" : "flat"}
              trendValue={latestMetrics && latestMetrics.radiation_msv >= 18 ? "SPE Surge" : "Normal"}
              subtitle="Active Silicon Dosimeter"
            />

            {/* Sleep Hours & Mood */}
            <TelemetryCard
              title="Circadian Sleep"
              hazardLabel="Isolation Hazard"
              value={latestMetrics ? latestMetrics.sleep_hours : 6.5}
              unit="Hours"
              icon={Moon}
              status={
                latestMetrics && latestMetrics.sleep_hours < 4.5 && latestMetrics.mood_score <= 2
                  ? "critical"
                  : latestMetrics && latestMetrics.sleep_hours < 5.5
                  ? "warning"
                  : "nominal"
              }
              sparklineData={sleepSparkline}
              trend={latestMetrics && latestMetrics.sleep_hours < 5.0 ? "down" : "flat"}
              trendValue={`Mood: ${latestMetrics ? latestMetrics.mood_score : 4}/5`}
              subtitle="Cumulative REM deficit: -4.2h"
            />
          </div>
        </section>

        {/* -------------------------------------------------------------
            ROW 2: NASA 5-HAZARD RISK MATRIX & COUNTERMEASURES
        -------------------------------------------------------------- */}
        <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* 5 Spaceflight Hazards Matrix */}
          <div className="rounded-xl border border-slate-800 bg-space-900/90 p-5 backdrop-blur-md">
            <div className="flex items-center justify-between mb-4 border-b border-slate-800 pb-3">
              <div className="flex items-center space-x-2">
                <Compass className="w-4 h-4 text-hud-cyan" />
                <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-white">
                  NASA 5 Spaceflight Hazards Radar
                </h3>
              </div>
              <span
                className={`text-[10px] font-mono px-2 py-0.5 rounded border uppercase font-bold ${
                  triage?.overall_status === "CRITICAL"
                    ? "bg-red-950 text-red-400 border-red-700"
                    : triage?.overall_status === "HIGH"
                    ? "bg-amber-950 text-amber-400 border-amber-700"
                    : "bg-cyan-950 text-cyan-400 border-cyan-700"
                }`}
              >
                {triage?.overall_status || "NOMINAL"} (Score: {triage?.overall_risk_score || 25}/100)
              </span>
            </div>

            {/* Hazard Progress Sliders */}
            <div className="space-y-3 font-mono text-xs">
              {/* 1. Space Radiation */}
              <div>
                <div className="flex justify-between text-slate-300 mb-1">
                  <span>1. Space Radiation (SPE / GCR)</span>
                  <span className="text-hud-amber font-bold">
                    {triage?.hazards.radiation_score || 15}%
                  </span>
                </div>
                <div className="w-full h-2 rounded-full bg-space-800 overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-yellow-500 to-red-500 rounded-full transition-all duration-500"
                    style={{ width: `${triage?.hazards.radiation_score || 15}%` }}
                  />
                </div>
              </div>

              {/* 2. Microgravity */}
              <div>
                <div className="flex justify-between text-slate-300 mb-1">
                  <span>2. Microgravity (Cardiovascular)</span>
                  <span className="text-hud-cyan font-bold">
                    {triage?.hazards.microgravity_score || 20}%
                  </span>
                </div>
                <div className="w-full h-2 rounded-full bg-space-800 overflow-hidden">
                  <div
                    className="h-full bg-hud-cyan rounded-full transition-all duration-500"
                    style={{ width: `${triage?.hazards.microgravity_score || 20}%` }}
                  />
                </div>
              </div>

              {/* 3. Isolation & Confinement */}
              <div>
                <div className="flex justify-between text-slate-300 mb-1">
                  <span>3. Isolation & Circadian Deprivation</span>
                  <span className="text-hud-purple font-bold">
                    {triage?.hazards.isolation_score || 25}%
                  </span>
                </div>
                <div className="w-full h-2 rounded-full bg-space-800 overflow-hidden">
                  <div
                    className="h-full bg-hud-purple rounded-full transition-all duration-500"
                    style={{ width: `${triage?.hazards.isolation_score || 25}%` }}
                  />
                </div>
              </div>

              {/* 4. Distance from Earth */}
              <div>
                <div className="flex justify-between text-slate-300 mb-1">
                  <span>4. Distance from Earth (24m Comm Delay)</span>
                  <span className="text-slate-400 font-bold">
                    {triage?.hazards.distance_score || 55}%
                  </span>
                </div>
                <div className="w-full h-2 rounded-full bg-space-800 overflow-hidden">
                  <div
                    className="h-full bg-slate-500 rounded-full transition-all duration-500"
                    style={{ width: `${triage?.hazards.distance_score || 55}%` }}
                  />
                </div>
              </div>

              {/* 5. Hostile Closed Environment */}
              <div>
                <div className="flex justify-between text-slate-300 mb-1">
                  <span>5. Hostile Closed Habitat / ECLSS</span>
                  <span className="text-hud-green font-bold">
                    {triage?.hazards.hostile_env_score || 15}%
                  </span>
                </div>
                <div className="w-full h-2 rounded-full bg-space-800 overflow-hidden">
                  <div
                    className="h-full bg-hud-green rounded-full transition-all duration-500"
                    style={{ width: `${triage?.hazards.hostile_env_score || 15}%` }}
                  />
                </div>
              </div>
            </div>

            {/* Active Clinical Flags */}
            {triage?.clinical_flags && triage.clinical_flags.length > 0 && (
              <div className="mt-4 pt-3 border-t border-slate-800 font-mono text-[11px]">
                <span className="text-slate-400 font-semibold block mb-1">
                  Active Clinical Triage Flags:
                </span>
                <ul className="space-y-1 text-amber-300">
                  {triage.clinical_flags.map((flag, idx) => (
                    <li key={idx} className="flex items-start space-x-1.5">
                      <AlertTriangle className="w-3.5 h-3.5 text-hud-amber mt-0.5 flex-shrink-0" />
                      <span>{flag}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Prescribed Countermeasures List */}
          <div className="lg:col-span-2 rounded-xl border border-slate-800 bg-space-900/90 p-5 backdrop-blur-md flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-4 border-b border-slate-800 pb-3">
                <div className="flex items-center space-x-2">
                  <FileText className="w-4 h-4 text-hud-cyan" />
                  <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-white">
                    Actionable Clinical Countermeasures (NASA HRP Guidelines)
                  </h3>
                </div>
                <span className="text-[10px] font-mono text-slate-400">
                  Autonomous Protocol Generator
                </span>
              </div>

              {/* Countermeasure Cards */}
              <div className="space-y-2.5 max-h-[260px] overflow-y-auto pr-1">
                {triage?.countermeasures && triage.countermeasures.length > 0 ? (
                  triage.countermeasures.map((cm) => (
                    <div
                      key={cm.id}
                      className="p-3 rounded-lg bg-space-850 border border-slate-700/70 hover:border-cyan-700 transition-colors"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono font-bold text-white tracking-wide">
                          {cm.title}
                        </span>
                        <div className="flex items-center space-x-2">
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-space-800 text-slate-300 border border-slate-700">
                            {cm.category}
                          </span>
                          <span
                            className={`text-[10px] font-mono px-1.5 py-0.5 rounded font-bold ${
                              cm.urgency === "IMMEDIATE"
                                ? "bg-red-950 text-red-400 border border-red-800"
                                : "bg-cyan-950 text-cyan-400 border border-cyan-800"
                            }`}
                          >
                            {cm.urgency}
                          </span>
                        </div>
                      </div>
                      <p className="text-xs text-slate-300 mt-1 font-mono">{cm.protocol}</p>
                      <p className="text-[10px] text-slate-500 mt-1 font-mono">
                        Ref: {cm.nasa_hrp_reference}
                      </p>
                    </div>
                  ))
                ) : (
                  <div className="text-center py-8 text-xs font-mono text-slate-400">
                    No urgent clinical countermeasures indicated. Standard mission nutrition and
                    resistive cycle ergometer routine active.
                  </div>
                )}
              </div>
            </div>

            {/* Rationale Footer */}
            <div className="mt-4 pt-3 border-t border-slate-800/80 text-[11px] font-mono text-slate-400 flex items-center justify-between">
              <span>{triage?.ai_rationale || "All telemetry nominal."}</span>
              <button
                onClick={() => setIsChatOpen(true)}
                className="text-hud-cyan hover:underline flex items-center space-x-1"
              >
                <span>Consult AI Flight Surgeon</span>
                <span>→</span>
              </button>
            </div>
          </div>
        </section>

        {/* -------------------------------------------------------------
            ROW 3: COMPREHENSIVE VITALS CHART & 7-DAY PREDICTION
        -------------------------------------------------------------- */}
        <section>
          <VitalsChart
            history={history}
            trajectory={prediction?.projected_trajectory || []}
          />
        </section>

        {/* -------------------------------------------------------------
            ROW 4: FORECASTING STRAIN SCORES & EARLY WARNINGS
        -------------------------------------------------------------- */}
        <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Cardiovascular Strain Score */}
          <div className="rounded-xl border border-slate-800 bg-space-900/90 p-5 backdrop-blur-md">
            <h4 className="text-xs font-mono uppercase text-slate-400 mb-2">
              Predicted 7-Day Cardiovascular Strain
            </h4>
            <div className="flex items-baseline space-x-2">
              <span className="text-3xl font-mono font-bold text-hud-cyan">
                {prediction ? prediction.cardiovascular_strain_score : 28.5}
              </span>
              <span className="text-xs font-mono text-slate-400">/ 100 Index</span>
            </div>
            <p className="text-xs text-slate-400 mt-2 font-mono">
              Composite model weighing plasma volume loss, resting pulse acceleration, and orthostatic
              rebound.
            </p>
          </div>

          {/* Cognitive Degradation Risk */}
          <div className="rounded-xl border border-slate-800 bg-space-900/90 p-5 backdrop-blur-md">
            <h4 className="text-xs font-mono uppercase text-slate-400 mb-2">
              Cognitive Degradation Risk
            </h4>
            <div className="flex items-baseline space-x-2">
              <span className="text-3xl font-mono font-bold text-hud-purple">
                {prediction ? prediction.cognitive_degradation_risk : 22.0}%
              </span>
              <span className="text-xs font-mono text-slate-400">Failure Probability</span>
            </div>
            <p className="text-xs text-slate-400 mt-2 font-mono">
              PVT reaction time lapse model based on cumulative sleep debt below 5 hours per night.
            </p>
          </div>

          {/* Early Inflection Warnings */}
          <div className="rounded-xl border border-slate-800 bg-space-900/90 p-5 backdrop-blur-md">
            <h4 className="text-xs font-mono uppercase text-slate-400 mb-2">
              Early Trend Inflection Warnings
            </h4>
            {prediction?.early_warnings && prediction.early_warnings.length > 0 ? (
              <ul className="space-y-1.5 text-xs font-mono text-amber-300">
                {prediction.early_warnings.map((warn, wIdx) => (
                  <li key={wIdx} className="flex items-start space-x-1.5">
                    <span className="text-hud-amber font-bold">•</span>
                    <span>{warn}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs font-mono text-emerald-400">
                ✓ No critical trajectory inflection points detected across 7-day regression horizon.
              </p>
            )}
          </div>
        </section>
      </main>

      {/* -------------------------------------------------------------
          MODALS & SLIDE-OVER DRAWERS
      -------------------------------------------------------------- */}
      <DailyCheckInModal
        isOpen={isCheckInOpen}
        onClose={() => setIsCheckInOpen(false)}
        onSubmit={handleCheckInSubmit}
        currentMissionDay={currentMissionDay}
        previousMetrics={latestMetrics}
      />

      <ProactiveChatDrawer
        isOpen={isChatOpen}
        onClose={() => setIsChatOpen(false)}
        latestMetrics={latestMetrics}
      />
    </div>
  );
}
