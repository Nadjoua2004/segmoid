import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Aegis-Bio | Autonomous Clinical Flight Surgeon System",
  description:
    "Autonomous onboard clinical decision-support and telemetry forecasting for deep-space missions. Team Sigmoid - NASA Space Apps Challenge.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-space-950 text-slate-100 aerospace-grid antialiased">
        {children}
      </body>
    </html>
  );
}
