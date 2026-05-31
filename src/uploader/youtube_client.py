from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import SeoMetadata, UploadItem


class YouTubeUploadError(RuntimeError):
    pass


def resolve_channel(config: dict, channel_key: str | None = None) -> tuple[str, dict[str, Any]]:
    channels = config.get("channels", {})
    key = channel_key or channels.get("default")
    items = channels.get("items", {})
    if key and key in items:
        channel = dict(items[key])
        channel.setdefault("credentials_json", config.get("auth", {}).get("credentials_json"))
        channel.setdefault("token_json", config.get("auth", {}).get("token_json"))
        channel.setdefault("scopes", config.get("auth", {}).get("scopes"))
        return str(key), channel
    if channel_key:
        raise YouTubeUploadError(f"알 수 없는 채널 키입니다: {channel_key}")
    auth = config.get("auth", {})
    return "default", {
        "title": "default",
        "channel_id": "",
        "credentials_json": auth.get("credentials_json"),
        "token_json": auth.get("token_json"),
        "scopes": auth.get("scopes"),
    }


def resolve_project_path(path: str | Path) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return Path(__file__).resolve().parents[2] / p


def build_youtube_service(
    config: dict,
    channel_key: str | None = None,
    allow_interactive: bool = False,
):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except Exception as exc:
        raise YouTubeUploadError(
            "Google API 패키지가 설치되어 있지 않습니다. `pip install -e .` 또는 의존성 설치가 필요합니다."
        ) from exc

    _, channel = resolve_channel(config, channel_key)
    scopes = list(channel.get("scopes") or ["https://www.googleapis.com/auth/youtube.upload"])
    token_path = resolve_project_path(channel.get("token_json", ""))
    credentials_path = resolve_project_path(channel.get("credentials_json", ""))
    if not credentials_path.exists():
        raise YouTubeUploadError(f"YouTube credentials.json을 찾을 수 없습니다: {credentials_path}")

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                if allow_interactive:
                    creds = None
                else:
                    raise
        if (not creds or not creds.valid) and allow_interactive:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), scopes)
            creds = flow.run_local_server(port=0, prompt="consent select_account")
        elif not creds or not creds.valid:
            raise YouTubeUploadError(f"YouTube 토큰이 없습니다. youtube-auth를 먼저 실행하세요: {token_path}")
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("youtube", "v3", credentials=creds)


def get_authenticated_channel(config: dict, channel_key: str | None = None) -> dict[str, Any]:
    youtube = build_youtube_service(config, channel_key=channel_key, allow_interactive=False)
    response = youtube.channels().list(part="snippet", mine=True).execute()
    items = response.get("items", [])
    if not items:
        raise YouTubeUploadError("인증된 YouTube 채널을 찾지 못했습니다.")
    channel = items[0]
    snippet = channel.get("snippet", {})
    return {
        "id": channel.get("id", ""),
        "title": snippet.get("title", ""),
        "customUrl": snippet.get("customUrl", ""),
    }


def upload_private_video(
    config: dict,
    item: UploadItem,
    seo: SeoMetadata,
    channel_key: str | None = None,
) -> dict[str, Any]:
    from googleapiclient.http import MediaFileUpload

    youtube = build_youtube_service(config, channel_key=channel_key or item.target_channel)
    upload_cfg = config.get("upload", {})
    policy = item.policy
    body = {
        "snippet": {
            "title": seo.title,
            "description": seo.description,
            "tags": seo.tags,
            "categoryId": str(seo.category_id or upload_cfg.get("default_category_id", "24")),
            "defaultLanguage": str(upload_cfg.get("default_language", "ko")),
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": bool(policy.self_declared_made_for_kids),
            "containsSyntheticMedia": bool(policy.contains_synthetic_media),
        },
    }
    media = MediaFileUpload(item.video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
        notifySubscribers=False,
    )
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"upload progress: {int(status.progress() * 100)}%")
    return response
