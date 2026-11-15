"use client";

import React, { useState } from "react";
import { api, ApiError } from "@/lib/api";

interface StationLoginPageProps {
  onLoginSuccess: (token: string, profile: any) => void;
}

export function StationLoginPage({ onLoginSuccess }: StationLoginPageProps) {
  const [username, setUsername] = useState<string>("");
  const [key, setKey] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string>("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setErrorMsg("");

    try {
      const res = await api.loginWithKey(username.trim(), key.trim());
      const resolvedUser = res.user || (res.username ? res : null);
      if (res.access_token && resolvedUser) {
        onLoginSuccess(res.access_token, resolvedUser);
      } else {
        setErrorMsg("Authentication did not return a valid station token.");
      }
    } catch (err: any) {
      if (err instanceof ApiError) {
        setErrorMsg(typeof err.detail === "string" ? err.detail : "Invalid station username or access key.");
      } else {
        setErrorMsg(err.message || "Unable to reach station authentication server.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const ovalDotsOuter = Array.from({ length: 18 }, (_, i) => -68 + i * 7.5);
  const ovalDotsInner = Array.from({ length: 16 }, (_, i) => 108 + i * 7);

  return (
    <div
      style={{
        position: "relative",
        minHeight: "100vh",
        width: "100vw",
        overflow: "hidden",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "radial-gradient(circle at 50% 50%, #0D1B2A 0%, #070B12 52%, #04070B 100%)",
        color: "#F1F5F9",
        fontFamily: "Inter, 'SF Pro Text', system-ui, sans-serif",
        padding: "20px",
        boxSizing: "border-box",
      }}
    >
      {/* Animated Concentric Holographic HUD Rings Background */}
      <div
        aria-hidden="true"
        style={{
          position: "fixed",
          inset: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          pointerEvents: "none",
          zIndex: 0,
        }}
      >
        {/* Soft center atmospheric vignette */}
        <div
          style={{
            position: "absolute",
            width: "min(86vmin, 760px)",
            height: "min(86vmin, 760px)",
            borderRadius: "50%",
            background: "radial-gradient(circle, rgba(45, 212, 191, 0.1) 0%, rgba(14, 116, 144, 0.05) 45%, transparent 72%)",
          }}
        />

        {/* Ring Layer 1: Outer segmented HUD arc (clockwise) */}
        <svg
          viewBox="0 0 600 600"
          style={{
            position: "absolute",
            width: "min(94vmin, 820px)",
            height: "min(94vmin, 820px)",
            animation: "astroSpinCW 42s linear infinite",
            opacity: 0.72,
          }}
        >
          <circle cx="300" cy="300" r="286" fill="none" stroke="rgba(45, 212, 191, 0.14)" strokeWidth="1.5" />
          <circle
            cx="300"
            cy="300"
            r="286"
            fill="none"
            stroke="#2DD4BF"
            strokeWidth="5"
            strokeDasharray="125 180 48 210 85 160"
            strokeLinecap="round"
          />
          <circle
            cx="300"
            cy="300"
            r="268"
            fill="none"
            stroke="rgba(94, 234, 212, 0.3)"
            strokeWidth="2"
            strokeDasharray="3 11"
          />
        </svg>

        {/* Ring Layer 2: Precision tick & arc assembly (counter-clockwise) */}
        <svg
          viewBox="0 0 600 600"
          style={{
            position: "absolute",
            width: "min(82vmin, 700px)",
            height: "min(82vmin, 700px)",
            animation: "astroSpinCCW 28s linear infinite",
            opacity: 0.78,
          }}
        >
          <circle cx="300" cy="300" r="244" fill="none" stroke="rgba(45, 212, 191, 0.18)" strokeWidth="1" />
          <circle
            cx="300"
            cy="300"
            r="234"
            fill="none"
            stroke="rgba(94, 234, 212, 0.45)"
            strokeWidth="8"
            strokeDasharray="4 9"
          />
          <circle
            cx="300"
            cy="300"
            r="214"
            fill="none"
            stroke="#2DD4BF"
            strokeWidth="2.5"
            strokeDasharray="160 110 65 140"
            strokeLinecap="round"
          />
          {/* Segmented block gauge on left/right */}
          <circle
            cx="300"
            cy="300"
            r="224"
            fill="none"
            stroke="rgba(45, 212, 191, 0.6)"
            strokeWidth="10"
            strokeDasharray="6 6"
            strokeDashoffset="30"
            style={{ opacity: 0.45 }}
          />
        </svg>

        {/* Ring Layer 3: Telemetry bead arcs & inner core dial (clockwise pulse) */}
        <svg
          viewBox="0 0 600 600"
          style={{
            position: "absolute",
            width: "min(68vmin, 580px)",
            height: "min(68vmin, 580px)",
            animation: "astroSpinCW 19s linear infinite, astroPulseGlow 4s ease-in-out infinite",
            opacity: 0.8,
          }}
        >
          <circle
            cx="300"
            cy="300"
            r="192"
            fill="none"
            stroke="rgba(94, 234, 212, 0.35)"
            strokeWidth="1.5"
            strokeDasharray="12 18"
          />
          <circle
            cx="300"
            cy="300"
            r="170"
            fill="none"
            stroke="#5EEAD4"
            strokeWidth="4"
            strokeDasharray="195 75 95 65"
            strokeLinecap="round"
          />
          {ovalDotsOuter.map((deg, idx) => (
            <rect
              key={`o-${idx}`}
              x="296"
              y="98"
              width="7"
              height="13"
              rx="3.5"
              fill="none"
              stroke="rgba(94, 234, 212, 0.55)"
              strokeWidth="1.4"
              transform={`rotate(${deg} 300 300)`}
            />
          ))}
          {ovalDotsInner.map((deg, idx) => (
            <circle
              key={`i-${idx}`}
              cx="300"
              cy="118"
              r="3.2"
              fill="none"
              stroke="rgba(45, 212, 191, 0.5)"
              strokeWidth="1.3"
              transform={`rotate(${deg} 300 300)`}
            />
          ))}
        </svg>
      </div>

      {/* Login Card */}
      <div
        style={{
          position: "relative",
          zIndex: 1,
          width: "100%",
          maxWidth: "440px",
          background: "rgba(19, 23, 32, 0.84)",
          backdropFilter: "blur(14px)",
          border: "1px solid #232B3B",
          borderRadius: "16px",
          padding: "34px 30px",
          boxShadow: "0 20px 50px rgba(0, 0, 0, 0.65)",
          display: "flex",
          flexDirection: "column",
          gap: "22px",
        }}
      >
        {/* Brand Header */}
        <div style={{ textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: "8px" }}>
          <div
            style={{
              width: "54px",
              height: "54px",
              borderRadius: "14px",
              background: "rgba(45, 212, 191, 0.1)",
              border: "1px solid rgba(45, 212, 191, 0.28)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#5EEAD4",
            }}
          >
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M12 2 L21 7 V17 L12 22 L3 17 V7 Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
              <path d="M7 12.5 H9.5 L11 9 L13 16 L14.5 12.5 H17" stroke="#2DD4BF" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <h1 style={{ margin: "6px 0 0", fontSize: "21px", fontWeight: 700, letterSpacing: "-0.02em", color: "#F1F5F9" }}>
            Aegis-Bio Station Portal
          </h1>
          <p style={{ margin: 0, fontSize: "12.5px", color: "#94A3B8" }}>
            Deep-Space Offline-First Station Access
          </p>
        </div>

        {errorMsg && (
          <div
            style={{
              padding: "10px 14px",
              borderRadius: "8px",
              background: "#3B2323",
              border: "1px solid #EF4444",
              color: "#FCA5A5",
              fontSize: "13px",
            }}
          >
            {errorMsg}
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleSubmit} autoComplete="off" style={{ display: "flex", flexDirection: "column", gap: "15px" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <span style={{ fontSize: "12px", fontWeight: 500, color: "#94A3B8" }}>
              Station Astronaut Username
            </span>
            <input
              type="text"
              required
              autoFocus
              autoComplete="off"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. lead"
              style={{
                height: "42px",
                padding: "0 14px",
                borderRadius: "10px",
                border: "1px solid #232B3B",
                background: "#0C0E12",
                color: "#F1F5F9",
                fontSize: "14px",
                outline: "none",
              }}
            />
          </label>

          <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <span style={{ fontSize: "12px", fontWeight: 500, color: "#94A3B8" }}>
              Station Access Key
            </span>
            <input
              type="password"
              required
              autoComplete="new-password"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="••••••••••••"
              style={{
                height: "42px",
                padding: "0 14px",
                borderRadius: "10px",
                border: "1px solid #232B3B",
                background: "#0C0E12",
                color: "#F1F5F9",
                fontSize: "14px",
                outline: "none",
              }}
            />
          </label>

          <button
            type="submit"
            disabled={isLoading}
            style={{
              marginTop: "6px",
              height: "44px",
              borderRadius: "10px",
              border: "1px solid rgba(45, 212, 191, 0.35)",
              background: isLoading ? "#334155" : "#2DD4BF",
              color: isLoading ? "#CBD5E1" : "#061312",
              fontSize: "14px",
              fontWeight: 700,
              cursor: isLoading ? "not-allowed" : "pointer",
              transition: "background 0.2s ease",
            }}
          >
            {isLoading ? "Authenticating with Station Core..." : "Sign In & Access Telemetry"}
          </button>
        </form>

        <div style={{ textAlign: "center", fontSize: "11px", color: "#64748B" }}>
          NASA Deep-Space Habitation Infrastructure · Encrypted Station Local Node
        </div>
      </div>
    </div>
  );
}
