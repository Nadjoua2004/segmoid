"use client";

import React, { useState } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  Area,
} from "recharts";
import { Activity, ShieldAlert, Moon, Heart } from "lucide-react";
import { HealthMetricsResponse, TrajectoryPoint } from "@/lib/types";

interface VitalsChartProps {
  history: HealthMetricsResponse[];
  trajectory: TrajectoryPoint[];
}

type MetricKey = "heart_rate" | "spo2" | "sleep_hours" | "radiation_msv";

export const VitalsChart: React.FC<VitalsChartProps> = ({ history, trajectory }) => {
  const [selectedMetric, setSelectedMetric] = useState<MetricKey>("heart_rate");

  const metricConfig = {
    heart_rate: {
      name: "Heart Rate",
      unit: "BPM",
      historyKey: "heart_rate",
      forecastKey: "heart_rate_predicted",
      color: "#00F0FF",
      forecastColor: "#38BDF8",
      threshold: 115,
      thresholdLabel: "Microgravity Tachycardia Threshold (115 BPM)",
      icon: Heart,
    },
    spo2: {
      name: "SpO2 (Pulse Oximetry)",
      unit: "%",
      historyKey: "spo2",
      forecastKey: "spo2_predicted",
      color: "#10B981",
      forecastColor: "#34D399",
      threshold: 94,
      thresholdLabel: "Hypoxemia Alert (<94%)",
      icon: Activity,
    },
    sleep_hours: {
      name: "Sleep Duration",
      unit: "Hours",
      historyKey: "sleep_hours",
      forecastKey: "sleep_predicted",
      color: "#A855F7",
      forecastColor: "#C084FC",
      threshold: 4.5,
      thresholdLabel: "Circadian Deprivation Floor (<4.5 hrs)",
      icon: Moon,
    },
    radiation_msv: {
      name: "Daily Radiation Exposure",
      unit: "mSv/day",
      historyKey: "radiation_msv",
      forecastKey: "radiation_cumulative_predicted",
      color: "#F59E0B",
      forecastColor: "#EF4444",
      threshold: 20.0,
      thresholdLabel: "SPE Critical Alarm (20 mSv/day)",
      icon: ShieldAlert,
    },
  }[selectedMetric];

  // Merge history (1-30) with forecast trajectory (31-37)
  const combinedData = [
    ...history.map((h) => ({
      day: `Sol ${h.mission_day}`,
      dayNum: h.mission_day,
      observed: h[metricConfig.historyKey as keyof HealthMetricsResponse] as number,
      predicted: null as number | null,
    })),
    // Link bridge point from last historical point
    ...(history.length > 0 && trajectory.length > 0
      ? [
          {
            day: `Sol ${history[history.length - 1].mission_day}`,
            dayNum: history[history.length - 1].mission_day,
            observed: history[history.length - 1][
              metricConfig.historyKey as keyof HealthMetricsResponse
            ] as number,
            predicted: history[history.length - 1][
              metricConfig.historyKey as keyof HealthMetricsResponse
            ] as number,
          },
        ]
      : []),
    ...trajectory.map((t) => ({
      day: `Sol ${t.day} (F)`,
      dayNum: t.day,
      observed: null as number | null,
      predicted: t[metricConfig.forecastKey as keyof TrajectoryPoint] as number,
    })),
  ];

  return (
    <div className="rounded-xl border border-slate-800 bg-space-900/90 p-5 backdrop-blur-md">
      {/* Header & Controls */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div>
          <div className="flex items-center space-x-2">
            <span className="inline-block w-2 h-2 rounded-full bg-hud-cyan animate-pulse"></span>
            <h3 className="text-base font-mono font-semibold text-white tracking-wide uppercase">
              Physiological Trajectory & 7-Day AI Forecast
            </h3>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Artemis Sol 1-30 baseline telemetry with machine learning polynomial regression
          </p>
        </div>

        {/* Metric Selector Buttons */}
        <div className="flex flex-wrap items-center gap-1.5 p-1 rounded-lg bg-space-850 border border-slate-700/60">
          {(
            [
              { key: "heart_rate", label: "Heart Rate", icon: Heart },
              { key: "spo2", label: "SpO2", icon: Activity },
              { key: "sleep_hours", label: "Sleep", icon: Moon },
              { key: "radiation_msv", label: "Radiation", icon: ShieldAlert },
            ] as const
          ).map((m) => {
            const Icon = m.icon;
            const active = selectedMetric === m.key;
            return (
              <button
                key={m.key}
                onClick={() => setSelectedMetric(m.key)}
                className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-xs font-mono transition-all ${
                  active
                    ? "bg-slate-700 text-white shadow-sm font-semibold border border-slate-600"
                    : "text-slate-400 hover:text-slate-200 hover:bg-space-800"
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{m.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Chart Canvas */}
      <div className="h-[320px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={combinedData}
            margin={{ top: 10, right: 20, left: -10, bottom: 0 }}
          >
            <defs>
              <linearGradient id="observedGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={metricConfig.color} stopOpacity={0.25} />
                <stop offset="95%" stopColor={metricConfig.color} stopOpacity={0.0} />
              </linearGradient>
              <linearGradient id="forecastGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={metricConfig.forecastColor} stopOpacity={0.3} />
                <stop offset="95%" stopColor={metricConfig.forecastColor} stopOpacity={0.0} />
              </linearGradient>
            </defs>

            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
            <XAxis
              dataKey="day"
              stroke="#64748b"
              fontSize={11}
              fontFamily="monospace"
              tickLine={false}
              interval={4}
            />
            <YAxis
              stroke="#64748b"
              fontSize={11}
              fontFamily="monospace"
              tickLine={false}
              domain={["auto", "auto"]}
            />

            <Tooltip
              content={({ active, payload, label }) => {
                if (active && payload && payload.length) {
                  return (
                    <div className="rounded-lg bg-space-950/95 border border-slate-700 p-3 shadow-xl backdrop-blur-md font-mono text-xs">
                      <p className="text-slate-400 mb-1 border-b border-slate-800 pb-1 font-semibold">
                        {label}
                      </p>
                      {payload.map((entry, index) => {
                        if (entry.value === null || entry.value === undefined) return null;
                        return (
                          <div key={index} className="flex items-center justify-between gap-4 py-0.5">
                            <span className="text-slate-300">
                              {entry.dataKey === "observed"
                                ? "Historical Telemetry"
                                : "AI Forecast Projection"}
                              :
                            </span>
                            <span
                              className="font-bold"
                              style={{ color: entry.stroke || entry.color }}
                            >
                              {entry.value} {metricConfig.unit}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  );
                }
                return null;
              }}
            />

            <Legend
              wrapperStyle={{ paddingTop: 15, fontFamily: "monospace", fontSize: 11 }}
            />

            {/* Threshold line */}
            <ReferenceLine
              y={metricConfig.threshold}
              stroke="#EF4444"
              strokeDasharray="4 4"
              strokeWidth={1.5}
              label={{
                value: metricConfig.thresholdLabel,
                fill: "#EF4444",
                fontSize: 10,
                position: "insideTopRight",
              }}
            />

            {/* Historical Telemetry Area & Line */}
            <Area
              type="monotone"
              dataKey="observed"
              name="Historical Telemetry"
              stroke={metricConfig.color}
              strokeWidth={2.2}
              fill="url(#observedGradient)"
              isAnimationActive={false}
            />

            {/* Projected Forecast Line */}
            <Line
              type="monotone"
              dataKey="predicted"
              name="7-Day AI Trajectory"
              stroke={metricConfig.forecastColor}
              strokeWidth={2.5}
              strokeDasharray="5 5"
              dot={{ r: 3, fill: metricConfig.forecastColor }}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
