from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class TranscriptSegment:
    start_sec: float
    end_sec: float
    text: str
    speaker: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AllowedUrlFlow:
    platform: str
    original_url: str
    canonical_url: str | None
    title: str | None
    thumbnail_url: str | None
    duration_sec: float | None
    capabilities: list[str]
    permission_state: str
    next_action: str
    source_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceVideoImport:
    source_path: str
    flow: AllowedUrlFlow
    title: str | None
    duration_sec: float | None
    extractor: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "flow": self.flow.to_dict(),
            "title": self.title,
            "duration_sec": self.duration_sec,
            "extractor": self.extractor,
        }


@dataclass(frozen=True)
class ClipCandidate:
    start_sec: float
    end_sec: float
    title: str
    reason: str
    hashtags: list[str]
    confidence: float
    score: float
    transcript: str
    hook_types: list[str]
    production_signals: dict[str, int] = field(default_factory=dict)
    edit_notes: list[str] = field(default_factory=list)
    review_warnings: list[str] = field(default_factory=list)

    @property
    def duration_sec(self) -> float:
        return round(self.end_sec - self.start_sec, 2)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["duration_sec"] = self.duration_sec
        return payload
