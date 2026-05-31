from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .adapters import scan_all
from .dedupe import DedupeStore, sha256_file
from .jsonio import write_json
from .models import CandidateReport
from .seo import build_seo
from .video_probe import probe_video


def build_report(
    config: dict,
    limit: int | None = None,
    record_seen: bool = True,
    target_date: str | None = None,
) -> dict[str, Any]:
    items = scan_all(config, limit=limit, target_date=target_date)
    db_path = config.get("dedupe", {}).get("database", "./data/upload_queue.sqlite3")
    default_channel = str(config.get("channels", {}).get("default") or "default")
    for item in items:
        if not item.target_channel:
            item.target_channel = default_channel
    store = DedupeStore(db_path, default_channel=default_channel)
    reports: list[CandidateReport] = []
    errors: list[dict[str, str]] = []

    try:
        for item in items:
            try:
                video_hash = sha256_file(item.video_path)
                duplicate_status, duplicate_reason = store.check(item, video_hash)
                video_probe = probe_video(item.video_path, config)
                seo = build_seo(item, config)
                upload_ready = (
                    video_probe.ok
                    and duplicate_status in {"new", "seen"}
                    and not item.policy.requires_review
                )
                report = CandidateReport(
                    item=item,
                    seo=seo,
                    video_probe=video_probe,
                    video_sha256=video_hash,
                    duplicate_status=duplicate_status,
                    duplicate_reason=duplicate_reason,
                    upload_ready=upload_ready,
                )
                reports.append(report)
                if record_seen and duplicate_status == "new":
                    store.record_seen(item, video_hash, "candidate")
            except Exception as exc:
                errors.append({"video_path": item.video_path, "error": str(exc)})
    finally:
        store.close()

    candidates = [report.to_dict() for report in reports]
    summary = summarize(candidates, errors)
    drive = drive_status(config, target_date)
    drive_candidates = [
        candidate
        for candidate in candidates
        if candidate.get("item", {}).get("adapter") == "google_drive_date"
    ]
    drive["candidates"] = len(drive_candidates)
    drive["downloaded_files"] = len(drive_candidates)
    return {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "candidates": candidates,
        "errors": errors,
        "auth": auth_status(config),
        "drive": drive,
        "channels": channels_status(config),
    }


def summarize(candidates: list[dict[str, Any]], errors: list[dict[str, str]]) -> dict[str, Any]:
    by_project: dict[str, int] = {}
    duplicate_counts: dict[str, int] = {}
    ready = 0
    review = 0
    video_fail = 0
    for candidate in candidates:
        item = candidate["item"]
        by_project[item["source_project"]] = by_project.get(item["source_project"], 0) + 1
        status = candidate["duplicate_status"]
        duplicate_counts[status] = duplicate_counts.get(status, 0) + 1
        if candidate["upload_ready"]:
            ready += 1
        if item["policy"]["requires_review"]:
            review += 1
        if not candidate["video_probe"]["ok"]:
            video_fail += 1
    return {
        "total": len(candidates),
        "ready": ready,
        "review": review,
        "videoFail": video_fail,
        "errors": len(errors),
        "byProject": by_project,
        "duplicates": duplicate_counts,
    }


def auth_status(config: dict) -> dict[str, Any]:
    auth = config.get("auth", {})
    drive_cfg = config.get("drive_ingest", {})
    credentials = Path(auth.get("credentials_json", ""))
    token = Path(auth.get("token_json", ""))
    drive_token = resolve_project_path(drive_cfg.get("drive_token_json", "./secrets/drive_token.json"))
    return {
        "credentialsJson": str(credentials),
        "credentialsExists": credentials.exists(),
        "tokenJson": str(token),
        "tokenExists": token.exists(),
        "driveTokenJson": str(drive_token),
        "driveTokenExists": drive_token.exists(),
        "mode": "connected_paths_only_beta_no_upload",
    }


def drive_status(config: dict, target_date: str | None = None) -> dict[str, Any]:
    try:
        from .drive_ingest import get_drive_status

        return get_drive_status(config, target_date=target_date).to_dict()
    except Exception as exc:
        drive_cfg = config.get("drive_ingest", {})
        return {
            "enabled": bool(drive_cfg.get("enabled")),
            "target_date": target_date or str(drive_cfg.get("target_date") or ""),
            "root_folder_id": str(drive_cfg.get("root_folder_id") or ""),
            "date_folder_found": False,
            "date_folder_id": "",
            "downloaded_files": 0,
            "candidates": 0,
            "error": str(exc),
        }


def channels_status(config: dict) -> dict[str, Any]:
    channels = config.get("channels", {})
    result = {
        "default": channels.get("default", ""),
        "items": {},
    }
    for key, channel in channels.get("items", {}).items():
        token = resolve_project_path(channel.get("token_json", ""))
        result["items"][key] = {
            "title": channel.get("title", ""),
            "channel_id": channel.get("channel_id", ""),
            "token_json": str(token),
            "token_exists": token.exists(),
        }
    return result


def resolve_project_path(path: str | Path) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return Path(__file__).resolve().parents[2] / p


def write_report_files(report: dict[str, Any], project_root: Path) -> None:
    data_dir = project_root / "data"
    web_dir = project_root / "web"
    write_json(data_dir / "mockup_report.json", report)
    web_dir.mkdir(parents=True, exist_ok=True)
    payload = "window.UPLOADER_REPORT = "
    payload += json_dumps_for_js(report)
    payload += ";\n"
    (web_dir / "report-data.js").write_text(payload, encoding="utf-8")


def json_dumps_for_js(data: Any) -> str:
    import json

    return json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/")
