/**
 * Health indicator definitions for the astronaut daily check-in form.
 *
 * Single source of truth for: units, plausibility limits, colour-coded status bands,
 * and plain-language guidance (how to measure, why it matters in space, what to do).
 *
 * - Hard limits (min/max) mirror the backend Pydantic schemas (app/schemas.py) so the
 *   form never sends a value the API will reject.
 * - Vital-sign status bands mirror the backend metric classifier
 *   (app/services/metric_classifier.py); lifestyle/environment bands mirror
 *   app/services/checkin_service.py. Reference values follow NASA ISS-era standards
 *   (NASA-STD-3001 technical briefs) as summarised in the team's reference sheet.
 */
import type { GlucoseContext, SymptomKey } from "./types";

export type Status = "NORMAL" | "MEDIUM" | "CRITICAL";
export type { GlucoseContext, SymptomKey };

export type Hazard =
  | "Space radiation"
  | "Altered gravity"
  | "Isolation & confinement"
  | "Hostile closed environment"
  | "Distance from Earth";

export type IndicatorKey =
  | "heart_rate"
  | "bp_sys"
  | "bp_dia"
  | "spo2"
  | "hrv_rmssd"
  | "core_temp_c"
  | "blood_glucose"
  | "sleep_hours"
  | "cardio_minutes"
  | "resistance_minutes"
  | "water_liters"
  | "calories_kcal"
  | "radiation_msv"
  | "cabin_temp_c"
  | "cabin_co2_mmhg";

export interface IndicatorSpec {
  key: IndicatorKey;
  label: string;
  unit: string;
  /** Hard plausibility limits: values outside are rejected as likely entry/sensor errors. */
  min: number;
  max: number;
  /** Decimal places accepted (0 = integers only). */
  decimals: number;
  required: boolean;
  placeholder: string;
  nominalText: string;
  hazard: Hazard;
  howTo: string[];
  whyInSpace: string;
  ifAbnormal: string;
  /** Omitted for inputs that are only meaningful in aggregate (e.g. one exercise type). */
  classify?: (v: number) => Status;
}

export const INDICATORS: Record<IndicatorKey, IndicatorSpec> = {
  // ---------------------------------------------------------------- Vitals
  heart_rate: {
    key: "heart_rate",
    label: "Resting heart rate",
    unit: "BPM",
    min: 30,
    max: 240,
    decimals: 0,
    required: true,
    placeholder: "e.g. 68",
    nominalText: "50–90 BPM",
    hazard: "Altered gravity",
    howTo: [
      "Measure right after waking, before coffee or exercise.",
      "Rest still for 5 minutes (restrained at your sleep station or seat).",
      "Read the value from the pulse oximeter or chest strap, or count your pulse for 60 s.",
    ],
    whyInSpace:
      "Without gravity, fluid shifts toward the head (about 2 L) and the heart works less. Over time this deconditions the cardiovascular system. A rising resting rate can be an early sign.",
    ifAbnormal:
      "Re-measure after 5 more minutes of rest. If it is still above 115 or below 45 BPM, inform the Crew Medical Officer.",
    classify: (v) => (v >= 115 || v <= 45 ? "CRITICAL" : v > 90 ? "MEDIUM" : "NORMAL"),
  },
  bp_sys: {
    key: "bp_sys",
    label: "Systolic (top number)",
    unit: "mmHg",
    min: 60,
    max: 250,
    decimals: 0,
    required: true,
    placeholder: "e.g. 118",
    nominalText: "90–130 mmHg",
    hazard: "Altered gravity",
    howTo: [
      "Sit or stay restrained and rest for 5 minutes. Don't talk during the reading.",
      "Put the cuff on your bare upper arm, at heart level.",
      "Take two readings 1 minute apart and enter the second one.",
    ],
    whyInSpace:
      "Microgravity resets the body's blood-pressure regulation and plasma volume can fall by up to 20 %. This can cause dizziness or fainting when returning to gravity. (Astronaut selection limit: 140/90.)",
    ifAbnormal:
      "Re-measure on the other arm. If systolic is 140 or more (or 85 or less), or diastolic is 90 or more, inform the Crew Medical Officer.",
    classify: (v) => (v >= 140 || v <= 85 ? "CRITICAL" : v > 130 ? "MEDIUM" : "NORMAL"),
  },
  bp_dia: {
    key: "bp_dia",
    label: "Diastolic (bottom number)",
    unit: "mmHg",
    min: 40,
    max: 160,
    decimals: 0,
    required: true,
    placeholder: "e.g. 76",
    nominalText: "60–85 mmHg",
    hazard: "Altered gravity",
    howTo: [],
    whyInSpace: "",
    ifAbnormal: "",
    classify: (v) => (v >= 90 || v <= 50 ? "CRITICAL" : v > 85 ? "MEDIUM" : "NORMAL"),
  },
  spo2: {
    key: "spo2",
    label: "Blood oxygen (SpO₂)",
    unit: "%",
    min: 50,
    max: 100,
    decimals: 1,
    required: true,
    placeholder: "e.g. 98",
    nominalText: "96–100 %",
    hazard: "Hostile closed environment",
    howTo: [
      "Clip the pulse oximeter on a warm finger with no nail polish.",
      "Keep your hand still and wait until the reading is stable (about 30 s).",
    ],
    whyInSpace:
      "The crew breathes air recycled by life support. A drop in oxygen saturation can be an early sign of a cabin air problem or a lung issue.",
    ifAbnormal:
      "Below 93 %: re-check on another finger right away. If confirmed, check the cabin atmosphere readouts and alert the crew.",
    classify: (v) => (v < 93 ? "CRITICAL" : v < 96 ? "MEDIUM" : "NORMAL"),
  },
  hrv_rmssd: {
    key: "hrv_rmssd",
    label: "Heart rate variability (RMSSD)",
    unit: "ms",
    min: 5,
    max: 200,
    decimals: 0,
    required: true,
    placeholder: "e.g. 48",
    nominalText: "35–100 ms",
    hazard: "Isolation & confinement",
    howTo: [
      "Read the overnight or morning RMSSD from your chest strap or wearable app.",
      "Wear the chest strap or wearable overnight so a reading is available every morning.",
    ],
    whyInSpace:
      "HRV reflects how well the nervous system recovers. Stress, poor sleep and heavy workloads lower it, often before you notice symptoms.",
    ifAbnormal:
      "A low value for several days in a row suggests accumulated stress. Plan a lighter workload and prioritise sleep.",
    classify: (v) => (v <= 22 ? "CRITICAL" : v < 35 ? "MEDIUM" : "NORMAL"),
  },
  core_temp_c: {
    key: "core_temp_c",
    label: "Body temperature",
    unit: "°C",
    min: 34,
    max: 42,
    decimals: 1,
    required: true,
    placeholder: "e.g. 36.8",
    nominalText: "36.5–37.5 °C",
    hazard: "Hostile closed environment",
    howTo: [
      "Use the oral or ear thermometer, at least 30 minutes after exercise or a hot drink.",
      "Note that body temperature in space tends to run slightly higher than on Earth.",
    ],
    whyInSpace:
      "Spaceflight weakens parts of the immune system, and germs spread easily in a sealed cabin. A fever is often the first sign of an infection.",
    ifAbnormal:
      "38.2 °C or more: rest, drink fluids, re-measure in 1 hour and inform the Crew Medical Officer.",
    classify: (v) => (v >= 38.2 || v <= 35.5 ? "CRITICAL" : v > 37.5 ? "MEDIUM" : "NORMAL"),
  },
  blood_glucose: {
    key: "blood_glucose",
    label: "Blood sugar",
    unit: "mg/dL",
    min: 40,
    max: 400,
    decimals: 0,
    required: true,
    placeholder: "e.g. 92",
    nominalText: "70–140 mg/dL (fasting 70–99)",
    hazard: "Altered gravity",
    howTo: [
      "Wash and dry your fingertip, then use the lancet and the glucometer test strip.",
      "Contain the blood drop with a wipe. Loose fluids float away in microgravity.",
      "Say when you last ate so the value can be interpreted correctly.",
    ],
    whyInSpace:
      "Inactivity and stress hormones in spaceflight can reduce insulin sensitivity. Low blood sugar can impair performance during critical tasks.",
    ifAbnormal:
      "Below 70: take fast-acting carbohydrates and re-test in 15 minutes. Above 250 or below 54: inform the Crew Medical Officer.",
    classify: (v) => (v < 54 || v >= 250 ? "CRITICAL" : v < 70 || v > 180 ? "MEDIUM" : "NORMAL"),
  },

  // ---------------------------------------------------------------- Sleep
  sleep_hours: {
    key: "sleep_hours",
    label: "Hours actually slept",
    unit: "hours",
    min: 0,
    max: 24,
    decimals: 1,
    required: true,
    placeholder: "e.g. 6.5",
    nominalText: "6.5–9 h (8.5 h scheduled)",
    hazard: "Isolation & confinement",
    howTo: [
      "Enter the actual time asleep, not the time spent in the sleep station.",
      "Use your wearable's sleep log if available, otherwise your best estimate.",
    ],
    whyInSpace:
      "ISS crews are scheduled 8.5 h of sleep but average only about 6 h. Without a normal day-night cycle (a sunrise every 90 minutes in orbit), sleep is short and fragmented, and sleep loss increases the risk of errors during critical tasks.",
    ifAbnormal:
      "Under 4.5 hours: avoid hazardous tasks such as EVA or robotics today and tell the crew. Use the circadian lighting protocol tonight.",
    classify: (v) => (v < 4.5 ? "CRITICAL" : v < 6.5 ? "MEDIUM" : "NORMAL"),
  },

  // ---------------------------------------------------------------- Exercise
  cardio_minutes: {
    key: "cardio_minutes",
    label: "Cardio (treadmill / bike)",
    unit: "min",
    min: 0,
    max: 600,
    decimals: 0,
    required: true,
    placeholder: "e.g. 75",
    nominalText: "enter 0 if none",
    hazard: "Altered gravity",
    howTo: [
      "Add up today's treadmill (with harness) and cycle ergometer sessions.",
      "Use the time logged by the device if available.",
    ],
    whyInSpace:
      "Aerobic exercise protects heart and lung fitness, which otherwise declines quickly in microgravity.",
    ifAbnormal: "Reschedule a missed session with the crew planner rather than skipping it.",
  },
  resistance_minutes: {
    key: "resistance_minutes",
    label: "Resistance (weights)",
    unit: "min",
    min: 0,
    max: 600,
    decimals: 0,
    required: true,
    placeholder: "e.g. 60",
    nominalText: "enter 0 if none",
    hazard: "Altered gravity",
    howTo: ["Enter the time spent on the resistance exercise device (squats, deadlifts, heel raises…)."],
    whyInSpace:
      "Without loading, the spine and hips lose about 1–2 % of bone mass per month. Heavy resistance exercise is the main countermeasure.",
    ifAbnormal: "Reschedule a missed session with the crew planner rather than skipping it.",
  },

  // ---------------------------------------------------------------- Nutrition
  water_liters: {
    key: "water_liters",
    label: "Water drunk",
    unit: "L",
    min: 0,
    max: 10,
    decimals: 1,
    required: true,
    placeholder: "e.g. 2.2",
    nominalText: "2 L or more",
    hazard: "Altered gravity",
    howTo: ["Count each drink bag or pouch (check its volume) and add up the total in litres."],
    whyInSpace:
      "Thirst is reduced in space, and calcium released from bone raises the risk of kidney stones. Drinking enough water dilutes the urine and lowers that risk.",
    ifAbnormal: "Below 2 L: keep a drink bag at your workstation and sip regularly.",
    classify: (v) => (v < 2 ? "MEDIUM" : "NORMAL"),
  },
  calories_kcal: {
    key: "calories_kcal",
    label: "Calories eaten",
    unit: "kcal",
    min: 0,
    max: 8000,
    decimals: 0,
    required: true,
    placeholder: "e.g. 2600",
    nominalText: "per your menu plan",
    hazard: "Distance from Earth",
    howTo: ["Use the total from the onboard food-tracking app, or add up the labels on today's packages."],
    whyInSpace:
      "Crews eat on average only about 80 % of what they need, which speeds up muscle and bone loss. Food supply is also limited far from Earth.",
    ifAbnormal: "If you are regularly under your menu target, tell the flight surgeon so the menu can be adjusted.",
  },

  // ---------------------------------------------------------------- Environment
  radiation_msv: {
    key: "radiation_msv",
    label: "Radiation dose today",
    unit: "mSv",
    min: 0,
    max: 500,
    decimals: 2,
    required: true,
    placeholder: "e.g. 0.35",
    nominalText: "ISS: 0.2–0.5 mSv/day",
    hazard: "Space radiation",
    howTo: [
      "Read the 24-hour dose from your personal dosimeter (radiation badge) display.",
      "On the ISS a typical value is about 0.2–0.5 mSv per day.",
    ],
    whyInSpace:
      "Outside Earth's magnetic field, cosmic rays and solar storms raise long-term cancer risk. NASA's career limit is 600 mSv, and 250 mSv per solar event.",
    ifAbnormal:
      "20 mSv or more in a day may indicate a solar particle event. Move to the shielded storm shelter and follow the radiation flight rule.",
    classify: (v) => (v >= 20 ? "CRITICAL" : v > 2 ? "MEDIUM" : "NORMAL"),
  },
  cabin_temp_c: {
    key: "cabin_temp_c",
    label: "Cabin temperature",
    unit: "°C",
    min: 0,
    max: 50,
    decimals: 1,
    required: true,
    placeholder: "e.g. 22.5",
    nominalText: "17.8–26.7 °C",
    hazard: "Hostile closed environment",
    howTo: ["Read the temperature for your module from the habitat environment display."],
    whyInSpace:
      "Without convection, heat doesn't rise away from the body, so warm cabins feel hotter and disturb sleep and exercise recovery.",
    ifAbnormal: "Outside 17.8–26.7 °C: report to the crew so the thermal control settings can be checked.",
    classify: (v) => (v < 17.8 || v > 26.7 ? "MEDIUM" : "NORMAL"),
  },
  cabin_co2_mmhg: {
    key: "cabin_co2_mmhg",
    label: "Cabin CO₂",
    unit: "mmHg",
    min: 0,
    max: 15,
    decimals: 1,
    required: true,
    placeholder: "e.g. 2.6",
    nominalText: "≤ 3 mmHg (1-h average)",
    hazard: "Hostile closed environment",
    howTo: ["Read the ppCO₂ value from the habitat life-support (ECLSS) display for your module."],
    whyInSpace:
      "With no convection, exhaled CO₂ can pool around your head. Even moderately high levels cause headaches and slow thinking.",
    ifAbnormal: "Above 3 mmHg: increase ventilation. Above 4.5 mmHg: check the CO₂ scrubber and notify the crew.",
    classify: (v) => (v >= 4.5 ? "CRITICAL" : v > 3 ? "MEDIUM" : "NORMAL"),
  },
};

export const EXERCISE_TARGET_MIN = 120;
export const exerciseStatus = (totalMin: number): Status => (totalMin < EXERCISE_TARGET_MIN ? "MEDIUM" : "NORMAL");

export const STATUS_META: Record<Status, { label: string; text: string; bg: string; border: string; dot: string }> = {
  NORMAL: {
    label: "Nominal",
    text: "text-emerald-300",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/40",
    dot: "bg-emerald-400",
  },
  MEDIUM: {
    label: "Watch",
    text: "text-amber-300",
    bg: "bg-amber-500/10",
    border: "border-amber-500/40",
    dot: "bg-amber-400",
  },
  CRITICAL: {
    label: "Critical",
    text: "text-red-300",
    bg: "bg-red-500/10",
    border: "border-red-500/50",
    dot: "bg-red-500",
  },
};

// ---------------------------------------------------------------- 1–5 rating scales
export interface RatingOption {
  value: number;
  label: string;
  hint?: string;
}

export type RatingKey = "sleep_quality" | "mood" | "energy" | "stress";

export const RATINGS: Record<RatingKey, { legend: string; description: string; options: RatingOption[]; status: (v: number) => Status }> = {
  sleep_quality: {
    legend: "Sleep quality",
    description: "How rested do you feel after last night's sleep?",
    options: [
      { value: 1, label: "Very poor" },
      { value: 2, label: "Poor" },
      { value: 3, label: "Fair" },
      { value: 4, label: "Good" },
      { value: 5, label: "Excellent" },
    ],
    status: (v) => (v <= 2 ? "MEDIUM" : "NORMAL"),
  },
  mood: {
    legend: "Mood",
    description: "Your overall mood and motivation over the last 24 hours.",
    options: [
      { value: 1, label: "Very low", hint: "Distressed, struggling to cope" },
      { value: 2, label: "Low", hint: "Irritable, withdrawn or anxious" },
      { value: 3, label: "Okay", hint: "Some ups and downs" },
      { value: 4, label: "Good", hint: "Steady and engaged" },
      { value: 5, label: "Great", hint: "Energetic and positive" },
    ],
    // mirrors backend mood_score classification
    status: (v) => (v <= 2 ? "CRITICAL" : v === 3 ? "MEDIUM" : "NORMAL"),
  },
  energy: {
    legend: "Energy level",
    description: "How much energy do you have right now?",
    options: [
      { value: 1, label: "Exhausted" },
      { value: 2, label: "Tired" },
      { value: 3, label: "OK" },
      { value: 4, label: "Good" },
      { value: 5, label: "Full energy" },
    ],
    status: (v) => (v <= 2 ? "MEDIUM" : "NORMAL"),
  },
  stress: {
    legend: "Stress",
    description: "How stressed or calm do you feel today?",
    options: [
      { value: 1, label: "Very stressed" },
      { value: 2, label: "Stressed" },
      { value: 3, label: "Some stress" },
      { value: 4, label: "Relaxed" },
      { value: 5, label: "Calm" },
    ],
    status: (v) => (v <= 2 ? "MEDIUM" : "NORMAL"),
  },
};

// ---------------------------------------------------------------- Yes/no checklists
export type CheckKey =
  | "breakfast"
  | "lunch"
  | "dinner"
  | "vitamin_d_taken"
  | "radiation_badge_worn"
  | "ear_protection_used";

export const CHECK_LABELS: Record<CheckKey, string> = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  dinner: "Dinner",
  vitamin_d_taken: "Vitamin D supplement taken",
  radiation_badge_worn: "Radiation badge worn all day",
  ear_protection_used: "Ear protection used in noisy areas",
};

export const MEAL_CHECKS: CheckKey[] = ["breakfast", "lunch", "dinner", "vitamin_d_taken"];
export const SAFETY_CHECKS: CheckKey[] = ["radiation_badge_worn", "ear_protection_used"];

export const GLUCOSE_CONTEXT: { value: GlucoseContext; label: string }[] = [
  { value: "fasting", label: "Fasting (8 h+)" },
  { value: "post_meal", label: "2 h after a meal" },
  { value: "random", label: "Other / not sure" },
];

/** Common spaceflight symptoms (fluid shift, SANS, space adaptation). Keys match the backend enum. */
export const SYMPTOMS: { key: SymptomKey; label: string }[] = [
  { key: "headache", label: "Headache" },
  { key: "nasal_congestion", label: "Nasal congestion" },
  { key: "puffy_face", label: "Puffy face" },
  { key: "vision_change", label: "Vision change" },
  { key: "nausea", label: "Nausea / motion sickness" },
  { key: "dizziness", label: "Dizziness" },
  { key: "back_pain", label: "Back pain" },
  { key: "muscle_joint_pain", label: "Muscle / joint pain" },
  { key: "fatigue", label: "Unusual fatigue" },
  { key: "trouble_concentrating", label: "Trouble concentrating" },
  { key: "shortness_of_breath", label: "Shortness of breath" },
  { key: "skin_irritation", label: "Skin rash / irritation" },
];

/** Parse user input ("36,8" or " 36.8 ") into a number, or null when empty/invalid. */
export function parseNumber(raw: string): number | null {
  const s = raw.trim().replace(",", ".");
  if (s === "" || !/^-?\d*\.?\d+$/.test(s)) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

/** Hours between two "HH:MM" times, wrapping past midnight. */
export function hoursBetween(start: string, end: string): number | null {
  const m = /^(\d{2}):(\d{2})$/;
  const a = m.exec(start);
  const b = m.exec(end);
  if (!a || !b) return null;
  const mins = (+b[1] * 60 + +b[2] - (+a[1] * 60 + +a[2]) + 1440) % 1440;
  return Math.round((mins / 60) * 100) / 100;
}

export function worstStatus(statuses: (Status | null | undefined)[]): Status | null {
  if (statuses.includes("CRITICAL")) return "CRITICAL";
  if (statuses.includes("MEDIUM")) return "MEDIUM";
  if (statuses.includes("NORMAL")) return "NORMAL";
  return null;
}
