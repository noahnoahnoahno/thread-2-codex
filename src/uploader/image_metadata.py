from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def metadata_from_image(
    image_path: str | Path,
    video_stem: str,
    config: dict,
) -> dict[str, Any]:
    cfg = config.get("metadata", {}).get("auto_from_image", {})
    if not cfg.get("enabled", True):
        return fallback_metadata(video_stem, "이미지 기반 자동 메타데이터가 비활성화됨")
    provider = str(cfg.get("provider", "gemini")).lower()
    if provider == "gemini":
        api_key = gemini_api_key(cfg)
        if api_key:
            try:
                return gemini_image_metadata(image_path, video_stem, config, api_key)
            except Exception as exc:
                if not cfg.get("allow_filename_fallback", True):
                    raise
                return fallback_metadata(video_stem, f"Gemini 이미지 분석 실패: {exc}")
    if cfg.get("allow_filename_fallback", True):
        return fallback_metadata(video_stem, "GEMINI_API_KEY 없음: 파일명 기반 폴백")
    return {}


def gemini_api_key(cfg: dict[str, Any]) -> str:
    env_names = [str(cfg.get("api_key_env", "GEMINI_API_KEY"))]
    env_names.extend(str(name) for name in cfg.get("api_key_env_fallbacks", []) if name)
    env_names.extend(["GEMINI_API_KEY", "GOOGLE_API_KEY"])
    for env_name in dict.fromkeys(env_names):
        value = os.environ.get(env_name)
        if value:
            return value
    return ""


def gemini_image_metadata(
    image_path: str | Path,
    video_stem: str,
    config: dict,
    api_key: str,
) -> dict[str, Any]:
    image_path = Path(image_path)
    model = config.get("metadata", {}).get("auto_from_image", {}).get("model", "gemini-2.5-flash")
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    prompt = build_prompt(video_stem)
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": image_b64,
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": metadata_response_schema(),
            "temperature": 0.4,
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Gemini HTTP {exc.code}: {body[:300]}") from exc
    text = extract_gemini_text(data)
    parsed = json.loads(strip_json_fence(text))
    return normalize_generated_metadata(parsed, "gemini_image")


def metadata_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "hook": {"type": "string"},
            "description": {"type": "string"},
            "seo_tags": {"type": "array", "items": {"type": "string"}},
            "hashtags": {"type": "array", "items": {"type": "string"}},
            "requires_review": {"type": "boolean"},
            "review_reason": {"type": "string"},
        },
        "required": [
            "title",
            "hook",
            "description",
            "seo_tags",
            "hashtags",
            "requires_review",
            "review_reason",
        ],
    }


def build_prompt(video_stem: str) -> str:
    return f"""
You are creating YouTube Shorts upload metadata from a single captured frame.

Rules:
- Analyze the image only. Do not generate, edit, or request any image.
- Output JSON only.
- Korean metadata first.
- The metadata must be hook-oriented: it should make viewers immediately understand why this Short is worth watching.
- The title and hook must attract attention with a clear curiosity gap, scene tension, trend angle, or visual/action point visible in the image.
- The metadata must be SEO-friendly: include natural searchable keywords for the scene, action, mood, format, and trend without keyword stuffing.
- Put the strongest searchable keyword phrase near the front of the title when it fits naturally.
- Description opening lines must combine hook + context + searchable keywords, not generic filler.
- No emoji, no pictographs, no decorative symbols.
- Do not use fire symbols, hearts, stars, or attention-bait symbols.
- Avoid sexualized or objectifying language. Describe the scene/action neutrally.
- Do not make false claims or overstate facts not visible from the image.
- Keep the title under 80 Korean characters.
- Include concise SEO tags without hashtags in seo_tags.
- Include 3-5 hashtags separately.
- Mark requires_review true if the image alone is not enough to verify context.

Video/file stem: {video_stem}

Return this schema:
{{
  "title": "plain text title",
  "hook": "viewer-attention hook line",
  "description": "SEO-friendly plain text description with hashtags at the end",
  "seo_tags": ["search keyword", "scene keyword", "trend keyword"],
  "hashtags": ["#Shorts"],
  "requires_review": true,
  "review_reason": "why review is needed or empty"
}}
""".strip()


def extract_gemini_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    for candidate in candidates:
        parts = candidate.get("content", {}).get("parts") or []
        for part in parts:
            if "text" in part:
                return str(part["text"])
    raise RuntimeError("Gemini 응답에 text가 없습니다")


def strip_json_fence(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def normalize_generated_metadata(data: dict[str, Any], source: str) -> dict[str, Any]:
    title = plain_text(data.get("title") or "")
    hook = plain_text(data.get("hook") or "")
    description = plain_multiline(data.get("description") or "")
    tags = list_values(data.get("seo_tags") or data.get("tags") or [])
    hashtags = normalize_hashtags(list_values(data.get("hashtags") or ["#Shorts"]))
    return {
        "project": "image-generated",
        "title": title,
        "hook": hook,
        "description": description,
        "tags": [plain_text(tag) for tag in tags if plain_text(tag)],
        "hashtags": hashtags,
        "requires_review": bool(data.get("requires_review", True)),
        "review_reason": plain_text(data.get("review_reason") or f"{source} 자동 생성 검토"),
        "metadata_source": source,
    }


def fallback_metadata(video_stem: str, reason: str) -> dict[str, Any]:
    title = plain_text(video_stem.replace("_", " ").replace("-", " "))
    return {
        "project": "image-generated",
        "title": title,
        "hook": title,
        "description": f"{title}\n\n#Shorts",
        "tags": [title] if title else [],
        "hashtags": ["#Shorts"],
        "requires_review": True,
        "review_reason": reason,
        "metadata_source": "filename_fallback",
    }


def plain_multiline(value: Any) -> str:
    text = str(value or "")
    text = strip_decorative_symbols(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def plain_text(value: Any) -> str:
    text = str(value or "").replace("\n", " ")
    text = strip_decorative_symbols(text)
    return re.sub(r"\s+", " ", text).strip()


def list_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[,\n]", value) if part.strip()]
    return []


def normalize_hashtags(values: list[str]) -> list[str]:
    hashtags = []
    for value in values:
        text = plain_text(value).strip("# ")
        if not text:
            continue
        hashtags.append(f"#{text}")
    return hashtags or ["#Shorts"]


def strip_decorative_symbols(text: str) -> str:
    cleaned = []
    for char in str(text or ""):
        code = ord(char)
        if (
            0x1F000 <= code <= 0x1FAFF
            or 0x2600 <= code <= 0x27BF
            or 0xFE00 <= code <= 0xFE0F
        ):
            continue
        cleaned.append(char)
    return "".join(cleaned)
