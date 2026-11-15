"use client";

/**
 * GuidedTour: a step-by-step walkthrough that dims the page, highlights one element at a
 * time, and shows a small popover with a title, a description, and Back / Next buttons.
 *
 * Steps point at elements with a CSS selector (usually `[data-tour="..."]`), so the tour
 * stays decoupled from the components it describes. A step can run `before()` first (e.g.
 * switch screen or open a panel); the tour waits briefly for the target to render and
 * skips the step if it never appears.
 *
 * Keyboard: ← / → move between steps, Esc closes, Tab stays inside the popover.
 */

import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/bio";

export type TourPlacement = "top" | "bottom" | "left" | "right" | "auto";

export interface TourStep {
  /** CSS selector of the element to highlight. */
  target: string;
  title: string;
  description: string;
  /** Preferred side for the popover; falls back to whichever side has room. */
  placement?: TourPlacement;
  /** Runs before the step is shown, e.g. to navigate to the screen that holds the target. */
  before?: () => void;
}

interface GuidedTourProps {
  steps: TourStep[];
  open: boolean;
  /** `completed` is true when the user reached the end, false when they closed early. */
  onClose: (completed: boolean) => void;
}

interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

const HIGHLIGHT_PADDING = 6;
const POPOVER_GAP = 14;
const VIEWPORT_MARGIN = 12;
/** How long to wait for a target that renders after `before()` (≈ 1 s at 60 fps). */
const MAX_WAIT_FRAMES = 60;

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Highlight box around the target, clamped to the viewport so huge elements stay visible. */
function highlightBox(rect: DOMRect): Box {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const top = Math.max(rect.top - HIGHLIGHT_PADDING, 4);
  const left = Math.max(rect.left - HIGHLIGHT_PADDING, 4);
  const bottom = Math.min(rect.bottom + HIGHLIGHT_PADDING, vh - 4);
  const right = Math.min(rect.right + HIGHLIGHT_PADDING, vw - 4);
  return { top, left, width: Math.max(right - left, 0), height: Math.max(bottom - top, 0) };
}

/** Put the popover on the preferred side if it fits, otherwise on the roomiest side. */
function popoverPosition(target: Box, pw: number, ph: number, preferred: TourPlacement) {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const space = {
    top: target.top,
    bottom: vh - (target.top + target.height),
    left: target.left,
    right: vw - (target.left + target.width),
  };
  const fits = {
    top: space.top >= ph + POPOVER_GAP + VIEWPORT_MARGIN,
    bottom: space.bottom >= ph + POPOVER_GAP + VIEWPORT_MARGIN,
    left: space.left >= pw + POPOVER_GAP + VIEWPORT_MARGIN,
    right: space.right >= pw + POPOVER_GAP + VIEWPORT_MARGIN,
  };
  const sides = (["bottom", "top", "right", "left"] as const).slice().sort((a, b) => space[b] - space[a]);
  const order = preferred !== "auto" ? [preferred, ...sides.filter((s) => s !== preferred)] : sides;
  const side = order.find((s) => fits[s]);

  const cx = target.left + target.width / 2 - pw / 2;
  const cy = target.top + target.height / 2 - ph / 2;
  let top: number;
  let left: number;
  switch (side) {
    case "top":
      top = target.top - ph - POPOVER_GAP;
      left = cx;
      break;
    case "bottom":
      top = target.top + target.height + POPOVER_GAP;
      left = cx;
      break;
    case "left":
      top = cy;
      left = target.left - pw - POPOVER_GAP;
      break;
    case "right":
      top = cy;
      left = target.left + target.width + POPOVER_GAP;
      break;
    default:
      // Target fills the screen: float the popover over its lower part.
      top = vh - ph - VIEWPORT_MARGIN * 2;
      left = vw / 2 - pw / 2;
  }
  return {
    top: Math.min(Math.max(top, VIEWPORT_MARGIN), vh - ph - VIEWPORT_MARGIN),
    left: Math.min(Math.max(left, VIEWPORT_MARGIN), vw - pw - VIEWPORT_MARGIN),
  };
}

export function GuidedTour({ steps, open, onClose }: GuidedTourProps) {
  const [index, setIndex] = useState(0);
  const [target, setTarget] = useState<Element | null>(null);
  const [box, setBox] = useState<Box | null>(null);
  const [popover, setPopover] = useState<{ top: number; left: number } | null>(null);

  const direction = useRef<1 | -1>(1);
  const popoverRef = useRef<HTMLDivElement>(null);
  const restoreFocus = useRef<HTMLElement | null>(null);

  const step = steps[index];
  const isFirst = index === 0;
  const isLast = index === steps.length - 1;

  // Reset on open; give focus back to whatever had it on close.
  useEffect(() => {
    if (open) {
      restoreFocus.current = document.activeElement as HTMLElement | null;
      direction.current = 1;
      setIndex(0);
    } else {
      setIndex(0); // so a reopened tour starts at step 1 without re-running the old step
      setTarget(null);
      setBox(null);
      setPopover(null);
      restoreFocus.current?.focus?.();
    }
  }, [open]);

  const finish = useCallback((completed: boolean) => onClose(completed), [onClose]);

  const go = useCallback(
    (delta: 1 | -1) => {
      direction.current = delta;
      const next = index + delta;
      if (next >= steps.length) finish(true);
      else if (next >= 0) setIndex(next);
    },
    [index, steps.length, finish]
  );

  // Resolve the current step's target (after `before()`), skipping steps whose target never renders.
  useEffect(() => {
    if (!open || !step) return;
    setTarget(null);
    setPopover(null);
    step.before?.();

    let frame = 0;
    let raf = 0;
    const find = () => {
      const el = document.querySelector(step.target);
      if (el) {
        const r = el.getBoundingClientRect();
        const offscreen = r.top < 0 || r.bottom > window.innerHeight || r.left < 0 || r.right > window.innerWidth;
        if (offscreen && getComputedStyle(el).position !== "fixed") {
          el.scrollIntoView({
            block: r.height > window.innerHeight * 0.8 ? "start" : "center",
            inline: "nearest",
            behavior: prefersReducedMotion() ? "auto" : "smooth",
          });
        }
        setTarget(el);
        return;
      }
      if (++frame < MAX_WAIT_FRAMES) {
        raf = requestAnimationFrame(find);
        return;
      }
      // Target missing (e.g. hidden for this user): skip in the direction of travel.
      const next = index + direction.current;
      if (next >= steps.length) finish(true);
      else if (next < 0) {
        direction.current = 1;
        setIndex(index + 1);
      } else setIndex(next);
    };
    raf = requestAnimationFrame(find);
    return () => cancelAnimationFrame(raf);
    // `step` is derived from `index`; re-running on every `steps` identity change would restart the step.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, index]);

  // Keep the highlight glued to the target while the page scrolls, resizes or re-lays out.
  useLayoutEffect(() => {
    if (!target) return;
    let raf = 0;
    const measure = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => setBox(highlightBox(target.getBoundingClientRect())));
    };
    setBox(highlightBox(target.getBoundingClientRect()));
    window.addEventListener("scroll", measure, true);
    window.addEventListener("resize", measure);
    const ro = new ResizeObserver(measure);
    ro.observe(target);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", measure, true);
      window.removeEventListener("resize", measure);
      ro.disconnect();
    };
  }, [target]);

  // Position the popover once its size is known.
  useLayoutEffect(() => {
    const el = popoverRef.current;
    if (!box || !el || !step) return;
    setPopover(popoverPosition(box, el.offsetWidth, el.offsetHeight, step.placement ?? "auto"));
  }, [box, step]);

  // Move focus into the popover on each step so keyboard and screen-reader users follow along.
  // The popover itself is focused (not Next) so Next doesn't show a focus ring on every step;
  // Enter still advances (see the key handler). Deferred, because a dialog opened by `before()`
  // (e.g. the check-in form) focuses its own first input right after it mounts.
  useEffect(() => {
    if (!popover) return;
    const t = window.setTimeout(() => popoverRef.current?.focus({ preventScroll: true }), 60);
    return () => window.clearTimeout(t);
  }, [popover !== null, index]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keyboard: arrows navigate, Esc closes, Tab is trapped in the popover.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        finish(false);
      } else if (e.key === "Enter" && document.activeElement === popoverRef.current) {
        e.preventDefault();
        go(1);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        go(1);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        if (!isFirst) go(-1);
      } else if (e.key === "Tab" && popoverRef.current) {
        const focusable = popoverRef.current.querySelectorAll<HTMLElement>("button:not([disabled])");
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        } else if (!popoverRef.current.contains(document.activeElement)) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, go, finish, isFirst]);

  if (!open || !step) return null;

  const animate = !prefersReducedMotion();
  const titleId = "guided-tour-title";
  const descId = "guided-tour-desc";

  return (
    <div className="fixed inset-0 z-[1000]">
      {/* Click shield: the page is inert while the tour runs (use Back / Next / Esc). */}
      <div className="absolute inset-0" onMouseDown={(e) => e.preventDefault()} />

      {/* Spotlight: the huge shadow dims everything except the highlighted box. */}
      {box && (
        <div
          aria-hidden="true"
          className="pointer-events-none fixed rounded-bio-lg"
          style={{
            top: box.top,
            left: box.left,
            width: box.width,
            height: box.height,
            boxShadow: "0 0 0 2px var(--bio-primary), 0 0 18px 2px rgba(45,212,191,0.35), 0 0 0 9999px rgba(4,7,13,0.74)",
            transition: animate ? "top 220ms ease, left 220ms ease, width 220ms ease, height 220ms ease" : undefined,
          }}
        />
      )}

      <div
        ref={popoverRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className="fixed flex w-[min(340px,calc(100vw-24px))] flex-col outline-none gap-bio-3 rounded-bio-lg border border-bio-border-strong bg-bio-surface-elevated p-bio-4 text-bio-text shadow-2xl"
        style={{
          top: popover?.top ?? 0,
          left: popover?.left ?? 0,
          // Rendered invisibly first so its size can be measured before it is placed.
          visibility: popover ? "visible" : "hidden",
          transition: animate && popover ? "top 220ms ease, left 220ms ease" : undefined,
        }}
      >
        <div className="flex items-start justify-between gap-bio-3">
          <div className="flex flex-col gap-bio-1">
            <span className="text-bio-xs font-medium uppercase tracking-wide text-bio-primary">
              Step {index + 1} of {steps.length}
            </span>
            <h2 id={titleId} className="text-bio-base font-semibold text-bio-text">
              {step.title}
            </h2>
          </div>
          <button
            type="button"
            onClick={() => finish(false)}
            aria-label="Close tour"
            title="Close tour (Esc)"
            className="bio-focus -mr-bio-1 -mt-bio-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-bio-md text-bio-text-secondary hover:bg-bio-surface-hover hover:text-bio-text"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        <p id={descId} className="text-bio-sm text-bio-text-secondary">
          {step.description}
        </p>

        {/* Progress dots: on their own row (wrapping if needed) so they never push the buttons out. */}
        <div className="flex flex-wrap items-center gap-[5px]" aria-hidden="true">
          {steps.map((_, i) => (
            <span
              key={i}
              className={`h-1.5 rounded-full transition-all motion-reduce:transition-none ${
                i === index ? "w-4 bg-bio-primary" : i < index ? "w-1.5 bg-bio-primary opacity-50" : "w-1.5 bg-bio-border-strong"
              }`}
            />
          ))}
        </div>

        <div className="flex items-center justify-end gap-bio-2">
          <Button variant="secondary" className="shrink-0" onClick={() => go(-1)} disabled={isFirst}>
            Back
          </Button>
          <Button data-tour-next variant="primary" className="shrink-0" onClick={() => go(1)}>
            {isLast ? "Finish" : "Next"}
          </Button>
        </div>
      </div>
    </div>
  );
}
