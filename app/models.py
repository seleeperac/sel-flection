import datetime as dt
import enum
import uuid

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LogCategory(str, enum.Enum):
    WORK = "WORK"
    LEARNING = "LEARNING"
    EXERCISE = "EXERCISE"
    REST = "REST"
    SOCIAL = "SOCIAL"
    OTHER = "OTHER"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    google_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Seoul")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    google_token: Mapped["UserGoogleToken"] = relationship(back_populates="user", uselist=False)
    sheet: Mapped["UserSheet"] = relationship(back_populates="user", uselist=False)
    logs: Mapped[list["ActivityLog"]] = relationship(back_populates="user")


class UserGoogleToken(Base):
    __tablename__ = "user_google_tokens"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    refresh_token_enc: Mapped[str] = mapped_column(Text)
    access_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="google_token")


class UserSheet(Base):
    __tablename__ = "user_sheets"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    spreadsheet_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    sheet_name: Mapped[str] = mapped_column(String(64), default="logs")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="sheet")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_text: Mapped[str] = mapped_column(Text)
    event_date: Mapped[dt.date] = mapped_column(Date, index=True)
    start_time: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    activity: Mapped[str] = mapped_column(Text)
    category: Mapped[LogCategory] = mapped_column(Enum(LogCategory), index=True)
    mood: Mapped[str | None] = mapped_column(String(64), nullable=True)
    energy: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3))
    ai_model: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="logs")


class ParseAudit(Base):
    __tablename__ = "parse_audit"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    input_text: Mapped[str] = mapped_column(Text)
    output_json: Mapped[str] = mapped_column(Text)
    save_decision: Mapped[bool] = mapped_column()
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

