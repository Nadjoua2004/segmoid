"""
Application Configuration and Environment Settings
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "Aegis-Bio Clinical Decision Support"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = (
        "Autonomous Clinical Decision-Support System for Deep-Space Artemis & Mars Transit Missions"
    )
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True
    
    # Database
    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'aegis_bio.sqlite3'}"

    # Authentication & Security
    SECRET_KEY: str = "aegis-bio-deep-space-secret-key-super-secure-token-2028"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7-day space mission token
    DEFAULT_ALERT_TIMEOUT_SECONDS: int = 60  # Default seconds before escalating to emergency contact
    
    # ChromaDB Vector Store for RAG
    CHROMA_PERSIST_DIR: str = str(BASE_DIR / "chroma_data")
    
    # Production front-end address(es), comma-separated, e.g. "https://aegis-bio.vercel.app".
    # When set, only these origins (plus localhost) may call the API; when empty, CORS stays open (local dev).
    FRONTEND_ORIGINS: str = ""
    # Optional regex for preview deployments, e.g. r"https://aegis-bio-.*\.vercel\.app"
    FRONTEND_ORIGIN_REGEX: str = ""

    # CORS Origins (Front-end Next.js default on 3000)
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    
    # Mission Context
    MISSION_NAME: str = "Artemis III - Lunar Base Alpha"
    ASTRONAUT_ID: str = "ASTRO-7702-HELENA"
    MISSION_DAY: int = 34
    COMM_LATENCY_MINUTES: float = 18.5

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
