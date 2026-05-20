from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .models import AllowedUrlFlow, SourceVideoImport

SUPPORTED_PLATFORMS = {"youtube", "tiktok", "douyin", "threads"}
ALLOWED_EXTRACTOR_PERMISSION_STATES = {"user_owned", "licensed", "platform_export"}
PROCESSABLE_IMPORT_PERMISSION_STATES = ALLOWED_EXTRACTOR_PERMISSION_STATES | {"approved_test_fixture"}
REQUIRED_HANDOFF_FIELDS = {
    "platform",
    "original_url",
    "local_path",
    "permission_state",
    "acquisition_method",
}


def detect_platform(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    if host in {"youtu.be", "youtube.com", "m.youtube.com", "music.youtube.com"} or host.endswith(".youtube.com"):
        return "youtube"
    if host in {"tiktok.com", "vm.tiktok.com", "vt.tiktok.com"} or host.endswith(".tiktok.com"):
        return "tiktok"
    if host in {"douyin.com", "iesdouyin.com", "v.douyin.com"} or host.endswith(".douyin.com"):
        return "douyin"
    if host in {"threads.net", "threads.com"} or host.endswith(".threads.net") or host.endswith(".threads.com"):
        return "threads"
    return "unsupported"


def inspect_allowed_url(url: str, permission_state: str = "needs_review") -> AllowedUrlFlow:
    platform = detect_platform(url)
    if platform == "unsupported":
        return AllowedUrlFlow(
            platform=platform,
            original_url=url,
            canonical_url=None,
            title=None,
            thumbnail_url=None,
            duration_sec=None,
            capabilities=["blocked"],
            permission_state="blocked",
            next_action="block",
            source_notes=["Unsupported URL. Upload a local file if you have rights to process it."],
        )

    capabilities = ["metadata", "upload_required"]
    next_action = "request_upload"
    source_notes = [
        "Metadata and embed checks should run before any binary import.",
        "Direct extraction is disabled unless the extractor feature flag and permission gate are both enabled.",
    ]

    if platform in {"youtube", "threads"}:
        capabilities.append("embed")
    if platform in {"tiktok", "douyin"}:
        capabilities.append("authorized_user_export")

    if permission_state in ALLOWED_EXTRACTOR_PERMISSION_STATES:
        capabilities.append("authorized_binary_import")
        next_action = "import_media"

    return AllowedUrlFlow(
        platform=platform,
        original_url=url,
        canonical_url=url,
        title=None,
        thumbnail_url=None,
        duration_sec=None,
        capabilities=capabilities,
        permission_state=permission_state,
        next_action=next_action,
        source_notes=source_notes,
    )


def require_extractor_permission(flow: AllowedUrlFlow, extractor_enabled: bool) -> None:
    if flow.platform not in SUPPORTED_PLATFORMS:
        raise PermissionError("Unsupported platform. Upload a local file instead.")
    if not extractor_enabled:
        raise PermissionError("Extractor is disabled. Pass the explicit extractor flag after permission review.")
    if flow.permission_state not in ALLOWED_EXTRACTOR_PERMISSION_STATES:
        allowed = ", ".join(sorted(ALLOWED_EXTRACTOR_PERMISSION_STATES))
        raise PermissionError(f"Permission state must be one of: {allowed}.")


def extract_with_ytdlp(
    url: str,
    output_dir: str | Path,
    permission_state: str,
    extractor_enabled: bool = False,
) -> SourceVideoImport:
    flow = inspect_allowed_url(url, permission_state=permission_state)
    require_extractor_permission(flow, extractor_enabled=extractor_enabled)

    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("yt-dlp is not installed. Install it only for the optional extractor connector.") from exc

    output_dir = Path(output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    extractor = "yt-dlp"

    with tempfile.TemporaryDirectory(prefix="ai-shorts-ingest-") as temp_name:
        temp_dir = Path(temp_name)
        ydl_opts: dict[str, Any] = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "outtmpl": str(temp_dir / "%(title).120B [%(id)s].%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "restrictfilenames": True,
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 20,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            metadata = ydl.extract_info(url, download=False)
            extractor = str(metadata.get("extractor") or metadata.get("extractor_key") or extractor)
            source_notes = list(flow.source_notes)
            source_notes.append(f"Extractor metadata checked with {extractor}.")
            flow = replace(
                flow,
                title=metadata.get("title"),
                thumbnail_url=metadata.get("thumbnail"),
                duration_sec=_duration_or_none(metadata.get("duration")),
                source_notes=source_notes,
            )
            ydl.download([url])

        downloaded_path = _find_downloaded_media(temp_dir)
        final_path = _dedupe_path(output_dir / downloaded_path.name)
        shutil.move(str(downloaded_path), final_path)

    return SourceVideoImport(
        source_path=str(final_path.resolve()),
        flow=flow,
        title=flow.title,
        duration_sec=flow.duration_sec,
        extractor=extractor,
    )


def flow_to_json(flow: AllowedUrlFlow) -> str:
    return json.dumps(flow.to_dict(), ensure_ascii=False, indent=2)


def import_to_json(source_import: SourceVideoImport) -> str:
    return json.dumps(source_import.to_dict(), ensure_ascii=False, indent=2)


def import_external_handoff(path: str | Path) -> SourceVideoImport:
    handoff_path = Path(path).expanduser()
    if handoff_path.is_dir():
        handoff_path = handoff_path / "source.json"
    if not handoff_path.exists():
        raise FileNotFoundError(f"Source handoff file not found: {handoff_path}")

    payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    missing = sorted(field for field in REQUIRED_HANDOFF_FIELDS if not payload.get(field))
    if missing:
        raise ValueError(f"Source handoff is missing required fields: {', '.join(missing)}")

    permission_state = str(payload["permission_state"])
    if permission_state not in PROCESSABLE_IMPORT_PERMISSION_STATES:
        allowed = ", ".join(sorted(PROCESSABLE_IMPORT_PERMISSION_STATES))
        raise PermissionError(f"Permission state must be one of: {allowed}.")

    platform = str(payload["platform"])
    if platform not in SUPPORTED_PLATFORMS:
        raise ValueError(f"Unsupported handoff platform: {platform}")

    source_path = Path(str(payload["local_path"])).expanduser()
    if not source_path.is_absolute():
        source_path = (handoff_path.parent / source_path).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Imported media file not found: {source_path}")

    source_notes = [str(item) for item in payload.get("source_notes", [])]
    warnings = [str(item) for item in payload.get("warnings", [])]
    if warnings:
        source_notes.extend(f"Warning: {warning}" for warning in warnings)
    source_notes.append(f"Imported through {payload['acquisition_method']}.")

    flow = AllowedUrlFlow(
        platform=platform,
        original_url=str(payload["original_url"]),
        canonical_url=payload.get("canonical_url") or payload.get("original_url"),
        title=payload.get("title"),
        thumbnail_url=payload.get("thumbnail_url") or payload.get("thumbnail_path"),
        duration_sec=_duration_or_none(payload.get("duration_sec")),
        capabilities=["metadata", "authorized_binary_import"],
        permission_state=permission_state,
        next_action="import_media",
        source_notes=source_notes,
    )
    return SourceVideoImport(
        source_path=str(source_path.resolve()),
        flow=flow,
        title=flow.title,
        duration_sec=flow.duration_sec,
        extractor=str(payload.get("connector_name") or payload.get("acquisition_method")),
    )


def _duration_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _find_downloaded_media(directory: Path) -> Path:
    candidates = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
    ]
    if not candidates:
        raise RuntimeError("yt-dlp finished but no media file was found.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _dedupe_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not create a unique output path for {path}.")
