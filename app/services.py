import datetime as dt
import json
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app import google_client
from app.config import settings
from app.models import ActivityLog, ParseAudit, User, UserGoogleToken, UserSheet
from app.schemas import CreateLogRequest, ParsedPayload
from app.security import decrypt_text, encrypt_text


def today_for_user(user: User) -> dt.date:
    return dt.datetime.now(ZoneInfo(user.timezone)).date()


def ensure_not_future(user: User, event_date: dt.date) -> None:
    if event_date > today_for_user(user):
        raise ValueError("FUTURE_DATE_NOT_ALLOWED")


def upsert_google_tokens(
    db: Session,
    user: User,
    access_token: str | None,
    refresh_token: str | None,
    expires_at: dt.datetime | None,
    scope: str | None,
) -> UserGoogleToken:
    row = db.get(UserGoogleToken, user.id)
    if not row:
        if not refresh_token:
            raise ValueError("refresh_token missing")
        row = UserGoogleToken(
            user_id=user.id,
            refresh_token_enc=encrypt_text(refresh_token),
            access_token_enc=encrypt_text(access_token) if access_token else None,
            token_expiry=expires_at,
            scope=scope,
        )
        db.add(row)
        db.flush()
        return row

    if refresh_token:
        row.refresh_token_enc = encrypt_text(refresh_token)
    if access_token:
        row.access_token_enc = encrypt_text(access_token)
    row.token_expiry = expires_at
    row.scope = scope
    db.add(row)
    db.flush()
    return row


async def get_google_access_token(db: Session, user: User) -> str:
    token_row = db.get(UserGoogleToken, user.id)
    if not token_row:
        raise ValueError("google token missing")

    # Prefer existing non-expired access token when available.
    if token_row.access_token_enc and token_row.token_expiry and token_row.token_expiry > dt.datetime.now(dt.timezone.utc):
        return decrypt_text(token_row.access_token_enc)

    refresh_token = decrypt_text(token_row.refresh_token_enc)
    refreshed = await google_client.refresh_access_token(refresh_token)
    access_token = refreshed["access_token"]
    expires_at = dt.datetime.fromisoformat(refreshed["expires_at"])
    upsert_google_tokens(
        db=db,
        user=user,
        access_token=access_token,
        refresh_token=None,
        expires_at=expires_at,
        scope=refreshed.get("scope"),
    )
    db.commit()
    return access_token


async def ensure_user_sheet(db: Session, user: User, access_token: str) -> tuple[UserSheet, bool]:
    sheet = db.get(UserSheet, user.id)
    if sheet:
        return sheet, False

    title = f"sel-flection-{user.email}"
    spreadsheet_id = await google_client.create_spreadsheet(access_token, title=title)
    sheet = UserSheet(user_id=user.id, spreadsheet_id=spreadsheet_id, sheet_name="logs")
    db.add(sheet)
    db.commit()
    db.refresh(sheet)
    return sheet, True


def save_parse_audit(db: Session, user_id: str, source_text: str, parsed: ParsedPayload) -> None:
    audit = ParseAudit(
        user_id=user_id,
        input_text=source_text,
        output_json=json.dumps(parsed.model_dump(mode="json"), ensure_ascii=False),
        save_decision=parsed.save,
        reason=parsed.reason,
    )
    db.add(audit)
    db.commit()


def insert_activity_log(db: Session, user: User, payload: CreateLogRequest, ai_model: str) -> ActivityLog:
    ensure_not_future(user, payload.event_date)
    row = ActivityLog(
        user_id=user.id,
        source_text=payload.source_text,
        event_date=payload.event_date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        duration_min=payload.duration_min,
        activity=payload.activity,
        category=payload.category,
        mood=payload.mood,
        energy=payload.energy,
        confidence=payload.confidence,
        ai_model=ai_model,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


async def append_log_to_sheet(db: Session, user: User, log: ActivityLog) -> bool:
    if not settings.enable_google_sheets:
        return False
    try:
        access_token = await get_google_access_token(db, user)
        sheet = db.get(UserSheet, user.id)
        if not sheet:
            sheet, _ = await ensure_user_sheet(db, user, access_token)

        values = [
            log.created_at.isoformat() if log.created_at else "",
            log.event_date.isoformat(),
            log.start_time.isoformat() if log.start_time else "",
            log.end_time.isoformat() if log.end_time else "",
            str(log.duration_min or ""),
            log.category.value,
            log.activity,
            log.mood or "",
            str(log.energy or ""),
            log.source_text,
            str(float(log.confidence)),
        ]
        await google_client.append_log_row(access_token, sheet.spreadsheet_id, values)
        return True
    except Exception:
        return False
