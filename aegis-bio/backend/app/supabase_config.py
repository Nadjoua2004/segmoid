"""
Supabase Configuration & Client Initialization for Aegis-Bio.

Reads `SUPABASE_URL` and `SUPABASE_KEY` from environment variables or `aegis-bio/backend/.env`.
Supports both modern `sb_publishable_...` / `sb_secret_...` keys and legacy JWT keys.
"""
import os
from pathlib import Path
from typing import Dict
import requests

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"

if ENV_FILE.is_file():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

SUPABASE_URL: str = os.getenv(
    "SUPABASE_URL", "https://hquoddrlnfdjblclpbjh.supabase.co"
).rstrip("/")
SUPABASE_KEY: str = os.getenv(
    "SUPABASE_KEY", "sb_publishable_8NNiWLe57Sf8xY0peSMAkg_OhDUgLGf"
)
REST_V1_URL: str = f"{SUPABASE_URL}/rest/v1"


def get_supabase_headers(prefer: str = "return=representation,resolution=merge-duplicates") -> Dict[str, str]:
    """Return PostgREST headers compatible with Supabase publishable & service keys."""
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
        "Prefer": prefer,
    }
    # Legacy JWT keys also use Authorization: Bearer <jwt>
    if SUPABASE_KEY.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {SUPABASE_KEY}"
    return headers


session = requests.Session()
