from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .models import VideoProbe


def probe_video(path: str | Path, config: dict) -> VideoProbe:
    video_path = Path(path)
    gate = config.get("video_gate", {})
    min_bytes = int(gate.get("min_file_bytes", 2048))
    max_duration = float(gate.get("max_duration_sec", 180))
    require_vertical = bool(gate.get("require_square_or_vertical", True))

    if not video_path.exists():
        return VideoProbe(ok=False, reason="영상 파일 없음")
    if video_path.stat().st_size < min_bytes:
        return VideoProbe(ok=False, reason="파일 크기가 너무 작음")
    if not shutil.which("ffprobe"):
        return VideoProbe(ok=True, reason="ffprobe 없음: 파일 존재만 확인")

    try:
        output = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,codec_name:format=duration",
                "-of",
                "json",
                str(video_path),
            ],
            text=True,
        )
        data = json.loads(output)
    except Exception as exc:
        return VideoProbe(ok=False, reason=f"ffprobe 실패: {exc}")

    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}
    width = to_int(stream.get("width"))
    height = to_int(stream.get("height"))
    duration = to_float(fmt.get("duration"))
    codec = str(stream.get("codec_name") or "")

    if duration and duration > max_duration:
        return VideoProbe(False, duration, width, height, codec, "Shorts 최대 길이 초과")
    if require_vertical and width and height and width > height:
        return VideoProbe(False, duration, width, height, codec, "세로/정사각형 비율이 아님")
    return VideoProbe(True, duration, width, height, codec, "Shorts 게이트 통과")


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

