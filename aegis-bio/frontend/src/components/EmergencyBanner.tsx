"use client";

import React, { useState, useEffect } from "react";
import { AlertOctagon, ShieldAlert, CheckCircle2, Siren, Radio, UserCheck, Clock, ArrowRight } from "lucide-react";
import { EmergencyAlert } from "@/lib/types";
import { api } from "@/lib/api";

interface EmergencyBannerProps {
  alert: EmergencyAlert | null;
  onAcknowledge: (alertId: string, callsign: string) => Promise<void>;
  onTriggerDrill: () => Promise<void>;
  onRefresh?: () => Promise<void>;
}

export const EmergencyBanner: React.FC<EmergencyBannerProps> = ({
  alert,
  onAcknowledge,
  onTriggerDrill,
  onRefresh,
}) => {
  const [callsign, setCallsign] = useState("CMO-ASTRONAUT-1");
  const [isAcking, setIsAcking] = useState(false);
  const [ownerNotes, setOwnerNotes] = useState("");
  const [countdown, setCountdown] = useState<number | null>(null);

  // Local tick countdown for real-time responsiveness
  useEffect(() => {
    if (alert && alert.status === "PENDING_OWNER" && alert.remaining_seconds !== undefined && alert.remaining_seconds !== null) {
      setCountdown(alert.remaining_seconds);
      const timer = setInterval(() => {
        setCountdown((prev) => {
          if (prev === null || prev <= 1) {
            clearInterval(timer);
            if (onRefresh) onRefresh();
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
      return () => clearInterval(timer);
    } else {
      setCountdown(null);
    }
  }, [alert?.alert_id, alert?.status, alert?.remaining_seconds]);

  if (!alert) {
    return (
      <div className="flex items-center justify-between px-4 py-2.5 rounded-xl border border-emerald-900/40 bg-emerald-950/20 text-emerald-400 text-xs font-mono">
        <div className="flex items-center space-x-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
          <span>INTRA-CREW ESCALATION MONITOR: NOMINAL — NO ACTIVE EMERGENCY ALARMS</span>
        </div>
        <button
          onClick={onTriggerDrill}
          className="text-[11px] px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors"
        >
          Simulate Emergency Drill
        </button>
      </div>
    );
  }

  const isSwitchedToContact = alert.status === "SWITCHED_TO_EMERGENCY_CONTACT" || countdown === 0;

  const handleOwnerAnswer = async () => {
    setIsAcking(true);
    try {
      await api.answerAlarmAsOwner(alert.alert_id, ownerNotes || "Astronaut responsive.");
      if (onRefresh) await onRefresh();
    } catch (err: any) {
      console.error("Owner answer failed:", err);
      if (onRefresh) await onRefresh();
    } finally {
      setIsAcking(false);
    }
  };

  const handleContactAck = async () => {
    setIsAcking(true);
    try {
      await api.acknowledgeAsEmergencyContact(
        alert.alert_id,
        callsign || alert.emergency_contact_callsign || "ASTRO-02",
        "Intervention recorded by emergency contact."
      );
      if (onRefresh) await onRefresh();
    } catch (err: any) {
      console.error("Contact ack failed:", err);
      await onAcknowledge(alert.alert_id, callsign);
    } finally {
      setIsAcking(false);
    }
  };

  return (
    <div
      className={`relative overflow-hidden rounded-xl border-2 p-4 shadow-[0_0_40px_rgba(239,68,68,0.4)] text-white backdrop-blur-md animate-glow-red ${
        isSwitchedToContact
          ? "border-amber-500 bg-amber-950/90 shadow-[0_0_40px_rgba(245,158,11,0.4)]"
          : "border-red-600 bg-red-950/90"
      }`}
    >
      {/* Background Strobe Line */}
      <div
        className={`absolute top-0 left-0 w-full h-1 bg-gradient-to-r animate-pulse ${
          isSwitchedToContact
            ? "from-amber-600 via-orange-400 to-amber-600"
            : "from-red-600 via-yellow-400 to-red-600"
        }`}
      ></div>

      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
        {/* Left Info Section */}
        <div className="flex items-start space-x-3.5">
          <div
            className={`p-2.5 rounded-xl border animate-bounce ${
              isSwitchedToContact
                ? "bg-amber-900/80 border-amber-500 text-amber-200"
                : "bg-red-900/80 border-red-500 text-red-200"
            }`}
          >
            <Siren className="w-6 h-6" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`px-2 py-0.5 rounded text-white font-mono font-bold text-xs uppercase tracking-wider ${
                  isSwitchedToContact ? "bg-amber-600" : "bg-red-600"
                }`}
              >
                {alert.severity}
              </span>
              <span className="text-xs font-mono text-red-300 font-bold">
                ALERT ID: {alert.alert_id}
              </span>
              <span className="flex items-center text-[10px] font-mono text-red-200 bg-red-900/60 px-2 py-0.5 rounded border border-red-700">
                <Radio className="w-3 h-3 mr-1" />
                24-MIN EARTH LATENCY: AUTONOMOUS ESCALATION ACTIVE
              </span>

              {/* Dead-Man's Switch Status Badge */}
              {isSwitchedToContact ? (
                <span className="flex items-center text-[10px] font-mono font-bold bg-amber-500/20 text-amber-300 px-2.5 py-0.5 rounded border border-amber-500">
                  <UserCheck className="w-3 h-3 mr-1 text-amber-400" />
                  ESCALATED: SWITCHED TO CONTACT {alert.emergency_contact_callsign} ({alert.emergency_contact_name})
                </span>
              ) : countdown !== null ? (
                <span className="flex items-center text-[10px] font-mono font-bold bg-red-500/20 text-yellow-300 px-2.5 py-0.5 rounded border border-yellow-500/50 animate-pulse">
                  <Clock className="w-3 h-3 mr-1 text-yellow-400" />
                  DEAD-MAN TIMEOUT: {countdown}s REMAINING BEFORE CONTACT SWITCH
                </span>
              ) : null}
            </div>

            <h3 className="text-base font-mono font-bold mt-1 text-white tracking-wide">
              {alert.hazard_origin}: {alert.message}
            </h3>

            {/* Emergency Contact routing details */}
            {alert.emergency_contact_callsign && (
              <div className="mt-1 flex items-center text-xs font-mono text-slate-300 gap-1.5">
                <span className="text-slate-400">Designated Emergency Contact:</span>
                <span className="text-cyan-300 font-semibold">{alert.emergency_contact_name}</span>
                <span className="px-1.5 py-0.2 rounded bg-cyan-950 border border-cyan-800 text-[10px] text-cyan-400">
                  {alert.emergency_contact_callsign}
                </span>
                <span className="text-[11px] text-slate-400">({alert.emergency_contact_role})</span>
              </div>
            )}

            {/* Crew Action Directives */}
            {alert.suggested_crew_actions.length > 0 && (
              <div className="mt-2 text-xs font-mono text-red-200">
                <span className="font-semibold text-yellow-300">MANDATORY INTRA-CREW DIRECTIVES:</span>
                <ul className="list-disc list-inside mt-0.5 space-y-0.5 text-[11px] text-red-100">
                  {alert.suggested_crew_actions.map((act, i) => (
                    <li key={i}>{act}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>

        {/* Right Acknowledgment Controls */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 w-full lg:w-auto">
          {!isSwitchedToContact ? (
            /* Mode 1: Owner is still within countdown window */
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
              <input
                type="text"
                value={ownerNotes}
                onChange={(e) => setOwnerNotes(e.target.value)}
                placeholder="Astronaut check-in notes (optional)"
                className="px-3 py-2 text-xs font-mono bg-red-900/60 rounded-lg border border-red-600 text-white placeholder-red-300 focus:outline-none"
              />
              <button
                onClick={handleOwnerAnswer}
                disabled={isAcking}
                className="flex items-center justify-center space-x-1.5 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-mono font-bold uppercase tracking-wider transition-all shadow-lg hover:shadow-emerald-500/50"
              >
                <CheckCircle2 className="w-4 h-4" />
                <span>{isAcking ? "Responding..." : `I am OK / Answer (${countdown !== null ? `${countdown}s` : "Owner"})`}</span>
              </button>
            </div>
          ) : (
            /* Mode 2: Switched to Emergency Contact */
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
              <input
                type="text"
                value={callsign}
                onChange={(e) => setCallsign(e.target.value)}
                placeholder="Contact Responder Callsign"
                className="px-3 py-2 text-xs font-mono bg-amber-900/60 rounded-lg border border-amber-600 text-white placeholder-amber-300 focus:outline-none"
              />
              <button
                onClick={handleContactAck}
                disabled={isAcking}
                className="flex items-center justify-center space-x-1.5 px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-mono font-bold uppercase tracking-wider transition-all shadow-lg hover:shadow-amber-500/50"
              >
                <UserCheck className="w-4 h-4" />
                <span>{isAcking ? "Logging..." : `Acknowledge Rescue (${alert.emergency_contact_callsign || "Contact"})`}</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
