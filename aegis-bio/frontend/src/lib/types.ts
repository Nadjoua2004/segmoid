/**
 * TypeScript type definitions mirroring backend Pydantic schemas for Aegis-Bio
 * Includes Dual-Classifier types:
 * 1. Metric-level severity classifier (NORMAL, MEDIUM, CRITICAL)
 * 2. Multi-hazard spaceflight triage classifier
 */

export interface HealthMetrics {
  astronaut_id: string;
  mission_day: number;
  timestamp?: string;
  heart_rate: number;
  bp_sys: number;
  bp_dia: number;
  spo2: number;
  sleep_hours: number;
  radiation_msv: number;
  blood_glucose: number;
  mood_score: number;
  core_temp_c?: number;
  hrv_rmssd?: number;
  cabin_co2_mmhg?: number;
  subjective_notes?: string;
}

export interface HealthMetricsResponse extends HealthMetrics {
  id: number;
  created_at: string;
}

// -------------------------------------------------------------
// CLASSIFIER 1: Metric-Level Severity (NORMAL, MEDIUM, CRITICAL)
// -------------------------------------------------------------
export interface MetricEvaluation {
  metric_name: string;
  label: string;
  value: number;
  unit: string;
  status: "NORMAL" | "MEDIUM" | "CRITICAL";
  nominal_range: string;
  deviation: string;
  clinical_note: string;
}

export interface MetricClassificationReport {
  astronaut_id: string;
  mission_day: number;
  highest_severity: "NORMAL" | "MEDIUM" | "CRITICAL";
  metrics: Record<string, MetricEvaluation>;
  critical_count: number;
  medium_count: number;
  normal_count: number;
}

// -------------------------------------------------------------
// CLASSIFIER 2: Multi-Hazard Spaceflight Triage
// -------------------------------------------------------------
export interface HazardBreakdown {
  radiation_score: number;
  microgravity_score: number;
  isolation_score: number;
  distance_score: number;
  hostile_env_score: number;
}

export interface Countermeasure {
  id: string;
  title: string;
  category: string;
  urgency: "IMMEDIATE" | "WITHIN_4H" | "ROUTINE";
  protocol: string;
  nasa_hrp_reference: string;
}

export interface TriageResult {
  astronaut_id: string;
  mission_day: number;
  overall_status: "NOMINAL" | "ELEVATED" | "HIGH" | "CRITICAL";
  overall_risk_score: number;
  hazards: HazardBreakdown;
  clinical_flags: string[];
  countermeasures: Countermeasure[];
  requires_emergency_escalation: boolean;
  ai_rationale: string;
  metric_evaluations?: Record<string, MetricEvaluation>;
  evaluated_at: string;
}

export interface TrajectoryPoint {
  day: number;
  heart_rate_predicted: number;
  spo2_predicted: number;
  radiation_cumulative_predicted: number;
  sleep_predicted: number;
  cardiovascular_strain_index: number;
  cognitive_readiness_index: number;
}

export interface PredictionResult {
  astronaut_id: string;
  forecast_horizon_days: number;
  projected_trajectory: TrajectoryPoint[];
  cardiovascular_strain_score: number;
  cognitive_degradation_risk: number;
  early_warnings: string[];
  critical_inflection_day: number | null;
  r2_fit_quality: number;
}

export interface EmergencyAlert {
  alert_id: string;
  astronaut_id: string;
  severity: "WARNING" | "HIGH_ALERT" | "CRITICAL_ESCALATION";
  hazard_origin: string;
  message: string;
  suggested_crew_actions: string[];
  timestamp: string;
  acknowledged: boolean;
  acknowledged_by?: string | null;
  acknowledged_at?: string | null;
}

export interface EmergencyAckRequest {
  alert_id: string;
  crew_member_callsign: string;
  override_notes?: string;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: string;
  citations?: string[];
}

export interface ProactiveChatPayload {
  astronaut_id: string;
  trigger_reason: string;
  clinical_summary: string;
  recommended_dialogue: string;
  suggested_actions: string[];
  reference_guidelines: string[];
  generated_at: string;
}

// -------------------------------------------------------------
// DAILY CHECK-IN (mirrors backend DailyCheckInCreate / DailyCheckInRead)
// -------------------------------------------------------------
export type GlucoseContext = "fasting" | "post_meal" | "random";

export type SymptomKey =
  | "headache"
  | "nasal_congestion"
  | "vision_change"
  | "back_pain"
  | "nausea"
  | "puffy_face"
  | "dizziness"
  | "muscle_joint_pain"
  | "fatigue"
  | "trouble_concentrating"
  | "shortness_of_breath"
  | "skin_irritation";

export interface DailyCheckInPayload {
  astronaut_id: string;
  mission_day: number;
  /** YYYY-MM-DD (local date) */
  checkin_date: string;
  vitals: {
    heart_rate: number;
    bp_sys: number;
    bp_dia: number;
    spo2: number;
    core_temp_c: number;
    blood_glucose: number;
    glucose_context: GlucoseContext;
    hrv_rmssd: number;
  };
  sleep: {
    /** HH:MM */
    bedtime: string;
    wake_time: string;
    sleep_hours: number;
    sleep_quality: number;
    sleep_medication: boolean;
  };
  wellbeing: { mood_score: number; energy_level: number; stress_level: number };
  exercise: { cardio_minutes: number; resistance_minutes: number };
  nutrition: {
    calories_kcal: number;
    water_liters: number;
    breakfast: boolean;
    lunch: boolean;
    dinner: boolean;
    vitamin_d_taken: boolean;
  };
  environment: {
    radiation_msv: number;
    radiation_badge_worn: boolean;
    cabin_temp_c: number;
    cabin_co2_mmhg: number;
    ear_protection_used: boolean;
  };
  symptoms: SymptomKey[];
}

export interface CheckInFlag {
  code: string;
  severity: "INFO" | "MEDIUM" | "CRITICAL";
  message: string;
}

export type AssessmentStatus = "NOMINAL" | "WATCH" | "CRITICAL";

/** Output of the ML daily check-in classifier (backend HealthAssessment). */
export interface HealthAssessment {
  status: AssessmentStatus;
  model_status: AssessmentStatus;
  status_confidence: number;
  safety_override: boolean;
  safety_reasons: string[];
  primary_concern: string;
  concern_label: string;
  hazard: string;
  /** null when a safety rule (not the model) determined the concern */
  concern_confidence: number | null;
  top_concerns: { concern: string; label: string; probability: number }[];
  key_factors: { factor: string; value: string; impact: number }[];
  model_version: string;
  disclaimer: string;
}

export interface DailyCheckInRecord extends DailyCheckInPayload {
  id: number;
  telemetry_log_id: number;
  created_at: string;
  sleep: DailyCheckInPayload["sleep"] & { time_in_bed_hours: number };
  exercise: DailyCheckInPayload["exercise"] & { total_minutes: number };
  flags: CheckInFlag[];
  /** null if the classifier model was unavailable when the check-in was saved */
  assessment: HealthAssessment | null;
}
