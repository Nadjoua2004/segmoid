"use client";

/**
 * Biomedical Precision UI primitives.
 *
 * Rules these components enforce so pages don't have to:
 *  - Colour is never the only carrier of status: every status has an icon shape AND a word.
 *  - Every interactive element gets the shared `.bio-focus` ring, a hover state, and a disabled state.
 *  - Only design tokens (tailwind.config.js -> globals.css) are used. No hex, no ad-hoc px.
 */
import React from "react";

/* ------------------------------------------------------------------ status */

/** Severity vocabulary used by the backend metric classifier. */
export type Severity = "NORMAL" | "MEDIUM" | "CRITICAL";
export type StatusKey = Severity | "UNCLASSIFIED" | "NODATA";

/** Normalise whatever the API sends into a StatusKey. Unknown values are surfaced, not hidden. */
export function toStatus(raw: string | null | undefined): StatusKey {
  switch ((raw || "").toUpperCase()) {
    case "NORMAL":
    case "NOMINAL":
      return "NORMAL";
    case "MEDIUM":
    case "ELEVATED":
    case "HIGH":
    case "WARNING":
      return "MEDIUM";
    case "CRITICAL":
      return "CRITICAL";
    default:
      return "UNCLASSIFIED";
  }
}

const STATUS_STYLE: Record<StatusKey, { label: string; tone: string; card: string }> = {
  NORMAL: {
    label: "Normal",
    tone: "text-bio-nominal bg-bio-nominal-bg border-bio-nominal-border",
    card: "border-bio-border",
  },
  MEDIUM: {
    label: "Caution",
    tone: "text-bio-warning bg-bio-warning-bg border-bio-warning-border",
    card: "border-bio-warning-border",
  },
  CRITICAL: {
    label: "Critical",
    tone: "text-bio-critical bg-bio-critical-bg border-bio-critical-border",
    card: "border-bio-critical-border shadow-bio-glow-red",
  },
  UNCLASSIFIED: {
    label: "Unclassified",
    tone: "text-bio-text-secondary bg-bio-surface border-bio-border-control",
    card: "border-bio-border",
  },
  NODATA: {
    label: "No data",
    tone: "text-bio-text-secondary bg-bio-surface border-bio-border-control",
    card: "border-bio-border",
  },
};

/** Distinct silhouettes so status survives colour-blindness: circle / triangle / diamond / dash. */
function StatusGlyph({ status }: { status: StatusKey }) {
  const common = { width: 12, height: 12, viewBox: "0 0 12 12", "aria-hidden": true, fill: "currentColor" } as const;
  switch (status) {
    case "NORMAL":
      return (
        <svg {...common}>
          <circle cx="6" cy="6" r="4" />
        </svg>
      );
    case "MEDIUM":
      return (
        <svg {...common}>
          <path d="M6 1.5 L11 10.5 H1 Z" />
        </svg>
      );
    case "CRITICAL":
      return (
        <svg {...common}>
          <path d="M6 0.5 L11.5 6 L6 11.5 L0.5 6 Z" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <rect x="2" y="5" width="8" height="2" rx="1" />
        </svg>
      );
  }
}

export function StatusBadge({
  status,
  label,
  className = "",
}: {
  status: StatusKey;
  /** override the default word, e.g. "Escalation predicted" */
  label?: string;
  className?: string;
}) {
  const s = STATUS_STYLE[status];
  return (
    <span
      className={`inline-flex items-center gap-bio-1 rounded-bio-sm border px-bio-2 py-bio-1 text-bio-xs font-medium ${s.tone} ${className}`}
    >
      <StatusGlyph status={status} />
      {label ?? s.label}
    </span>
  );
}

/* ------------------------------------------------------------------ surfaces */

export function Panel({
  as: Tag = "section",
  className = "",
  children,
  ...rest
}: {
  as?: "section" | "div" | "article";
  className?: string;
  children: React.ReactNode;
} & React.HTMLAttributes<HTMLElement>) {
  return (
    <Tag
      className={`flex flex-col gap-bio-4 rounded-bio-lg border border-bio-border bg-bio-surface p-bio-5 ${className}`}
      {...rest}
    >
      {children}
    </Tag>
  );
}

export function PanelHeader({
  title,
  description,
  actions,
  titleId,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  titleId?: string;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-bio-3">
      <div className="flex min-w-0 flex-col gap-bio-1">
        <h2 id={titleId} className="text-bio-base font-semibold text-bio-text">
          {title}
        </h2>
        {description && (
          <p className="max-w-[65ch] text-bio-xs text-bio-text-secondary">{description}</p>
        )}
      </div>
      {actions}
    </header>
  );
}

/* ------------------------------------------------------------------ metric card */

export function MetricCard({
  label,
  value,
  unit,
  status,
  delta,
  range,
}: {
  label: string;
  /** null = no reading logged yet */
  value: string | null;
  unit: string;
  status: StatusKey;
  /** already formatted, e.g. "+5.0%"; null hides it */
  delta: string | null;
  /** human-readable normal range from the backend classifier */
  range: string;
}) {
  const s = STATUS_STYLE[status];
  return (
    <article
      aria-label={`${label}: ${value === null ? "no reading" : `${value} ${unit}`}, ${s.label}`}
      className={`flex flex-col gap-bio-3 rounded-bio-lg border bg-bio-surface-elevated p-bio-5 shadow-bio-card ${s.card}`}
    >
      <div className="flex items-center justify-between gap-bio-2">
        <h3 className="text-bio-sm font-medium text-bio-text-secondary">{label}</h3>
        <StatusBadge status={status} />
      </div>

      <p className="flex items-baseline gap-bio-2">
        <span className="font-mono text-bio-2xl font-semibold text-bio-text">{value ?? "—"}</span>
        {value !== null && <span className="text-bio-sm text-bio-text-muted">{unit}</span>}
      </p>

      <footer className="flex flex-wrap items-center justify-between gap-x-bio-3 gap-y-bio-1 border-t border-bio-border pt-bio-3 text-bio-xs">
        <span className="text-bio-text-muted">Normal {range}</span>
        {delta && <span className="font-mono text-bio-text-secondary">{delta}</span>}
      </footer>
    </article>
  );
}

/* ------------------------------------------------------------------ controls */

type ButtonVariant = "primary" | "secondary";

const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  primary:
    "bg-bio-primary text-bio-canvas hover:bg-bio-primary-hover active:bg-bio-primary disabled:bg-bio-surface-active disabled:text-bio-text-secondary",
  secondary:
    "bg-bio-surface-elevated text-bio-text border border-bio-border-control hover:bg-bio-surface-hover active:bg-bio-surface-active disabled:text-bio-text-secondary disabled:bg-bio-surface",
};

export function Button({
  variant = "secondary",
  className = "",
  children,
  ...rest
}: { variant?: ButtonVariant } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={`bio-focus inline-flex h-9 items-center justify-center gap-bio-2 rounded-bio-md px-bio-4 text-bio-sm font-semibold transition-colors duration-150 disabled:cursor-not-allowed max-sm:h-11 ${BUTTON_VARIANT[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

/** Accessible segmented control (WAI-ARIA tabs pattern, arrow-key navigation). */
export function SegmentedTabs<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  const refs = React.useRef<(HTMLButtonElement | null)[]>([]);

  const onKeyDown = (e: React.KeyboardEvent, index: number) => {
    let next = -1;
    if (e.key === "ArrowRight") next = (index + 1) % options.length;
    if (e.key === "ArrowLeft") next = (index - 1 + options.length) % options.length;
    if (e.key === "Home") next = 0;
    if (e.key === "End") next = options.length - 1;
    if (next < 0) return;
    e.preventDefault();
    onChange(options[next].value);
    refs.current[next]?.focus();
  };

  return (
    <div
      role="tablist"
      aria-label={label}
      className="inline-flex items-center gap-bio-1 rounded-bio-md border border-bio-border-control bg-bio-canvas p-bio-1"
    >
      {options.map((o, i) => {
        const selected = o.value === value;
        return (
          <button
            key={o.value}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(o.value)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={`bio-focus h-8 rounded-bio-sm px-bio-3 text-bio-xs font-semibold transition-colors duration-150 max-sm:h-10 ${
              selected
                ? "bg-bio-surface-active text-bio-text"
                : "text-bio-text-secondary hover:bg-bio-surface-hover hover:text-bio-text"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ feedback states */

export function Spinner({ label }: { label: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-bio-2 text-bio-xs text-bio-text-secondary">
      <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="9" className="stroke-bio-border-control" strokeWidth="3" />
        <path d="M21 12a9 9 0 0 0-9-9" className="stroke-bio-primary" strokeWidth="3" strokeLinecap="round" />
      </svg>
      {label}
    </span>
  );
}

export function EmptyState({
  title,
  body,
  action,
  className = "",
}: {
  title: string;
  body: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`flex flex-col items-start justify-center gap-bio-3 rounded-bio-md border border-dashed border-bio-border-control p-bio-5 ${className}`}
    >
      <div className="flex flex-col gap-bio-1">
        <p className="text-bio-sm font-semibold text-bio-text">{title}</p>
        <p className="max-w-[55ch] text-bio-xs text-bio-text-secondary">{body}</p>
      </div>
      {action}
    </div>
  );
}

export function InlineError({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-bio-3 rounded-bio-md border border-bio-critical-border bg-bio-critical-bg p-bio-4"
    >
      <div className="flex items-start gap-bio-3">
        <span className="mt-bio-1 text-bio-critical">
          <StatusGlyph status="CRITICAL" />
        </span>
        <div className="flex flex-col gap-bio-1">
          <p className="text-bio-sm font-semibold text-bio-text">{title}</p>
          <p className="max-w-[60ch] text-bio-xs text-bio-text-secondary">{body}</p>
        </div>
      </div>
      {action}
    </div>
  );
}
