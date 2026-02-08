import datetime as dt
import json
import re
from zoneinfo import ZoneInfo

import httpx

from app.config import settings
from app.models import LogCategory
from app.schemas import ParsedPayload


SYSTEM_PROMPT = """
You extract past activity logs from Korean user chat.
Goal: record what already happened, especially today.
Never create future plans as logs.

Return STRICT JSON only.
Schema:
{
  "save": boolean,
  "reason": string|null,
  "event_date": "YYYY-MM-DD",
  "start_time": "HH:MM"|null,
  "end_time": "HH:MM"|null,
  "duration_min": number|null,
  "activity": string|null,
  "category": "WORK"|"LEARNING"|"EXERCISE"|"REST"|"SOCIAL"|"OTHER"|null,
  "mood": string|null,
  "energy": 1|2|3|4|5|null,
  "confidence": number
}

Rules:
1) If statement is future plan/intent/todo, set save=false and reason="FUTURE_OR_PLAN".
2) If date omitted, assume user's today.
3) Infer duration from start/end when possible.
4) If key info missing but still likely past activity, save=true with null fields where unknown.
5) confidence range 0~1.
6) No extra keys. No markdown.
""".strip()


def _today_in_tz(timezone: str, client_now: dt.datetime | None) -> dt.date:
    if client_now:
        return client_now.astimezone(ZoneInfo(timezone)).date()
    return dt.datetime.now(ZoneInfo(timezone)).date()


def _is_future_or_plan(text: str) -> bool:
    future_patterns = [
        r"\ud560\s*\uac70\uc57c",
        r"\ud558\ub824\uace0",
        r"\uc608\uc815",
        r"\uacc4\ud68d",
        r"\ub0b4\uc77c",
        r"\ub2e4\uc74c\s*\uc8fc",
        r"\ub2e4\uc74c\s*\ub2ec",
        r"\ud560\uac8c",
        r"\ud574\uc57c\s*\ud574",
        r"to\s*do",
    ]
    return any(re.search(pat, text, flags=re.IGNORECASE) for pat in future_patterns)


def _extract_times(text: str) -> tuple[dt.time | None, dt.time | None]:
    matches = re.findall(r"(\d{1,2})\s*\uc2dc(?:\s*(\d{1,2})\s*\ubd84?)?", text)
    if not matches:
        return None, None
    times: list[dt.time] = []
    for hour, minute in matches[:2]:
        h = int(hour)
        m = int(minute) if minute else 0
        if 0 <= h <= 23 and 0 <= m <= 59:
            times.append(dt.time(h, m))
    if not times:
        return None, None
    return (times[0], times[1] if len(times) > 1 else None)


def _infer_category(text: str) -> LogCategory:
    keywords = {
        LogCategory.WORK: [
            "\ubcf4\uace0\uc11c",
            "\ud68c\uc758",
            "\uc5c5\ubb34",
            "\ucf54\ub529",
            "\uac1c\ubc1c",
            "work",
        ],
        LogCategory.LEARNING: [
            "\uacf5\ubd80",
            "\uac15\uc758",
            "\ub3c5\uc11c",
            "\ud559\uc2b5",
            "study",
        ],
        LogCategory.EXERCISE: [
            "\uc6b4\ub3d9",
            "\ud5ec\uc2a4",
            "\ub7ec\ub2dd",
            "\uc870\uae45",
            "\uc694\uac00",
            "exercise",
        ],
        LogCategory.REST: [
            "\ud734\uc2dd",
            "\ub0ae\uc7a0",
            "\uc270",
            "\uba4d\ub54c\ub9bc",
            "rest",
        ],
        LogCategory.SOCIAL: [
            "\uce5c\uad6c",
            "\uac00\uc871",
            "\ub9cc\ub0a8",
            "\uc2dd\uc0ac",
            "\ud1b5\ud654",
            "social",
        ],
    }
    lowered = text.lower()
    for category, words in keywords.items():
        if any(word.lower() in lowered for word in words):
            return category
    return LogCategory.OTHER


def _build_heuristic_payload(text: str, timezone: str, client_now: dt.datetime | None) -> ParsedPayload:
    today = _today_in_tz(timezone, client_now)
    if _is_future_or_plan(text):
        return ParsedPayload(
            save=False,
            reason="FUTURE_OR_PLAN",
            event_date=today,
            start_time=None,
            end_time=None,
            duration_min=None,
            activity=None,
            category=None,
            mood=None,
            energy=None,
            confidence=0.9,
        )

    start_time, end_time = _extract_times(text)
    duration = None
    if start_time and end_time:
        start_dt = dt.datetime.combine(today, start_time)
        end_dt = dt.datetime.combine(today, end_time)
        if end_dt >= start_dt:
            duration = int((end_dt - start_dt).total_seconds() // 60)

    mood = "\uc88b\uc74c" if ("\uc88b" in text or "good" in text.lower()) else None

    return ParsedPayload(
        save=True,
        reason=None,
        event_date=today,
        start_time=start_time,
        end_time=end_time,
        duration_min=duration,
        activity=text.strip(),
        category=_infer_category(text),
        mood=mood,
        energy=None,
        confidence=0.65,
    )


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json", "", 1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no json object found")
    return json.loads(text[start : end + 1])


async def _parse_with_gemini(text: str, timezone: str, client_now: dt.datetime | None) -> ParsedPayload:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY missing")

    now = client_now.isoformat() if client_now else dt.datetime.now(ZoneInfo(timezone)).isoformat()
    user_prompt = f"timezone={timezone}\nclient_now={now}\ntext={text}"
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
    )
    body = {
        "contents": [{"parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "generationConfig": {"temperature": 0.1, "topP": 0.8, "topK": 20},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=body)
    if resp.status_code >= 400:
        raise RuntimeError(f"gemini parse failed: {resp.text}")

    data = resp.json()
    text_out = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    parsed = _extract_json(text_out)
    return ParsedPayload.model_validate(parsed)


async def _parse_with_ollama(text: str, timezone: str, client_now: dt.datetime | None) -> ParsedPayload:
    now = client_now.isoformat() if client_now else dt.datetime.now(ZoneInfo(timezone)).isoformat()
    user_prompt = f"timezone={timezone}\nclient_now={now}\ntext={text}"
    body = {
        "model": settings.ollama_model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "options": {"temperature": 0.1},
    }
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=body)
    if resp.status_code >= 400:
        raise RuntimeError(f"ollama parse failed: {resp.text}")

    data = resp.json()
    content = data.get("message", {}).get("content", "")
    parsed = _extract_json(content)
    return ParsedPayload.model_validate(parsed)


async def parse_activity_text(text: str, timezone: str, client_now: dt.datetime | None) -> tuple[ParsedPayload, str]:
    if settings.ai_provider == "ollama":
        try:
            return await _parse_with_ollama(text, timezone, client_now), f"ollama:{settings.ollama_model}"
        except Exception:
            return _build_heuristic_payload(text, timezone, client_now), "heuristic-fallback"

    if settings.ai_provider == "gemini":
        try:
            return await _parse_with_gemini(text, timezone, client_now), settings.gemini_model
        except Exception:
            return _build_heuristic_payload(text, timezone, client_now), "heuristic-fallback"

    return _build_heuristic_payload(text, timezone, client_now), "heuristic"

