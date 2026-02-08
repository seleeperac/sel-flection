import datetime as dt
from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import ActivityLog, LogCategory, User
from app.schemas import MoodTrendItem, StatsCategoryItem, StatsResponse, TimeBucketItem, TopActivityItem


router = APIRouter(prefix="/v1/stats", tags=["stats"])


def _rows_for_range(db: Session, user_id: str, start: dt.date, end: dt.date) -> list[ActivityLog]:
    q = (
        select(ActivityLog)
        .where(ActivityLog.user_id == user_id)
        .where(ActivityLog.event_date >= start)
        .where(ActivityLog.event_date <= end)
        .order_by(ActivityLog.event_date.asc())
    )
    return db.scalars(q).all()


def _bucket_for_hour(hour: int) -> str:
    if hour < 6:
        return "00-06"
    if hour < 9:
        return "06-09"
    if hour < 12:
        return "09-12"
    if hour < 15:
        return "12-15"
    if hour < 18:
        return "15-18"
    if hour < 21:
        return "18-21"
    return "21-24"


def _build_stats(rows: list[ActivityLog], start: dt.date, end: dt.date) -> StatsResponse:
    cat_minutes: dict[LogCategory, int] = defaultdict(int)
    act_count: dict[str, int] = defaultdict(int)
    act_minutes: dict[str, int] = defaultdict(int)
    buckets: dict[str, int] = {
        "00-06": 0,
        "06-09": 0,
        "09-12": 0,
        "12-15": 0,
        "15-18": 0,
        "18-21": 0,
        "21-24": 0,
    }
    moods_per_day: dict[dt.date, list[int]] = defaultdict(list)

    for row in rows:
        minutes = int(row.duration_min or 0)
        cat_minutes[row.category] += minutes
        act_count[row.activity] += 1
        act_minutes[row.activity] += minutes

        if row.start_time:
            bucket = _bucket_for_hour(row.start_time.hour)
            buckets[bucket] += minutes

        if row.energy:
            moods_per_day[row.event_date].append(row.energy)

    by_category = [
        StatsCategoryItem(category=category, duration_min=duration)
        for category, duration in sorted(cat_minutes.items(), key=lambda x: x[1], reverse=True)
    ]

    top_activities = [
        TopActivityItem(activity=activity, count=act_count[activity], duration_min=act_minutes[activity])
        for activity in sorted(act_count.keys(), key=lambda k: (act_minutes[k], act_count[k]), reverse=True)[:5]
    ]

    time_pattern = [TimeBucketItem(bucket=bucket, duration_min=minutes) for bucket, minutes in buckets.items()]

    mood_trend: list[MoodTrendItem] = []
    cursor = start
    while cursor <= end:
        values = moods_per_day.get(cursor, [])
        mood_score = round(sum(values) / len(values), 2) if values else None
        mood_trend.append(MoodTrendItem(date=cursor, mood_score=mood_score))
        cursor += dt.timedelta(days=1)

    return StatsResponse(
        total_duration_min=sum(cat_minutes.values()),
        by_category=by_category,
        top_activities=top_activities,
        time_of_day_pattern=time_pattern,
        mood_trend=mood_trend,
    )


@router.get("/daily", response_model=StatsResponse)
def daily(
    date: dt.date = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = _rows_for_range(db, current_user.id, date, date)
    return _build_stats(rows, date, date)


@router.get("/weekly", response_model=StatsResponse)
def weekly(
    week_start: dt.date = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    end = week_start + dt.timedelta(days=6)
    rows = _rows_for_range(db, current_user.id, week_start, end)
    return _build_stats(rows, week_start, end)


@router.get("/monthly", response_model=StatsResponse)
def monthly(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    y, m = map(int, month.split("-"))
    start = dt.date(y, m, 1)
    if m == 12:
        end = dt.date(y + 1, 1, 1) - dt.timedelta(days=1)
    else:
        end = dt.date(y, m + 1, 1) - dt.timedelta(days=1)
    rows = _rows_for_range(db, current_user.id, start, end)
    return _build_stats(rows, start, end)

