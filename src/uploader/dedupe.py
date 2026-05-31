from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from .models import UploadItem


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class DedupeStore:
    def __init__(self, db_path: str | Path, default_channel: str = "default"):
        self.db_path = Path(db_path)
        self.default_channel = default_channel
        if not self.db_path.is_absolute():
            self.db_path = Path.cwd() / self.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.init_schema()

    def init_schema(self) -> None:
        self.conn.executescript(
            """
            create table if not exists upload_seen (
              id integer primary key autoincrement,
              video_sha256 text not null,
              channel_key text not null default '',
              source_fingerprint text not null,
              video_path text not null,
              status text not null,
              youtube_video_id text,
              first_seen_at text not null default current_timestamp,
              last_seen_at text not null default current_timestamp
            );
            create index if not exists idx_upload_seen_fingerprint
              on upload_seen(source_fingerprint);
            """
        )
        self.ensure_channel_schema()
        self.conn.commit()

    def ensure_channel_schema(self) -> None:
        columns = [
            row["name"]
            for row in self.conn.execute("pragma table_info(upload_seen)").fetchall()
        ]
        if "channel_key" not in columns:
            self.conn.execute("alter table upload_seen add column channel_key text not null default ''")
        self.conn.execute("drop index if exists idx_upload_seen_hash")
        self.conn.execute(
            "update upload_seen set channel_key = ? where channel_key = ''",
            (self.default_channel,),
        )
        self.conn.execute(
            """
            create unique index if not exists idx_upload_seen_channel_hash
              on upload_seen(channel_key, video_sha256)
            """
        )

    def item_channel(self, item: UploadItem) -> str:
        return item.target_channel or self.default_channel

    def check(self, item: UploadItem, video_sha256: str) -> tuple[str, str]:
        channel_key = self.item_channel(item)
        by_hash = self.conn.execute(
            "select * from upload_seen where channel_key = ? and video_sha256 = ?",
            (channel_key, video_sha256),
        ).fetchone()
        if by_hash:
            status = by_hash["status"]
            if status == "uploaded":
                return "duplicate", "같은 채널에 같은 영상 해시가 이미 업로드됨"
            return "seen", "같은 채널에 같은 영상 해시가 이미 후보로 등록됨"

        by_fp = self.conn.execute(
            "select * from upload_seen where channel_key = ? and source_fingerprint = ? limit 1",
            (channel_key, item.source_fingerprint()),
        ).fetchone()
        if by_fp:
            return "possible_rerender", "같은 채널에 같은 소스 지문이 이미 존재함"
        return "new", "새 업로드 후보"

    def record_seen(self, item: UploadItem, video_sha256: str, status: str = "candidate") -> None:
        channel_key = self.item_channel(item)
        self.conn.execute(
            """
            insert into upload_seen(video_sha256, channel_key, source_fingerprint, video_path, status)
            values (?, ?, ?, ?, ?)
            on conflict(channel_key, video_sha256) do update set
              last_seen_at = current_timestamp,
              video_path = excluded.video_path
            """,
            (video_sha256, channel_key, item.source_fingerprint(), item.video_path, status),
        )
        self.conn.commit()

    def mark_uploaded(self, item: UploadItem, video_sha256: str, youtube_video_id: str) -> None:
        channel_key = self.item_channel(item)
        self.conn.execute(
            """
            insert into upload_seen(video_sha256, channel_key, source_fingerprint, video_path, status, youtube_video_id)
            values (?, ?, ?, ?, 'uploaded', ?)
            on conflict(channel_key, video_sha256) do update set
              last_seen_at = current_timestamp,
              video_path = excluded.video_path,
              status = 'uploaded',
              youtube_video_id = excluded.youtube_video_id
            """,
            (video_sha256, channel_key, item.source_fingerprint(), item.video_path, youtube_video_id),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
