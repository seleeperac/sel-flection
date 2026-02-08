import datetime as dt

import httpx

from app.config import settings


class GoogleApiError(RuntimeError):
    pass


async def exchange_oauth_code(code: str, redirect_uri: str) -> dict:
    payload = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(settings.google_oauth_token_url, data=payload)
    if resp.status_code >= 400:
        raise GoogleApiError(f"token exchange failed: {resp.text}")
    return resp.json()


async def refresh_access_token(refresh_token: str) -> dict:
    payload = {
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(settings.google_oauth_token_url, data=payload)
    if resp.status_code >= 400:
        raise GoogleApiError(f"token refresh failed: {resp.text}")
    body = resp.json()
    expires_in = int(body.get("expires_in", 3600))
    body["expires_at"] = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=expires_in)).isoformat()
    return body


async def fetch_userinfo(access_token: str) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(settings.google_userinfo_url, headers=headers)
    if resp.status_code >= 400:
        raise GoogleApiError(f"userinfo failed: {resp.text}")
    return resp.json()


async def create_spreadsheet(access_token: str, title: str) -> str:
    headers = {"Authorization": f"Bearer {access_token}"}
    body = {"properties": {"title": title}, "sheets": [{"properties": {"title": "logs"}}]}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post("https://sheets.googleapis.com/v4/spreadsheets", headers=headers, json=body)
    if resp.status_code >= 400:
        raise GoogleApiError(f"sheet create failed: {resp.text}")
    data = resp.json()
    spreadsheet_id = data["spreadsheetId"]
    await append_headers(access_token, spreadsheet_id)
    return spreadsheet_id


async def append_headers(access_token: str, spreadsheet_id: str) -> None:
    headers = {"Authorization": f"Bearer {access_token}"}
    body = {
        "values": [
            [
                "created_at",
                "event_date",
                "start_time",
                "end_time",
                "duration_min",
                "category",
                "activity",
                "mood",
                "energy",
                "source_text",
                "ai_confidence",
            ]
        ]
    }
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/"
        "logs!A1:K1:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS"
    )
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, headers=headers, json=body)
    if resp.status_code >= 400:
        raise GoogleApiError(f"header append failed: {resp.text}")


async def append_log_row(access_token: str, spreadsheet_id: str, values: list[str]) -> None:
    headers = {"Authorization": f"Bearer {access_token}"}
    body = {"values": [values]}
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/"
        "logs!A:K:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS"
    )
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, headers=headers, json=body)
    if resp.status_code >= 400:
        raise GoogleApiError(f"log append failed: {resp.text}")

