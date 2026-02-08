from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User, UserSheet
from app.schemas import MeResponse


router = APIRouter(prefix="/v1", tags=["me"])


@router.get("/me", response_model=MeResponse)
def me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sheet = db.get(UserSheet, current_user.id)
    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        timezone=current_user.timezone,
        spreadsheet_id=sheet.spreadsheet_id if sheet else None,
    )

