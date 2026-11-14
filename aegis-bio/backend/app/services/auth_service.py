"""
Authentication and Security Service for Aegis-Bio
Implements bcrypt password hashing, JWT token handling, and astronaut auth helpers.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import UserModel

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

def hash_password(password: str) -> str:
    """Hash plaintext password with bcrypt salt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plaintext password against bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Generate signed JWT access token for astronaut authentication session."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate JWT access token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except Exception:
        return None

def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> UserModel:
    """FastAPI Dependency for strictly authenticated routes."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate flight credentials or session expired.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception

    payload = decode_access_token(token)
    if not payload:
        raise credentials_exception

    username: Optional[str] = payload.get("sub")
    if not username:
        raise credentials_exception

    user = db.query(UserModel).filter(UserModel.username == username).first()
    if not user or not user.is_active:
        raise credentials_exception

    return user

def get_optional_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Optional[UserModel]:
    """FastAPI Dependency for endpoints supporting both authenticated and anonymous calls."""
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    username = payload.get("sub")
    if not username:
        return None
    return db.query(UserModel).filter(UserModel.username == username).first()

def seed_default_users_if_empty(db: Session):
    """Ensure baseline astronauts exist with pre-configured emergency contacts."""
    if db.query(UserModel).count() > 0:
        return

    default_users = [
        {
            "username": "cmdr_vance",
            "email": "vance@artemis.nasa.gov",
            "password": "Password123!",
            "full_name": "Cmdr. Elena Vance",
            "callsign": "ASTRO-01",
            "role": "Mission Commander",
            "emergency_contact_name": "Dr. Marcus Chen",
            "emergency_contact_callsign": "ASTRO-02",
            "emergency_contact_email": "chen@artemis.nasa.gov",
            "emergency_contact_phone": "MCC-CH-02",
            "emergency_contact_role": "Crew Medical Officer",
            "alert_timeout_seconds": 60,
        },
        {
            "username": "dr_chen",
            "email": "chen@artemis.nasa.gov",
            "password": "Password123!",
            "full_name": "Dr. Marcus Chen",
            "callsign": "ASTRO-02",
            "role": "Crew Medical Officer",
            "emergency_contact_name": "Cmdr. Elena Vance",
            "emergency_contact_callsign": "ASTRO-01",
            "emergency_contact_email": "vance@artemis.nasa.gov",
            "emergency_contact_phone": "MCC-CH-01",
            "emergency_contact_role": "Mission Commander",
            "alert_timeout_seconds": 60,
        },
        {
            "username": "eng_kowalski",
            "email": "kowalski@artemis.nasa.gov",
            "password": "Password123!",
            "full_name": "Eng. Jan Kowalski",
            "callsign": "ASTRO-03",
            "role": "ECLSS Engineer",
            "emergency_contact_name": "Dr. Marcus Chen",
            "emergency_contact_callsign": "ASTRO-02",
            "emergency_contact_email": "chen@artemis.nasa.gov",
            "emergency_contact_phone": "MCC-CH-02",
            "emergency_contact_role": "Crew Medical Officer",
            "alert_timeout_seconds": 60,
        },
        {
            "username": "helena_astro",
            "email": "helena@artemis.nasa.gov",
            "password": "Password123!",
            "full_name": "Helena Rostova",
            "callsign": "ASTRO-7702-HELENA",
            "role": "Payload Specialist",
            "emergency_contact_name": "Dr. Marcus Chen",
            "emergency_contact_callsign": "ASTRO-02",
            "emergency_contact_email": "chen@artemis.nasa.gov",
            "emergency_contact_phone": "MCC-CH-02",
            "emergency_contact_role": "Crew Medical Officer",
            "alert_timeout_seconds": 60,
        }
    ]

    for u in default_users:
        user_record = UserModel(
            username=u["username"],
            email=u["email"],
            hashed_password=hash_password(u["password"]),
            full_name=u["full_name"],
            callsign=u["callsign"],
            role=u["role"],
            emergency_contact_name=u["emergency_contact_name"],
            emergency_contact_callsign=u["emergency_contact_callsign"],
            emergency_contact_email=u["emergency_contact_email"],
            emergency_contact_phone=u["emergency_contact_phone"],
            emergency_contact_role=u["emergency_contact_role"],
            alert_timeout_seconds=u["alert_timeout_seconds"],
            is_active=True
        )
        db.add(user_record)
    db.commit()
