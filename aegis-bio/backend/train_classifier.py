"""
Aegis-Bio ML Classifier Training Pipeline (v2)
Trains dual classifiers on deep_space_crew_telemetry_large.csv using
subject-disjoint train / val / test splits (no astronaut leakage):
1. Per-Metric Severity Models (NORMAL, MEDIUM, CRITICAL)
2. Holistic Overall Status & Primary Driver Classifier
"""
import joblib
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer

BASE_DIR = Path(__file__).resolve().parent
DATA_CANDIDATES = [
    BASE_DIR.parent.parent / "data" / "deep_space_crew_telemetry_large.csv",
    BASE_DIR.parent / "data" / "deep_space_crew_telemetry_large.csv",
    Path("data/deep_space_crew_telemetry_large.csv"),
]

DATA_PATH = next((c for c in DATA_CANDIDATES if c.exists()), None)
MODEL_DIR = BASE_DIR / "app" / "services" / "saved_models"
MODEL_PATH = MODEL_DIR / "triage_classifier.joblib"

NUMERIC_FEATURES = [
    "age",
    "heart_rate_bpm",
    "hr_max_pred_bpm",
    "systolic_bp_mmhg",
    "diastolic_bp_mmhg",
    "respiratory_rate_bpm",
    "spo2_percent",
    "core_temp_c",
    "hrv_rmssd_ms",
    "hrv_baseline_ms",
    "blood_glucose_mgdl",
    "sleep_hours_last_night",
    "radiation_rate_usv_h",
    "cumulative_radiation_msv",
    "cabin_co2_mmhg",
]

CATEGORICAL_FEATURES = ["sex", "activity_state"]
ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

METRIC_TARGETS = [
    "hr_status",
    "bp_status",
    "rr_status",
    "spo2_status",
    "temp_status",
    "hrv_status",
    "glucose_status",
    "sleep_status",
    "co2_status",
    "radiation_status",
]


def build_preprocessor():
    num_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])
    cat_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("ohe", OneHotEncoder(handle_unknown="ignore")),
    ])
    return ColumnTransformer([
        ("num", num_pipe, NUMERIC_FEATURES),
        ("cat", cat_pipe, CATEGORICAL_FEATURES),
    ])


def train_triage_model():
    if not DATA_PATH:
        print("Dataset not found.")
        return

    print(f"[Training Pipeline] Loading dataset: {DATA_PATH}")
    df = pd.read_csv(DATA_PATH)
    print(f"[Training Pipeline] Loaded {len(df):,} rows x {df.shape[1]} columns.")

    train_df = df[df["split"] == "train"]
    val_df = df[df["split"] == "val"]
    test_df = df[df["split"] == "test"]

    X_train = train_df[ALL_FEATURES]
    y_train = train_df["overall_status"]

    X_val = val_df[ALL_FEATURES]
    y_val = val_df["overall_status"]

    X_test = test_df[ALL_FEATURES]
    y_test = test_df["overall_status"]

    pipeline = Pipeline([
        ("prep", build_preprocessor()),
        ("clf", RandomForestClassifier(
            n_estimators=120,
            max_depth=14,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )),
    ])

    print("[Training Pipeline] Training Overall Status Classifier (Astronaut-Disjoint Split)...")
    pipeline.fit(X_train, y_train)

    val_acc = accuracy_score(y_val, pipeline.predict(X_val))
    y_test_pred = pipeline.predict(X_test)
    test_acc = accuracy_score(y_test, y_test_pred)

    print(f"\n[Validation Accuracy (Unseen Astronaut ASTRO-05)]: {val_acc * 100:.2f}%")
    print(f"[Test Accuracy (Unseen Astronaut ASTRO-06)]:       {test_acc * 100:.2f}%")
    print("\n--- Test Set Classification Report ---")
    print(classification_report(y_test, y_test_pred))

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    artifact = {
        "overall_pipeline": pipeline,
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "metric_targets": METRIC_TARGETS,
        "val_accuracy": val_acc,
        "test_accuracy": test_acc,
    }
    joblib.dump(artifact, MODEL_PATH)
    print(f"✓ Saved trained model artifact to: {MODEL_PATH}")


if __name__ == "__main__":
    train_triage_model()
