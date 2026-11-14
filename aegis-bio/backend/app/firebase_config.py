"""
Firebase Admin & Google Cloud Firestore Configuration for Aegis-Bio.

Architectural Note:
- Firestore acts exclusively as the operational and real-time clinical state database
  (crew profiles, high-frequency telemetry time-series, daily check-ins, triage alerts,
  Flight Surgeon chat logs, dead-man's switch escalations, and 7-day risk trajectories).
- NASA RAG vector embeddings are stored locally in ChromaDB, NOT in Firebase.
"""
import os
from pathlib import Path
from typing import Optional

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.client import Client as FirestoreClient

# Resolve default paths for serviceAccountKey.json
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

DEFAULT_CREDENTIAL_PATHS = [
    os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", ""),
    "serviceAccountKey.json",
    str(BACKEND_DIR / "serviceAccountKey.json"),
    str(APP_DIR / "serviceAccountKey.json"),
    str(PROJECT_ROOT / "serviceAccountKey.json"),
]


def _resolve_credential_path() -> Optional[Path]:
    """Locate serviceAccountKey.json across standard backend and project locations."""
    for raw_path in DEFAULT_CREDENTIAL_PATHS:
        if raw_path:
            candidate = Path(raw_path).expanduser().resolve()
            if candidate.is_file():
                return candidate
    return None


def initialize_firebase() -> FirestoreClient:
    """
    Initialize the Firebase Admin SDK (idempotent) and return the Firestore client.
    """
    if not firebase_admin._apps:
        cred_path = _resolve_credential_path()
        if cred_path is not None:
            cred = credentials.Certificate(str(cred_path))
            firebase_admin.initialize_app(cred)
        elif os.getenv("FIRESTORE_EMULATOR_HOST") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            # Fallback to Application Default Credentials or local Firestore emulator
            firebase_admin.initialize_app()
        else:
            # Explicit path expected for standard serviceAccountKey.json setup
            expected_path = BACKEND_DIR / "serviceAccountKey.json"
            cred = credentials.Certificate(str(expected_path))
            firebase_admin.initialize_app(cred)

    return firestore.client()


# Singleton Firestore client exported for services and scripts
db: FirestoreClient = initialize_firebase()
