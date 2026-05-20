from __future__ import annotations

import re
from pathlib import Path

from .models import TranscriptSegment


TIMESTAMP_RE = re.compile(
    r"(?P<h>\d{1,2}:)?(?P<m>\d{1,2}):(?P<s>\d{2})(?P<ms>[,.]\d{1,3})?"
)
BRACKET_LINE_RE = re.compile(r"^\[(?P<time>[^\]]+)\]\s*(?P<text>.*)$")


def parse_timestamp(value: str) -> float:
    match = TIMESTAMP_RE.search(value.strip())
    if not match:
        raise ValueError(f"Invalid timestamp: {value!r}")

    hours = int((match.group("h") or "0:").rstrip(":"))
    minutes = int(match.group("m"))
    seconds = int(match.group("s"))
    millis_text = match.group("ms")
    millis = float(f"0.{millis_text[1:] if millis_text else '0'}")
    return hours * 3600 + minutes * 60 + seconds + millis


def format_timestamp(seconds: float, separator: str = ",") -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    whole_seconds = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis == 1000:
        whole_seconds += 1
        millis = 0
    return f"{hours:02}:{minutes:02}:{whole_seconds:02}{separator}{millis:03}"


def load_transcript(path: str | Path) -> list[TranscriptSegment]:
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    suffix = path.suffix.lower()

    if suffix == ".srt":
        segments = parse_srt(text)
    elif suffix == ".vtt":
        segments = parse_vtt(text)
    else:
        segments = parse_bracket_transcript(text)

    if not segments:
        raise ValueError(f"No transcript segments found in {path}")
    return normalize_segments(segments)


def parse_srt(text: str) -> list[TranscriptSegment]:
    blocks = re.split(r"\n\s*\n", text.strip())
    segments: list[TranscriptSegment] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if re.fullmatch(r"\d+", lines[0]):
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        start_text, end_text = [part.strip() for part in lines[0].split("-->", 1)]
        caption = clean_caption_text(" ".join(lines[1:]))
        if caption:
            segments.append(
                TranscriptSegment(parse_timestamp(start_text), parse_timestamp(end_text), caption)
            )
    return segments


def parse_vtt(text: str) -> list[TranscriptSegment]:
    text = re.sub(r"^\s*WEBVTT.*?(?:\n\s*\n)", "", text, flags=re.DOTALL)
    return parse_srt(text)


def parse_bracket_transcript(text: str) -> list[TranscriptSegment]:
    raw_segments: list[tuple[float, str]] = []
    for line in text.splitlines():
        match = BRACKET_LINE_RE.match(line.strip())
        if not match:
            continue
        caption = clean_caption_text(match.group("text"))
        if caption:
            raw_segments.append((parse_timestamp(match.group("time")), caption))

    segments: list[TranscriptSegment] = []
    for index, (start, caption) in enumerate(raw_segments):
        next_start = raw_segments[index + 1][0] if index + 1 < len(raw_segments) else start + 3
        end = max(start + 0.8, next_start)
        segments.append(TranscriptSegment(start, end, caption))
    return segments


def clean_caption_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"^\s*(>>|-)\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_segments(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    normalized: list[TranscriptSegment] = []
    for segment in sorted(segments, key=lambda item: item.start_sec):
        text = clean_caption_text(segment.text)
        if not text:
            continue
        start = max(0.0, segment.start_sec)
        end = max(start + 0.5, segment.end_sec)
        normalized.append(TranscriptSegment(start, end, text, segment.speaker))
    return normalized


def write_clip_srt(
    segments: list[TranscriptSegment],
    output_path: str | Path,
    start_sec: float,
    end_sec: float,
) -> Path:
    output_path = Path(output_path)
    lines: list[str] = []
    clip_segments = [
        segment
        for segment in segments
        if segment.end_sec > start_sec and segment.start_sec < end_sec
    ]
    for index, segment in enumerate(clip_segments, start=1):
        start = max(0.0, segment.start_sec - start_sec)
        end = min(end_sec - start_sec, segment.end_sec - start_sec)
        lines.extend(
            [
                str(index),
                f"{format_timestamp(start)} --> {format_timestamp(end)}",
                segment.text,
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
