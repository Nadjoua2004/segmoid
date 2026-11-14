"""
Astronaut Authentication & Emergency Contact Configuration API
Allows astronauts to register, choose their emergency contact, authenticate,
and manage intra-crew dead-man's switch alert timeout settings.
"""
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import UserModel
from app.schemas import (
    UserRegister,
    UserLogin,
    UserResponse,
    TokenResponse,
    UpdateEmergencyContactRequest
)
from app.services.auth_service import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    seed_default_users_if_empty
)
from app.services.data_loader import data_loader

router = APIRouter(prefix="/api/auth", tags=["Astronaut Authentication & Emergency Contact"])

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register_astronaut(
    payload: UserRegister,
    db: Session = Depends(get_db)
):
    """
    Register a new astronaut profile with mandatory designated emergency contact.
    In case of unacknowledged critical alarms, the alert automatically switches
    to this designated contact after the alert_timeout_seconds window expires.
    """
    # Check if username or email already exists
    existing_user = db.query(UserModel).filter(
        (UserModel.username == payload.username) | (UserModel.email == payload.email)
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email is already registered on this mission."
        )

    # Create new user record
    new_user = UserModel(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        callsign=payload.callsign,
        role=payload.role or "Astronaut",
        emergency_contact_name=payload.emergency_contact_name,
        emergency_contact_callsign=payload.emergency_contact_callsign,
        emergency_contact_email=payload.emergency_contact_email,
        emergency_contact_phone=payload.emergency_contact_phone,
        emergency_contact_role=payload.emergency_contact_role or "Crew Medical Officer",
        alert_timeout_seconds=payload.alert_timeout_seconds or 60,
        is_active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Generate JWT session token
    token = create_access_token(
        data={"sub": new_user.username, "callsign": new_user.callsign}
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(new_user)
    )

@router.post("/login", response_model=TokenResponse)
def login_astronaut(
    payload: UserLogin,
    db: Session = Depends(get_db)
):
    """
    Authenticate an astronaut and return JWT token along with their emergency contact settings.
    """
    # Seed default users if table is empty
    seed_default_users_if_empty(db)

    user = db.query(UserModel).filter(
        (UserModel.username == payload.username_or_email) |
        (UserModel.email == payload.username_or_email)
    ).first()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid flight credentials or callsign.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Astronaut profile is deactivated on mission roster."
        )

    token = create_access_token(
        data={"sub": user.username, "callsign": user.callsign}
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user)
    )

@router.get("/me", response_model=UserResponse)
def get_current_astronaut_profile(
    current_user: UserModel = Depends(get_current_user)
):
    """
    Get the authenticated astronaut's current profile, including chosen emergency contact
    and countdown timeout window.
    """
    return UserResponse.model_validate(current_user)

@router.put("/emergency-contact", response_model=UserResponse)
def update_emergency_contact(
    payload: UpdateEmergencyContactRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update the designated emergency contact who receives escalated critical alarms
    if the astronaut becomes unresponsive.
    """
    current_user.emergency_contact_name = payload.emergency_contact_name
    current_user.emergency_contact_callsign = payload.emergency_contact_callsign
    current_user.emergency_contact_email = payload.emergency_contact_email
    current_user.emergency_contact_phone = payload.emergency_contact_phone
    current_user.emergency_contact_role = payload.emergency_contact_role or "Crew Medical Officer"
    if payload.alert_timeout_seconds:
        current_user.alert_timeout_seconds = payload.alert_timeout_seconds

    db.commit()
    db.refresh(current_user)
    return UserResponse.model_validate(current_user)

@router.get("/crew-contacts")
def list_available_crew_contacts(db: Session = Depends(get_db)):
    """
    Returns available crew members who can be chosen as an Emergency Contact during sign-up or profile setup.
    """
    seed_default_users_if_empty(db)
    members = data_loader.get_crew_members()
    db_users = db.query(UserModel).filter(UserModel.is_active == True).all()

    contacts = []
    seen = set()

    # From DB users
    for u in db_users:
        if u.callsign not in seen:
            seen.add(u.callsign)
            contacts.append({
                "name": u.full_name,
                "callsign": u.callsign,
                "role": u.role,
                "email": u.email,
                "phone": u.emergency_contact_phone or f"HAB-COM-{u.callsign}"
            })

    # From static crew list
    for m in members:
        if m.get("id") not in seen:
            seen.add(m.get("id"))
            contacts.append({
                "name": m.get("name"),
                "callsign": m.get("id"),
                "role": "Crew Member",
                "email": f"{m.get('id').lower()}@artemis.nasa.gov",
                "phone": f"HAB-COM-{m.get('id')}"
            })

    return {"contacts": contacts, "count": len(contacts)}
