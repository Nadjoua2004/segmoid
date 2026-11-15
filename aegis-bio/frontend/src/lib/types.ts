/**
 * TypeScript type definitions for Aegis-Bio
 * Includes OpenTelemetry weekly telemetry, predictor agent, and clinical triage.
 */

export interface CrewMember {
  id: string;
  name: string;
  sex: string;
  age: number;
  hrv_baseline: number;
  hr_max_pred: number;
  total_weeks: number;
}

export interface HourlyVital {
  timestamp: string;
  sol: number;
  hour: number;
  label: string;
  heart_rate: number | null;
  systolic_bp: number | null;
  diastolic_bp: number | null;
  respiratory_rate: number | null;
  activity: string;
}

export interface ShipEnvironmentPoint {
  timestamp: string;
  sol: number;
  hour: number;
  label: string;
  cabin_co2: number;
  radiation_rate_usv: number;
  spo2: number | null;
  core_temp: number | null;
}

export interface StatusDistribution {
  name: string;
  value: number;
  color: string;
}

export interface StressRecoveryDaily {
  sol: number;
  sol_label: string;
  stress_hrv_rmssd: number;
  sleep_hours: number;
  avg_cabin_co2: number;
  peak_radiation_usv: number;
  critical_events: number;
  medium_events: number;
}

export interface WeeklySummaryKPIs {
  avg_heart_rate: number;
  min_heart_rate: number;
  max_heart_rate: number;
  avg_spo2: number;
  min_spo2: number;
  avg_hrv_rmssd: number;
  avg_sleep_hours: number;
  peak_cabin_co2: number;
  peak_radiation_rate: number;
  cumulative_radiation_msv: number;
  avg_core_temp: number;
  total_critical_hours: number;
  total_medium_hours: number;
  dominant_driver: string;
}

export interface WeeklyTelemetryResponse {
  astronaut: {
    id: string;
    name: string;
    sex: string;
    age: number;
    week_number: number;
    max_available_weeks: number;
    start_sol: number;
    end_sol: number;
  };
  summary_kpis: WeeklySummaryKPIs;
  hourly_vitals: HourlyVital[];
  ship_environment: ShipEnvironmentPoint[];
  status_distribution: StatusDistribution[];
  stress_recovery_daily: StressRecoveryDaily[];
  otel_telemetry?: {
    resourceMetrics: any[];
    collector_status: {
      active: boolean;
      protocol: string;
      total_spans_processed: number;
      last_sync: string;
      connected_subsystems: string[];
    };
  };
}

export interface PredictorTrajectoryPoint {
  day_offset: number;
  sol: number;
  sol_label: string;
  predicted_heart_rate: number;
  predicted_spo2: number;
  predicted_cabin_co2: number;
  predicted_radiation_rate: number;
  cardiovascular_strain: number;
  cognitive_fatigue: number;
  status: "NORMAL" | "MEDIUM" | "CRITICAL";
}

export interface ClinicalDirective {
  category: string;
  urgency: string;
  action: string;
  reference: string;
}

export interface PredictorResponse {
  astronaut_id: string;
  astronaut_name: string;
  evaluated_week: number;
  forecast_horizon_days: number;
  health_outlook: "OPTIMAL_STABILITY" | "ELEVATED_STRAIN" | "CRITICAL_DRIFT";
  cardiovascular_strain_score: number;
  cognitive_fatigue_risk: number;
  hypoxia_eclss_risk: number;
  radiation_hazard_index: number;
  projected_trajectory: PredictorTrajectoryPoint[];
  clinical_directives: ClinicalDirective[];
  environmental_drivers: {
    cabin_co2_impact: string;
    radiation_state: string;
    stress_recovery_ratio: string;
  };
}

// -------------------------------------------------------------
// Legacy & Ingestion Schemas
// -------------------------------------------------------------
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

export interface EmergencyAlert {
  alert_id: string;
  astronaut_id: string;
  crew_name?: string;
  station_name?: string;
  severity: "WARNING" | "HIGH_ALERT" | "CRITICAL_ESCALATION" | string;
  hazard_origin: string;
  message: string;
  suggested_crew_actions: string[];
  timestamp: string;
  acknowledged: boolean;
  acknowledged_by?: string | null;
  acknowledged_at?: string | null;
  override_notes?: string | null;
  status?: "PENDING_OWNER" | "ACKNOWLEDGED_BY_OWNER" | "SWITCHED_TO_EMERGENCY_CONTACT" | "ACKNOWLEDGED_BY_CONTACT" | "RESOLVED" | string;
  timeout_seconds?: number;
  timeout_at?: string | null;
  remaining_seconds?: number | null;
  emergency_contact_name?: string | null;
  emergency_contact_callsign?: string | null;
  emergency_contact_email?: string | null;
  emergency_contact_phone?: string | null;
  emergency_contact_role?: string | null;
  emergency_contact_notified_at?: string | null;
  source?: string;
  requires_action?: boolean;
  owner_answered?: boolean;
  prediction_data?: any;
}

export interface UserProfile {
  id: number;
  username: string;
  crew_name: string;
  station_name: string;
  is_lead: boolean;
  callsign?: string;
  alert_timeout_seconds: number;
  created_at: string;
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
  transcript?: string | null; // voice questions: what speech-to-text heard
  photo_description?: string | null; // photo questions: what the vision model saw
  photo_readings?: string[] | null; // values read from the photo (logged only after the astronaut says "yes")
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

export interface HealthMetricsResponse extends HealthMetrics {
  id?: string | number;
  created_at?: string;
}

export interface TrajectoryPoint {
  day: number;
  heart_rate_predicted: number;
  spo2_predicted: number;
  sleep_predicted: number;
  radiation_cumulative_predicted: number;
  [key: string]: any;
}

export interface TriageResult {
  astronaut_id: string;
  mission_day: number;
  overall_status: "NOMINAL" | "WARNING" | "CRITICAL" | string;
  overall_risk_score: number;
  hazards: {
    radiation_score: number;
    microgravity_score: number;
    isolation_score: number;
    hostile_env_score: number;
    distance_score: number;
    [key: string]: number;
  };
  metric_evaluations?: Record<string, any>;
  [key: string]: any;
}

export interface PredictionResult {
  astronaut_id: string;
  horizon_days?: number;
  trajectory?: TrajectoryPoint[];
  projected_trajectory?: PredictorTrajectoryPoint[];
  [key: string]: any;
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
