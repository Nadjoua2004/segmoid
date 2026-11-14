#!/usr/bin/env python3
"""
Train the daily check-in health classifier.

Usage (from aegis-bio/backend):
    python train_checkin_classifier.py              # full training (~1 min)
    python train_checkin_classifier.py --fast       # quick run

Outputs:
    app/services/saved_models/checkin_classifier.joblib        model bundle
    app/services/saved_models/checkin_classifier.report.json   test metrics
    ../../data/daily_checkin_synthetic.csv                     training data (features + labels)
"""
from app.ml.train import main

if __name__ == "__main__":
    main()
