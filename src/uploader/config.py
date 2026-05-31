from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "watch": {
        "roots": [
            {
                "name": "randers_clips_archive",
                "path": "/Users/noahai/Desktop/randers-clips",
                "adapter": "randers_manifest",
            },
            {
                "name": "movie_to_shorts_runs",
                "path": "/Users/noahai/Desktop/movie to shorts codex/runs",
                "adapter": "movie_runs",
            },
        ]
    },
    "auth": {
        "credentials_json": "/Users/noahai/Desktop/Auto-Up Project/credentials.json",
        "token_json": "/Users/noahai/Desktop/Auto-Up Project/token.json",
    },
    "upload": {
        "default_privacy_status": "private",
        "default_category_id": "24",
        "default_language": "ko",
        "notify_subscribers": False,
        "require_review_for_public": True,
    },
    "metadata": {
        "title_max_chars": 100,
        "description_max_bytes": 5000,
        "tags_max_chars": 500,
        "auto_from_image": {
            "enabled": True,
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "api_key_env": "GEMINI_API_KEY",
            "api_key_env_fallbacks": ["GOOGLE_API_KEY"],
            "allow_filename_fallback": True,
            "generated_suffix": ".generated.json",
        },
    },
    "dedupe": {"database": "./data/upload_queue.sqlite3"},
    "video_gate": {
        "max_duration_sec": 180,
        "require_square_or_vertical": True,
        "min_file_bytes": 2048,
    },
}

RUNTIME_SECRET_FILES = {
    "UPLOADER_SECRET_AUTO_UP_CREDENTIALS_JSON": "auto_up_credentials.json",
    "UPLOADER_SECRET_AUTO_UP_TOKEN_JSON": "auto_up_token.json",
    "UPLOADER_SECRET_DRIVE_TOKEN_JSON": "drive_token.json",
    "UPLOADER_SECRET_NINGNING_YOUTUBE_CREDENTIALS_JSON": "ningning_youtube_credentials.json",
    "UPLOADER_SECRET_MOSONGEEAI_YOUTUBE_CREDENTIALS_JSON": "mosongeeai_youtube_credentials.json",
    "UPLOADER_SECRET_YOUTUBE_DAPJEONGSA_JSON": "youtube_dapjeongsa.json",
    "UPLOADER_SECRET_YOUTUBE_NANGMAN_TONGSINSA_JSON": "youtube_nangman_tongsinsa.json",
    "UPLOADER_SECRET_YOUTUBE_NINGNING_JSON": "youtube_ningning.json",
    "UPLOADER_SECRET_YOUTUBE_AMUSEASIA_JSON": "youtube_amuseasia.json",
    "UPLOADER_SECRET_YOUTUBE_VOGUE_CITY_JSON": "youtube_vogue_city.json",
    "UPLOADER_SECRET_YOUTUBE_TWOSOME_MOVIE_JSON": "youtube_twosome_movie.json",
    "UPLOADER_SECRET_YOUTUBE_MOSONGEEAI_JSON": "youtube_mosongeeai.json",
}


def load_config(path: str | Path) -> dict[str, Any]:
    materialize_runtime_secrets()
    config_path = Path(path)
    if not config_path.exists():
        return DEFAULT_CONFIG
    try:
        import yaml

        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return DEFAULT_CONFIG
    return deep_merge(DEFAULT_CONFIG, loaded)


def materialize_runtime_secrets() -> None:
    secrets_dir = Path(__file__).resolve().parents[2] / "secrets"
    wrote_any = False
    for env_name, filename in RUNTIME_SECRET_FILES.items():
        value = os.environ.get(f"{env_name}_B64")
        if value:
            content = base64.b64decode(value).decode("utf-8")
        else:
            content = os.environ.get(env_name, "")
        if not content.strip():
            continue
        if not wrote_any:
            secrets_dir.mkdir(parents=True, exist_ok=True)
            wrote_any = True
        target = secrets_dir / filename
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            target.write_text(content, encoding="utf-8")


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
