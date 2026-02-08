import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import LogCategory


class GoogleExchangeRequest(BaseModel):
    code: str
    redirect_uri: str
    timezone: str = "Asia/Seoul"


class LocalLoginRequest(BaseModel):
    email: str = Field(min_length=3)
    name: str | None = None
    timezone: str = "Asia/Seoul"


class UserOut(BaseModel):
    id: str
    email: str
    timezone: str


class SheetOut(BaseModel):
    spreadsheet_id: str
    created: bool


class GoogleExchangeResponse(BaseModel):
    access_token: str
    user: UserOut
    sheet: SheetOut


class LocalLoginResponse(BaseModel):
    access_token: str
    user: UserOut


class MeResponse(UserOut):
    spreadsheet_id: str | None = None


class ParseRequest(BaseModel):
    text: str = Field(min_length=1)
    client_now: dt.datetime | None = None
    timezone: str = "Asia/Seoul"


class ParsedPayload(BaseModel):
    save: bool
    reason: str | None = None
    event_date: dt.date
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    duration_min: int | None = None
    activity: str | None = None
    category: LogCategory | None = None
    mood: str | None = None
    energy: int | None = None
    confidence: float


class ParseResponse(BaseModel):
    save: bool
    reason: str | None
    parsed: ParsedPayload
    saved_log_id: str | None = None
    saved_to_sheet: bool | None = None


class CreateLogRequest(BaseModel):
    source_text: str
    event_date: dt.date
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    duration_min: int | None = None
    activity: str | None = None
    category: LogCategory | None = None
    mood: str | None = None
    energy: int | None = None
    confidence: float = Field(ge=0, le=1)


class CreateLogResponse(BaseModel):
    id: str
    saved_to_sheet: bool


class LogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_date: dt.date
    start_time: dt.time | None
    end_time: dt.time | None
    duration_min: int | None
    activity: str
    category: LogCategory
    mood: str | None
    energy: int | None
    confidence: float
    created_at: dt.datetime


class StatsCategoryItem(BaseModel):
    category: LogCategory
    duration_min: int


class TopActivityItem(BaseModel):
    activity: str
    count: int
    duration_min: int


class TimeBucketItem(BaseModel):
    bucket: Literal["00-06", "06-09", "09-12", "12-15", "15-18", "18-21", "21-24"]
    duration_min: int


class MoodTrendItem(BaseModel):
    date: dt.date
    mood_score: float | None


class StatsResponse(BaseModel):
    total_duration_min: int
    by_category: list[StatsCategoryItem]
    top_activities: list[TopActivityItem]
    time_of_day_pattern: list[TimeBucketItem]
    mood_trend: list[MoodTrendItem]
