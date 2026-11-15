"use client";

import React, { useState } from "react";
import { api, ApiError } from "@/lib/api";

interface StationLoginPageProps {
  onLoginSuccess: (token: string, profile: any) => void;
}

export function StationLoginPage({ onLoginSuccess }: StationLoginPageProps) {
  const [username, setUsername] = useState<string>("lead");
  const [key, setKey] = useState<string>("Key1234!");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string>("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setErrorMsg("");

    try {
      const res = await api.loginWithKey(username.trim(), key.trim());
      if (res.access_token && res.user) {
        onLoginSuccess(res.access_token, res.user);
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

  return (
    <div
      style={{
        minHeight: "100vh",
        width: "100vw",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "radial-gradient(ellipse at top, #1a2233 0%, #0d0f14 100%)",
        color: "#FFFFFF",
        fontFamily: "Inter, 'SF Pro Text', system-ui, sans-serif",
        padding: "20px",
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "460px",
          background: "#1C1C1C",
          border: "1px solid #333333",
          borderRadius: "20px",
          padding: "36px 32px",
          boxShadow: "0 24px 60px rgba(0, 0, 0, 0.6), 0 0 40px rgba(125, 211, 252, 0.08)",
          display: "flex",
          flexDirection: "column",
          gap: "24px",
        }}
      >
        {/* Brand Header */}
        <div style={{ textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: "8px" }}>
          <div
            style={{
              width: "56px",
              height: "56px",
              borderRadius: "14px",
              background: "rgba(125, 211, 252, 0.12)",
              border: "1px solid rgba(125, 211, 252, 0.3)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#7DD3FC",
            }}
          >
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M12 2 L21 7 V17 L12 22 L3 17 V7 Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
              <path d="M7 12.5 H9.5 L11 9 L13 16 L14.5 12.5 H17" stroke="#7DD3FC" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <h1 style={{ margin: "6px 0 0", fontSize: "22px", fontWeight: 700, letterSpacing: "-0.02em" }}>
            Aegis-Bio Station Portal
          </h1>
          <p style={{ margin: 0, fontSize: "13px", color: "#A3A3A3" }}>
            Artemis Base Alpha · Offline-First Station Access
          </p>
        </div>

        {/* Credentials Notice Box */}
        <div
          style={{
            padding: "12px 14px",
            borderRadius: "10px",
            background: "rgba(125, 211, 252, 0.06)",
            border: "1px solid rgba(125, 211, 252, 0.2)",
            fontSize: "12px",
            lineHeight: "18px",
            color: "#E2E8F0",
          }}
        >
          <div style={{ fontWeight: 600, color: "#7DD3FC", marginBottom: "4px" }}>
            🧑‍🚀 Crew Lead Station Credentials:
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              Username: <strong style={{ color: "#FFFFFF" }}>lead</strong> &nbsp;|&nbsp; Key: <strong style={{ color: "#FFFFFF" }}>Key1234!</strong>
            </div>
            <button
              type="button"
              onClick={() => {
                setUsername("lead");
                setKey("Key1234!");
              }}
              style={{
                fontSize: "11px",
                padding: "3px 8px",
                borderRadius: "4px",
                background: "#7DD3FC",
                color: "#0F172A",
                border: "none",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Autofill
            </button>
          </div>
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
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <span style={{ fontSize: "12px", fontWeight: 500, color: "#A3A3A3" }}>
              Station Astronaut Username
            </span>
            <input
              type="text"
              required
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. lead"
              style={{
                height: "42px",
                padding: "0 14px",
                borderRadius: "10px",
                border: "1px solid #333333",
                background: "#121212",
                color: "#FFFFFF",
                fontSize: "14px",
                outline: "none",
              }}
            />
          </label>

          <label style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <span style={{ fontSize: "12px", fontWeight: 500, color: "#A3A3A3" }}>
              Station Access Key
            </span>
            <input
              type="password"
              required
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="••••••••••••"
              style={{
                height: "42px",
                padding: "0 14px",
                borderRadius: "10px",
                border: "1px solid #333333",
                background: "#121212",
                color: "#FFFFFF",
                fontSize: "14px",
                outline: "none",
              }}
            />
          </label>

          <button
            type="submit"
            disabled={isLoading}
            style={{
              marginTop: "8px",
              height: "44px",
              borderRadius: "10px",
              border: "none",
              background: isLoading ? "#475569" : "#7DD3FC",
              color: "#0F172A",
              fontSize: "14px",
              fontWeight: 700,
              cursor: isLoading ? "not-allowed" : "pointer",
              transition: "background 0.2s ease",
            }}
          >
            {isLoading ? "Authenticating with Station Core..." : "Sign In & Access Telemetry"}
          </button>
        </form>

        <div style={{ textAlign: "center", fontSize: "11px", color: "#666666" }}>
          NASA Deep-Space Habitation Infrastructure · Encrypted Station Local Node
        </div>
      </div>
    </div>
  );
}
