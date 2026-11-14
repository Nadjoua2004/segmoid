"""
Aegis-Bio ML Classifier Training Pipeline
Trains a Machine Learning model (Random Forest / Gradient Boosting)
on deep_space_crew_telemetry_large.csv to predict flight status & spaceflight hazards.
"""
import os
import joblib
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

BASE_DIR = Path(__file__).resolve().parent

# Check potential data locations
DATA_CANDIDATES = [
    BASE_DIR.parent.parent / "data" / "deep_space_crew_telemetry_large.csv",
    BASE_DIR.parent / "data" / "deep_space_crew_telemetry_large.csv",
    Path("data/deep_space_crew_telemetry_large.csv"),
    Path("../data/deep_space_crew_telemetry_large.csv")
]

DATA_PATH = None
for candidate in DATA_CANDIDATES:
    if candidate.exists():
        DATA_PATH = candidate
        break

MODEL_DIR = BASE_DIR / "app" / "services" / "saved_models"
MODEL_PATH = MODEL_DIR / "triage_classifier.joblib"

FEATURES = [
    "heart_rate_bpm",
    "hrv_rmssd_ms",
    "spo2_percent",
    "core_temp_c",
    "radiation_rate_usv_h",
    "cumulative_radiation_msv",
    "cabin_co2_mmhg"
]

def train_triage_model():
    if not DATA_PATH or not DATA_PATH.exists():
        print(f"Data file not found. Checked: {[str(c) for c in DATA_CANDIDATES]}")
        return

    print(f"[Training Pipeline] Loading dataset: {DATA_PATH}")
    df = pd.read_csv(DATA_PATH)
    print(f"[Training Pipeline] Total records: {len(df)}")

    # Features and Targets
    X = df[FEATURES].copy()
    y_composite = df["status"] + "__" + df["primary_hazard"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_composite, test_size=0.2, random_state=42, stratify=y_composite
    )

    print("[Training Pipeline] Training Random Forest Classifier...")
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("classifier", RandomForestClassifier(
            n_estimators=100,
            max_depth=12,
            class_weight="balanced",
            random_state=42
        ))
    ])

    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"\n[Training Pipeline] Model Accuracy: {acc * 100:.2f}%")
    print("\n--- Classification Report ---")
    print(classification_report(y_test, y_pred))

    # Save model
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    metadata = {
        "pipeline": pipeline,
        "features": FEATURES,
        "classes": list(pipeline.classes_),
        "accuracy": acc
    }
    joblib.dump(metadata, MODEL_PATH)
    print(f"\n✓ Saved trained classifier model to: {MODEL_PATH}")

if __name__ == "__main__":
    train_triage_model()
