"""
Training pipeline for the daily check-in classifier.

Two targets are learned from the same feature vector:
  * status  : NOMINAL / WATCH / CRITICAL
  * concern : which health concern (mapped to a NASA spaceflight hazard) drives the day's risk

Protocol (per target):
  1. stratified 70 / 15 / 15 split into train / validation / test
  2. candidate models (Random Forest, Histogram Gradient Boosting) fitted on train
  3. the candidate with the best validation macro-F1 is selected
  4. the selected model is re-fitted on train + validation with isotonic probability calibration
     and scored ONCE on the untouched test set
The model bundle (joblib) and a JSON report with test metrics are written next to each other.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import joblib
import numpy as np
import sklearn
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score, log_loss
from sklearn.model_selection import train_test_split

from app.ml.features import CONCERNS, FEATURE_NAMES, STATUSES, extract_features
from app.ml.synthetic import generate_dataset

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = BACKEND_DIR / "app" / "services" / "saved_models" / "checkin_classifier.joblib"
DEFAULT_DATA_PATH = BACKEND_DIR.parents[1] / "data" / "daily_checkin_synthetic.csv"
MODEL_VERSION = "1.0.0"


def _candidates(seed: int, fast: bool) -> Dict[str, Any]:
    return {
        "random_forest": RandomForestClassifier(
            n_estimators=60 if fast else 300, min_samples_leaf=2, class_weight="balanced",
            n_jobs=-1, random_state=seed,
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            max_iter=80 if fast else 300, learning_rate=0.08, class_weight="balanced",
            early_stopping=False, random_state=seed,
        ),
    }


def _fit_target(name: str, X: np.ndarray, y: np.ndarray, idx: Dict[str, np.ndarray], labels: list,
                seed: int, fast: bool) -> Dict[str, Any]:
    tr, va, te = idx["train"], idx["val"], idx["test"]
    val_scores, fitted = {}, {}
    for cand_name, model in _candidates(seed, fast).items():
        m = clone(model).fit(X[tr], y[tr])
        val_scores[cand_name] = round(float(f1_score(y[va], m.predict(X[va]), average="macro")), 4)
        fitted[cand_name] = model
    best = max(val_scores, key=val_scores.get)

    # Re-fit the winner on train+val with probability calibration, so reported confidences are meaningful
    # (boosted trees are otherwise over-confident, e.g. 1.00 on almost every case).
    trva = np.concatenate([tr, va])
    final = CalibratedClassifierCV(clone(fitted[best]), method="isotonic", cv=2 if fast else 3)
    final.fit(X[trva], y[trva])
    pred = final.predict(X[te])
    proba = final.predict_proba(X[te])

    report = {
        "selected_model": best,
        "calibration": "isotonic",
        "validation_macro_f1": val_scores,
        "test_accuracy": round(float(accuracy_score(y[te], pred)), 4),
        "test_macro_f1": round(float(f1_score(y[te], pred, average="macro")), 4),
        "test_log_loss": round(float(log_loss(y[te], proba, labels=list(final.classes_))), 4),
        "labels": labels,
        "confusion_matrix": confusion_matrix(y[te], pred, labels=labels).tolist(),
        "per_class": {
            k: {m: round(v, 4) for m, v in d.items()}
            for k, d in classification_report(y[te], pred, labels=labels, output_dict=True, zero_division=0).items()
            if k in labels
        },
    }
    if not fast:
        imp = permutation_importance(final, X[te], y[te], n_repeats=3, random_state=seed, scoring="f1_macro",
                                     n_jobs=-1)
        order = np.argsort(imp.importances_mean)[::-1][:10]
        report["top_features"] = [
            {"feature": FEATURE_NAMES[i], "importance": round(float(imp.importances_mean[i]), 4)} for i in order
        ]
    print(f"[{name}] selected={best} val_f1={val_scores} test_acc={report['test_accuracy']} "
          f"test_macro_f1={report['test_macro_f1']}")
    return {"model": final, "report": report}


def train(n_samples: int = 14000, seed: int = 42, model_path: Path = DEFAULT_MODEL_PATH,
          data_path: Optional[Path] = DEFAULT_DATA_PATH, fast: bool = False) -> Dict[str, Any]:
    payloads, statuses, concerns = generate_dataset(n_samples, seed=seed)
    X = np.asarray([extract_features(p) for p in payloads], dtype=float)
    y_status, y_concern = np.asarray(statuses), np.asarray(concerns)

    strata = np.char.add(np.char.add(y_status, "|"), y_concern)
    all_idx = np.arange(len(X))
    tr, rest = train_test_split(all_idx, test_size=0.30, random_state=seed, stratify=strata)
    va, te = train_test_split(rest, test_size=0.50, random_state=seed, stratify=strata[rest])
    idx = {"train": tr, "val": va, "test": te}

    status = _fit_target("status", X, y_status, idx, STATUSES, seed, fast)
    concern = _fit_target("concern", X, y_concern, idx, CONCERNS, seed, fast)

    critical_i = STATUSES.index("CRITICAL")
    cm = np.asarray(status["report"]["confusion_matrix"])
    status["report"]["critical_recall"] = round(float(cm[critical_i, critical_i] / max(cm[critical_i].sum(), 1)), 4)

    trained_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report = {
        "model_version": MODEL_VERSION,
        "trained_at": trained_at,
        "sklearn_version": sklearn.__version__,
        "data": {
            "source": "synthetic (app/ml/synthetic.py)",
            "n_samples": n_samples, "seed": seed,
            "split": {k: int(len(v)) for k, v in idx.items()},
        },
        "n_features": len(FEATURE_NAMES),
        "status": status["report"],
        "concern": concern["report"],
        "notes": "Labels are simulated, not clinician-assigned. Generated with AI assistance (Claude). "
                 "Re-train on real, clinically labelled data before operational use.",
    }
    bundle = {
        "status_model": status["model"],
        "concern_model": concern["model"],
        "feature_names": FEATURE_NAMES,
        "statuses": STATUSES,
        "concerns": CONCERNS,
        "model_version": MODEL_VERSION,
        "trained_at": trained_at,
        "sklearn_version": sklearn.__version__,
        "metrics": {"status_test_macro_f1": status["report"]["test_macro_f1"],
                    "status_critical_recall": status["report"]["critical_recall"],
                    "concern_test_macro_f1": concern["report"]["test_macro_f1"]},
    }

    model_path = Path(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, model_path, compress=3)
    model_path.with_suffix(".report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved model  -> {model_path}")

    if data_path is not None:
        import csv
        data_path = Path(data_path)
        data_path.parent.mkdir(parents=True, exist_ok=True)
        with data_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([*FEATURE_NAMES, "status", "concern"])
            for row, s, c in zip(X, y_status, y_concern):
                w.writerow([*(f"{v:g}" for v in row), s, c])
        print(f"Saved data   -> {data_path}")
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="Train the daily check-in health classifier.")
    ap.add_argument("--samples", type=int, default=14000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--fast", action="store_true", help="Smaller models, no feature importance (for quick runs)")
    ap.add_argument("--no-csv", action="store_true", help="Don't export the synthetic dataset as CSV")
    args = ap.parse_args()
    train(args.samples, args.seed, data_path=None if args.no_csv else DEFAULT_DATA_PATH, fast=args.fast)


if __name__ == "__main__":
    main()
