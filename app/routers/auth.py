import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.google_client import GoogleApiError, exchange_oauth_code, fetch_userinfo
from app.models import User
from app.schemas import (
    GoogleExchangeRequest,
    GoogleExchangeResponse,
    LocalLoginRequest,
    LocalLoginResponse,
    SheetOut,
    UserOut,
)
from app.security import create_access_token
from app.services import ensure_user_sheet, upsert_google_tokens


router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/local/login", response_model=LocalLoginResponse)
def local_login(payload: LocalLoginRequest, db: Session = Depends(get_db)):
    local_sub = f"local:{payload.email.strip().lower()}"
    user = db.scalar(select(User).where(User.google_sub == local_sub))
    if not user:
        user = User(
            google_sub=local_sub,
            email=payload.email.strip().lower(),
            name=payload.name,
            timezone=payload.timezone,
        )
    else:
        user.email = payload.email.strip().lower()
        user.name = payload.name or user.name
        user.timezone = payload.timezone or user.timezone

    db.add(user)
    db.commit()
    db.refresh(user)
    app_token = create_access_token(user.id)
    return LocalLoginResponse(
        access_token=app_token,
        user=UserOut(id=user.id, email=user.email, timezone=user.timezone),
    )


@router.post("/google/exchange", response_model=GoogleExchangeResponse)
async def google_exchange(payload: GoogleExchangeRequest, db: Session = Depends(get_db)):
    if settings.auth_mode != "google":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google auth disabled. Use /v1/auth/local/login.",
        )
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google credentials are not configured.",
        )
    try:
        token_data = await exchange_oauth_code(payload.code, payload.redirect_uri)
        access_token = token_data["access_token"]
        userinfo = await fetch_userinfo(access_token)
    except GoogleApiError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    google_sub = userinfo.get("sub")
    email = userinfo.get("email")
    if not google_sub or not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="google userinfo missing sub/email")

    user = db.scalar(select(User).where(User.google_sub == google_sub))
    if not user:
        user = User(
            google_sub=google_sub,
            email=email,
            name=userinfo.get("name"),
            timezone=payload.timezone,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.email = email
        user.name = userinfo.get("name")
        user.timezone = payload.timezone or user.timezone
        db.add(user)
        db.commit()
        db.refresh(user)

    expires_in = int(token_data.get("expires_in", 3600))
    expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=expires_in)
    try:
        upsert_google_tokens(
            db=db,
            user=user,
            access_token=access_token,
            refresh_token=token_data.get("refresh_token"),
            expires_at=expires_at,
            scope=token_data.get("scope"),
        )
        db.commit()
        sheet, created = await ensure_user_sheet(db, user, access_token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    app_token = create_access_token(user.id)
    return GoogleExchangeResponse(
        access_token=app_token,
        user=UserOut(id=user.id, email=user.email, timezone=user.timezone),
        sheet=SheetOut(spreadsheet_id=sheet.spreadsheet_id, created=created),
    )
