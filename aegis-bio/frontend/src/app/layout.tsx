import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Aegis-Bio — Autonomous Crew Health & Flight Surgeon",
  description:
    "Autonomous astronaut health monitoring and clinical decision-support system for deep-space missions.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
