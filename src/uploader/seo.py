from __future__ import annotations

import re

from .models import SeoMetadata, UploadItem


STOPWORDS = {
    "그리고",
    "그래서",
    "하지만",
    "이것",
    "저것",
    "오늘",
    "진짜",
    "그냥",
    "영상",
    "쇼츠",
}

SEO_RULES_SUMMARY = (
    "후킹 가능성, 시청자 이목, 검색 적합성을 동시에 만족하도록 제목/설명/tags를 구성한다. "
    "단, 허위 과장, 선정적 표현, 이모지, 장식문자는 사용하지 않는다."
)

SENSITIVE_REPLACEMENTS = [
    ("이 몸매에 이 춤선은", "이 퍼포먼스와 춤선은"),
    ("몸매에", "퍼포먼스에"),
    ("몸매", "퍼포먼스"),
    ("눈나", "출연자"),
    ("핫 트렌드", "주목 트렌드"),
    ("핫", "주목"),
    ("미모의 여성", "강한 존재감의 출연자"),
    ("미모", "존재감"),
    ("비주얼레전드", "무대하이라이트"),
    ("비주얼 레전드", "무대 하이라이트"),
    ("비주얼", "무대 분위기"),
    ("난리 난", "주목받는"),
    ("완전히 뒤집어놓은", "시선을 끄는"),
    ("역대급", "인상적인"),
    ("시선 강탈", "눈길을 끄는"),
    ("레전드", "하이라이트"),
    ("반칙이지", "눈길을 끈다"),
    ("섹시", "강렬한"),
    ("야한", "강렬한"),
    ("노출", "무대"),
]

POLISH_REPLACEMENTS = [
    ("클럽을 시선을 끄는", "클럽에서 시선을 끄는"),
    ("출연자이", "출연자가"),
    ("출연자이 등장", "출연자가 등장"),
    ("눈길을 끄는...", "눈길을 끕니다."),
    ("몰입감 장난 아닙니다", "몰입감이 큽니다"),
    ("퍼포먼스에", "퍼포먼스와"),
]


def build_seo(item: UploadItem, config: dict) -> SeoMetadata:
    meta_cfg = config.get("metadata", {})
    title_max = int(meta_cfg.get("title_max_chars", 100))
    description_max = int(meta_cfg.get("description_max_bytes", 5000))
    tags_max = int(meta_cfg.get("tags_max_chars", 500))

    base_title = clean_title(item.title_seed or first_sentence(item.transcript) or item.video_name)
    base_title = enforce_hookable_title(base_title, item)
    title = trim_chars(base_title, title_max)

    hashtags = merge_hashtags(item.hashtags_seed, ["#Shorts"])
    keywords = keyword_candidates(item)
    tags = fit_tags(merge_unique(item.tags_seed + keywords), tags_max)

    hook = clean_sentence(item.hook_seed or first_sentence(item.transcript) or title)
    hook = enforce_hook_line(hook, title)
    source_line = source_context(item)
    transcript_line = clean_sentence(first_sentence(item.transcript, max_len=120))
    description_seed = clean_description_seed(item.description_seed)
    description_parts = [
        hook,
        description_seed,
        source_line,
        transcript_line if transcript_line and transcript_line != hook else "",
        " ".join(hashtags[:5]),
    ]
    description = trim_bytes("\n\n".join([part for part in description_parts if part]), description_max)
    risk_notes = []
    if item.policy.requires_review:
        risk_notes.append(item.policy.review_reason)
    if item.source_url:
        risk_notes.append("원본 URL 기반 재가공 콘텐츠")

    return SeoMetadata(
        title=title,
        description=description,
        tags=tags,
        hashtags=hashtags[:5],
        category_id=str(config.get("upload", {}).get("default_category_id", "24")),
        rationale=f"{SEO_RULES_SUMMARY} 제목 seed, hook, 자막 첫 문장, 기존 해시태그를 조합함",
        risk_notes=risk_notes,
    )


def enforce_hookable_title(title: str, item: UploadItem) -> str:
    title = clean_title(title)
    if not title:
        return clean_title(item.video_name)
    # Titles that are only bare filenames are weak for SEO and viewer attention.
    if re.fullmatch(r"[A-Za-z0-9._ -]{1,40}", title):
        keyword = clean_title(first_meaningful_keyword(item) or title)
        return f"{keyword} 쇼츠 하이라이트"
    return title


def enforce_hook_line(hook: str, title: str) -> str:
    hook = clean_sentence(hook)
    if not hook or hook == title:
        return f"{title}의 핵심 장면"
    return hook


def first_meaningful_keyword(item: UploadItem) -> str:
    for value in [item.title_seed, item.source_title, item.transcript, item.video_name]:
        words = keyword_candidates(
            UploadItem(
                source_project=item.source_project,
                source_root=item.source_root,
                source_run_dir=item.source_run_dir,
                adapter=item.adapter,
                video_path=item.video_path,
                title_seed=str(value or ""),
            )
        )
        if words:
            return words[0]
    return ""


def keyword_candidates(item: UploadItem) -> list[str]:
    text = " ".join(
        [
            item.title_seed,
            item.source_title,
            item.source_channel,
            item.transcript[:500],
            " ".join(item.hashtags_seed),
        ]
    )
    words = re.findall(r"[A-Za-z][A-Za-z0-9+.#-]{2,}|[가-힣]{2,}", text)
    normalized = []
    for word in words:
        cleaned = clean_tag(word)
        if not cleaned or cleaned in STOPWORDS:
            continue
        normalized.append(cleaned)
    return merge_unique(normalized)[:12]


def merge_hashtags(existing: list[str], defaults: list[str]) -> list[str]:
    values = []
    for tag in existing + defaults:
        text = str(tag).strip()
        if not text:
            continue
        if not text.startswith("#"):
            text = f"#{text}"
        text = "#" + clean_tag(text.lstrip("#"))
        if text != "#":
            values.append(text)
    return merge_unique(values)


def merge_unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def fit_tags(tags: list[str], max_chars: int) -> list[str]:
    result = []
    total = 0
    for tag in tags:
        tag = clean_tag(tag)
        if not tag:
            continue
        add = len(tag) + (1 if result else 0)
        if total + add > max_chars:
            break
        result.append(tag)
        total += add
    return result


def source_context(item: UploadItem) -> str:
    if item.source_title and item.source_channel:
        return f"출처 맥락: {item.source_channel} - {item.source_title}"
    if item.source_title:
        return f"출처 맥락: {item.source_title}"
    return f"프로젝트: {item.source_project}"


def clean_title(text: str) -> str:
    text = clean_sentence(text)
    text = strip_decorative_symbols(text)
    text = replace_sensitive_terms(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -|")


def clean_sentence(text: str) -> str:
    text = str(text or "").replace("\n", " ")
    text = strip_decorative_symbols(text)
    text = replace_sensitive_terms(text)
    return re.sub(r"\s+", " ", text).strip()


def clean_description_seed(text: str) -> str:
    text = str(text or "").strip()
    if not text:
        return ""
    text = strip_decorative_symbols(text)
    text = replace_sensitive_terms(text)
    return re.sub(r"\n{3,}", "\n\n", text)


def clean_tag(text: str) -> str:
    text = str(text or "").strip("#,.!?()[]{} ")
    text = strip_decorative_symbols(text)
    text = replace_sensitive_terms(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip("#,.!?()[]{} ")


def replace_sensitive_terms(text: str) -> str:
    cleaned = str(text or "")
    for source, replacement in SENSITIVE_REPLACEMENTS:
        cleaned = cleaned.replace(source, replacement)
    for source, replacement in POLISH_REPLACEMENTS:
        cleaned = cleaned.replace(source, replacement)
    return cleaned


def first_sentence(text: str, max_len: int = 80) -> str:
    cleaned = clean_sentence(text)
    if not cleaned:
        return ""
    parts = re.split(r"(?<=[.!?。！？])\s+", cleaned)
    sentence = parts[0] if parts else cleaned
    return trim_chars(sentence, max_len)


def trim_chars(text: str, max_chars: int) -> str:
    text = clean_sentence(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def trim_bytes(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    trimmed = encoded[: max_bytes - 3]
    return trimmed.decode("utf-8", errors="ignore").rstrip() + "..."


def strip_decorative_symbols(text: str) -> str:
    # Keep upload metadata plain text: no emoji, pictographs, or decorative dingbats.
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
    text = "".join(cleaned)
    text = re.sub(r"^[^\w가-힣'\"]+|[^\w가-힣.!?'\")]+$", "", text)
    return text
