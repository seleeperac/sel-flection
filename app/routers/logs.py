import datetime as dt
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_parser import parse_activity_text
from app.database import get_db
from app.dependencies import get_current_user
from app.models import ActivityLog, LogCategory, User
from app.schemas import CreateLogRequest, CreateLogResponse, LogItem, ParseRequest, ParseResponse
from app.services import append_log_to_sheet, insert_activity_log, save_parse_audit


router = APIRouter(prefix="/v1/logs", tags=["logs"])


def _normalize_parsed_fields(source_text: str, save: bool, parsed) -> None:
    if not save:
        return

    if not parsed.activity or not parsed.activity.strip():
        parsed.activity = source_text.strip()

    if parsed.category is None:
        parsed.category = LogCategory.OTHER


@router.post("/parse", response_model=ParseResponse)
async def parse_log(
    payload: ParseRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    parsed, ai_model = await parse_activity_text(payload.text, payload.timezone or current_user.timezone, payload.client_now)
    _normalize_parsed_fields(payload.text, parsed.save, parsed)

    today = dt.datetime.now(ZoneInfo(current_user.timezone)).date()
    if parsed.event_date > today:
        parsed.save = False
        parsed.reason = "FUTURE_DATE_NOT_ALLOWED"

    saved_log_id: str | None = None
    saved_to_sheet: bool | None = None
    if parsed.save:
        create_payload = CreateLogRequest(
            source_text=payload.text,
            event_date=parsed.event_date,
            start_time=parsed.start_time,
            end_time=parsed.end_time,
            duration_min=parsed.duration_min,
            activity=parsed.activity or payload.text,
            category=parsed.category or LogCategory.OTHER,
            mood=parsed.mood,
            energy=parsed.energy,
            confidence=parsed.confidence,
        )
        row = insert_activity_log(db, current_user, create_payload, ai_model=ai_model)
        saved_to_sheet = await append_log_to_sheet(db, current_user, row)
        saved_log_id = row.id

    save_parse_audit(db, current_user.id, payload.text, parsed)
    return ParseResponse(
        save=parsed.save,
        reason=parsed.reason,
        parsed=parsed,
        saved_log_id=saved_log_id,
        saved_to_sheet=saved_to_sheet,
    )


@router.post("", response_model=CreateLogResponse)
async def create_log(
    payload: CreateLogRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = dt.datetime.now(ZoneInfo(current_user.timezone)).date()
    if payload.event_date > today:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="FUTURE_DATE_NOT_ALLOWED")

    normalized_activity = (payload.activity or payload.source_text).strip()
    if not normalized_activity:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="ACTIVITY_REQUIRED")

    normalized_payload = payload.model_copy(
        update={
            "activity": normalized_activity,
            "category": payload.category or LogCategory.OTHER,
        }
    )

    row = insert_activity_log(db, current_user, normalized_payload, ai_model="manual-confirmed")
    saved_to_sheet = await append_log_to_sheet(db, current_user, row)
    return CreateLogResponse(id=row.id, saved_to_sheet=saved_to_sheet)


@router.get("", response_model=list[LogItem])
def list_logs(
    date_from: dt.date | None = Query(default=None),
    date_to: dt.date | None = Query(default=None),
    category: LogCategory | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = select(ActivityLog).where(ActivityLog.user_id == current_user.id)
    if date_from:
        q = q.where(ActivityLog.event_date >= date_from)
    if date_to:
        q = q.where(ActivityLog.event_date <= date_to)
    if category:
        q = q.where(ActivityLog.category == category)

    q = q.order_by(ActivityLog.event_date.desc(), ActivityLog.start_time.desc())
    rows = db.scalars(q).all()
    return [LogItem.model_validate(r) for r in rows]
