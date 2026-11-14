"use client";

import React, { useState } from "react";
import { AlertOctagon, ShieldAlert, CheckCircle2, Siren, Radio } from "lucide-react";
import { EmergencyAlert } from "@/lib/types";

interface EmergencyBannerProps {
  alert: EmergencyAlert | null;
  onAcknowledge: (alertId: string, callsign: string) => Promise<void>;
  onTriggerDrill: () => Promise<void>;
}

export const EmergencyBanner: React.FC<EmergencyBannerProps> = ({
  alert,
  onAcknowledge,
  onTriggerDrill,
}) => {
  const [callsign, setCallsign] = useState("CMO-ASTRONAUT-1");
  const [isAcking, setIsAcking] = useState(false);

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

  const handleAck = async () => {
    setIsAcking(true);
    try {
      await onAcknowledge(alert.alert_id, callsign);
    } finally {
      setIsAcking(false);
    }
  };

  return (
    <div className="relative overflow-hidden rounded-xl border-2 border-red-600 bg-red-950/90 p-4 shadow-[0_0_40px_rgba(239,68,68,0.4)] text-white backdrop-blur-md animate-glow-red">
      {/* Background Strobe Line */}
      <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-red-600 via-yellow-400 to-red-600 animate-pulse"></div>

      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
        {/* Left Info Section */}
        <div className="flex items-start space-x-3.5">
          <div className="p-2.5 rounded-xl bg-red-900/80 border border-red-500 text-red-200 animate-bounce">
            <Siren className="w-6 h-6" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="px-2 py-0.5 rounded bg-red-600 text-white font-mono font-bold text-xs uppercase tracking-wider">
                {alert.severity}
              </span>
              <span className="text-xs font-mono text-red-300 font-bold">
                ALERT ID: {alert.alert_id}
              </span>
              <span className="flex items-center text-[10px] font-mono text-red-200 bg-red-900/60 px-2 py-0.5 rounded border border-red-700">
                <Radio className="w-3 h-3 mr-1" />
                24-MIN EARTH LATENCY: AUTONOMOUS ESCALATION ACTIVE
              </span>
            </div>

            <h3 className="text-base font-mono font-bold mt-1 text-white tracking-wide">
              {alert.hazard_origin}: {alert.message}
            </h3>

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
          <input
            type="text"
            value={callsign}
            onChange={(e) => setCallsign(e.target.value)}
            placeholder="Responder Callsign"
            className="px-3 py-2 text-xs font-mono bg-red-900/60 rounded-lg border border-red-600 text-white placeholder-red-300 focus:outline-none"
          />
          <button
            onClick={handleAck}
            disabled={isAcking}
            className="flex items-center justify-center space-x-1.5 px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white text-xs font-mono font-bold uppercase tracking-wider transition-all shadow-lg hover:shadow-red-500/50"
          >
            <CheckCircle2 className="w-4 h-4" />
            <span>{isAcking ? "Logging..." : "Acknowledge (CMO)"}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
