"use client";

/**
 * TourWelcome: the centred prompt shown on someone's first login, asking whether they want
 * the guided tour. "Start the tour" launches it; "Skip" (or Esc) dismisses it for good.
 */

import React, { useEffect, useRef } from "react";
import { Clock, Compass } from "lucide-react";
import { Button } from "@/components/bio";

interface TourWelcomeProps {
  open: boolean;
  onAccept: () => void;
  onSkip: () => void;
}

export function TourWelcome({ open, onAccept, onSkip }: TourWelcomeProps) {
  const dialogRef = useRef<HTMLDivElement>(null);

  // Focus the main action, close on Esc, keep Tab inside the dialog.
  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const t = window.setTimeout(
      () => dialogRef.current?.querySelector<HTMLElement>("[data-welcome-accept]")?.focus(),
      0
    );

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onSkip();
      } else if (e.key === "Tab" && dialogRef.current) {
        const buttons = dialogRef.current.querySelectorAll<HTMLElement>("button");
        const first = buttons[0];
        const last = buttons[buttons.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        } else if (!dialogRef.current.contains(document.activeElement)) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener("keydown", onKey);
      previouslyFocused?.focus?.();
    };
  }, [open, onSkip]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-[rgba(4,7,13,0.74)] p-bio-4 backdrop-blur-sm">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-welcome-title"
        aria-describedby="tour-welcome-desc"
        className="flex w-full max-w-[400px] flex-col items-center gap-bio-4 rounded-bio-lg border border-bio-border-strong bg-bio-surface-elevated p-bio-6 text-center text-bio-text shadow-2xl"
      >
        <span className="flex h-12 w-12 items-center justify-center rounded-full border border-bio-primary bg-bio-surface text-bio-primary">
          <Compass size={24} aria-hidden="true" />
        </span>

        <div className="flex flex-col gap-bio-2">
          <h2 id="tour-welcome-title" className="text-bio-lg font-semibold text-bio-text">
            Welcome aboard
          </h2>
          <p id="tour-welcome-desc" className="text-bio-sm text-bio-text-secondary">
            Would you like a quick guided tour of the platform? We&apos;ll show you where everything is, from the
            daily check-in to the AstroDoc assistant.
          </p>
        </div>

        <p className="flex items-center gap-bio-1 text-bio-xs text-bio-text-secondary">
          <Clock size={14} aria-hidden="true" />
          Takes about 30 seconds
        </p>

        <div className="flex w-full flex-col-reverse gap-bio-2 sm:flex-row">
          <Button variant="secondary" className="w-full sm:flex-1" onClick={onSkip}>
            Skip
          </Button>
          <Button data-welcome-accept variant="primary" className="w-full sm:flex-1" onClick={onAccept}>
            Start the tour
          </Button>
        </div>

        <p className="text-bio-xs text-bio-text-secondary">
          You can open the tour any time from the <span className="font-semibold text-bio-text">?</span> button at the
          top.
        </p>
      </div>
    </div>
  );
}
