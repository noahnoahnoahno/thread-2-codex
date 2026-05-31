from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PolicyFlags:
    self_declared_made_for_kids: bool = False
    contains_synthetic_media: bool = False
    has_paid_product_placement: bool = False
    requires_review: bool = True
    review_reason: str = "초기 베타 기본 검토"


@dataclass
class UploadItem:
    source_project: str
    source_root: str
    source_run_dir: str
    adapter: str
    video_path: str
    clip_index: int | None = None
    source_url: str = ""
    source_title: str = ""
    source_channel: str = ""
    target_channel: str = ""
    title_seed: str = ""
    hook_seed: str = ""
    description_seed: str = ""
    hashtags_seed: list[str] = field(default_factory=list)
    tags_seed: list[str] = field(default_factory=list)
    transcript: str = ""
    start_sec: float | None = None
    end_sec: float | None = None
    duration_sec: float | None = None
    public_signals: dict[str, Any] = field(default_factory=dict)
    policy: PolicyFlags = field(default_factory=PolicyFlags)

    @property
    def video_name(self) -> str:
        return Path(self.video_path).name

    def source_fingerprint(self) -> str:
        parts = [
            self.source_project,
            self.source_url or self.source_title,
            self.target_channel,
            str(self.clip_index or ""),
            str(self.start_sec or ""),
            str(self.end_sec or ""),
            self.video_name,
        ]
        return "|".join(parts)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["video_name"] = self.video_name
        data["source_fingerprint"] = self.source_fingerprint()
        return data


@dataclass
class VideoProbe:
    ok: bool
    duration_sec: float | None = None
    width: int | None = None
    height: int | None = None
    codec: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SeoMetadata:
    title: str
    description: str
    tags: list[str]
    hashtags: list[str]
    category_id: str = "24"
    rationale: str = ""
    risk_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CandidateReport:
    item: UploadItem
    seo: SeoMetadata
    video_probe: VideoProbe
    video_sha256: str
    duplicate_status: str
    duplicate_reason: str
    upload_ready: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "item": self.item.to_dict(),
            "seo": self.seo.to_dict(),
            "video_probe": self.video_probe.to_dict(),
            "video_sha256": self.video_sha256,
            "duplicate_status": self.duplicate_status,
            "duplicate_reason": self.duplicate_reason,
            "upload_ready": self.upload_ready,
        }
