"use client";

import React from "react";
import { ResponsiveContainer, LineChart, Line } from "recharts";
import { LucideIcon, ArrowUpRight, ArrowDownRight, Minus } from "lucide-react";

interface TelemetryCardProps {
  title: string;
  value: string | number;
  unit: string;
  icon: LucideIcon;
  status?: "nominal" | "warning" | "critical";
  sparklineData?: { val: number }[];
  trend?: "up" | "down" | "flat";
  trendValue?: string;
  subtitle?: string;
  hazardLabel?: string;
}

export const TelemetryCard: React.FC<TelemetryCardProps> = ({
  title,
  value,
  unit,
  icon: Icon,
  status = "nominal",
  sparklineData = [],
  trend = "flat",
  trendValue,
  subtitle,
  hazardLabel,
}) => {
  const statusStyles = {
    nominal: {
      border: "border-slate-800 hover:border-hud-cyan/50",
      accent: "text-hud-cyan",
      badge: "bg-cyan-950/40 text-cyan-400 border-cyan-800/50",
      sparkColor: "#00F0FF",
      glow: "hover:shadow-[0_0_15px_rgba(0,240,255,0.15)]",
    },
    warning: {
      border: "border-amber-900/60 hover:border-hud-amber",
      accent: "text-hud-amber",
      badge: "bg-amber-950/40 text-amber-400 border-amber-700/50",
      sparkColor: "#F59E0B",
      glow: "hover:shadow-[0_0_15px_rgba(245,158,11,0.2)]",
    },
    critical: {
      border: "border-red-900/80 hover:border-hud-red",
      accent: "text-hud-red",
      badge: "bg-red-950/50 text-red-400 border-red-700/60 animate-pulse",
      sparkColor: "#EF4444",
      glow: "hover:shadow-[0_0_20px_rgba(239,68,68,0.3)]",
    },
  }[status];

  return (
    <div
      className={`relative overflow-hidden rounded-xl bg-space-900/90 p-4 border backdrop-blur-md transition-all duration-300 ${statusStyles.border} ${statusStyles.glow}`}
    >
      {/* Top Bar with Hazard Label and Icon */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center space-x-2">
          <div className={`p-2 rounded-lg bg-space-850 border border-slate-700/60 ${statusStyles.accent}`}>
            <Icon className="w-5 h-5" />
          </div>
          <div>
            <h4 className="text-xs uppercase font-mono tracking-wider text-slate-400">{title}</h4>
            {hazardLabel && (
              <span className="text-[10px] font-mono text-slate-500 uppercase tracking-tight">
                {hazardLabel}
              </span>
            )}
          </div>
        </div>

        <span
          className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded border tracking-wider ${statusStyles.badge}`}
        >
          {status}
        </span>
      </div>

      {/* Numerical Value and Unit */}
      <div className="flex items-baseline justify-between mt-1">
        <div className="flex items-baseline space-x-1.5">
          <span className="text-2xl lg:text-3xl font-mono font-bold tracking-tight text-white">
            {value}
          </span>
          <span className="text-xs font-mono text-slate-400">{unit}</span>
        </div>

        {/* Trend Indicator */}
        {trendValue && (
          <div className="flex items-center space-x-0.5 text-xs font-mono">
            {trend === "up" && <ArrowUpRight className="w-3.5 h-3.5 text-hud-amber" />}
            {trend === "down" && <ArrowDownRight className="w-3.5 h-3.5 text-hud-cyan" />}
            {trend === "flat" && <Minus className="w-3.5 h-3.5 text-slate-400" />}
            <span
              className={
                trend === "up"
                  ? "text-hud-amber"
                  : trend === "down"
                  ? "text-hud-cyan"
                  : "text-slate-400"
              }
            >
              {trendValue}
            </span>
          </div>
        )}
      </div>

      {/* Sparkline & Subtitle */}
      <div className="mt-3 pt-2 border-t border-slate-800/80 flex items-center justify-between">
        <div className="text-[11px] text-slate-400 truncate max-w-[130px]">
          {subtitle || "Real-time telemetry stream"}
        </div>
        {sparklineData.length > 0 && (
          <div className="w-20 h-7">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sparklineData}>
                <Line
                  type="monotone"
                  dataKey="val"
                  stroke={statusStyles.sparkColor}
                  strokeWidth={1.8}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
};
