from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from .models import ClipCandidate, TranscriptSegment
from .transcript import write_clip_srt


def ensure_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required. Install it first, then rerun rendering.")
    return ffmpeg


def render_candidates(
    video_path: str | Path,
    candidates: list[ClipCandidate],
    output_dir: str | Path,
    segments: list[TranscriptSegment] | None = None,
    layout: str = "crop",
    burn_subtitles: bool = False,
    limit: int | None = None,
) -> list[Path]:
    ffmpeg = ensure_ffmpeg()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[Path] = []
    for index, candidate in enumerate(candidates[: limit or len(candidates)], start=1):
        rendered.append(
            render_clip(
                ffmpeg,
                Path(video_path),
                candidate,
                output_dir,
                index,
                segments=segments,
                layout=layout,
                burn_subtitles=burn_subtitles,
            )
        )
    return rendered


def render_clip(
    ffmpeg: str,
    video_path: Path,
    candidate: ClipCandidate,
    output_dir: Path,
    index: int,
    segments: list[TranscriptSegment] | None,
    layout: str,
    burn_subtitles: bool,
) -> Path:
    output_path = output_dir / f"short_{index:02}_{safe_slug(candidate.title)}.mp4"
    filters = [layout_filter(layout)]

    if burn_subtitles and segments:
        srt_path = output_dir / f"short_{index:02}.srt"
        write_clip_srt(segments, srt_path, candidate.start_sec, candidate.end_sec)
        if ffmpeg_has_filter(ffmpeg, "subtitles"):
            filters.append(f"subtitles=filename={escape_filter_value(str(srt_path))}")
        else:
            print(
                f"Warning: this ffmpeg build has no subtitles filter; wrote sidecar SRT instead: {srt_path}",
                file=sys.stderr,
            )

    command = [
        ffmpeg,
        "-y",
        "-ss",
        f"{candidate.start_sec:.3f}",
        "-to",
        f"{candidate.end_sec:.3f}",
        "-i",
        str(video_path),
        "-vf",
        ",".join(filters),
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    subprocess.run(command, check=True)
    return output_path


def layout_filter(layout: str) -> str:
    if layout == "letterbox":
        return "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black"
    if layout == "crop":
        return "scale='if(gt(a,9/16),-2,1080)':'if(gt(a,9/16),1920,-2)',crop=1080:1920"
    raise ValueError("layout must be 'crop' or 'letterbox'")


def safe_slug(value: str) -> str:
    allowed = []
    for char in value.strip().lower().replace(" ", "_"):
        if char.isalnum() or char in {"_", "-"}:
            allowed.append(char)
    slug = "".join(allowed).strip("_")
    return slug[:48] or "clip"


def escape_filter_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    for char in ("'", ":", ",", "[", "]", " "):
        escaped = escaped.replace(char, f"\\{char}")
    return escaped


def ffmpeg_has_filter(ffmpeg: str, filter_name: str) -> bool:
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-filters"],
        check=True,
        capture_output=True,
        text=True,
    )
    return any(line.split()[1:2] == [filter_name] for line in result.stdout.splitlines())


def candidates_from_json(path: str | Path) -> list[ClipCandidate]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_clips = payload["clips"] if isinstance(payload, dict) else payload
    return [
        ClipCandidate(
            start_sec=float(item["start_sec"]),
            end_sec=float(item["end_sec"]),
            title=str(item["title"]),
            reason=str(item.get("reason", "")),
            hashtags=list(item.get("hashtags", [])),
            confidence=float(item.get("confidence", 0)),
            score=float(item.get("score", 0)),
            transcript=str(item.get("transcript", "")),
            hook_types=list(item.get("hook_types", [])),
            production_signals=dict(item.get("production_signals", {})),
            edit_notes=list(item.get("edit_notes", [])),
            review_warnings=list(item.get("review_warnings", [])),
        )
        for item in raw_clips
    ]
