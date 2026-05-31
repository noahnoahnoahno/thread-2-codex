from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .image_metadata import metadata_from_image
from .metadata_templates import TEMPLATE_FILENAME, same_name_metadata_template
from .models import PolicyFlags, UploadItem


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v"}
METADATA_EXTENSIONS = {".json", ".txt"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class DriveIngestError(RuntimeError):
    pass


class DriveTokenMissing(DriveIngestError):
    pass


@dataclass
class DriveStatus:
    enabled: bool
    target_date: str
    root_folder_id: str
    date_folder_found: bool = False
    date_folder_id: str = ""
    downloaded_files: int = 0
    candidates: int = 0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_target_date(config: dict, target_date: str | None = None) -> str:
    drive_cfg = config.get("drive_ingest", {})
    explicit = target_date or drive_cfg.get("target_date")
    if explicit:
        return normalize_date(str(explicit))
    timezone = drive_cfg.get("timezone", "Asia/Seoul")
    fmt = drive_cfg.get("date_folder_format", "%Y%m%d")
    return datetime.now(ZoneInfo(timezone)).strftime(fmt)


def normalize_date(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) != 8:
        raise ValueError("Drive 날짜는 YYYYMMDD 형식이어야 합니다")
    return digits


def get_drive_status(config: dict, target_date: str | None = None) -> DriveStatus:
    drive_cfg = config.get("drive_ingest", {})
    date = resolve_target_date(config, target_date)
    status = DriveStatus(
        enabled=bool(drive_cfg.get("enabled")),
        target_date=date,
        root_folder_id=str(drive_cfg.get("root_folder_id") or ""),
    )
    if not status.enabled:
        return status
    try:
        service = build_drive_service(config, allow_interactive=False)
        folder = find_date_folder(service, status.root_folder_id, date)
        if folder:
            status.date_folder_found = True
            status.date_folder_id = folder["id"]
    except Exception as exc:
        status.error = str(exc)
    return status


def scan_drive_date_folder(config: dict, target_date: str | None = None) -> list[UploadItem]:
    drive_cfg = config.get("drive_ingest", {})
    if not drive_cfg.get("enabled"):
        return []
    date = resolve_target_date(config, target_date)
    service = build_drive_service(config, allow_interactive=False)
    root_folder_id = str(drive_cfg.get("root_folder_id") or "")
    if not root_folder_id:
        raise DriveIngestError("Drive root_folder_id가 비어 있습니다")
    date_folder = find_date_folder(service, root_folder_id, date)
    if not date_folder:
        return []

    max_depth = int(drive_cfg.get("query", {}).get("max_depth", 2))
    files = list_files_recursive(service, date_folder["id"], max_depth=max_depth)
    cache_root = resolve_project_path(drive_cfg.get("local_cache_dir", "./data/drive_cache"))
    date_cache = cache_root / date
    downloaded = download_drive_files(service, files, date_cache)
    return normalize_downloaded_date_folder(config, date, date_folder, downloaded)


def build_drive_service(config: dict, allow_interactive: bool = False):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except Exception as exc:
        raise DriveIngestError(
            "Google Drive 패키지가 설치되어 있지 않습니다. `pip install -e .` 또는 pyproject 의존성을 설치하세요."
        ) from exc

    drive_cfg = config.get("drive_ingest", {})
    scopes = list(drive_cfg.get("drive_scopes") or ["https://www.googleapis.com/auth/drive.readonly"])
    token_path = resolve_project_path(drive_cfg.get("drive_token_json", "./secrets/drive_token.json"))
    credentials_path = resolve_project_path(drive_cfg.get("drive_credentials_json", ""))
    if not credentials_path.exists():
        raise DriveIngestError(f"Drive credentials.json을 찾을 수 없습니다: {credentials_path}")

    creds = None
    if token_path.exists():
        token_data = json.loads(token_path.read_text(encoding="utf-8"))
        granted_scopes = set(token_data.get("scopes") or [])
        scope_missing = bool(granted_scopes and not set(scopes).issubset(granted_scopes))
        if scope_missing:
            if allow_interactive:
                creds = None
            else:
                raise DriveTokenMissing(
                    f"Drive 토큰 권한이 부족합니다. `python3 -m uploader.cli drive-auth --config config.yaml`로 다시 인증하세요: {token_path}"
                )
        else:
            creds = Credentials.from_authorized_user_file(str(token_path), scopes)
        if creds and not creds.has_scopes(scopes):
            if allow_interactive:
                creds = None
            else:
                raise DriveTokenMissing(
                    f"Drive 토큰 권한이 부족합니다. `python3 -m uploader.cli drive-auth --config config.yaml`로 다시 인증하세요: {token_path}"
                )

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
            token_path.parent.mkdir(parents=True, exist_ok=True)
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), scopes)
            creds = flow.run_local_server(port=0)
        elif not creds or not creds.valid:
            raise DriveTokenMissing(
                f"Drive 토큰이 없습니다. 먼저 `python3 -m uploader.cli drive-auth --config config.yaml`을 실행하세요: {token_path}"
            )
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("drive", "v3", credentials=creds)


def setup_drive_upload_folders(config: dict, target_date: str | None = None) -> dict[str, Any]:
    service = build_drive_service(config, allow_interactive=False)
    drive_cfg = config.get("drive_ingest", {})
    root_folder_id = str(drive_cfg.get("root_folder_id") or "")
    if not root_folder_id:
        raise DriveIngestError("Drive root_folder_id가 비어 있습니다")
    date = resolve_target_date(config, target_date)
    date_folder = ensure_drive_folder(service, root_folder_id, date)
    channel_keys = list(config.get("drive_folder_setup", {}).get("channels") or [])
    if not channel_keys:
        channel_keys = list(config.get("channels", {}).get("items", {}).keys())
    channel_results = []
    for channel_key in channel_keys:
        channel = config.get("channels", {}).get("items", {}).get(channel_key)
        if not channel:
            channel_results.append(
                {
                    "channel_key": channel_key,
                    "error": "config에 없는 채널 키",
                }
            )
            continue
        folder_name = channel_folder_name(channel_key, channel)
        folder = ensure_drive_folder(service, date_folder["id"], folder_name)
        channel_results.append(
            {
                "channel_key": channel_key,
                "folder_name": folder_name,
                "folder_id": folder["id"],
                "webViewLink": folder.get("webViewLink", ""),
                "created": bool(folder.get("_created")),
            }
        )
    return {
        "date": date,
        "root_folder_id": root_folder_id,
        "date_folder": {
            "id": date_folder["id"],
            "name": date_folder["name"],
            "webViewLink": date_folder.get("webViewLink", ""),
            "created": bool(date_folder.get("_created")),
        },
        "channels": channel_results,
    }


def channel_folder_name(channel_key: str, channel: dict[str, Any]) -> str:
    names = [str(name).strip() for name in channel.get("folder_names", []) if str(name).strip()]
    if names:
        return names[0]
    title = str(channel.get("title") or "").strip()
    return title or channel_key


def write_drive_metadata_templates(config: dict, target_date: str | None = None) -> dict[str, Any]:
    service = build_drive_service(config, allow_interactive=False)
    folder_result = setup_drive_upload_folders(config, target_date=target_date)
    written = []
    for channel_result in folder_result.get("channels", []):
        if channel_result.get("error"):
            written.append(channel_result)
            continue
        channel_key = str(channel_result.get("channel_key") or "")
        channel = config.get("channels", {}).get("items", {}).get(channel_key, {})
        payload = same_name_metadata_template(
            channel_key=channel_key,
            channel_title=str(channel.get("title") or ""),
            date=str(folder_result.get("date") or ""),
        )
        uploaded = upsert_drive_json_file(
            service,
            str(channel_result["folder_id"]),
            TEMPLATE_FILENAME,
            payload,
        )
        written.append(
            {
                "channel_key": channel_key,
                "folder_name": channel_result.get("folder_name", ""),
                "template_name": TEMPLATE_FILENAME,
                "file_id": uploaded.get("id", ""),
                "webViewLink": uploaded.get("webViewLink", ""),
                "updated": bool(uploaded.get("_updated")),
                "created": bool(uploaded.get("_created")),
            }
        )
    return {
        "date": folder_result.get("date"),
        "template_name": TEMPLATE_FILENAME,
        "channels": written,
    }


def upsert_drive_json_file(service, parent_id: str, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    from googleapiclient.http import MediaIoBaseUpload

    body_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    media = MediaIoBaseUpload(io.BytesIO(body_bytes), mimetype="application/json", resumable=False)
    existing = find_child_file(service, parent_id, name)
    body = {"name": name, "mimeType": "application/json"}
    if existing:
        response = (
            service.files()
            .update(
                fileId=existing["id"],
                body=body,
                media_body=media,
                fields="id,name,mimeType,parents,webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )
        response["_updated"] = True
        return response
    response = (
        service.files()
        .create(
            body=dict(body, parents=[parent_id]),
            media_body=media,
            fields="id,name,mimeType,parents,webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )
    response["_created"] = True
    return response


def ensure_drive_folder(service, parent_id: str, name: str) -> dict[str, Any]:
    existing = find_child_folder(service, parent_id, name)
    if existing:
        existing["_created"] = False
        return existing
    body = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = (
        service.files()
        .create(
            body=body,
            fields="id,name,mimeType,parents,webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )
    folder["_created"] = True
    return folder


def find_child_folder(service, parent_id: str, name: str) -> dict[str, Any] | None:
    query = (
        f"'{escape_query(parent_id)}' in parents "
        f"and name = '{escape_query(name)}' "
        "and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    response = (
        service.files()
        .list(
            q=query,
            fields="files(id,name,mimeType,parents,webViewLink)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=10,
        )
        .execute()
    )
    files = response.get("files", [])
    return files[0] if files else None


def find_child_file(service, parent_id: str, name: str) -> dict[str, Any] | None:
    query = (
        f"'{escape_query(parent_id)}' in parents "
        f"and name = '{escape_query(name)}' "
        "and mimeType != 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    response = (
        service.files()
        .list(
            q=query,
            fields="files(id,name,mimeType,parents,webViewLink)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=10,
        )
        .execute()
    )
    files = response.get("files", [])
    return files[0] if files else None


def find_date_folder(service, root_folder_id: str, date: str) -> dict[str, Any] | None:
    query = (
        f"'{escape_query(root_folder_id)}' in parents "
        f"and name = '{escape_query(date)}' "
        "and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    response = (
        service.files()
        .list(
            q=query,
            fields="files(id,name,mimeType,modifiedTime,parents,webViewLink)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    files = response.get("files", [])
    return files[0] if files else None


def list_files_recursive(service, folder_id: str, max_depth: int = 2) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []

    def walk(parent_id: str, depth: int, folder_path: list[str]) -> None:
        query = f"'{escape_query(parent_id)}' in parents and trashed = false"
        response = (
            service.files()
            .list(
                q=query,
                fields="files(id,name,mimeType,size,md5Checksum,modifiedTime,parents,webViewLink)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageSize=1000,
            )
            .execute()
        )
        for file in response.get("files", []):
            mime = file.get("mimeType", "")
            if mime == "application/vnd.google-apps.folder":
                if depth < max_depth:
                    walk(file["id"], depth + 1, folder_path + [str(file.get("name") or "")])
            elif is_supported_drive_file(file):
                file["_folder_path"] = folder_path
                file["_folder_path_key"] = "/".join(folder_path)
                file["_channel_folder_name"] = folder_path[0] if folder_path else ""
                collected.append(file)

    walk(folder_id, 0, [])
    return collected


def download_drive_files(service, files: list[dict[str, Any]], cache_dir: Path) -> list[dict[str, Any]]:
    from googleapiclient.http import MediaIoBaseDownload

    cache_dir.mkdir(parents=True, exist_ok=True)
    downloaded = []
    for file in files:
        local_dir = cache_dir / safe_name(file["id"])
        local_dir.mkdir(parents=True, exist_ok=True)
        local_path = local_dir / safe_name(file["name"])
        if not local_path.exists() or local_path.stat().st_size == 0:
            if str(file.get("mimeType", "")).startswith("application/vnd.google-apps."):
                request = service.files().export_media(
                    fileId=file["id"],
                    mimeType="text/plain",
                )
            else:
                request = service.files().get_media(fileId=file["id"], supportsAllDrives=True)
            with local_path.open("wb") as handle:
                downloader = MediaIoBaseDownload(handle, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
        metadata_path = local_dir / "drive_file.json"
        metadata_path.write_text(json.dumps(file, ensure_ascii=False, indent=2), encoding="utf-8")
        downloaded.append({"drive": file, "local_path": str(local_path)})
    return downloaded


def normalize_downloaded_date_folder(
    config: dict,
    date: str,
    date_folder: dict[str, Any],
    downloaded: list[dict[str, Any]],
) -> list[UploadItem]:
    metadata = [entry for entry in downloaded if Path(entry["local_path"]).suffix.lower() in METADATA_EXTENSIONS]
    videos = [entry for entry in downloaded if Path(entry["local_path"]).suffix.lower() in VIDEO_EXTENSIONS]
    images = [entry for entry in downloaded if Path(entry["local_path"]).suffix.lower() in IMAGE_EXTENSIONS]
    metadata_by_folder = group_metadata_by_drive_folder(metadata)
    images_by_folder = group_images_by_drive_folder(images)
    upload_items = []
    for index, video in enumerate(videos, start=1):
        video_path = Path(video["local_path"])
        drive_file = video["drive"]
        local_meta = metadata_by_folder.get(str(drive_file.get("_folder_path_key") or ""), {})
        folder_channel = channel_key_from_folder(config, str(drive_file.get("_channel_folder_name") or ""))
        seed = metadata_seed_for_video(video_path, local_meta, index, config)
        if seed.get("metadata_source") == "filename_fallback":
            image_path = matching_image_for_video(video_path, images_by_folder.get(str(drive_file.get("_folder_path_key") or ""), {}))
            if image_path:
                seed = metadata_from_image(image_path, video_path.stem, config)
                write_generated_metadata(video_path, image_path, seed, config)
        target_channel = str(seed.get("channel") or folder_channel or "")
        channel_known = is_known_channel(config, target_channel) if target_channel else True
        upload_items.append(
            UploadItem(
                source_project=seed.get("project") or "google-drive-date-folder",
                source_root=f"drive://{date_folder.get('id')}",
                source_run_dir=f"drive://{date_folder.get('id')}/{date}",
                adapter="google_drive_date",
                video_path=str(video_path),
                clip_index=seed.get("clip_index") or index,
                source_url=str(drive_file.get("webViewLink") or ""),
                source_title=str(drive_file.get("name") or video_path.name),
                source_channel=str(drive_file.get("_folder_path_key") or ""),
                target_channel=target_channel,
                title_seed=str(seed.get("title") or video_path.stem),
                hook_seed=str(seed.get("hook") or seed.get("title") or ""),
                description_seed=str(seed.get("description") or ""),
                hashtags_seed=list(seed.get("hashtags") or []),
                tags_seed=list(seed.get("tags") or []),
                transcript=str(seed.get("transcript") or ""),
                duration_sec=seed.get("duration_sec"),
                public_signals={
                    "metadata_source": seed.get("metadata_source", ""),
                    "drive_file_id": drive_file.get("id", ""),
                    "drive_folder": drive_file.get("_folder_path_key", ""),
                },
                policy=PolicyFlags(
                    self_declared_made_for_kids=bool(seed.get("selfDeclaredMadeForKids", False)),
                    contains_synthetic_media=bool(seed.get("containsSyntheticMedia", False)),
                    has_paid_product_placement=bool(seed.get("hasPaidProductPlacement", False)),
                    requires_review=bool(seed.get("requires_review", True)) or not channel_known,
                    review_reason=(
                        f"알 수 없는 채널 폴더: {drive_file.get('_channel_folder_name')}"
                        if not channel_known
                        else str(seed.get("review_reason") or "Drive 날짜 폴더 입력 검토")
                    ),
                ),
            )
        )
    return upload_items


def group_metadata_by_drive_folder(metadata: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for entry in metadata:
        path = Path(entry["local_path"])
        folder_key = str(entry.get("drive", {}).get("_folder_path_key") or "")
        grouped.setdefault(folder_key, {})
        if path.suffix.lower() == ".json":
            try:
                grouped[folder_key][path.name] = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception:
                grouped[folder_key][path.name] = {}
        elif path.suffix.lower() == ".txt":
            grouped[folder_key][path.name] = path.read_text(encoding="utf-8", errors="ignore")
    return grouped


def group_images_by_drive_folder(images: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    grouped: dict[str, dict[str, str]] = {}
    for entry in images:
        path = Path(entry["local_path"])
        folder_key = str(entry.get("drive", {}).get("_folder_path_key") or "")
        grouped.setdefault(folder_key, {})
        grouped[folder_key][normalize_stem(path.stem)] = str(path)
    return grouped


def matching_image_for_video(video_path: Path, images: dict[str, str]) -> str:
    return images.get(normalize_stem(video_path.stem), "")


def write_generated_metadata(video_path: Path, image_path: str, seed: dict[str, Any], config: dict) -> None:
    suffix = config.get("metadata", {}).get("auto_from_image", {}).get("generated_suffix", ".generated.json")
    output_path = video_path.with_suffix("")
    output_file = output_path.parent / f"{output_path.name}{suffix}"
    payload = dict(seed)
    payload["source_image"] = image_path
    output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_stem(value: str) -> str:
    return re.sub(r"[\s._-]+", "", str(value or "").strip().lower())


def channel_key_from_folder(config: dict, folder_name: str) -> str:
    name = normalize_channel_name(folder_name)
    if not name:
        return str(config.get("channels", {}).get("default") or "")
    channels = config.get("channels", {}).get("items", {})
    for key, channel in channels.items():
        aliases = [key, channel.get("title", ""), *(channel.get("folder_names") or [])]
        for alias in aliases:
            if normalize_channel_name(str(alias)) == name:
                return str(key)
    return folder_name


def is_known_channel(config: dict, channel_key: str) -> bool:
    if not channel_key:
        return True
    return channel_key in config.get("channels", {}).get("items", {})


def normalize_channel_name(value: str) -> str:
    return re.sub(r"[\s'\"._-]+", "", str(value or "").strip().lower())


def metadata_seed_for_video(
    video_path: Path,
    metadata: dict[str, Any],
    index: int,
    config: dict | None = None,
) -> dict[str, Any]:
    upload_json = metadata.get("upload.json")
    if isinstance(upload_json, dict):
        for item in upload_json.get("items", []):
            if item.get("video") == video_path.name:
                return normalize_metadata_dict(
                    dict(item, project=upload_json.get("project"), clip_index=index),
                    index,
                    "upload_json",
                )
    sibling_json = metadata.get(video_path.with_suffix(".json").name)
    if isinstance(sibling_json, dict):
        return normalize_metadata_dict(sibling_json, index, "same_name_json")
    generated = cached_generated_metadata(video_path, config or {})
    if generated:
        return normalize_metadata_dict(generated, index, str(generated.get("metadata_source") or "generated_json"))
    title_txt = metadata.get("title.txt")
    hook_txt = metadata.get("hook.txt")
    desc_txt = metadata.get("description.txt")
    tag_txt = metadata.get("tag.txt")
    tags = []
    if isinstance(tag_txt, str):
        tags = [part.strip() for part in re.split(r"[,\n]", tag_txt) if part.strip()]
    return {
        "title": title_txt if isinstance(title_txt, str) else video_path.stem,
        "channel": metadata.get("channel.txt") if isinstance(metadata.get("channel.txt"), str) else "",
        "hook": hook_txt if isinstance(hook_txt, str) else "",
        "description": desc_txt if isinstance(desc_txt, str) else "",
        "tags": tags,
        "hashtags": [tag for tag in tags if tag.startswith("#")],
        "clip_index": index,
        "requires_review": True,
        "review_reason": "메타데이터 JSON 없음",
        "metadata_source": "filename_fallback",
    }


def cached_generated_metadata(video_path: Path, config: dict) -> dict[str, Any]:
    suffix = config.get("metadata", {}).get("auto_from_image", {}).get("generated_suffix", ".generated.json")
    output_path = video_path.with_suffix("")
    generated_path = output_path.parent / f"{output_path.name}{suffix}"
    if not generated_path.exists():
        return {}
    try:
        return json.loads(generated_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def normalize_metadata_dict(data: dict[str, Any], index: int, source: str) -> dict[str, Any]:
    seo = data.get("seo") if isinstance(data.get("seo"), dict) else {}
    description = first_metadata_value(data, seo, "description", "desc")
    if isinstance(description, dict):
        description = description.get("korean") or description.get("ko") or description.get("english")
    hook = first_metadata_value(data, seo, "hook", "hookLine", "hook_line", "reason")
    hook_lines = data.get("hook_lines") or data.get("hookLines")
    if not hook and isinstance(hook_lines, dict):
        korean_hooks = hook_lines.get("korean") or hook_lines.get("ko") or []
        english_hooks = hook_lines.get("english") or []
        if korean_hooks:
            hook = korean_hooks[0]
        elif english_hooks:
            hook = english_hooks[0]
    return {
        "project": first_metadata_value(data, seo, "project", "sourceProject") or "google-drive-date-folder",
        "channel": first_metadata_value(data, seo, "channel", "targetChannel", "target_channel"),
        "title": first_metadata_value(data, seo, "title"),
        "hook": hook,
        "description": description,
        "tags": metadata_list(first_metadata_value(data, seo, "tags", "seo_tags", "seoTags", "keywords")),
        "hashtags": normalize_metadata_hashtags(metadata_list(first_metadata_value(data, seo, "hashtags", "hashTags"))),
        "transcript": first_metadata_value(data, seo, "transcript", "source_text", "sourceText") or "",
        "duration_sec": first_metadata_value(data, seo, "durationSec", "duration_sec"),
        "clip_index": first_metadata_value(data, seo, "clipIndex", "clip_number", "clip_index") or index,
        "requires_review": bool(first_metadata_value(data, seo, "requires_review", "requiresReview", default=False)),
        "review_reason": first_metadata_value(data, seo, "review_reason", "reviewReason") or "",
        "selfDeclaredMadeForKids": bool(first_metadata_value(data, seo, "selfDeclaredMadeForKids", "madeForKids", default=False)),
        "containsSyntheticMedia": bool(first_metadata_value(data, seo, "containsSyntheticMedia", default=False)),
        "hasPaidProductPlacement": bool(first_metadata_value(data, seo, "hasPaidProductPlacement", default=False)),
        "metadata_source": source,
    }


def first_metadata_value(primary: dict[str, Any], secondary: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for source in [primary, secondary]:
        if not isinstance(source, dict):
            continue
        for key in keys:
            if key in source and source[key] not in (None, ""):
                return source[key]
    return default


def metadata_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[,\n]", value) if part.strip()]
    return []


def normalize_metadata_hashtags(values: list[str]) -> list[str]:
    hashtags = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        hashtags.append(text if text.startswith("#") else f"#{text}")
    return hashtags


def is_supported_drive_file(file: dict[str, Any]) -> bool:
    name = str(file.get("name") or "")
    suffix = Path(name).suffix.lower()
    mime = str(file.get("mimeType") or "")
    return (
        suffix in VIDEO_EXTENSIONS | METADATA_EXTENSIONS | IMAGE_EXTENSIONS
        or mime.startswith("video/")
        or mime.startswith("image/")
    )


def resolve_project_path(path: str | Path) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return Path(__file__).resolve().parents[2] / p


def escape_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9가-힣._ -]+", "_", value).strip() or "file"
