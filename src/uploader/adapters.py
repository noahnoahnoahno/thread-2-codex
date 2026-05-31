from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from .jsonio import read_json, read_text_if_exists
from .models import PolicyFlags, UploadItem


def scan_root(root: dict, limit: int | None = None) -> list[UploadItem]:
    path = Path(root["path"]).expanduser()
    adapter = root.get("adapter", "")
    if not path.exists():
        return []
    if adapter == "randers_manifest":
        items = list(scan_randers_clips(path))
    elif adapter == "movie_runs":
        items = list(scan_movie_runs(path))
    elif adapter == "longform_runs":
        items = list(scan_longform_runs(path))
    elif adapter == "upload_json":
        items = list(scan_upload_json(path))
    else:
        items = []
    if limit is not None:
        return items[:limit]
    return items


def scan_all(config: dict, limit: int | None = None, target_date: str | None = None) -> list[UploadItem]:
    items: list[UploadItem] = []
    if config.get("drive_ingest", {}).get("enabled"):
        try:
            from .drive_ingest import scan_drive_date_folder

            items.extend(scan_drive_date_folder(config, target_date=target_date))
        except Exception:
            # Report generation records Drive status separately. Local scanning
            # should continue even when Drive auth is not ready yet.
            pass
    roots = config.get("watch", {}).get("roots", [])
    for root in roots:
        remaining = None if limit is None else max(limit - len(items), 0)
        if remaining == 0:
            break
        items.extend(scan_root(root, remaining))
    return items


def scan_randers_clips(root: Path) -> Iterable[UploadItem]:
    for json_path in sorted(root.glob("*/*.json"), reverse=True):
        if json_path.name.startswith("upload-manifest"):
            continue
        try:
            data = read_json(json_path)
        except Exception:
            continue
        video_path = Path(data.get("videoPath") or json_path.with_suffix(".mp4"))
        if not video_path.exists():
            continue
        source_project = "longform to shorts"
        edit_config = str(data.get("editConfig") or "")
        transcript = find_longform_transcript(edit_config, data)
        policy = PolicyFlags(
            requires_review=bool(data.get("sourceUrl")),
            review_reason="원본 YouTube 기반 재가공 영상 검토 필요" if data.get("sourceUrl") else "베타 기본 검토",
        )
        yield UploadItem(
            source_project=source_project,
            source_root=str(root),
            source_run_dir=str(json_path.parent),
            adapter="randers_manifest",
            video_path=str(video_path),
            clip_index=to_int(data.get("clipIndex")),
            source_url=str(data.get("sourceUrl") or ""),
            source_title=str(data.get("sourceTitle") or ""),
            source_channel=str(data.get("sourceChannel") or ""),
            target_channel=str(data.get("channel") or data.get("targetChannel") or ""),
            title_seed=str(data.get("title") or ""),
            hook_seed=str(data.get("title") or ""),
            hashtags_seed=normalize_hashtags(data.get("hashtags") or []),
            transcript=transcript,
            start_sec=to_float(data.get("startSec")),
            end_sec=to_float(data.get("endSec")),
            duration_sec=to_float(data.get("durationSec")),
            policy=policy,
        )


def scan_movie_runs(root: Path) -> Iterable[UploadItem]:
    for run_dir in sorted([p for p in root.iterdir() if p.is_dir()], reverse=True):
        clips_path = run_dir / "clips.json"
        highlights_path = run_dir / "highlights.json"
        if not clips_path.exists():
            continue
        try:
            clips_data = read_json(clips_path)
            highlights = read_json(highlights_path) if highlights_path.exists() else {}
        except Exception:
            continue
        movie = highlights.get("metadata", {}).get("movie_identity") or highlights.get("movie") or {}
        source_title = " ".join(
            str(x)
            for x in [movie.get("title"), movie.get("year")]
            if x
        ).strip()
        for clip in clips_data.get("clips", []):
            clip_index = to_int(clip.get("clip_number"))
            if clip_index is None:
                continue
            video_path = run_dir / f"final_shorts_{clip_index}.mp4"
            if not video_path.exists():
                continue
            transcript = (
                clip.get("ko_transcript")
                or clip.get("display_transcript")
                or clip.get("transcript")
                or ""
            )
            yield UploadItem(
                source_project="movie to shorts",
                source_root=str(root.parent),
                source_run_dir=str(run_dir),
                adapter="movie_runs",
                video_path=str(video_path),
                clip_index=clip_index,
                source_title=source_title,
                target_channel=str(clip.get("channel") or clip.get("targetChannel") or ""),
                title_seed=str(clip.get("title") or ""),
                hook_seed=str(clip.get("reason") or clip.get("title") or ""),
                hashtags_seed=normalize_hashtags(clip.get("hashtags") or []),
                transcript=str(transcript),
                start_sec=to_float(clip.get("start_sec")),
                end_sec=to_float(clip.get("end_sec")),
                duration_sec=to_float(clip.get("duration_sec")),
                public_signals=clip.get("public_signals") or {},
                policy=PolicyFlags(
                    requires_review=True,
                    review_reason="영화/방송 소스는 공개 전 저작권 검토 필요",
                ),
            )


def scan_longform_runs(root: Path) -> Iterable[UploadItem]:
    # Longform render outputs are usually archived into randers-clips.
    # This adapter adds coverage for run folders that directly contain mp4 exports.
    for run_dir in sorted([p for p in root.iterdir() if p.is_dir()], reverse=True):
        candidates_path = run_dir / "candidates.json"
        if not candidates_path.exists():
            continue
        try:
            candidates = read_json(candidates_path).get("clips", [])
        except Exception:
            candidates = []
        for mp4_path in sorted(run_dir.glob("*.mp4")):
            if mp4_path.name == "input.mp4":
                continue
            index = parse_clip_index(mp4_path.name)
            clip = match_clip(candidates, index)
            yield UploadItem(
                source_project="longform to shorts",
                source_root=str(root.parent),
                source_run_dir=str(run_dir),
                adapter="longform_runs",
                video_path=str(mp4_path),
                clip_index=index,
                target_channel=str(clip.get("channel") or clip.get("targetChannel") or ""),
                title_seed=str(clip.get("title") or mp4_path.stem),
                hook_seed=str(clip.get("reason") or clip.get("title") or ""),
                hashtags_seed=normalize_hashtags(clip.get("hashtags") or []),
                transcript=str(clip.get("source_text") or ""),
                start_sec=to_float(clip.get("start_sec")),
                end_sec=to_float(clip.get("end_sec")),
                duration_sec=to_float(clip.get("duration_sec")),
                policy=PolicyFlags(
                    requires_review=True,
                    review_reason="롱폼 재가공 소스 검토 필요",
                ),
            )


def scan_upload_json(root: Path) -> Iterable[UploadItem]:
    for upload_json in sorted(root.glob("*/*/upload.json"), reverse=True):
        try:
            data = read_json(upload_json)
        except Exception:
            continue
        for index, entry in enumerate(data.get("items", []), start=1):
            video_path = Path(entry.get("video", ""))
            if not video_path.is_absolute():
                video_path = upload_json.parent / video_path
            if not video_path.exists():
                continue
            yield UploadItem(
                source_project=str(data.get("project") or upload_json.parent.parent.name),
                source_root=str(root),
                source_run_dir=str(upload_json.parent),
                adapter="upload_json",
                video_path=str(video_path),
                clip_index=index,
                target_channel=str(entry.get("channel") or ""),
                title_seed=str(entry.get("title") or ""),
                hook_seed=str(entry.get("hook") or ""),
                description_seed=str(entry.get("description") or ""),
                hashtags_seed=normalize_hashtags(entry.get("hashtags") or []),
                tags_seed=list(entry.get("tags") or []),
                policy=PolicyFlags(
                    self_declared_made_for_kids=bool(entry.get("selfDeclaredMadeForKids", False)),
                    contains_synthetic_media=bool(entry.get("containsSyntheticMedia", False)),
                    has_paid_product_placement=bool(entry.get("hasPaidProductPlacement", False)),
                    requires_review=False,
                    review_reason="manual upload.json",
                ),
            )


def find_longform_transcript(edit_config: str, data: dict) -> str:
    if edit_config:
        run_dir = infer_run_dir_from_edit_config(Path(edit_config))
        if run_dir:
            candidates = read_candidate_text(run_dir / "candidates.json", data.get("clipIndex"))
            if candidates:
                return candidates
            transcript = read_text_if_exists(run_dir / "transcript.txt", 4000)
            if transcript:
                return transcript
    return ""


def infer_run_dir_from_edit_config(path: Path) -> Path | None:
    parts = path.parts
    if "runs" not in parts:
        return None
    idx = parts.index("runs")
    if len(parts) <= idx + 1:
        return None
    return Path(*parts[: idx + 2])


def read_candidate_text(candidates_path: Path, clip_index: object) -> str:
    if not candidates_path.exists():
        return ""
    try:
        clips = read_json(candidates_path).get("clips", [])
    except Exception:
        return ""
    index = to_int(clip_index)
    clip = match_clip(clips, index)
    return str(clip.get("source_text") or "")


def match_clip(clips: list[dict], index: int | None) -> dict:
    if index is None:
        return clips[0] if clips else {}
    for clip in clips:
        if to_int(clip.get("index")) == index or to_int(clip.get("clipIndex")) == index:
            return clip
    if 1 <= index <= len(clips):
        return clips[index - 1]
    return clips[0] if clips else {}


def normalize_hashtags(values: list[str]) -> list[str]:
    tags = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        tags.append(text if text.startswith("#") else f"#{text}")
    return tags


def parse_clip_index(name: str) -> int | None:
    match = re.search(r"clip[-_](\d+)|final_shorts_(\d+)", name)
    if not match:
        return None
    return to_int(match.group(1) or match.group(2))


def to_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
