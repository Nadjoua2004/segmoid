"""
Daily Check-in API
Full astronaut daily self-report (ISS-style daily health sheet).

POST /api/checkins             create today's check-in (+ ML assessment, stored with the record)
GET  /api/checkins             list check-ins for an astronaut (newest first, paginated)
POST /api/checkins/classify    ML assessment of a check-in without saving it
GET  /api/checkins/classifier  deployed classifier version and test metrics
GET  /api/checkins/{id}        fetch one check-in
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.schemas import ClassifierInfo, DailyCheckInCreate, DailyCheckInRead, HealthAssessment
from app.services import checkin_classifier
from app.services.health_predictor_agent import run_agent_background_prediction
from app.services.checkin_service import (
    CheckInConflictError,
    create_checkin,
    get_checkin,
    list_checkins,
    to_read_model,
)

router = APIRouter(prefix="/api/checkins", tags=["Daily Check-ins"])


@router.post(
    "",
    response_model=DailyCheckInRead,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "A check-in already exists for this astronaut and mission day"}},
)
def create_daily_checkin(
    payload: DailyCheckInCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> DailyCheckInRead:
    """
    Submit a daily check-in. Vitals are also written to telemetry, so triage and the 7-day
    forecast pick them up immediately. The response includes rule-based lifestyle/environment flags.
    """
    try:
        row = create_checkin(db, payload)
        background_tasks.add_task(run_agent_background_prediction, payload.astronaut_id)
    except CheckInConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return to_read_model(row)


@router.get("", response_model=List[DailyCheckInRead])
def list_daily_checkins(
    astronaut_id: str = Query(settings.ASTRONAUT_ID, min_length=1, max_length=64),
    limit: int = Query(30, ge=1, le=365),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> List[DailyCheckInRead]:
    return [to_read_model(r) for r in list_checkins(db, astronaut_id, limit, offset)]


@router.post(
    "/classify",
    response_model=HealthAssessment,
    responses={503: {"description": "Classifier model not available"}},
)
def classify_daily_checkin(payload: DailyCheckInCreate) -> HealthAssessment:
    """Run the ML health classifier on a check-in WITHOUT saving it (preview / what-if)."""
    try:
        return checkin_classifier.assess(payload.model_dump(mode="json"))
    except checkin_classifier.ModelUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get(
    "/classifier",
    response_model=ClassifierInfo,
    responses={503: {"description": "Classifier model not available"}},
)
def get_classifier_info() -> ClassifierInfo:
    """Version, training date and test metrics of the deployed classifier."""
    try:
        return checkin_classifier.classifier_info()
    except checkin_classifier.ModelUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/{checkin_id}", response_model=DailyCheckInRead, responses={404: {"description": "Not found"}})
def get_daily_checkin(checkin_id: int, db: Session = Depends(get_db)) -> DailyCheckInRead:
    row = get_checkin(db, checkin_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Check-in {checkin_id} not found.")
    return to_read_model(row)
