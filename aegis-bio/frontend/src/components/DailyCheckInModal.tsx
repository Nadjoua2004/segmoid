"use client";

import React, { useState } from "react";
import { X, Send, Heart, Moon, Smile, ShieldAlert, Activity, Thermometer } from "lucide-react";
import { HealthMetrics } from "@/lib/types";

interface DailyCheckInModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: HealthMetrics) => Promise<void>;
  currentMissionDay: number;
}

export const DailyCheckInModal: React.FC<DailyCheckInModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  currentMissionDay,
}) => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formData, setFormData] = useState<HealthMetrics>({
    astronaut_id: "ASTRO-7702-HELENA",
    mission_day: currentMissionDay + 1,
    heart_rate: 76,
    bp_sys: 122,
    bp_dia: 80,
    spo2: 98.0,
    sleep_hours: 6.5,
    radiation_msv: 1.2,
    blood_glucose: 94,
    mood_score: 4,
    core_temp_c: 36.8,
    hrv_rmssd: 44,
    subjective_notes: "",
  });

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await onSubmit(formData);
      onClose();
    } catch (err) {
      console.error("Submission failed:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
      <div className="relative w-full max-w-2xl rounded-2xl border border-cyan-800/60 bg-space-950 p-6 shadow-[0_0_50px_rgba(0,240,255,0.15)] text-slate-100">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-4 mb-5">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-cyan-950 border border-cyan-700/50 text-hud-cyan">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-mono font-bold tracking-wide uppercase text-white">
                Astronaut Daily Self-Check-in
              </h2>
              <p className="text-xs font-mono text-slate-400">
                Artemis III Crew Biometric Logging • Sol {formData.mission_day}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-space-850 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Heart Rate Slider */}
            <div className="p-3 rounded-xl bg-space-900 border border-slate-800">
              <div className="flex justify-between items-center text-xs font-mono mb-1.5">
                <span className="flex items-center space-x-1.5 text-slate-300">
                  <Heart className="w-3.5 h-3.5 text-hud-cyan" />
                  <span>Resting Heart Rate</span>
                </span>
                <span className="text-hud-cyan font-bold">{formData.heart_rate} BPM</span>
              </div>
              <input
                type="range"
                min="45"
                max="140"
                value={formData.heart_rate}
                onChange={(e) =>
                  setFormData({ ...formData, heart_rate: parseFloat(e.target.value) })
                }
                className="w-full accent-hud-cyan cursor-pointer"
              />
            </div>

            {/* SpO2 Slider */}
            <div className="p-3 rounded-xl bg-space-900 border border-slate-800">
              <div className="flex justify-between items-center text-xs font-mono mb-1.5">
                <span className="flex items-center space-x-1.5 text-slate-300">
                  <Activity className="w-3.5 h-3.5 text-hud-green" />
                  <span>Pulse Oximetry (SpO2)</span>
                </span>
                <span className="text-hud-green font-bold">{formData.spo2}%</span>
              </div>
              <input
                type="range"
                min="88"
                max="100"
                step="0.5"
                value={formData.spo2}
                onChange={(e) =>
                  setFormData({ ...formData, spo2: parseFloat(e.target.value) })
                }
                className="w-full accent-hud-green cursor-pointer"
              />
            </div>

            {/* Sleep Hours Slider */}
            <div className="p-3 rounded-xl bg-space-900 border border-slate-800">
              <div className="flex justify-between items-center text-xs font-mono mb-1.5">
                <span className="flex items-center space-x-1.5 text-slate-300">
                  <Moon className="w-3.5 h-3.5 text-hud-purple" />
                  <span>Sleep Duration</span>
                </span>
                <span className="text-hud-purple font-bold">{formData.sleep_hours} hrs</span>
              </div>
              <input
                type="range"
                min="2.0"
                max="10.0"
                step="0.5"
                value={formData.sleep_hours}
                onChange={(e) =>
                  setFormData({ ...formData, sleep_hours: parseFloat(e.target.value) })
                }
                className="w-full accent-hud-purple cursor-pointer"
              />
            </div>

            {/* Mood Score Slider */}
            <div className="p-3 rounded-xl bg-space-900 border border-slate-800">
              <div className="flex justify-between items-center text-xs font-mono mb-1.5">
                <span className="flex items-center space-x-1.5 text-slate-300">
                  <Smile className="w-3.5 h-3.5 text-hud-amber" />
                  <span>Subjective Mood / Morale</span>
                </span>
                <span className="text-hud-amber font-bold">
                  {formData.mood_score} / 5 (
                  {formData.mood_score <= 2
                    ? "Severe Fatigue"
                    : formData.mood_score === 3
                    ? "Moderate"
                    : "Optimal"}
                  )
                </span>
              </div>
              <input
                type="range"
                min="1"
                max="5"
                step="1"
                value={formData.mood_score}
                onChange={(e) =>
                  setFormData({ ...formData, mood_score: parseInt(e.target.value) })
                }
                className="w-full accent-hud-amber cursor-pointer"
              />
            </div>

            {/* Blood Pressure (Sys / Dia) */}
            <div className="p-3 rounded-xl bg-space-900 border border-slate-800">
              <div className="flex justify-between items-center text-xs font-mono mb-1.5">
                <span className="text-slate-300">Blood Pressure (Sys / Dia)</span>
                <span className="text-white font-bold">
                  {formData.bp_sys} / {formData.bp_dia} mmHg
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <input
                  type="number"
                  min="80"
                  max="200"
                  value={formData.bp_sys}
                  onChange={(e) =>
                    setFormData({ ...formData, bp_sys: parseFloat(e.target.value) })
                  }
                  className="px-2 py-1 text-xs font-mono bg-space-850 rounded border border-slate-700 text-white"
                  placeholder="Systolic"
                />
                <input
                  type="number"
                  min="50"
                  max="130"
                  value={formData.bp_dia}
                  onChange={(e) =>
                    setFormData({ ...formData, bp_dia: parseFloat(e.target.value) })
                  }
                  className="px-2 py-1 text-xs font-mono bg-space-850 rounded border border-slate-700 text-white"
                  placeholder="Diastolic"
                />
              </div>
            </div>

            {/* Radiation Dosimeter */}
            <div className="p-3 rounded-xl bg-space-900 border border-slate-800">
              <div className="flex justify-between items-center text-xs font-mono mb-1.5">
                <span className="flex items-center space-x-1.5 text-slate-300">
                  <ShieldAlert className="w-3.5 h-3.5 text-hud-red" />
                  <span>Dosimeter Reading</span>
                </span>
                <span className="text-hud-red font-bold">{formData.radiation_msv} mSv</span>
              </div>
              <input
                type="number"
                step="0.1"
                min="0.1"
                max="50.0"
                value={formData.radiation_msv}
                onChange={(e) =>
                  setFormData({ ...formData, radiation_msv: parseFloat(e.target.value) })
                }
                className="w-full px-2 py-1 text-xs font-mono bg-space-850 rounded border border-slate-700 text-white"
              />
            </div>
          </div>

          {/* Subjective Symptoms / Notes */}
          <div className="p-3 rounded-xl bg-space-900 border border-slate-800">
            <label className="block text-xs font-mono text-slate-300 mb-1.5">
              Subjective Clinical Notes / Space Adaptation Symptoms:
            </label>
            <textarea
              rows={2}
              value={formData.subjective_notes}
              onChange={(e) =>
                setFormData({ ...formData, subjective_notes: e.target.value })
              }
              placeholder="e.g. Mild headache following EVA, calf stiffness during cycle ergometer..."
              className="w-full px-3 py-2 text-xs font-mono bg-space-850 rounded-lg border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500"
            />
          </div>

          {/* Footer Submit Buttons */}
          <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-xs font-mono text-slate-400 hover:text-white hover:bg-space-850 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex items-center space-x-2 px-5 py-2 rounded-lg bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white text-xs font-mono font-bold uppercase tracking-wider transition-all shadow-[0_0_20px_rgba(0,240,255,0.3)] disabled:opacity-50"
            >
              <Send className="w-3.5 h-3.5" />
              <span>{isSubmitting ? "Ingesting..." : "Log Telemetry & Run Triage"}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
