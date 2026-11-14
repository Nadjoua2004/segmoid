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
