"""
Astronaut Authentication & Crew Management API
Designed for Deep-Space Offline-First Habitats:
- Crew Lead creates the Crew and registers Station Information using username and key.
- Crew Lead provisions Crew Members (username + key).
- Astronauts authenticate using username and key.
- Strict Crew-Isolation: Alarms route only within the victim's crew.
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import UserModel
from app.schemas import (
    CrewLeadRegister,
    CrewMemberCreate,
    UserLogin,
    UserResponse,
    TokenResponse
)
from app.services.auth_service import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    seed_default_users_if_empty
)

router = APIRouter(prefix="/api/auth", tags=["Station Crew Management & Auth"])

@router.post("/register-lead", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register_crew_lead(
    payload: CrewLeadRegister,
    db: Session = Depends(get_db)
):
    """
    Crew Lead registers the Station and Crew using username and key.
    Enables the Lead Management tab to provision team members.
    """
    existing_user = db.query(UserModel).filter(UserModel.username == payload.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username is already registered on this station."
        )

    lead_user = UserModel(
        username=payload.username,
        email=f"{payload.username}@{payload.crew_name.lower()}.station.local",
        hashed_password=hash_password(payload.key),
        callsign=payload.username.upper(),
        crew_name=payload.crew_name.upper(),
        station_name=payload.station_name.upper(),
        is_lead=True,
        is_active=True
    )
    db.add(lead_user)
    db.commit()
    db.refresh(lead_user)

    token = create_access_token(
        data={
            "sub": lead_user.username,
            "crew_name": lead_user.crew_name,
            "station_name": lead_user.station_name,
            "is_lead": True
        }
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(lead_user)
    )

@router.post("/login", response_model=TokenResponse)
def login_astronaut(
    payload: UserLogin,
    db: Session = Depends(get_db)
):
    """
    Authenticate an astronaut using username and key.
    Runs locally on station edge node with zero internet lag.
    """
    seed_default_users_if_empty(db)

    user = db.query(UserModel).filter(UserModel.username == payload.username).first()
    if not user or not verify_password(payload.key, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid astronaut username or access key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Astronaut credentials inactive on station roster."
        )

    token = create_access_token(
        data={
            "sub": user.username,
            "crew_name": user.crew_name,
            "station_name": user.station_name,
            "is_lead": user.is_lead
        }
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user)
    )

@router.post("/crew/members", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_crew_member(
    payload: CrewMemberCreate,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Crew Lead provisions a new crew member for their crew and station.
    Only requires username and key.
    """
    if not current_user.is_lead:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the Crew Lead can provision new crew members."
        )

    existing = db.query(UserModel).filter(UserModel.username == payload.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Username '{payload.username}' is already in use."
        )

    member = UserModel(
        username=payload.username,
        email=f"{payload.username}@{current_user.crew_name.lower()}.station.local",
        hashed_password=hash_password(payload.key),
        callsign=payload.callsign or payload.username.upper(),
        crew_name=current_user.crew_name,
        station_name=current_user.station_name,
        is_lead=False,
        is_active=True
    )
    db.add(member)
    db.commit()
    db.refresh(member)

    return UserResponse.model_validate(member)

@router.get("/crew/members", response_model=List[UserResponse])
def list_crew_members(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Lists all crew members belonging to the authenticated astronaut's crew and station.
    """
    members = db.query(UserModel).filter(
        UserModel.crew_name == current_user.crew_name,
        UserModel.is_active == True
    ).all()
    return [UserResponse.model_validate(m) for m in members]

@router.get("/me", response_model=UserResponse)
def get_current_astronaut_profile(
    current_user: UserModel = Depends(get_current_user)
):
    """
    Get current logged in astronaut profile, crew, station, and lead status.
    """
    return UserResponse.model_validate(current_user)
