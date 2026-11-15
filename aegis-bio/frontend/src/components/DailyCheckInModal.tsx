"use client";

/**
 * Astronaut Daily Health Check-in
 *
 * A guided, multi-step self-assessment modelled on the ISS daily health routine:
 * vitals, sleep & wellbeing, exercise & nutrition, environment, symptoms.
 *
 * Design principles:
 *  - No pre-filled vitals: every value must actually be measured (no silent "fake normal" data).
 *  - One topic per step, short and scannable.
 *  - Live colour-coded status (+ text label, never colour alone) using the same thresholds
 *    as the backend, so feedback is immediate and consistent with triage.
 *  - "How to measure / why it matters in space / what to do" help on every numeric indicator.
 *  - Plausibility validation that catches typos and sensor glitches, with clear messages.
 *  - Draft auto-saved on the device, so an interruption (alarm, task) never loses data.
 *  - After submitting, the backend's findings are shown so the astronaut can act on them.
 *  - Accessible: real labels, fieldsets, aria-invalid/aria-describedby, focus management,
 *    keyboard-only operation (Enter = next, Esc = close), large touch targets.
 */

import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  X,
  Send,
  Heart,
  Moon,
  Dumbbell,
  ShieldAlert,
  Stethoscope,
  ClipboardCheck,
  ChevronLeft,
  ChevronRight,
  HelpCircle,
  AlertTriangle,
  CheckCircle2,
  AlertOctagon,
  Info,
  Save,
  Pencil,
  Check,
  RotateCcw,
  Brain,
} from "lucide-react";
import type {
  DailyCheckInPayload,
  DailyCheckInRecord,
  HealthMetricsResponse,
  CheckInFlag,
  HealthAssessment,
} from "@/lib/types";
import { ApiError } from "@/lib/api";
import {
  INDICATORS,
  IndicatorKey,
  IndicatorSpec,
  Status,
  STATUS_META,
  RATINGS,
  RatingKey,
  CHECK_LABELS,
  CheckKey,
  MEAL_CHECKS,
  SAFETY_CHECKS,
  GLUCOSE_CONTEXT,
  GlucoseContext,
  SYMPTOMS,
  SymptomKey,
  EXERCISE_TARGET_MIN,
  exerciseStatus,
  parseNumber,
  hoursBetween,
  worstStatus,
} from "@/lib/healthIndicators";

// ---------------------------------------------------------------------------
// Types & constants
// ---------------------------------------------------------------------------

interface DailyCheckInModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: DailyCheckInPayload) => Promise<DailyCheckInRecord>;
  currentMissionDay: number;
  /** Most recent logged entry, shown as a reference next to each vital. */
  previousMetrics?: HealthMetricsResponse | null;
  astronautId?: string;
}

type FieldId =
  | IndicatorKey
  | RatingKey
  | "glucose_context"
  | "sleep_medication"
  | "bedtime"
  | "wake_time"
  | "symptoms";

interface FormState {
  values: Record<IndicatorKey, string>;
  bedtime: string;
  wakeTime: string;
  ratings: Record<RatingKey, number | null>;
  sleepMedication: boolean | null;
  glucoseContext: GlucoseContext | "";
  checks: Record<CheckKey, boolean>;
  symptoms: SymptomKey[];
  noSymptoms: boolean;
}

const EMPTY_FORM: FormState = {
  values: Object.fromEntries(Object.keys(INDICATORS).map((k) => [k, ""])) as Record<IndicatorKey, string>,
  bedtime: "",
  wakeTime: "",
  ratings: { sleep_quality: null, mood: null, energy: null, stress: null },
  sleepMedication: null,
  glucoseContext: "",
  checks: Object.fromEntries(Object.keys(CHECK_LABELS).map((k) => [k, false])) as Record<CheckKey, boolean>,
  symptoms: [],
  noSymptoms: false,
};

const STEPS: { title: string; short: string; intro: string; icon: React.ElementType; fields: FieldId[] }[] = [
  {
    title: "Vital signs",
    short: "Vitals",
    intro: "Take these measurements at rest, ideally right after waking up.",
    icon: Heart,
    fields: ["heart_rate", "spo2", "bp_sys", "bp_dia", "core_temp_c", "hrv_rmssd"],
  },
  {
    title: "Sleep & wellbeing",
    short: "Sleep",
    intro: "Be honest. This is for your own health tracking, and nobody scores you on it.",
    icon: Moon,
    fields: ["bedtime", "wake_time", "sleep_hours", "sleep_quality", "sleep_medication", "mood", "energy", "stress"],
  },
  {
    title: "Exercise & nutrition",
    short: "Activity",
    intro: "Exercise and food are your main protection against bone and muscle loss.",
    icon: Dumbbell,
    fields: ["cardio_minutes", "resistance_minutes", "blood_glucose", "glucose_context", "water_liters", "calories_kcal"],
  },
  {
    title: "Environment",
    short: "Environment",
    intro: "Today's radiation dose, protective equipment, and cabin conditions.",
    icon: ShieldAlert,
    fields: ["radiation_msv", "cabin_temp_c", "cabin_co2_mmhg"],
  },
  {
    title: "Symptoms",
    short: "Symptoms",
    intro: "Report anything unusual, even if it seems minor. Small changes matter in space.",
    icon: Stethoscope,
    fields: ["symptoms"],
  },
  {
    title: "Review & submit",
    short: "Review",
    intro: "Check your entries. Re-measure anything marked Critical before submitting.",
    icon: ClipboardCheck,
    fields: [],
  },
];

const LAST_STEP = STEPS.length - 1;
// v3: free-text fields removed (all inputs are structured for the classifier); older drafts are ignored.
const DRAFT_VERSION = "v3";
const domId = (id: string) => `checkin-${id}`;

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

function validate(form: FormState): Partial<Record<FieldId, string>> {
  const errors: Partial<Record<FieldId, string>> = {};

  for (const spec of Object.values(INDICATORS)) {
    const raw = form.values[spec.key].trim();
    if (raw === "") {
      if (spec.required) {
        errors[spec.key] =
          spec.unit === "min" ? "Required. Enter the minutes (use 0 if none)." : "Required. Measure and enter this value.";
      }
      continue;
    }
    const n = parseNumber(raw);
    if (n === null) {
      errors[spec.key] = "Enter a number (digits and one decimal point only).";
      continue;
    }
    if (n < spec.min || n > spec.max) {
      errors[spec.key] = `Outside the possible range (${spec.min}–${spec.max} ${spec.unit}). Check for a typo or re-measure.`;
      continue;
    }
    const decimals = (raw.replace(",", ".").split(".")[1] ?? "").length;
    if (decimals > spec.decimals) {
      errors[spec.key] =
        spec.decimals === 0 ? "Enter a whole number." : `Use at most ${spec.decimals} decimal place${spec.decimals > 1 ? "s" : ""}.`;
    }
  }

  const sys = parseNumber(form.values.bp_sys);
  const dia = parseNumber(form.values.bp_dia);
  if (sys !== null && dia !== null && !errors.bp_sys && !errors.bp_dia && dia >= sys) {
    errors.bp_dia = "Diastolic must be lower than systolic. Check whether the two numbers are swapped.";
  }

  if (!form.bedtime) errors.bedtime = "Required. Enter the time you went to bed.";
  if (!form.wakeTime) errors.wake_time = "Required. Enter the time you woke up.";

  for (const key of Object.keys(RATINGS) as RatingKey[]) {
    if (form.ratings[key] === null) errors[key] = "Choose one option.";
  }
  if (form.sleepMedication === null) errors.sleep_medication = "Choose yes or no.";

  if (form.values.blood_glucose.trim() !== "" && !form.glucoseContext) {
    errors.glucose_context = "Select when you last ate, so the value can be interpreted.";
  }

  if (form.symptoms.length === 0 && !form.noSymptoms) {
    errors.symptoms = "Select any symptoms you have, or tick “No symptoms today”.";
  }

  return errors;
}

// ---------------------------------------------------------------------------
// Draft persistence (per astronaut + mission day, on this device only)
// ---------------------------------------------------------------------------

function loadDraft(key: string): FormState | null {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const p = JSON.parse(raw) as Partial<FormState>;
    const validSymptoms = new Set(SYMPTOMS.map((s) => s.key));
    return {
      ...EMPTY_FORM,
      ...p,
      values: { ...EMPTY_FORM.values, ...(p.values ?? {}) },
      ratings: { ...EMPTY_FORM.ratings, ...(p.ratings ?? {}) },
      checks: { ...EMPTY_FORM.checks, ...(p.checks ?? {}) },
      symptoms: Array.isArray(p.symptoms) ? p.symptoms.filter((s) => validSymptoms.has(s)) : [],
    };
  } catch {
    return null;
  }
}

function isDirty(form: FormState): boolean {
  return (
    Object.values(form.values).some((v) => v.trim() !== "") ||
    form.bedtime !== "" ||
    form.wakeTime !== "" ||
    Object.values(form.ratings).some((v) => v !== null) ||
    form.sleepMedication !== null ||
    form.glucoseContext !== "" ||
    Object.values(form.checks).some(Boolean) ||
    form.symptoms.length > 0 ||
    form.noSymptoms
  );
}

function todayLocalISO(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function describeSubmitError(err: unknown, missionDay: number): { title: string; detail: string } {
  if (err instanceof ApiError) {
    if (err.status === 409) {
      return {
        title: `A check-in for Sol ${missionDay} was already submitted.`,
        detail: "Only one check-in per mission day is stored. Contact the Crew Medical Officer to correct it.",
      };
    }
    if (err.status === 422 && Array.isArray(err.detail)) {
      const msgs = (err.detail as { loc?: (string | number)[]; msg?: string }[])
        .map((d) => `${(d.loc ?? []).slice(1).join(" › ")}: ${d.msg ?? "invalid"}`)
        .join("; ");
      return { title: "The server rejected some values.", detail: msgs };
    }
    return { title: "Couldn't send your check-in.", detail: err.message };
  }
  return {
    title: "Couldn't reach the onboard server.",
    detail: err instanceof Error ? err.message : "Unknown error",
  };
}

// ---------------------------------------------------------------------------
// Small presentational pieces
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: Status }) {
  const m = STATUS_META[status];
  const Icon = status === "CRITICAL" ? AlertOctagon : status === "MEDIUM" ? AlertTriangle : CheckCircle2;
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold ${m.text} ${m.bg} ${m.border}`}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {m.label}
    </span>
  );
}

function HelpPanel({ spec, id }: { spec: IndicatorSpec; id: string }) {
  return (
    <div id={id} className="mt-3 space-y-3 rounded-lg border border-slate-700/70 bg-space-950/60 p-3 text-sm leading-relaxed">
      <div>
        <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-hud-cyan">How to measure</h4>
        <ol className="list-decimal space-y-0.5 pl-5 text-slate-300">
          {spec.howTo.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ol>
      </div>
      <div>
        <h4 className="mb-1 flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-wide text-hud-purple">
          Why it matters in space
          <span className="rounded border border-purple-500/40 px-1.5 py-px text-[10px] font-medium normal-case tracking-normal text-purple-300">
            Hazard: {spec.hazard}
          </span>
        </h4>
        <p className="text-slate-300">{spec.whyInSpace}</p>
      </div>
      <div>
        <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-hud-amber">If it&apos;s out of range</h4>
        <p className="text-slate-300">{spec.ifAbnormal}</p>
      </div>
    </div>
  );
}

function HelpToggle({ open, onClick, controls, label }: { open: boolean; onClick: () => void; controls: string; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-expanded={open}
      aria-controls={controls}
      className="inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-1 text-xs text-slate-400 hover:bg-space-800 hover:text-hud-cyan focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-hud-cyan"
    >
      <HelpCircle className="h-4 w-4" aria-hidden="true" />
      <span>{open ? "Hide help" : "Help"}</span>
      <span className="sr-only"> for {label}</span>
    </button>
  );
}

function cardClass(status: Status | null, hasError: boolean) {
  const border = hasError
    ? "border-red-500/70"
    : status === "CRITICAL"
      ? "border-red-500/50"
      : status === "MEDIUM"
        ? "border-amber-500/40"
        : status === "NORMAL"
          ? "border-emerald-500/30"
          : "border-slate-800";
  return `rounded-xl border bg-space-900 p-4 transition-colors ${border}`;
}

function inputClass(hasError: boolean) {
  return `w-full rounded-lg border bg-space-850 px-3 py-2.5 pr-16 font-mono text-base text-white placeholder:font-sans placeholder:text-sm placeholder:text-slate-600 focus:outline-none focus:ring-2 [color-scheme:dark] ${
    hasError ? "border-red-500/70 focus:ring-red-500/60" : "border-slate-700 focus:border-hud-cyan focus:ring-hud-cyan/40"
  }`;
}

function Alert({ tone, children }: { tone: "critical" | "watch" | "info"; children: React.ReactNode }) {
  const styles = {
    critical: "bg-red-500/10 text-red-200",
    watch: "bg-amber-500/10 text-amber-200",
    info: "bg-sky-500/10 text-sky-200",
  }[tone];
  const Icon = tone === "critical" ? AlertOctagon : tone === "watch" ? AlertTriangle : Info;
  return (
    <p className={`mt-2 flex gap-1.5 rounded-md px-2 py-1.5 text-xs leading-snug ${styles}`}>
      <Icon className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span>{children}</span>
    </p>
  );
}

function GuidanceLine({ spec, status }: { spec: IndicatorSpec; status: Status | null }) {
  if (status !== "CRITICAL" && status !== "MEDIUM") return null;
  return <Alert tone={status === "CRITICAL" ? "critical" : "watch"}>{spec.ifAbnormal}</Alert>;
}

function FieldError({ id, children }: { id: string; children?: React.ReactNode }) {
  if (!children) return null;
  return (
    <p id={id} className="mt-1.5 text-xs font-medium text-red-400">
      {children}
    </p>
  );
}

const pillClass =
  "inline-flex items-center justify-center rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition-colors hover:border-slate-500 peer-checked:border-hud-cyan peer-checked:bg-cyan-500/10 peer-checked:text-hud-cyan peer-focus-visible:ring-2 peer-focus-visible:ring-hud-cyan";

const textButtonClass =
  "inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-hud-cyan hover:bg-space-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-hud-cyan";

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export const DailyCheckInModal: React.FC<DailyCheckInModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  currentMissionDay,
  previousMetrics,
  astronautId = "ASTRO-7702-HELENA",
}) => {
  const missionDay = currentMissionDay + 1;
  const draftKey = `aegis-bio:checkin-draft:${DRAFT_VERSION}:${astronautId}:${missionDay}`;

  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [step, setStep] = useState(0);
  const [touched, setTouched] = useState<Set<FieldId>>(new Set());
  const [attempted, setAttempted] = useState<Set<number>>(new Set());
  const [openHelp, setOpenHelp] = useState<IndicatorKey | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<{ title: string; detail: string } | null>(null);
  const [result, setResult] = useState<DailyCheckInRecord | null>(null);
  const [draftRestored, setDraftRestored] = useState(false);

  const dialogRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const hydrated = useRef(false);
  const reviewEnteredAt = useRef(0);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const errors = useMemo(() => validate(form), [form]);

  // --- Load draft when the dialog opens -------------------------------------
  useEffect(() => {
    if (!isOpen) {
      hydrated.current = false;
      return;
    }
    const draft = loadDraft(draftKey);
    setForm(draft ?? EMPTY_FORM);
    setDraftRestored(!!draft && isDirty(draft));
    setStep(0);
    setTouched(new Set());
    setAttempted(new Set());
    setOpenHelp(null);
    setSubmitError(null);
    setResult(null);
    hydrated.current = true;
  }, [isOpen, draftKey]);

  // --- Auto-save draft --------------------------------------------------------
  useEffect(() => {
    if (!isOpen || !hydrated.current || result) return;
    try {
      if (isDirty(form)) window.localStorage.setItem(draftKey, JSON.stringify(form));
      else window.localStorage.removeItem(draftKey);
    } catch {
      /* storage unavailable: the form still works, just without draft recovery */
    }
  }, [form, isOpen, draftKey, result]);

  // --- Scroll lock, Escape to close, focus trap, focus restore ----------------
  useEffect(() => {
    if (!isOpen) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCloseRef.current();
        return;
      }
      if (e.key === "Tab" && dialogRef.current) {
        const focusables = Array.from(
          dialogRef.current.querySelectorAll<HTMLElement>(
            'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
          )
        );
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = prevOverflow;
      previouslyFocused?.focus?.();
    };
  }, [isOpen]);

  // --- Move focus to the start of each step -----------------------------------
  useEffect(() => {
    if (!isOpen) return;
    if (step === LAST_STEP) reviewEnteredAt.current = Date.now();
    const t = window.setTimeout(() => {
      bodyRef.current?.scrollTo({ top: 0 });
      const target =
        step === LAST_STEP || result
          ? headingRef.current
          : bodyRef.current?.querySelector<HTMLElement>("input[type='text'], textarea");
      target?.focus({ preventScroll: true });
    }, 0);
    return () => window.clearTimeout(t);
  }, [step, isOpen, result]);

  if (!isOpen) return null;

  // --- Helpers ----------------------------------------------------------------
  const stepOf = (id: FieldId) => STEPS.findIndex((s) => s.fields.includes(id));
  const shownError = (id: FieldId) => (touched.has(id) || attempted.has(stepOf(id)) ? errors[id] : undefined);
  const touch = (id: FieldId) => setTouched((t) => (t.has(id) ? t : new Set(t).add(id)));
  const setValue = (k: IndicatorKey, v: string) => setForm((f) => ({ ...f, values: { ...f.values, [k]: v } }));
  const setRating = (k: RatingKey, v: number) => setForm((f) => ({ ...f, ratings: { ...f.ratings, [k]: v } }));
  const toggleCheck = (k: CheckKey) => setForm((f) => ({ ...f, checks: { ...f.checks, [k]: !f.checks[k] } }));

  const statusFor = (k: IndicatorKey): Status | null => {
    const classify = INDICATORS[k].classify;
    if (!classify || errors[k]) return null;
    const n = parseNumber(form.values[k]);
    return n === null ? null : classify(n);
  };

  const ratingStatus = (k: RatingKey): Status | null => {
    const v = form.ratings[k];
    return v === null ? null : RATINGS[k].status(v);
  };

  const exerciseTotal = (): number | null => {
    const c = errors.cardio_minutes ? null : parseNumber(form.values.cardio_minutes);
    const r = errors.resistance_minutes ? null : parseNumber(form.values.resistance_minutes);
    return c === null || r === null ? null : c + r;
  };

  const timeInBed = form.bedtime && form.wakeTime ? hoursBetween(form.bedtime, form.wakeTime) : null;

  const previousFor = (k: IndicatorKey): number | null => {
    const v = previousMetrics?.[k as keyof HealthMetricsResponse];
    return typeof v === "number" ? v : null;
  };

  const referenceText = (k: IndicatorKey) => {
    const spec = INDICATORS[k];
    const prev = previousFor(k);
    const cur = errors[k] ? null : parseNumber(form.values[k]);
    let text = `Normal: ${spec.nominalText}`;
    if (prev !== null) {
      text += ` · Last (Sol ${previousMetrics?.mission_day}): ${prev} ${spec.unit}`;
      if (cur !== null) {
        const d = +(cur - prev).toFixed(spec.decimals);
        text += d === 0 ? " (no change)" : ` (${d > 0 ? "+" : ""}${d})`;
      }
    }
    return text;
  };

  const focusField = (id: FieldId) => {
    const el =
      document.getElementById(domId(id)) ?? dialogRef.current?.querySelector<HTMLElement>(`[name="${id}"]`) ?? null;
    el?.focus();
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
  };

  const stepErrorFields = (i: number) => STEPS[i].fields.filter((f) => errors[f]);
  const stepIsValid = (i: number) => stepErrorFields(i).length === 0;

  const goNext = () => {
    const bad = stepErrorFields(step);
    if (bad.length > 0) {
      setAttempted((a) => new Set(a).add(step));
      focusField(bad[0]);
      return;
    }
    setStep((s) => Math.min(s + 1, LAST_STEP));
  };

  const goToStep = (i: number) => {
    if (i <= step) return setStep(i);
    // Only allow jumping forward if every step before the target is complete.
    for (let s = 0; s < i; s++) {
      if (!stepIsValid(s)) {
        setStep(s);
        setAttempted((a) => new Set(a).add(s));
        return;
      }
    }
    setStep(i);
  };

  const startOver = () => {
    setForm(EMPTY_FORM);
    setTouched(new Set());
    setAttempted(new Set());
    setDraftRestored(false);
    setStep(0);
  };

  const buildPayload = (): DailyCheckInPayload => {
    const n = (k: IndicatorKey) => parseNumber(form.values[k]);
    const req = (k: IndicatorKey) => n(k) as number; // guaranteed by validate()
    const c = form.checks;
    return {
      astronaut_id: astronautId,
      mission_day: missionDay,
      checkin_date: todayLocalISO(),
      vitals: {
        heart_rate: req("heart_rate"),
        bp_sys: req("bp_sys"),
        bp_dia: req("bp_dia"),
        spo2: req("spo2"),
        core_temp_c: req("core_temp_c"),
        blood_glucose: req("blood_glucose"),
        glucose_context: form.glucoseContext as GlucoseContext,
        hrv_rmssd: req("hrv_rmssd"),
      },
      sleep: {
        bedtime: form.bedtime,
        wake_time: form.wakeTime,
        sleep_hours: req("sleep_hours"),
        sleep_quality: form.ratings.sleep_quality as number,
        sleep_medication: form.sleepMedication as boolean,
      },
      wellbeing: {
        mood_score: form.ratings.mood as number,
        energy_level: form.ratings.energy as number,
        stress_level: form.ratings.stress as number,
      },
      exercise: {
        cardio_minutes: req("cardio_minutes"),
        resistance_minutes: req("resistance_minutes"),
      },
      nutrition: {
        calories_kcal: req("calories_kcal"),
        water_liters: req("water_liters"),
        breakfast: c.breakfast,
        lunch: c.lunch,
        dinner: c.dinner,
        vitamin_d_taken: c.vitamin_d_taken,
      },
      environment: {
        radiation_msv: req("radiation_msv"),
        radiation_badge_worn: c.radiation_badge_worn,
        cabin_temp_c: req("cabin_temp_c"),
        cabin_co2_mmhg: req("cabin_co2_mmhg"),
        ear_protection_used: c.ear_protection_used,
      },
      symptoms: form.noSymptoms ? [] : form.symptoms,
    };
  };

  const handleFormSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (result) return onClose();
    if (step < LAST_STEP) return goNext();
    // Guard against a double-click on "Next" landing on "Submit".
    if (Date.now() - reviewEnteredAt.current < 400) return;

    const firstInvalid = STEPS.findIndex((_, i) => !stepIsValid(i));
    if (firstInvalid !== -1) {
      setAttempted(new Set(STEPS.map((_, i) => i)));
      setStep(firstInvalid);
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);
    try {
      const record = await onSubmit(buildPayload());
      try {
        window.localStorage.removeItem(draftKey);
      } catch {
        /* ignore */
      }
      setResult(record);
    } catch (err) {
      setSubmitError(describeSubmitError(err, missionDay));
    } finally {
      setIsSubmitting(false);
    }
  };

  // --- Field renderers --------------------------------------------------------
  const renderNumberField = (k: IndicatorKey, extra?: React.ReactNode, showReference = true) => {
    const spec = INDICATORS[k];
    const err = shownError(k);
    const status = statusFor(k);
    const id = domId(k);
    const helpId = `${id}-help`;
    return (
      <div key={k} className={cardClass(status, !!err)}>
        <div className="flex items-start justify-between gap-2">
          <label htmlFor={id} className="pt-1 text-sm font-medium text-slate-100">
            {spec.label}
            {!spec.required && <span className="ml-1.5 text-xs font-normal text-slate-500">(optional)</span>}
          </label>
          <HelpToggle
            open={openHelp === k}
            onClick={() => setOpenHelp(openHelp === k ? null : k)}
            controls={helpId}
            label={spec.label}
          />
        </div>

        <div className="mt-2 flex items-center gap-3">
          <div className="relative flex-1">
            <input
              id={id}
              name={k}
              type="text"
              inputMode={spec.decimals === 0 ? "numeric" : "decimal"}
              autoComplete="off"
              spellCheck={false}
              value={form.values[k]}
              onChange={(e) => setValue(k, e.target.value)}
              onBlur={() => touch(k)}
              placeholder={spec.placeholder}
              aria-required={spec.required}
              aria-invalid={!!err}
              aria-describedby={`${id}-ref${err ? ` ${id}-err` : ""}`}
              className={inputClass(!!err)}
            />
            <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 font-mono text-xs text-slate-500">
              {spec.unit}
            </span>
          </div>
          {spec.classify && (
            <div className="w-[5.5rem]" aria-live="polite">
              {status && <StatusBadge status={status} />}
            </div>
          )}
        </div>

        <p id={`${id}-ref`} className="mt-1.5 text-xs text-slate-500">
          {showReference ? referenceText(k) : `Normal: ${spec.nominalText}`}
        </p>
        <FieldError id={`${id}-err`}>{err}</FieldError>
        <GuidanceLine spec={spec} status={status} />
        {extra}
        {openHelp === k && <HelpPanel spec={spec} id={helpId} />}
      </div>
    );
  };

  const renderBloodPressure = () => {
    const sysErr = shownError("bp_sys");
    const diaErr = shownError("bp_dia");
    const status = worstStatus([statusFor("bp_sys"), statusFor("bp_dia")]);
    const helpId = `${domId("bp_sys")}-help`;
    const prevSys = previousFor("bp_sys");
    const prevDia = previousFor("bp_dia");
    const part = (k: "bp_sys" | "bp_dia", short: string, err?: string) => (
      <div className="flex-1">
        <label htmlFor={domId(k)} className="mb-1 block text-xs text-slate-400">
          {short}
        </label>
        <div className="relative">
          <input
            id={domId(k)}
            name={k}
            type="text"
            inputMode="numeric"
            autoComplete="off"
            value={form.values[k]}
            onChange={(e) => setValue(k, e.target.value)}
            onBlur={() => touch(k)}
            placeholder={INDICATORS[k].placeholder}
            aria-required
            aria-invalid={!!err}
            aria-describedby={`checkin-bp-ref${err ? ` ${domId(k)}-err` : ""}`}
            className={inputClass(!!err)}
          />
          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 font-mono text-xs text-slate-500">
            mmHg
          </span>
        </div>
      </div>
    );

    return (
      <fieldset key="bp" className={`${cardClass(status, !!(sysErr || diaErr))} md:col-span-2`}>
        <div className="flex items-start justify-between gap-2">
          <legend className="float-left pt-1 text-sm font-medium text-slate-100">Blood pressure</legend>
          <HelpToggle
            open={openHelp === "bp_sys"}
            onClick={() => setOpenHelp(openHelp === "bp_sys" ? null : "bp_sys")}
            controls={helpId}
            label="blood pressure"
          />
        </div>
        <div className="clear-both mt-2 flex items-end gap-3">
          {part("bp_sys", "Systolic (top)", sysErr)}
          <span className="pb-3 font-mono text-lg text-slate-600" aria-hidden="true">
            /
          </span>
          {part("bp_dia", "Diastolic (bottom)", diaErr)}
          <div className="w-[5.5rem] pb-2" aria-live="polite">
            {status && <StatusBadge status={status} />}
          </div>
        </div>
        <p id="checkin-bp-ref" className="mt-1.5 text-xs text-slate-500">
          Normal: 90–130 / 60–85 mmHg
          {prevSys !== null && prevDia !== null && ` · Last (Sol ${previousMetrics?.mission_day}): ${prevSys}/${prevDia} mmHg`}
        </p>
        <FieldError id={`${domId("bp_sys")}-err`}>{sysErr && `Systolic: ${sysErr}`}</FieldError>
        <FieldError id={`${domId("bp_dia")}-err`}>{diaErr && `Diastolic: ${diaErr}`}</FieldError>
        <GuidanceLine spec={INDICATORS.bp_sys} status={status} />
        {openHelp === "bp_sys" && <HelpPanel spec={INDICATORS.bp_sys} id={helpId} />}
      </fieldset>
    );
  };

  const renderTimeInputs = () => {
    const bedErr = shownError("bedtime");
    const wakeErr = shownError("wake_time");
    const time = (id: "bedtime" | "wake_time", label: string, value: string, err?: string) => (
      <div className="flex-1">
        <label htmlFor={domId(id)} className="mb-1 block text-xs text-slate-400">
          {label}
        </label>
        <input
          id={domId(id)}
          name={id}
          type="time"
          value={value}
          onChange={(e) =>
            setForm((f) => (id === "bedtime" ? { ...f, bedtime: e.target.value } : { ...f, wakeTime: e.target.value }))
          }
          onBlur={() => touch(id)}
          aria-required
          aria-invalid={!!err}
          aria-describedby={err ? `${domId(id)}-err` : undefined}
          className={`${inputClass(!!err)} pr-3`}
        />
      </div>
    );
    return (
      <fieldset className={cardClass(null, !!(bedErr || wakeErr))}>
        <legend className="float-left text-sm font-medium text-slate-100">
          Sleep period
        </legend>
        <div className="clear-both flex gap-3 pt-2">
          {time("bedtime", "Bedtime", form.bedtime, bedErr)}
          {time("wake_time", "Wake time", form.wakeTime, wakeErr)}
        </div>
        <FieldError id={`${domId("bedtime")}-err`}>{bedErr}</FieldError>
        <FieldError id={`${domId("wake_time")}-err`}>{wakeErr}</FieldError>
        {timeInBed !== null && (
          <p className="mt-1.5 text-xs text-slate-400">
            Time in bed: <span className="font-mono text-slate-200">{timeInBed} h</span> (8.5 h scheduled on the ISS)
          </p>
        )}
      </fieldset>
    );
  };

  const renderSleepHours = () => {
    const slept = errors.sleep_hours ? null : parseNumber(form.values.sleep_hours);
    const extra =
      slept !== null && timeInBed !== null && slept > timeInBed + 0.25 ? (
        <Alert tone="info">
          Hours slept ({slept} h) is more than your time in bed ({timeInBed} h). That&apos;s fine if you napped;
          otherwise check the times.
        </Alert>
      ) : null;
    return renderNumberField("sleep_hours", extra);
  };

  const renderRating = (k: RatingKey) => {
    const cfg = RATINGS[k];
    const err = shownError(k);
    const status = ratingStatus(k);
    const value = form.ratings[k];
    const hasHints = cfg.options.some((o) => o.hint);
    return (
      <fieldset key={k} className={cardClass(status, !!err)} aria-describedby={`${domId(k)}-desc${err ? ` ${domId(k)}-err` : ""}`}>
        <div className="flex items-start justify-between gap-2">
          <legend className="float-left text-sm font-medium text-slate-100">{cfg.legend}</legend>
          {status && status !== "NORMAL" && <StatusBadge status={status} />}
        </div>
        <p id={`${domId(k)}-desc`} className="clear-both mb-3 pt-1 text-xs text-slate-500">
          {cfg.description}
        </p>
        <div className={`grid gap-2 ${hasHints ? "grid-cols-1 sm:grid-cols-5" : "grid-cols-5"}`}>
          {cfg.options.map((opt) => (
            <label key={opt.value} className="cursor-pointer">
              <input
                type="radio"
                name={k}
                value={opt.value}
                checked={value === opt.value}
                onChange={() => {
                  setRating(k, opt.value);
                  touch(k);
                }}
                className="peer sr-only"
              />
              <span
                className={`flex h-full rounded-lg border border-slate-700 p-2 transition-colors hover:border-slate-500 peer-checked:border-hud-cyan peer-checked:bg-cyan-500/10 peer-focus-visible:ring-2 peer-focus-visible:ring-hud-cyan ${
                  hasHints ? "items-center gap-3 sm:flex-col sm:gap-1 sm:text-center" : "flex-col items-center gap-0.5 text-center"
                }`}
              >
                <span className="font-mono text-base font-bold text-white">{opt.value}</span>
                <span>
                  <span className="block text-xs font-medium leading-tight text-slate-200">{opt.label}</span>
                  {opt.hint && <span className="block text-[11px] leading-tight text-slate-500">{opt.hint}</span>}
                </span>
              </span>
            </label>
          ))}
        </div>
        <FieldError id={`${domId(k)}-err`}>{err}</FieldError>
        {k === "mood" && status === "CRITICAL" && (
          <Alert tone="critical">
            Thank you for being honest. Please talk to a crewmate or the Crew Medical Officer today. A private
            conference with the flight psychologist can also be scheduled.
          </Alert>
        )}
      </fieldset>
    );
  };

  const renderSleepMedication = () => {
    const err = shownError("sleep_medication");
    return (
      <fieldset className={cardClass(null, !!err)} aria-describedby={err ? `${domId("sleep_medication")}-err` : undefined}>
        <legend className="float-left text-sm font-medium text-slate-100">Did you take sleep medication?</legend>
        <div className="clear-both flex gap-2 pt-2">
          {[
            { v: false, label: "No" },
            { v: true, label: "Yes" },
          ].map((o) => (
            <label key={o.label} className="cursor-pointer">
              <input
                type="radio"
                name="sleep_medication"
                checked={form.sleepMedication === o.v}
                onChange={() => {
                  setForm((f) => ({ ...f, sleepMedication: o.v }));
                  touch("sleep_medication");
                }}
                className="peer sr-only"
              />
              <span className={`${pillClass} min-w-[4rem]`}>{o.label}</span>
            </label>
          ))}
        </div>
        <FieldError id={`${domId("sleep_medication")}-err`}>{err}</FieldError>
        {form.sleepMedication && (
          <Alert tone="info">Allow for possible drowsiness before hazardous tasks such as EVA or robotics.</Alert>
        )}
      </fieldset>
    );
  };

  const renderGlucoseContext = () => {
    const err = shownError("glucose_context");
    return (
      <fieldset className="mt-3" aria-describedby={err ? `${domId("glucose_context")}-err` : undefined}>
        <legend className="mb-1.5 text-xs text-slate-400">When did you last eat?</legend>
        <div className="flex flex-wrap gap-2">
          {GLUCOSE_CONTEXT.map((opt) => (
            <label key={opt.value} className="cursor-pointer">
              <input
                type="radio"
                name="glucose_context"
                value={opt.value}
                checked={form.glucoseContext === opt.value}
                onChange={() => {
                  setForm((f) => ({ ...f, glucoseContext: opt.value }));
                  touch("glucose_context");
                }}
                className="peer sr-only"
              />
              <span className={pillClass}>{opt.label}</span>
            </label>
          ))}
        </div>
        <FieldError id={`${domId("glucose_context")}-err`}>{err}</FieldError>
      </fieldset>
    );
  };

  const renderChecklist = (legend: string, keys: CheckKey[], hint?: string, footer?: React.ReactNode) => (
    <fieldset className="rounded-xl border border-slate-800 bg-space-900 p-4">
      <legend className="float-left text-sm font-medium text-slate-100">{legend}</legend>
      {hint && <p className="clear-both pt-1 text-xs text-slate-500">{hint}</p>}
      <div className="clear-both grid grid-cols-1 gap-2 pt-3 sm:grid-cols-2">
        {keys.map((k) => (
          <label key={k} className="cursor-pointer">
            <input
              type="checkbox"
              name={k}
              checked={form.checks[k]}
              onChange={() => toggleCheck(k)}
              className="peer sr-only"
            />
            <span className="flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 transition-colors hover:border-slate-500 peer-checked:border-emerald-500/60 peer-checked:bg-emerald-500/10 peer-checked:text-emerald-100 peer-focus-visible:ring-2 peer-focus-visible:ring-hud-cyan">
              <span
                className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                  form.checks[k] ? "border-emerald-400 bg-emerald-400 text-space-950" : "border-slate-600"
                }`}
                aria-hidden="true"
              >
                {form.checks[k] && <Check className="h-3 w-3" strokeWidth={3} />}
              </span>
              {CHECK_LABELS[k]}
            </span>
          </label>
        ))}
      </div>
      {footer}
    </fieldset>
  );

  const renderExercise = () => {
    const total = exerciseTotal();
    const status = total === null ? null : exerciseStatus(total);
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-1 items-start gap-3 md:grid-cols-2">
          {renderNumberField("cardio_minutes", undefined, false)}
          {renderNumberField("resistance_minutes", undefined, false)}
        </div>
        <div className={`${cardClass(status, false)} flex flex-wrap items-center justify-between gap-2`} aria-live="polite">
          <p className="text-sm text-slate-300">
            Total exercise:{" "}
            <span className="font-mono text-base font-semibold text-white">{total ?? "—"}</span> min
            <span className="ml-2 text-xs text-slate-500">Target {EXERCISE_TARGET_MIN}–150 min</span>
          </p>
          {status && <StatusBadge status={status} />}
        </div>
      </div>
    );
  };

  const renderSymptoms = () => {
    const err = shownError("symptoms");
    return (
      <fieldset
        className={cardClass(form.symptoms.length > 0 ? "MEDIUM" : null, !!err)}
        aria-describedby={err ? `${domId("symptoms")}-err` : undefined}
      >
        <legend className="float-left text-sm font-medium text-slate-100">
          Any symptoms today? <span className="text-xs font-normal text-slate-500">(select all that apply)</span>
        </legend>
        <div className="clear-both grid grid-cols-1 gap-2 pt-3 sm:grid-cols-2">
          {SYMPTOMS.map((s) => {
            const checked = form.symptoms.includes(s.key);
            return (
              <label key={s.key} className="cursor-pointer">
                <input
                  type="checkbox"
                  name="symptoms"
                  value={s.key}
                  checked={checked}
                  onChange={() => {
                    setForm((f) => ({
                      ...f,
                      noSymptoms: false,
                      symptoms: checked ? f.symptoms.filter((x) => x !== s.key) : [...f.symptoms, s.key],
                    }));
                    touch("symptoms");
                  }}
                  className="peer sr-only"
                />
                <span className="flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 transition-colors hover:border-slate-500 peer-checked:border-amber-400/70 peer-checked:bg-amber-500/10 peer-checked:text-amber-100 peer-focus-visible:ring-2 peer-focus-visible:ring-hud-cyan">
                  <span
                    className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                      checked ? "border-amber-400 bg-amber-400 text-space-950" : "border-slate-600"
                    }`}
                    aria-hidden="true"
                  >
                    {checked && <Check className="h-3 w-3" strokeWidth={3} />}
                  </span>
                  {s.label}
                </span>
              </label>
            );
          })}
        </div>

        <label className="mt-3 block cursor-pointer border-t border-slate-800 pt-3">
          <input
            type="checkbox"
            name="no_symptoms"
            checked={form.noSymptoms}
            onChange={() => {
              setForm((f) => ({ ...f, noSymptoms: !f.noSymptoms, symptoms: !f.noSymptoms ? [] : f.symptoms }));
              touch("symptoms");
            }}
            className="peer sr-only"
          />
          <span className="flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 transition-colors hover:border-slate-500 peer-checked:border-emerald-500/60 peer-checked:bg-emerald-500/10 peer-checked:text-emerald-100 peer-focus-visible:ring-2 peer-focus-visible:ring-hud-cyan">
            <span
              className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                form.noSymptoms ? "border-emerald-400 bg-emerald-400 text-space-950" : "border-slate-600"
              }`}
              aria-hidden="true"
            >
              {form.noSymptoms && <Check className="h-3 w-3" strokeWidth={3} />}
            </span>
            No symptoms today
          </span>
        </label>

        <FieldError id={`${domId("symptoms")}-err`}>{err}</FieldError>
        {form.symptoms.includes("vision_change") && (
          <Alert tone="watch">
            Vision changes can be a sign of Spaceflight-Associated Neuro-ocular Syndrome (SANS), seen in about 70 % of
            long-stay crew. Schedule an eye exam (fundoscopy / ocular ultrasound) with the Crew Medical Officer.
          </Alert>
        )}
        {(form.symptoms.includes("puffy_face") || form.symptoms.includes("nasal_congestion")) && (
          <Alert tone="info">
            Facial puffiness and congestion are common: about 2 L of body fluid shifts toward the head in microgravity.
            Report it if it gets worse or comes with headache or vision changes.
          </Alert>
        )}
      </fieldset>
    );
  };

  // --- Review step ------------------------------------------------------------
  type Row = { label: string; value: string; status: Status | null; normal?: string };

  const numRow = (k: IndicatorKey, label?: string): Row | null => {
    const n = parseNumber(form.values[k]);
    if (n === null) return null;
    const s = INDICATORS[k];
    return { label: label ?? s.label, value: `${n} ${s.unit}`, status: s.classify?.(n) ?? null, normal: s.nominalText };
  };

  const ratingRow = (k: RatingKey): Row | null => {
    const v = form.ratings[k];
    if (v === null) return null;
    const opt = RATINGS[k].options.find((o) => o.value === v);
    return { label: RATINGS[k].legend, value: `${v}/5 · ${opt?.label ?? ""}`, status: RATINGS[k].status(v) };
  };

  const checksRow = (label: string, keys: CheckKey[], warnIfMissing = false): Row => {
    const done = keys.filter((k) => form.checks[k]);
    return {
      label,
      value: done.length ? done.map((k) => CHECK_LABELS[k]).join(", ") : "None",
      status: warnIfMissing && done.length < keys.length ? "MEDIUM" : null,
    };
  };

  const renderReview = () => {
    const glucoseCtx = GLUCOSE_CONTEXT.find((g) => g.value === form.glucoseContext)?.label;
    const total = exerciseTotal();

    const groups: { step: number; rows: (Row | null)[] }[] = [
      {
        step: 0,
        rows: [
          numRow("heart_rate"),
          {
            label: "Blood pressure",
            value: `${form.values.bp_sys}/${form.values.bp_dia} mmHg`,
            status: worstStatus([statusFor("bp_sys"), statusFor("bp_dia")]),
            normal: "90–130 / 60–85 mmHg",
          },
          numRow("spo2"),
          numRow("core_temp_c"),
          numRow("hrv_rmssd"),
        ],
      },
      {
        step: 1,
        rows: [
          form.bedtime && form.wakeTime
            ? { label: "Sleep period", value: `${form.bedtime} → ${form.wakeTime} (${timeInBed} h in bed)`, status: null }
            : null,
          numRow("sleep_hours"),
          ratingRow("sleep_quality"),
          { label: "Sleep medication", value: form.sleepMedication ? "Yes" : "No", status: null },
          ratingRow("mood"),
          ratingRow("energy"),
          ratingRow("stress"),
        ],
      },
      {
        step: 2,
        rows: [
          total !== null
            ? {
                label: "Exercise",
                value: `${total} min (cardio ${form.values.cardio_minutes} + resistance ${form.values.resistance_minutes})`,
                status: exerciseStatus(total),
                normal: `${EXERCISE_TARGET_MIN}–150 min`,
              }
            : null,
          (() => {
            const r = numRow("blood_glucose");
            return r && glucoseCtx ? { ...r, value: `${r.value} · ${glucoseCtx.toLowerCase()}` } : r;
          })(),
          numRow("water_liters"),
          numRow("calories_kcal"),
          {
            ...checksRow("Meals & supplements", MEAL_CHECKS),
            status: [form.checks.breakfast, form.checks.lunch, form.checks.dinner].filter(Boolean).length < 2 ? "MEDIUM" : null,
          },
        ],
      },
      {
        step: 3,
        rows: [
          numRow("radiation_msv"),
          {
            label: "Radiation badge",
            value: form.checks.radiation_badge_worn ? "Worn all day" : "Not worn",
            status: form.checks.radiation_badge_worn ? null : "MEDIUM",
          },
          numRow("cabin_temp_c"),
          numRow("cabin_co2_mmhg"),
          { label: "Ear protection", value: form.checks.ear_protection_used ? "Used" : "Not used", status: null },
        ],
      },
      {
        step: 4,
        rows: [
          {
            label: "Symptoms",
            value: form.symptoms.length
              ? form.symptoms.map((s) => SYMPTOMS.find((x) => x.key === s)?.label).join(", ")
              : "None",
            status: form.symptoms.length ? "MEDIUM" : null,
          },
        ],
      },
    ];

    const all = groups.flatMap((g) => g.rows).filter((r): r is Row => r !== null);
    const critical = all.filter((r) => r.status === "CRITICAL");
    const watch = all.filter((r) => r.status === "MEDIUM");
    const overall = worstStatus(all.map((r) => r.status)) ?? "NORMAL";

    return (
      <div className="space-y-4">
        <div
          role="status"
          className={`flex gap-3 rounded-xl border p-4 text-sm ${STATUS_META[overall].bg} ${STATUS_META[overall].border}`}
        >
          {overall === "CRITICAL" ? (
            <AlertOctagon className="h-5 w-5 shrink-0 text-red-400" aria-hidden="true" />
          ) : overall === "MEDIUM" ? (
            <AlertTriangle className="h-5 w-5 shrink-0 text-amber-400" aria-hidden="true" />
          ) : (
            <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-400" aria-hidden="true" />
          )}
          <div className="space-y-1">
            {overall === "CRITICAL" && (
              <>
                <p className="font-semibold text-red-200">
                  {critical.length} item{critical.length > 1 ? "s" : ""} in the critical range:{" "}
                  {critical.map((r) => r.label).join(", ")}.
                </p>
                <p className="text-red-200/80">
                  Re-measure to confirm a sensor or entry error isn&apos;t the cause. Submitting runs triage and may alert
                  the Crew Medical Officer automatically.
                </p>
              </>
            )}
            {overall === "MEDIUM" && (
              <>
                <p className="font-semibold text-amber-200">
                  {watch.length} item{watch.length > 1 ? "s" : ""} to watch: {watch.map((r) => r.label).join(", ")}.
                </p>
                <p className="text-amber-200/80">You&apos;ll get specific advice after submitting.</p>
              </>
            )}
            {overall === "NORMAL" && <p className="font-semibold text-emerald-200">Everything is within the nominal range.</p>}
          </div>
        </div>

        {groups.map((g) => (
          <section key={g.step} className="rounded-xl border border-slate-800 bg-space-900">
            <div className="flex items-center justify-between border-b border-slate-800 px-4 py-2.5">
              <h4 className="text-sm font-semibold text-slate-200">{STEPS[g.step].title}</h4>
              <button type="button" onClick={() => setStep(g.step)} className={textButtonClass}>
                <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                Edit<span className="sr-only"> {STEPS[g.step].title}</span>
              </button>
            </div>
            <dl className="divide-y divide-slate-800/70">
              {g.rows
                .filter((r): r is Row => r !== null)
                .map((r) => (
                  <div
                    key={r.label}
                    className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 px-4 py-2.5 sm:grid-cols-[minmax(0,10rem)_minmax(0,1fr)_auto]"
                  >
                    <dt className="text-sm text-slate-300">
                      {r.label}
                      {r.normal && <span className="block text-[11px] text-slate-600">Normal: {r.normal}</span>}
                    </dt>
                    <dd className="col-span-2 break-words text-sm text-white sm:col-span-1 sm:text-right sm:font-mono">
                      {r.value}
                    </dd>
                    <dd className="col-start-2 row-start-1 justify-self-end sm:col-start-3">
                      {r.status && <StatusBadge status={r.status} />}
                    </dd>
                  </div>
                ))}
            </dl>
          </section>
        ))}

        {submitError && (
          <div role="alert" className="rounded-xl border border-red-500/60 bg-red-500/10 p-4 text-sm text-red-200">
            <p className="font-semibold">{submitError.title}</p>
            <p className="mt-1 text-red-200/80">Your entries are still saved on this device.</p>
            <p className="mt-2 break-words font-mono text-[11px] text-red-300/70">{submitError.detail}</p>
          </div>
        )}
      </div>
    );
  };

  // --- Result (after submit) ----------------------------------------------------
  const renderAssessment = (a: HealthAssessment | null) => {
    if (!a) {
      return (
        <section className="rounded-xl border border-slate-800 bg-space-900 px-4 py-3 text-sm text-slate-400">
          AI health assessment unavailable: the classifier model is not loaded on the server.
        </section>
      );
    }
    const status: Status = a.status === "WATCH" ? "MEDIUM" : a.status === "NOMINAL" ? "NORMAL" : "CRITICAL";
    const pct = (x: number) => `${Math.round(x * 100)} %`;
    const alternatives = a.top_concerns.filter((c) => c.concern !== a.primary_concern && c.probability >= 0.1);
    return (
      <section className={`rounded-xl border bg-space-900 ${STATUS_META[status].border}`} aria-labelledby="checkin-ai-title">
        <div className="flex items-center justify-between gap-2 border-b border-slate-800 px-4 py-2.5">
          <h4 id="checkin-ai-title" className="flex items-center gap-2 text-sm font-semibold text-slate-200">
            <Brain className="h-4 w-4 text-hud-purple" aria-hidden="true" />
            AI health assessment
          </h4>
          <StatusBadge status={status} />
        </div>
        <div className="space-y-3 px-4 py-3 text-sm">
          <div>
            <p className="font-semibold text-white">
              {a.primary_concern === "NONE" ? "No specific health concern detected" : a.concern_label}
            </p>
            <p className="mt-0.5 text-xs text-slate-400">
              {a.primary_concern !== "NONE" && <>Related hazard: {a.hazard} · </>}
              {a.concern_confidence === null
                ? "Determined by a critical safety rule"
                : `Model confidence ${pct(a.primary_concern === "NONE" ? a.status_confidence : a.concern_confidence)}`}
            </p>
          </div>

          {a.safety_override && (
            <Alert tone="critical">
              Status raised to Critical by a safety rule (the model alone said {a.model_status.toLowerCase()}):{" "}
              {a.safety_reasons.join("; ")}.
            </Alert>
          )}

          {a.key_factors.length > 0 && (
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">What drove this result</p>
              <ul className="space-y-1.5">
                {a.key_factors.map((f) => (
                  <li key={f.factor} className="flex items-center gap-3">
                    <span className="min-w-0 flex-1 text-slate-200">
                      {f.factor}: <span className="font-mono text-slate-300">{f.value}</span>
                    </span>
                    <span className="h-1.5 w-20 shrink-0 overflow-hidden rounded-full bg-slate-800" aria-hidden="true">
                      <span className="block h-full rounded-full bg-hud-purple" style={{ width: `${Math.min(100, f.impact * 100)}%` }} />
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {alternatives.length > 0 && (
            <p className="text-xs text-slate-400">
              Also possible: {alternatives.map((c) => `${c.label} (${pct(c.probability)})`).join(", ")}
            </p>
          )}

          <p className="border-t border-slate-800 pt-2 text-[11px] leading-snug text-slate-500">
            {a.disclaimer} Model v{a.model_version}.
          </p>
        </div>
      </section>
    );
  };

  const renderResult = (rec: DailyCheckInRecord) => {
    const order: Record<CheckInFlag["severity"], number> = { CRITICAL: 0, MEDIUM: 1, INFO: 2 };
    const flags = [...rec.flags].sort((a, b) => order[a.severity] - order[b.severity]);
    return (
      <div className="space-y-4">
        <div role="status" className="flex gap-3 rounded-xl border border-emerald-500/40 bg-emerald-500/10 p-4 text-sm">
          <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-400" aria-hidden="true" />
          <div>
            <p className="font-semibold text-emerald-200">Check-in for Sol {rec.mission_day} saved.</p>
            <p className="mt-0.5 text-emerald-200/80">
              Your vitals were sent to triage. The dashboard and 7-day forecast are updating now.
            </p>
          </div>
        </div>

        {renderAssessment(rec.assessment)}

        <section className="rounded-xl border border-slate-800 bg-space-900">
          <h4 className="border-b border-slate-800 px-4 py-2.5 text-sm font-semibold text-slate-200">
            Advice from today&apos;s check-in
          </h4>
          {flags.length === 0 ? (
            <p className="px-4 py-3 text-sm text-slate-400">
              No lifestyle or environment issues found. Keep up the routine.
            </p>
          ) : (
            <ul className="divide-y divide-slate-800/70">
              {flags.map((f) => {
                const tone = f.severity === "CRITICAL" ? "text-red-400" : f.severity === "MEDIUM" ? "text-amber-400" : "text-sky-400";
                const Icon = f.severity === "CRITICAL" ? AlertOctagon : f.severity === "MEDIUM" ? AlertTriangle : Info;
                return (
                  <li key={f.code} className="flex gap-3 px-4 py-3 text-sm">
                    <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${tone}`} aria-hidden="true" />
                    <span className="text-slate-200">
                      <span className="sr-only">{f.severity}: </span>
                      {f.message}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>
    );
  };

  // --- Layout -----------------------------------------------------------------
  const current = STEPS[step];
  const StepIcon = result ? CheckCircle2 : current.icon;
  const dateLabel = new Date().toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-2 backdrop-blur-md sm:p-4">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="checkin-title"
        aria-describedby="checkin-subtitle"
        className="relative flex max-h-[96vh] w-full max-w-2xl flex-col rounded-2xl border border-cyan-800/60 bg-space-950 text-slate-100 shadow-[0_0_50px_rgba(0,240,255,0.15)]"
      >
        {/* Header */}
        <header className="border-b border-slate-800 px-5 pb-4 pt-5">
          <div className="flex items-start justify-between gap-4">
            <div data-tour="checkin-title">
              <h2 id="checkin-title" className="font-mono text-lg font-bold uppercase tracking-wide text-white">
                Daily health check-in
              </h2>
              <p id="checkin-subtitle" className="mt-0.5 text-xs text-slate-400">
                {astronautId} · Sol {missionDay} · {dateLabel} · about 6 minutes
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label={result ? "Close" : "Close check-in (your draft is kept)"}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-space-850 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-hud-cyan"
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>

          {/* Stepper */}
          {!result && (
            <nav aria-label="Check-in progress" data-tour="checkin-progress" className="mt-4">
              <ol className="grid grid-cols-6 gap-1.5">
                {STEPS.map((s, i) => {
                  const done = i < step && stepIsValid(i);
                  const active = i === step;
                  return (
                    <li key={s.title}>
                      <button
                        type="button"
                        onClick={() => goToStep(i)}
                        aria-current={active ? "step" : undefined}
                        aria-label={`Step ${i + 1}: ${s.title}${done ? " (complete)" : ""}`}
                        className="group flex w-full flex-col gap-1.5 text-left focus-visible:outline-none"
                      >
                        <span
                          className={`h-1 w-full rounded-full transition-colors ${
                            active ? "bg-hud-cyan" : done ? "bg-cyan-700" : "bg-slate-800"
                          } group-focus-visible:ring-2 group-focus-visible:ring-hud-cyan`}
                        />
                        <span
                          className={`flex items-center gap-0.5 truncate text-[11px] font-medium ${
                            active ? "text-hud-cyan" : done ? "text-slate-300" : "text-slate-500"
                          }`}
                        >
                          {done && <Check className="h-3 w-3 shrink-0" aria-hidden="true" />}
                          <span className="truncate">{s.short}</span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ol>
            </nav>
          )}
        </header>

        <form onSubmit={handleFormSubmit} noValidate className="flex min-h-0 flex-1 flex-col">
          {/* Body */}
          <div ref={bodyRef} data-tour="checkin-body" className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
            {draftRestored && step === 0 && !result && (
              <div className="mb-4 flex items-center justify-between gap-3 rounded-lg border border-cyan-800/60 bg-cyan-950/40 px-3 py-2 text-xs text-cyan-100">
                <span>We restored your unfinished check-in for Sol {missionDay}.</span>
                <button type="button" onClick={startOver} className={`${textButtonClass} shrink-0 font-medium`}>
                  <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                  Start over
                </button>
              </div>
            )}

            <div className="mb-4 flex items-center gap-3">
              <div className="rounded-lg border border-cyan-700/50 bg-cyan-950 p-2 text-hud-cyan">
                <StepIcon className="h-5 w-5" aria-hidden="true" />
              </div>
              <div>
                {!result && (
                  <p className="text-[11px] uppercase tracking-wider text-slate-500">
                    Step {step + 1} of {STEPS.length}
                  </p>
                )}
                <h3 ref={headingRef} tabIndex={-1} className="text-base font-semibold text-white focus:outline-none">
                  {result ? "Check-in complete" : current.title}
                </h3>
              </div>
            </div>
            {!result && <p className="-mt-2 mb-4 text-sm text-slate-400">{current.intro}</p>}

            {result ? (
              renderResult(result)
            ) : (
              <>
                {step === 0 && (
                  <div className="grid grid-cols-1 items-start gap-3 md:grid-cols-2">
                    {renderNumberField("heart_rate")}
                    {renderNumberField("spo2")}
                    {renderBloodPressure()}
                    {renderNumberField("core_temp_c")}
                    {renderNumberField("hrv_rmssd")}
                  </div>
                )}

                {step === 1 && (
                  <div className="space-y-3">
                    {renderTimeInputs()}
                    {renderSleepHours()}
                    {renderRating("sleep_quality")}
                    {renderSleepMedication()}
                    {renderRating("mood")}
                    {renderRating("energy")}
                    {renderRating("stress")}
                  </div>
                )}

                {step === 2 && (
                  <div className="space-y-3">
                    {renderExercise()}
                    {renderNumberField("blood_glucose", renderGlucoseContext())}
                    <div className="grid grid-cols-1 items-start gap-3 md:grid-cols-2">
                      {renderNumberField("water_liters", undefined, false)}
                      {renderNumberField("calories_kcal", undefined, false)}
                    </div>
                    {renderChecklist("Meals & supplements", MEAL_CHECKS, "Tick each meal you ate today.")}
                  </div>
                )}

                {step === 3 && (
                  <div className="space-y-3">
                    {renderNumberField("radiation_msv")}
                    {renderChecklist(
                      "Protective equipment",
                      SAFETY_CHECKS,
                      undefined,
                      !form.checks.radiation_badge_worn ? (
                        <Alert tone="watch">
                          Without the badge worn all day, today&apos;s radiation dose may be under-reported.
                        </Alert>
                      ) : null
                    )}
                    <div className="grid grid-cols-1 items-start gap-3 md:grid-cols-2">
                      {renderNumberField("cabin_temp_c", undefined, false)}
                      {renderNumberField("cabin_co2_mmhg", undefined, false)}
                    </div>
                  </div>
                )}

                {step === 4 && (
                  <div className="space-y-3">
                    {renderSymptoms()}
                  </div>
                )}

                {step === LAST_STEP && renderReview()}
              </>
            )}
          </div>

          {/* Footer */}
          <footer data-tour="checkin-footer" className="flex items-center justify-between gap-3 border-t border-slate-800 px-5 py-3">
            {result ? (
              <button
                type="submit"
                className="ml-auto inline-flex items-center gap-1 rounded-lg bg-cyan-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-cyan-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-hud-cyan focus-visible:ring-offset-2 focus-visible:ring-offset-space-950"
              >
                Done
              </button>
            ) : (
              <>
                <p className="hidden items-center gap-1.5 text-[11px] text-slate-500 sm:flex">
                  <Save className="h-3.5 w-3.5" aria-hidden="true" />
                  Draft saved on this device
                </p>
                <div className="ml-auto flex items-center gap-2">
                  {step === 0 ? (
                    <button
                      type="button"
                      onClick={onClose}
                      className="rounded-lg px-4 py-2.5 text-sm text-slate-400 hover:bg-space-850 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-hud-cyan"
                    >
                      Cancel
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setStep((s) => s - 1)}
                      disabled={isSubmitting}
                      className="inline-flex items-center gap-1 rounded-lg px-4 py-2.5 text-sm text-slate-300 hover:bg-space-850 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-hud-cyan disabled:opacity-50"
                    >
                      <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                      Back
                    </button>
                  )}

                  {step < LAST_STEP ? (
                    <button
                      type="submit"
                      className="inline-flex items-center gap-1 rounded-lg bg-cyan-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-cyan-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-hud-cyan focus-visible:ring-offset-2 focus-visible:ring-offset-space-950"
                    >
                      {step === LAST_STEP - 1 ? "Review" : "Next"}
                      <ChevronRight className="h-4 w-4" aria-hidden="true" />
                    </button>
                  ) : (
                    <button
                      type="submit"
                      disabled={isSubmitting}
                      aria-busy={isSubmitting}
                      className="inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-cyan-600 to-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-[0_0_20px_rgba(0,240,255,0.3)] hover:from-cyan-500 hover:to-blue-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-hud-cyan focus-visible:ring-offset-2 focus-visible:ring-offset-space-950 disabled:opacity-60"
                    >
                      <Send className="h-4 w-4" aria-hidden="true" />
                      {isSubmitting ? "Submitting…" : "Submit & run triage"}
                    </button>
                  )}
                </div>
              </>
            )}
          </footer>
        </form>
      </div>
    </div>
  );
};
