from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .dedupe import DedupeStore
from .drive_ingest import setup_drive_upload_folders
from .jsonio import write_json
from .models import PolicyFlags, SeoMetadata, UploadItem
from .report import build_report, write_report_files
from .youtube_client import resolve_project_path, upload_private_video


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_upload_trigger(
    config: dict,
    *,
    target_date: str | None = None,
    execute: bool = False,
    allow_review: bool = False,
    limit: int | None = None,
    channel_filter: set[str] | None = None,
) -> dict[str, Any]:
    folder_result = setup_drive_upload_folders(config, target_date=target_date)
    scan_limit = limit or int(config.get("trigger", {}).get("scan_limit", 500))
    report = build_report(config, limit=scan_limit, record_seen=False, target_date=target_date)
    write_report_files(report, PROJECT_ROOT)

    candidates = [
        candidate
        for candidate in report.get("candidates", [])
        if candidate.get("item", {}).get("adapter") == "google_drive_date"
    ]
    if channel_filter:
        candidates = [
            candidate
            for candidate in candidates
            if str(candidate.get("item", {}).get("target_channel") or "") in channel_filter
        ]

    db_path = resolve_project_path(config.get("dedupe", {}).get("database", "./data/upload_queue.sqlite3"))
    default_channel = str(config.get("channels", {}).get("default") or "default")
    store = DedupeStore(db_path, default_channel=default_channel)
    uploaded: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    try:
        for index, candidate in enumerate(candidates, start=1):
            reason = skip_reason(candidate, config, allow_review=allow_review)
            channel_key = str(candidate.get("item", {}).get("target_channel") or "")
            title = str(candidate.get("seo", {}).get("title") or candidate.get("item", {}).get("title_seed") or "")
            if reason:
                skipped.append(
                    {
                        "index": index,
                        "channel_key": channel_key,
                        "title": title,
                        "reason": reason,
                    }
                )
                continue

            item, seo = candidate_to_objects(candidate)
            if not execute:
                skipped.append(
                    {
                        "index": index,
                        "channel_key": channel_key,
                        "title": title,
                        "reason": "dry_run",
                    }
                )
                continue

            try:
                response = upload_private_video(config, item, seo, channel_key=channel_key)
                video_id = response["id"]
                store.mark_uploaded(item, candidate["video_sha256"], video_id)
                upload_result = {
                    "youtube_video_id": video_id,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "privacyStatus": "private",
                    "title": seo.title,
                    "channel_key": channel_key,
                    "channel_id": response.get("snippet", {}).get("channelId"),
                    "channel_title": response.get("snippet", {}).get("channelTitle"),
                    "source_video": item.video_path,
                    "response": response,
                }
                write_json(PROJECT_ROOT / "data" / f"upload_result_{video_id}.json", upload_result)
                uploaded.append(upload_result)
            except Exception as exc:
                failed.append(
                    {
                        "index": index,
                        "channel_key": channel_key,
                        "title": title,
                        "error": str(exc),
                    }
                )
    finally:
        store.close()

    result = {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "execute": execute,
        "allow_review": allow_review,
        "date": folder_result["date"],
        "folder_setup": folder_result,
        "candidate_count": len(candidates),
        "uploaded_count": len(uploaded),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "uploaded": uploaded,
        "skipped": skipped,
        "failed": failed,
        "report": str(PROJECT_ROOT / "data" / "mockup_report.json"),
    }
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    write_json(PROJECT_ROOT / "data" / f"trigger_upload_{stamp}.json", result)
    return result


def skip_reason(candidate: dict[str, Any], config: dict, *, allow_review: bool) -> str:
    item = candidate.get("item", {})
    channel_key = str(item.get("target_channel") or "")
    if not channel_key:
        return "target_channel 없음"
    channel = config.get("channels", {}).get("items", {}).get(channel_key)
    if not channel:
        return f"알 수 없는 채널 키: {channel_key}"
    token_path = resolve_project_path(channel.get("token_json", ""))
    if not token_path.exists():
        return f"YouTube 토큰 없음: {token_path}"
    probe = candidate.get("video_probe", {})
    if not probe.get("ok"):
        return f"영상 검증 실패: {probe.get('reason') or 'unknown'}"
    if str(candidate.get("duplicate_status") or "") not in {"new", "seen"}:
        return f"중복/재렌더 의심: {candidate.get('duplicate_status')} - {candidate.get('duplicate_reason')}"
    policy = item.get("policy", {})
    if policy.get("requires_review") and not allow_review:
        return f"검토 필요: {policy.get('review_reason') or 'review required'}"
    return ""


def candidate_to_objects(candidate: dict[str, Any]) -> tuple[UploadItem, SeoMetadata]:
    item_data = dict(candidate["item"])
    policy_data = dict(item_data.pop("policy"))
    item_data.pop("video_name", None)
    item_data.pop("source_fingerprint", None)
    item = UploadItem(**item_data, policy=PolicyFlags(**policy_data))
    seo = SeoMetadata(**candidate["seo"])
    return item, seo
