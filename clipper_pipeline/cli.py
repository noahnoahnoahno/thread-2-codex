from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from urllib.parse import parse_qs, urlparse
from dataclasses import asdict, dataclass
from pathlib import Path


TIME_RE = re.compile(r"^\[(?:(?P<hour>\d{2}):)?(?P<minute>\d{2}):(?P<second>\d{2})\]\s*(?P<text>.*)$")
SENTENCE_END_RE = re.compile(
    r"([.!?。？！]|(습니다|합니다|했습니다|됩니다|입니다|이에요|예요|거예요|거에요|같아요|있어요|없어요|"
    r"잖아요|되잖아요|네요|거죠|이죠|하죠|좋습니다|같습니다|드립니다|합니다요|해요)[.!?。？！]?)$"
)
FONT_CANDIDATES = [
    Path("/Users/noahai/Library/Fonts/NEXON Lv1 Gothic OTF Bold.otf"),
    Path("/Users/noahai/Library/Fonts/NEXON Lv1 Gothic OTF.otf"),
    Path("/Users/noahai/Library/Fonts/NEXON Lv1 Gothic OTF Light.otf"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
]
DEFAULT_FONT_FAMILY = "NEXON Lv1 Gothic"
STEP_LABELS = {
    "youtube_info": "영상 확인",
    "download_youtube": "영상 다운로드",
    "fetch_transcript": "자막 가져오기",
    "extract_audio": "오디오 추출",
    "analyze": "AI 분석",
    "render": "클립 생성",
    "validate_render": "렌더 검수",
}


def apply_ytdlp_auth_options(options: dict) -> dict:
    """Add optional local browser/cookie auth for yt-dlp calls."""
    cookie_file = os.getenv("YT_DLP_COOKIES")
    cookies_from_browser = os.getenv("YT_DLP_COOKIES_FROM_BROWSER")
    if cookie_file:
        options["cookiefile"] = cookie_file
    if cookies_from_browser:
        parts = [part.strip() for part in cookies_from_browser.split(":") if part.strip()]
        if parts:
            options["cookiesfrombrowser"] = tuple(parts)
    return options


@dataclass
class TranscriptSegment:
    start_sec: float
    end_sec: float
    text: str


@dataclass
class ClipCandidate:
    start_sec: float
    end_sec: float
    duration_sec: float
    category: str
    title: str
    reason: str
    hashtags: list[str]
    score: float
    source_text: str
    most_replayed: bool = False
    replay_source: str = "analysis"
    replay_score: float | None = None


HOOK_KEYWORDS = {
    "자동": 3.0,
    "AI": 3.0,
    "후킹": 3.0,
    "쇼츠": 2.8,
    "제목": 2.0,
    "자막": 2.0,
    "다운로드": 2.0,
    "대박": 1.5,
    "가능": 1.4,
    "분석": 1.4,
    "클립": 1.4,
    "세이프존": 1.2,
    "레터박스": 1.2,
    "크롭": 1.2,
    "글꼴": 1.0,
    "색상": 1.0,
    "위치": 1.0,
    "헤르메스": 2.5,
    "오픈": 1.8,
    "비서": 1.5,
    "직원": 1.5,
    "메모리": 1.5,
    "스킬": 1.5,
    "비용": 1.5,
    "단점": 1.5,
    "이슈": 1.2,
    "역할": 1.2,
    "블로그": 2.4,
    "성장": 1.8,
    "키워드": 2.2,
    "GPT": 2.2,
    "채치": 1.6,
    "자동화": 2.0,
    "수익": 2.0,
    "서치 콘솔": 1.5,
    "마법사": 1.4,
    "부업": 1.6,
    "추론": 1.4,
    "비밀": 1.5,
}

HOOK_FEATURES = {
    "curiosity": {
        "왜": 1.0,
        "이유": 1.0,
        "비밀": 1.2,
        "진짜": 0.7,
        "뭐냐": 0.8,
        "무엇": 0.7,
        "어떻게": 0.8,
    },
    "contrast": {
        "하지만": 1.0,
        "근데": 0.8,
        "그런데": 0.8,
        "반면": 1.0,
        "차이": 1.0,
        "vs": 1.1,
        "보다": 0.6,
        "아니라": 0.8,
    },
    "turning_point": {
        "사실": 1.0,
        "오히려": 1.2,
        "문제는": 1.1,
        "중요한 건": 1.1,
        "핵심은": 1.1,
        "알고 보면": 1.0,
        "대부분": 0.7,
        "정확하게": 0.5,
    },
    "attention": {
        "핵심": 1.1,
        "중요": 0.9,
        "놓치": 1.1,
        "반전": 1.3,
        "충격": 1.1,
        "바로": 0.6,
        "꼭": 0.6,
        "절대": 0.8,
    },
    "proof": {
        "결론": 1.1,
        "결과": 0.9,
        "실제로": 0.9,
        "써봤": 1.2,
        "해봤": 1.0,
        "테스트": 0.8,
        "가능": 0.7,
    },
    "pain": {
        "문제": 1.0,
        "실수": 1.0,
        "단점": 1.0,
        "아쉬": 0.8,
        "못": 0.4,
        "비용": 0.8,
        "부담": 0.8,
    },
    "personal": {
        "제가": 0.5,
        "저는": 0.5,
        "고백": 1.1,
        "느낌": 0.5,
        "경험": 0.8,
    },
}

LOW_VALUE_PATTERNS = [
    "안녕하세요",
    "반갑습니다",
    "구독",
    "좋아요",
    "알림",
    "시작하겠습니다",
    "마무리",
    "시청해 주셔서",
]

MIN_RECOMMEND_SCORE = 1.0

TOPIC_BOUNDARY_CUES = [
    "첫 번째",
    "두 번째",
    "세 번째",
    "마지막",
    "다음",
    "그다음",
    "그러면",
    "여기서",
    "이제",
    "정리하면",
    "결론",
    "핵심",
    "중요",
    "비밀",
    "방법",
    "키워드",
    "수익",
    "자동화",
    "GPT",
]


def parse_transcript(path: Path) -> list[TranscriptSegment]:
    raw_segments: list[tuple[float, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = TIME_RE.match(line.strip())
        if not match:
            continue
        hour = int(match.group("hour") or 0)
        start = hour * 3600 + int(match.group("minute")) * 60 + int(match.group("second"))
        text = normalize_text(match.group("text"))
        if text:
            raw_segments.append((float(start), text))

    segments: list[TranscriptSegment] = []
    for index, (start, text) in enumerate(raw_segments):
        if index + 1 < len(raw_segments):
            end = max(start + 1.0, raw_segments[index + 1][0])
        else:
            end = start + 3.0
        segments.append(TranscriptSegment(start_sec=start, end_sec=end, text=text))
    return segments


def normalize_text(text: str) -> str:
    text = text.replace(">>", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_sentence_blocks(
    segments: list[TranscriptSegment],
    max_block_duration: float = 45.0,
) -> list[TranscriptSegment]:
    blocks: list[TranscriptSegment] = []
    start_sec: float | None = None
    end_sec = 0.0
    texts: list[str] = []

    for segment in segments:
        if start_sec is None:
            start_sec = segment.start_sec
        texts.append(segment.text)
        end_sec = segment.end_sec
        source_text = " ".join(texts)
        duration = end_sec - start_sec
        if is_sentence_end(source_text) or should_close_topic_block(source_text, segment.text, duration, max_block_duration):
            blocks.append(TranscriptSegment(start_sec=start_sec, end_sec=end_sec, text=source_text))
            start_sec = None
            texts = []

    if texts and start_sec is not None:
        blocks.append(TranscriptSegment(start_sec=start_sec, end_sec=end_sec, text=" ".join(texts)))
    return blocks


def should_close_topic_block(
    source_text: str,
    latest_text: str,
    duration: float,
    max_block_duration: float,
) -> bool:
    if duration >= max_block_duration:
        return True
    if duration < 22:
        return False
    if duration >= 34 and any(cue in latest_text or cue in source_text[-120:] for cue in TOPIC_BOUNDARY_CUES):
        return True
    return False


def analyze_segments(
    segments: list[TranscriptSegment],
    max_candidates: int = 6,
    min_duration: int = 20,
    max_duration: int = 45,
    most_replayed_range: tuple[float, float, float | None] | None = None,
) -> list[ClipCandidate]:
    windows: list[ClipCandidate] = []
    total_duration = max((segment.end_sec for segment in segments), default=0.0)
    sentence_blocks = build_sentence_blocks(segments)
    for start_index, segment in enumerate(sentence_blocks):
        texts: list[str] = []
        score = 0.0
        end_sec = segment.start_sec

        for next_segment in sentence_blocks[start_index:]:
            texts.append(next_segment.text)
            end_sec = next_segment.end_sec
            duration = end_sec - segment.start_sec
            score += score_text(next_segment.text)
            if duration > max_duration:
                break
            if duration >= min_duration:
                source_text = " ".join(texts)
                windows.append(
                    build_candidate(
                        segment.start_sec,
                        end_sec,
                        duration,
                        source_text,
                        score,
                        total_duration,
                    )
                )

    ranked = sorted(windows, key=lambda item: item.score, reverse=True)
    most_replayed_candidate = choose_most_replayed_candidate(ranked, most_replayed_range)
    selected: list[ClipCandidate] = []
    if most_replayed_candidate:
        most_replayed_candidate.most_replayed = True
        most_replayed_candidate.replay_source = "youtube_heatmap" if most_replayed_range else "hook_score_fallback"
        most_replayed_candidate.replay_score = most_replayed_range[2] if most_replayed_range else most_replayed_candidate.score
        selected.append(most_replayed_candidate)

    category_order = [
        "blog_growth",
        "keyword_research",
        "gpt_builder",
        "monetization",
        "ai_tool",
        "agent_comparison",
        "workflow",
        "memory_skill",
        "cost",
        "limitation",
        "input",
        "processing",
        "hook_analysis",
        "candidate_list",
        "layout",
        "text_style",
        "timeline",
        "render",
    ]
    for category in category_order:
        category_matches = [
            candidate
            for candidate in ranked
            if candidate.category == category and is_recommendable(candidate)
        ]
        for candidate in category_matches:
            if is_duplicate(candidate, selected):
                continue
            selected.append(candidate)
            break
        if len(selected) >= max_candidates:
            break

    for candidate in [item for item in ranked if is_sentence_end(item.source_text) and is_recommendable(item)]:
        if len(selected) >= max_candidates:
            break
        if is_duplicate(candidate, selected):
            continue
        selected.append(candidate)
        if len(selected) >= max_candidates:
            break
    for candidate in [item for item in ranked if is_recommendable(item)]:
        if len(selected) >= max_candidates:
            break
        if is_duplicate(candidate, selected):
            continue
        selected.append(candidate)
    return sorted(selected, key=lambda item: item.start_sec)


def is_recommendable(candidate: ClipCandidate) -> bool:
    return candidate.score >= MIN_RECOMMEND_SCORE


def build_candidate(
    start_sec: float,
    end_sec: float,
    duration: float,
    source_text: str,
    raw_score: float,
    total_duration: float,
) -> ClipCandidate:
    return ClipCandidate(
        start_sec=start_sec,
        end_sec=end_sec,
        duration_sec=round(duration, 1),
        category=classify_text(source_text),
        title=make_title(source_text),
        reason=make_reason(source_text),
        hashtags=make_hashtags(source_text),
        score=round(score_window(source_text, raw_score, duration, start_sec, total_duration), 3),
        source_text=source_text,
    )


def is_sentence_end(text: str) -> bool:
    clean = text.strip().rstrip("\"'”’)]} ")
    if not clean:
        return False
    return bool(SENTENCE_END_RE.search(clean))


def choose_most_replayed_candidate(
    ranked: list[ClipCandidate],
    replay_range: tuple[float, float, float | None] | None,
) -> ClipCandidate | None:
    if not ranked:
        return None
    sentence_ranked = [candidate for candidate in ranked if is_sentence_end(candidate.source_text)]
    if replay_range is None:
        return ranked[0]

    replay_start, replay_end, _ = replay_range
    midpoint = (replay_start + replay_end) / 2

    def candidate_rank(candidate: ClipCandidate) -> tuple[float, float, float]:
        overlap = max(0.0, min(candidate.end_sec, replay_end) - max(candidate.start_sec, replay_start))
        candidate_midpoint = (candidate.start_sec + candidate.end_sec) / 2
        distance = abs(candidate_midpoint - midpoint)
        return (overlap, -distance, candidate.score)

    pool = sentence_ranked or ranked
    return max(pool, key=candidate_rank)


def score_text(text: str) -> float:
    score = 0.0
    for keyword, weight in HOOK_KEYWORDS.items():
        if keyword in text:
            score += weight
    if "?" in text or "뭐예요" in text:
        score += 1.0
    if any(token in text for token in ("와", "대박", "가능한가")):
        score += 0.8
    return score


def score_window(
    text: str,
    raw_score: float,
    duration: float,
    start_sec: float,
    total_duration: float,
) -> float:
    base = raw_score / max(duration / 10, 1)
    feature_score = score_hook_features(text)
    structure_score = score_structure(text)
    position_score = score_position(start_sec, total_duration)
    penalty = score_low_value_penalty(text)
    if not is_sentence_end(text):
        penalty += 4.0
    return max(0.1, base + feature_score + structure_score + position_score - penalty)


def score_hook_features(text: str) -> float:
    normalized = text.lower()
    score = 0.0
    for feature in HOOK_FEATURES.values():
        for keyword, weight in feature.items():
            if keyword.lower() in normalized:
                score += weight
    return min(score, 5.0)


def score_structure(text: str) -> float:
    score = 0.0
    if re.search(r"\d+\s*(개|가지|초|분|%|배|번)", text):
        score += 1.0
    if "?" in text:
        score += 0.9
    if any(token in text for token in ("첫 번째", "두 번째", "마지막", "핵심", "정리하면")):
        score += 0.8
    if any(token in text for token in ("바로", "딱", "꼭", "절대", "중요한 건", "문제는")):
        score += 0.5
    return score


def score_position(start_sec: float, total_duration: float) -> float:
    if total_duration <= 0:
        return 0.0
    ratio = start_sec / total_duration
    if ratio < 0.03:
        return -0.6
    if ratio > 0.94:
        return -0.8
    if 0.08 <= ratio <= 0.82:
        return 0.4
    return 0.0


def score_low_value_penalty(text: str) -> float:
    penalty = 0.0
    for pattern in LOW_VALUE_PATTERNS:
        if pattern in text:
            penalty += 0.7
    return min(penalty, 2.4)


def overlaps(a: ClipCandidate, b: ClipCandidate) -> bool:
    overlap = max(0.0, min(a.end_sec, b.end_sec) - max(a.start_sec, b.start_sec))
    return overlap > min(a.duration_sec, b.duration_sec) * 0.35


def is_duplicate(candidate: ClipCandidate, selected: list[ClipCandidate]) -> bool:
    for existing in selected:
        if candidate.title == existing.title:
            return True
        if abs(candidate.start_sec - existing.start_sec) < 30:
            return True
        if overlaps(candidate, existing):
            return True
    return False


def classify_text(text: str) -> str:
    if "블로그" in text and ("키워드" in text or "성장" in text or "수익" in text):
        return "blog_growth"
    if "블로그" in text and ("사진" in text or "그림" in text or "영상" in text):
        return "blog_growth"
    if "GPT" in text or "채치" in text or "챗" in text:
        if "만들" in text or "마법사" in text or "지침" in text:
            return "gpt_builder"
        return "ai_tool"
    if "모델" in text and ("자동화" in text or "효율" in text or "발전 속도" in text):
        return "ai_tool"
    if "키워드" in text and ("추천" in text or "부업" in text or "검색" in text):
        return "keyword_research"
    if "수익" in text or "광고" in text or "상품" in text or "링크" in text:
        return "monetization"
    if "헤르메스" in text and ("오픈" in text or "오픈클로" in text or "오픈 컬" in text):
        if "비서" in text and "직원" in text:
            return "agent_comparison"
        if "역할" in text or "구조" in text or "위임" in text or "둘 다" in text:
            return "workflow"
    if "메모리" in text or "스킬" in text or "학습 루프" in text:
        return "memory_skill"
    if "비용" in text or "부담" in text or "오픈 AI 오스" in text:
        return "cost"
    if "단점" in text or "이슈" in text or "아쉬" in text or "못했습니다" in text:
        return "limitation"
    if ("URL" in text or "링크" in text) and "쇼츠" in text:
        return "input"
    if "영상 다운로드" in text and "오디오 추출" in text:
        return "processing"
    if "후킹" in text and ("문맥" in text or "음성" in text or "분석" in text):
        return "hook_analysis"
    if "여섯" in text or "최대" in text or "몇 초짜리" in text:
        return "candidate_list"
    if "세이프존" in text or "레터박스" in text or "크롭" in text:
        return "layout"
    if "글꼴" in text or "색상" in text or "채널명" in text or "위치 조정" in text:
        return "text_style"
    if "1초" in text or "시작점" in text or "끝점" in text or "길 조정" in text:
        return "timeline"
    if "MP4" in text or "클립 생성" in text or "다 다운" in text:
        return "render"
    return "general"


def make_title(text: str) -> str:
    if "블로그" in text and "비밀" in text:
        return "블로그 성장의 비밀"
    if "블로그" in text and ("사진" in text or "그림" in text or "영상" in text):
        return "블로그가 초보자에게 유리한 이유"
    if "블로그" in text and "키워드" in text:
        return "블로그 키워드를 자동으로 찾는 방법"
    if "블로그 자동화" in text and ("GPT" in text or "학습" in text):
        return "GPT로 블로그 자동화를 만드는 이유"
    if ("GPT" in text or "채치" in text or "챗" in text) and ("만들" in text or "마법사" in text):
        return "GPT로 키워드 마법사 만들기"
    if "수익" in text or "광고" in text or "상품" in text:
        return "블로그 수익화가 시작되는 지점"
    if "추론 기능" in text:
        return "GPT 추론 기능이 중요한 이유"
    if "lm 모델" in text or "모델들의 발전 속도" in text:
        return "AI 모델 발전 속도가 중요한 이유"
    if "부업" in text and "키워드" in text:
        return "부업 키워드가 자동으로 쏟아진다"
    if "헤르메스" in text and "오픈" in text and "비서" in text and "직원" in text:
        return "오픈클로는 비서, 헤르메스는 AI 직원"
    if "헤르메스 에이전트가 뭐냐" in text or ("뉴스 리서치" in text and "오픈소스 AI 에이전트" in text):
        return "헤르메스 에이전트란 무엇인가"
    if "헤르메스" in text and ("역할" in text or "위임" in text or "둘 다" in text):
        return "헤르메스와 오픈클로를 같이 쓰는 이유"
    if "토픽별 맥락" in text or "자동화 습관" in text or "쌓아둔" in text:
        return "쌓아둔 AI 작업 맥락은 쉽게 못 옮긴다"
    if "메모리" in text and "스킬" in text:
        return "헤르메스가 좋은 이유: 메모리와 스킬"
    if "학습 루프" in text:
        return "AI 에이전트의 핵심은 학습 루프"
    if "비용" in text or "부담" in text:
        return "AI 에이전트 비용을 줄인 모델 조합"
    if "단점" in text or "이슈" in text or "아쉬" in text:
        return "헤르메스 에이전트의 아쉬운 점"
    if "유튜브 URL" in text or "URL" in text:
        return "유튜브 링크만 넣으면 쇼츠가 자동으로 만들어진다"
    if "영상 다운로드" in text and "오디오 추출" in text:
        return "다운로드부터 AI 분석까지 5단계로 처리한다"
    if "여섯" in text or "6" in text:
        return "롱폼 하나에서 쇼츠 후보 6개를 자동 추천"
    if "후킹" in text and "제목" in text:
        return "아무 장면이 아니라 후킹 구간을 골라준다"
    if "세이프존" in text or "레터박스" in text or "크롭" in text:
        return "쇼츠 화면 레이아웃까지 직접 편집한다"
    if "글꼴" in text or "색상" in text or "위치" in text:
        return "제목 위치와 글자 스타일을 바로 조정한다"
    if "1초" in text or "시작점" in text or "끝점" in text:
        return "시작점과 끝점을 1초 단위로 조정한다"
    if "다운로드" in text or "MP4" in text:
        return "선택한 클립을 MP4로 바로 다운로드"
    return shorten_title(text)


def shorten_title(text: str) -> str:
    clean = re.sub(r"[^\w가-힣A-Za-z0-9 ]+", "", text)
    words = clean.split()
    return " ".join(words[:10])[:42] or "쇼츠 후보 클립"


def make_reason(text: str) -> str:
    if "블로그" in text and "키워드" in text:
        return "블로그 성장과 검색 유입의 핵심인 키워드 찾기 과정을 다뤄 실용적인 후킹 포인트가 있다."
    if "블로그" in text and ("사진" in text or "그림" in text or "영상" in text):
        return "다른 콘텐츠보다 블로그가 초보자에게 접근 가능한 이유를 설명해 진입 장벽을 낮춰준다."
    if "블로그 자동화" in text and ("GPT" in text or "학습" in text):
        return "AI를 단순 사용이 아니라 블로그 자동화 도구로 학습시키는 핵심 전환점이다."
    if ("GPT" in text or "채치" in text or "챗" in text) and ("만들" in text or "지침" in text):
        return "GPT를 단순 질문 도구가 아니라 맞춤형 작업 도구로 바꾸는 장면이라 관심을 끌기 좋다."
    if "수익" in text or "광고" in text or "상품" in text:
        return "블로그 운영이 실제 수익으로 연결되는 지점을 설명해 시청자의 관심을 끌 수 있다."
    if "추론 기능" in text:
        return "AI가 답만 내는 것이 아니라 생각 과정을 설명한다는 반전 포인트가 있다."
    if "모델" in text and ("자동화" in text or "효율" in text or "발전 속도" in text):
        return "AI 모델 발전이 개인 부업을 넘어 업무 효율까지 바꾸는 이유를 설명해 확장성이 큰 후킹 포인트다."
    if "헤르메스" in text and "오픈" in text and "비서" in text and "직원" in text:
        return "두 AI 에이전트의 차이를 비서와 직원이라는 쉬운 비유로 설명해 독립 쇼츠로 이해하기 좋다."
    if "헤르메스 에이전트가 뭐냐" in text or "오픈소스 AI 에이전트" in text:
        return "영상의 핵심 대상인 헤르메스 에이전트를 짧게 정의하는 도입 구간이다."
    if "역할" in text or "위임" in text or "둘 다" in text:
        return "헤르메스와 오픈클로를 함께 쓰는 실제 운영 구조가 드러나는 구간이다."
    if "토픽별 맥락" in text or "자동화 습관" in text or "쌓아둔" in text:
        return "기존 도구에 축적된 맥락과 습관이 전환 비용이 된다는 실제 사용 경험이 드러난다."
    if "메모리" in text or "스킬" in text or "학습 루프" in text:
        return "헤르메스 에이전트의 핵심 장점인 메모리, 스킬, 학습 루프가 설명되는 구간이다."
    if "비용" in text or "부담" in text:
        return "AI 에이전트 사용 비용과 모델 조합이라는 실용적인 포인트가 있어 관심을 끌기 좋다."
    if "단점" in text or "이슈" in text or "아쉬" in text or "못했습니다" in text:
        return "제품의 한계와 사용 중 겪은 문제를 다뤄 리뷰형 쇼츠로 활용하기 좋다."
    if "URL" in text and "쇼츠" in text:
        return "입력부터 자동 분석까지 제품의 핵심 가치가 짧게 설명되는 구간이다."
    if "영상 다운로드" in text and "오디오 추출" in text:
        return "영상 인입, 오디오 추출, 음성 인식, AI 분석, 생성으로 이어지는 처리 단계가 직접 언급된다."
    if "후킹" in text:
        return "AI가 문맥과 음성을 분석해 후킹 구간을 찾는 차별점이 드러난다."
    if "세이프존" in text or "레터박스" in text:
        return "타이틀 배치, 가이드, 레이아웃 등 편집 기능을 보여주는 구간이다."
    if "다운로드" in text:
        return "편집 결과를 실제 MP4 파일로 생성하는 마지막 사용 흐름이 명확하다."
    return "제품 기능 설명과 사용자의 반응이 함께 있어 쇼츠 후보로 활용하기 좋다."


def make_hashtags(text: str) -> list[str]:
    tags = ["#유튜브쇼츠"]
    if "블로그" in text or "키워드" in text:
        tags.extend(["#블로그성장", "#키워드분석"])
    elif "GPT" in text or "채치" in text or "챗" in text:
        tags.extend(["#GPT활용", "#AI자동화"])
    elif "헤르메스" in text or "오픈" in text:
        tags.extend(["#AI에이전트", "#HermesAgent"])
    else:
        tags.append("#AI영상편집")
    if "자막" in text:
        tags.append("#자동자막")
    if "오픈클로" in text or "오픈 클로" in text or "오픈 컬" in text:
        tags.append("#OpenClaw")
    if "레터박스" in text or "크롭" in text:
        tags.append("#쇼츠편집")
    elif "다운로드" in text or "MP4" in text:
        tags.append("#MP4다운로드")
    else:
        tags.append("#콘텐츠자동화")
    return tags


def write_candidates(candidates: list[ClipCandidate], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"clips": [asdict(candidate) for candidate in candidates]}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_most_replayed_range(info: dict) -> tuple[float, float, float | None] | None:
    heatmap = info.get("heatmap")
    if not isinstance(heatmap, list) or not heatmap:
        return None

    best_segment: dict | None = None
    best_value = float("-inf")
    for item in heatmap:
        if not isinstance(item, dict):
            continue
        try:
            value = float(item.get("value"))
            start = float(item.get("start_time"))
            end = float(item.get("end_time"))
        except (TypeError, ValueError):
            continue
        if end <= start:
            continue
        if value > best_value:
            best_value = value
            best_segment = {"start_time": start, "end_time": end, "value": value}

    if not best_segment:
        return None
    return (
        float(best_segment["start_time"]),
        float(best_segment["end_time"]),
        float(best_segment["value"]),
    )


def extract_youtube_id(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.endswith("youtu.be"):
        return parsed.path.strip("/")
    if "youtube.com" in parsed.netloc:
        query = parse_qs(parsed.query)
        if query.get("v"):
            return query["v"][0]
        if parsed.path.startswith("/shorts/"):
            return parsed.path.split("/")[2]
    if re.fullmatch(r"[\w-]{11}", url):
        return url
    raise ValueError(f"Could not extract YouTube video id from {url}")


def youtube_info(url: str, out_path: Path) -> dict:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError("yt-dlp is required for YouTube metadata.") from exc

    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    apply_ytdlp_auth_options(options)
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    sanitized = {
        "id": info.get("id"),
        "webpage_url": info.get("webpage_url"),
        "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "duration": info.get("duration"),
        "duration_string": info.get("duration_string"),
        "upload_date": info.get("upload_date"),
        "availability": info.get("availability"),
        "live_status": info.get("live_status"),
        "view_count": info.get("view_count"),
        "description": info.get("description"),
        "heatmap": info.get("heatmap") or [],
        "subtitles": sorted((info.get("subtitles") or {}).keys()),
        "automatic_captions": sorted((info.get("automatic_captions") or {}).keys()),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding="utf-8")
    return sanitized


def build_failure_state(
    step: str,
    error: Exception,
    retry_command: str,
    retry_args: dict,
    url: str | None = None,
) -> dict:
    message = str(error) or error.__class__.__name__
    step_label = STEP_LABELS.get(step, step)
    return {
        "status": "failed",
        "step": step,
        "stepLabel": step_label,
        "url": url,
        "errorType": error.__class__.__name__,
        "message": message,
        "display": {
            "title": f"{step_label} 실패",
            "description": "작업을 완료하지 못했습니다. 주소 입력 화면으로 돌아가거나 같은 작업을 다시 실행할 수 있습니다.",
            "errorMessage": message,
            "actions": [
                {
                    "id": "restart",
                    "label": "처음으로",
                    "type": "navigate",
                    "target": "url_input",
                },
                {
                    "id": "retry",
                    "label": "다시 실행",
                    "type": "command",
                    "command": retry_command,
                    "args": retry_args,
                },
            ],
        },
    }


def write_failure_state(out_path: Path, state: dict) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def handle_cli_failure(
    args: argparse.Namespace,
    step: str,
    error: Exception,
    retry_command: str,
    retry_args: dict,
    url: str | None = None,
) -> int:
    failure_out = getattr(args, "failure_out", None)
    if not failure_out:
        raise error
    state = build_failure_state(step, error, retry_command, retry_args, url=url)
    write_failure_state(Path(failure_out), state)
    print(f"Failed: {state['display']['title']}")
    print(state["message"])
    print("Actions: 처음으로(restart), 다시 실행(retry)")
    print(f"Saved failure state to {failure_out}")
    return 1


def download_youtube(url: str, out_path: Path, max_height: int) -> Path:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError("yt-dlp is required for YouTube download.") from exc

    out_path.parent.mkdir(parents=True, exist_ok=True)
    output_template = str(out_path.with_suffix("")) + ".%(ext)s"
    options = {
        "format": (
            f"bv*[ext=mp4][height<={max_height}]+ba[ext=m4a]/"
            f"b[ext=mp4][height<={max_height}]/"
            f"bv*[height<={max_height}]+ba/b[height<={max_height}]/best"
        ),
        "merge_output_format": "mp4",
        "outtmpl": output_template,
        "noplaylist": True,
        "overwrites": True,
        "quiet": False,
        "no_warnings": False,
    }
    apply_ytdlp_auth_options(options)
    with YoutubeDL(options) as ydl:
        ydl.download([url])

    candidates = sorted(out_path.parent.glob(out_path.stem + ".*"))
    media_candidates = [
        candidate
        for candidate in candidates
        if candidate.suffix.lower() in {".mp4", ".m4v", ".webm", ".mkv"}
    ]
    if not media_candidates:
        raise FileNotFoundError(f"Could not find downloaded media for {url}")
    downloaded = media_candidates[0]
    if downloaded != out_path and downloaded.suffix.lower() == ".mp4":
        downloaded.replace(out_path)
        return out_path
    return downloaded


def fetch_youtube_transcript(url: str, out_path: Path, languages: list[str]) -> None:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise RuntimeError("youtube-transcript-api is required for transcript fetching.") from exc

    video_id = extract_youtube_id(url)
    api = YouTubeTranscriptApi()
    transcript = api.fetch(video_id, languages=languages)
    lines: list[str] = []
    for snippet in transcript:
        start = float(snippet.start)
        text = normalize_text(snippet.text.replace("\n", " "))
        if not text:
            continue
        lines.append(f"[{format_time(start)}] {text}")

    if not lines:
        raise RuntimeError(f"No transcript lines found for {video_id}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def load_candidate(path: Path, index: int) -> ClipCandidate:
    payload = json.loads(path.read_text(encoding="utf-8"))
    clips = payload.get("clips", [])
    if not clips:
        raise ValueError(f"No clips found in {path}")
    if index < 0 or index >= len(clips):
        raise ValueError(f"Index {index} is outside candidate range 0..{len(clips) - 1}")
    clip = clips[index]
    return ClipCandidate(
        start_sec=float(clip["start_sec"]),
        end_sec=float(clip["end_sec"]),
        duration_sec=float(clip["duration_sec"]),
        category=str(clip.get("category", "general")),
        title=str(clip["title"]),
        reason=str(clip["reason"]),
        hashtags=list(clip["hashtags"]),
        score=float(clip["score"]),
        source_text=str(clip.get("source_text", "")),
        most_replayed=bool(clip.get("most_replayed") or clip.get("mostReplayed", False)),
        replay_source=str(clip.get("replay_source") or clip.get("replaySource") or "analysis"),
        replay_score=(
            float(clip.get("replay_score") or clip.get("replayScore"))
            if clip.get("replay_score") is not None or clip.get("replayScore") is not None
            else None
        ),
    )


def load_candidates(path: Path) -> list[ClipCandidate]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    clips = payload.get("clips", [])
    candidates: list[ClipCandidate] = []
    for index in range(len(clips)):
        candidates.append(load_candidate(path, index))
    return candidates


def render_clip(
    input_path: Path,
    candidate: ClipCandidate,
    out_path: Path,
    layout: str,
    edit_config_path: Path | None = None,
    transcript_path: Path | None = None,
) -> None:
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required for rendering.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    edit_config = load_edit_config(edit_config_path) if edit_config_path else None
    clip_config = edit_config.get("clip", {}) if edit_config else {}
    start_sec = float(clip_config.get("startSec", candidate.start_sec))
    end_sec = float(clip_config.get("endSec", candidate.end_sec))
    duration = max(1.0, end_sec - start_sec)
    layout = str(edit_config.get("layout", layout)) if edit_config else layout

    video_filter = build_video_filter(layout, (edit_config or {}).get("cropConfig", {}))

    text_layers = get_render_text_layers(candidate, edit_config)
    static_overlay_path = create_text_overlay_image(text_layers, out_path.parent)
    subtitle_overlays = create_subtitle_overlays(
        transcript_path=transcript_path,
        start_sec=start_sec,
        end_sec=end_sec,
        duration=duration,
        directory=out_path.parent,
        enabled=bool((edit_config or {}).get("subtitleEnabled", True)),
        style=(edit_config or {}).get("subtitleStyle", {}),
    )
    overlay_paths = [static_overlay_path, *[item["path"] for item in subtitle_overlays]]
    filter_complex = build_overlay_filter(video_filter, subtitle_overlays)

    command = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start_sec),
        "-i",
        str(input_path),
        *overlay_input_args(overlay_paths),
        "-t",
        str(duration),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-threads",
        "2",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    try:
        subprocess.run(command, check=True)
    finally:
        for overlay_path in overlay_paths:
            overlay_path.unlink(missing_ok=True)


def overlay_input_args(paths: list[Path]) -> list[str]:
    args: list[str] = []
    for path in paths:
        args.extend(["-loop", "1", "-i", str(path)])
    return args


def build_overlay_filter(video_filter: str, subtitle_overlays: list[dict]) -> str:
    filters = [f"[0:v]{video_filter}[base]", "[base][1:v]overlay=0:0:format=auto[v1]"]
    current = "v1"
    for index, item in enumerate(subtitle_overlays, start=2):
        next_label = f"v{index}"
        start = float(item["start"])
        end = float(item["end"])
        filters.append(
            f"[{current}][{index}:v]overlay=0:0:format=auto:"
            f"enable='between(t,{start:.3f},{end:.3f})'[{next_label}]"
        )
        current = next_label
    filters[-1] = filters[-1].rsplit("[", 1)[0] + "[v]"
    return ";".join(filters)


def build_video_filter(layout: str, crop_config: dict | None = None) -> str:
    if layout != "crop":
        return (
            "scale=1080:1320:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:300:color=black,"
            "setsar=1"
        )

    crop_config = crop_config or {}
    zoom = clamp_float(crop_config.get("zoom", 1.0), 1.0, 2.0)
    focus_x = clamp_float(crop_config.get("focusX", 0.5), 0.0, 1.0)
    focus_y = clamp_float(crop_config.get("focusY", 0.5), 0.0, 1.0)
    scaled_width = int(round(1080 * zoom))
    scaled_height = int(round(1920 * zoom))
    return (
        f"scale={scaled_width}:{scaled_height}:force_original_aspect_ratio=increase,"
        f"crop=1080:1920:(iw-ow)*{focus_x:.3f}:(ih-oh)*{focus_y:.3f},"
        "setsar=1"
    )


def clamp_float(value: object, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))


def load_edit_config(path: Path | None) -> dict:
    if path is None:
        return {}
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def get_render_text_layers(candidate: ClipCandidate, edit_config: dict | None) -> list[dict]:
    if edit_config:
        layers = edit_config.get("textLayers", [])
        if isinstance(layers, list) and layers:
            return layers
    return [
        {
            "id": "title",
            "text": candidate.title,
            "visible": True,
            "x": 540,
            "y": 140,
            "anchor": "center",
            "fontSize": 54,
            "fontWeight": 800,
            "color": "#ffffff",
            "strokeColor": "#000000",
            "strokeWidth": 3,
        }
    ]


def create_text_overlay_image(text_layers: list[dict], directory: Path) -> Path:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError("Pillow is required for text overlay rendering.") from exc

    directory.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font_path = find_fontfile()

    for layer in text_layers:
        if not layer.get("visible", True):
            continue
        text = str(layer.get("text", "")).strip()
        if not text:
            continue

        font_size = int(layer.get("fontSize", 54))
        if font_path:
            font = ImageFont.truetype(str(font_path), font_size)
        else:
            font = ImageFont.load_default()

        max_width = int(layer.get("maxWidth", 920))
        lines = wrap_text(text, font, max_width, draw)
        line_gap = max(6, int(font_size * 0.16))
        line_heights = [text_bbox(draw, line, font)[3] for line in lines]
        total_height = sum(line_heights) + line_gap * max(len(lines) - 1, 0)

        x = float(layer.get("x", 540))
        y = float(layer.get("y", 140))
        anchor = str(layer.get("anchor", "center"))
        align = str(layer.get("align", "center"))
        fill = rgba_color(str(layer.get("color", "#ffffff")))
        stroke_fill = rgba_color(str(layer.get("strokeColor", "#000000")))
        stroke_width = int(layer.get("strokeWidth", 0))

        current_y = y
        if str(layer.get("verticalAnchor", "top")) == "center":
            current_y = y - total_height / 2

        for line, line_height in zip(lines, line_heights, strict=False):
            line_width = text_bbox(draw, line, font)[2]
            if anchor == "center" or align == "center":
                line_x = x - line_width / 2
            elif anchor == "right" or align == "right":
                line_x = x - line_width
            else:
                line_x = x
            draw.text(
                (line_x, current_y),
                line,
                font=font,
                fill=fill,
                stroke_width=stroke_width,
                stroke_fill=stroke_fill,
            )
            current_y += line_height + line_gap

    with tempfile.NamedTemporaryFile(
        prefix="text-overlay-",
        suffix=".png",
        dir=directory,
        delete=False,
    ) as handle:
        output_path = Path(handle.name)
    image.save(output_path)
    return output_path


def create_subtitle_overlays(
    transcript_path: Path | None,
    start_sec: float,
    end_sec: float,
    duration: float,
    directory: Path,
    enabled: bool = True,
    style: dict | None = None,
) -> list[dict]:
    if not enabled or transcript_path is None:
        return []
    if not transcript_path.exists():
        raise FileNotFoundError(transcript_path)

    segments = parse_transcript(transcript_path)
    overlays: list[dict] = []
    for segment in segments:
        if segment.end_sec <= start_sec or segment.start_sec >= end_sec:
            continue
        rel_start = max(0.0, segment.start_sec - start_sec)
        rel_end = min(duration, segment.end_sec - start_sec)
        if rel_end - rel_start < 0.25:
            continue
        overlay_path = create_subtitle_overlay_image(segment.text, directory, style or {})
        overlays.append({"path": overlay_path, "start": rel_start, "end": rel_end})
    return overlays


def create_subtitle_overlay_image(text: str, directory: Path, style: dict | None = None) -> Path:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError("Pillow is required for subtitle overlay rendering.") from exc

    style = style or {}
    directory.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font_path = find_fontfile()
    font_size = int(style.get("fontSize", 48))
    font = ImageFont.truetype(str(font_path), font_size) if font_path else ImageFont.load_default()
    max_width = int(style.get("maxWidth", 900))
    max_lines = max(1, int(style.get("maxLines", 2)))
    lines = wrap_text(text, font, max_width, draw)
    lines = lines[:max_lines]
    line_gap = max(6, int(style.get("lineGap", font_size * 0.18)))
    line_heights = [text_bbox(draw, line, font)[3] for line in lines]
    total_height = sum(line_heights) + line_gap * max(len(lines) - 1, 0)
    x = float(style.get("x", 540))
    y = float(style.get("y", 1220)) - total_height / 2
    anchor = str(style.get("anchor", "center"))
    align = str(style.get("align", "center"))
    fill = rgba_color(str(style.get("color", "#ffffff")))
    stroke_fill = rgba_color(str(style.get("strokeColor", "#000000")))
    stroke_width = int(style.get("strokeWidth", 3))
    background_enabled = bool(style.get("backgroundEnabled", True))
    background_fill = rgba_color(
        str(style.get("backgroundColor", "#000000")),
        alpha=int(style.get("backgroundOpacity", 172)),
    )
    padding_x = int(style.get("paddingX", 22))
    padding_y = int(style.get("paddingY", 10))
    radius = int(style.get("backgroundRadius", 14))

    for line, line_height in zip(lines, line_heights, strict=False):
        line_width = text_bbox(draw, line, font)[2]
        if anchor == "center" or align == "center":
            line_x = x - line_width / 2
        elif anchor == "right" or align == "right":
            line_x = x - line_width
        else:
            line_x = x
        if background_enabled:
            draw.rounded_rectangle(
                (
                    line_x - padding_x,
                    y - padding_y,
                    line_x + line_width + padding_x,
                    y + line_height + padding_y,
                ),
                radius=radius,
                fill=background_fill,
            )
        draw.text(
            (line_x, y),
            line,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
        y += line_height + line_gap

    with tempfile.NamedTemporaryFile(
        prefix="subtitle-overlay-",
        suffix=".png",
        dir=directory,
        delete=False,
    ) as handle:
        output_path = Path(handle.name)
    image.save(output_path)
    return output_path


def wrap_text(text: str, font: object, max_width: int, draw: object) -> list[str]:
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if text_bbox(draw, candidate, font)[2] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def text_bbox(draw: object, text: str, font: object) -> tuple[int, int, int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return left, top, right - left, bottom - top


def rgba_color(value: str, alpha: int = 255) -> tuple[int, int, int, int]:
    alpha = max(0, min(255, alpha))
    if value.startswith("#") and len(value) == 7:
        return (
            int(value[1:3], 16),
            int(value[3:5], 16),
            int(value[5:7], 16),
            alpha,
        )
    named = {
        "white": (255, 255, 255, alpha),
        "black": (0, 0, 0, alpha),
        "red": (255, 0, 0, alpha),
    }
    return named.get(value.lower(), (255, 255, 255, 255))


def build_drawtext_filter(layer: dict) -> str:
    fontfile = find_fontfile()
    text = escape_drawtext(str(layer.get("text", "")))
    x = float(layer.get("x", 540))
    y = float(layer.get("y", 140))
    anchor = str(layer.get("anchor", "center"))
    font_size = int(layer.get("fontSize", 54))
    color = ffmpeg_color(str(layer.get("color", "#ffffff")))
    stroke_color = ffmpeg_color(str(layer.get("strokeColor", "#000000")))
    stroke_width = int(layer.get("strokeWidth", 0))

    if anchor == "center":
        x_expr = f"{x:g}-text_w/2"
    elif anchor == "right":
        x_expr = f"{x:g}-text_w"
    else:
        x_expr = f"{x:g}"

    parts = [
        f"drawtext=text='{text}'",
        f"x={x_expr}",
        f"y={y:g}",
        f"fontsize={font_size}",
        f"fontcolor={color}",
        f"borderw={stroke_width}",
        f"bordercolor={stroke_color}",
    ]
    if fontfile:
        parts.append(f"fontfile='{escape_drawtext(str(fontfile))}'")
    return ":".join(parts)


def find_fontfile() -> Path | None:
    for font_path in FONT_CANDIDATES:
        if font_path.exists():
            return font_path
    return None


def ffmpeg_color(value: str) -> str:
    if value.startswith("#") and len(value) == 7:
        return "0x" + value[1:]
    return value


def probe_video(input_path: Path, out_path: Path) -> None:
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe is required for probing media.")

    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(input_path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    metadata = json.loads(result.stdout)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def read_media_metadata(input_path: Path) -> dict:
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe is required for validating media.")

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(input_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def validate_render(
    input_path: Path,
    out_path: Path,
    edit_config_path: Path | None = None,
    expected_width: int = 1080,
    expected_height: int = 1920,
    min_duration: float = 1.0,
    max_black_ratio: float = 0.92,
) -> dict:
    metadata = read_media_metadata(input_path)
    video_streams = [stream for stream in metadata.get("streams", []) if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in metadata.get("streams", []) if stream.get("codec_type") == "audio"]
    format_info = metadata.get("format", {})
    duration = float(format_info.get("duration", 0) or 0)
    checks: list[dict] = []

    video_stream = video_streams[0] if video_streams else {}
    checks.append(
        make_check(
            "video_stream",
            bool(video_streams),
            "Video stream is present.",
            "No video stream found.",
        )
    )
    checks.append(
        make_check(
            "audio_stream",
            bool(audio_streams),
            "Audio stream is present.",
            "No audio stream found.",
        )
    )
    checks.append(
        make_check(
            "dimensions",
            int(video_stream.get("width", 0) or 0) == expected_width
            and int(video_stream.get("height", 0) or 0) == expected_height,
            f"Video is {expected_width}x{expected_height}.",
            f"Expected {expected_width}x{expected_height}, got {video_stream.get('width')}x{video_stream.get('height')}.",
        )
    )
    checks.append(
        make_check(
            "duration",
            duration >= min_duration,
            f"Duration is {duration:.2f}s.",
            f"Duration {duration:.2f}s is shorter than {min_duration:.2f}s.",
        )
    )
    checks.append(
        make_check(
            "pixel_format",
            str(video_stream.get("pix_fmt", "")) == "yuv420p",
            "Pixel format is yuv420p.",
            f"Expected yuv420p, got {video_stream.get('pix_fmt')}.",
            warn_only=True,
        )
    )

    frame_samples = sample_frame_quality(input_path, duration, max_black_ratio)
    for sample in frame_samples:
        checks.append(
            make_check(
                f"frame_black_ratio_{sample['timeSec']:.2f}",
                sample["blackRatio"] <= max_black_ratio,
                f"Black ratio {sample['blackRatio']:.3f} at {sample['timeSec']:.2f}s.",
                f"Black ratio {sample['blackRatio']:.3f} exceeds {max_black_ratio:.3f} at {sample['timeSec']:.2f}s.",
            )
        )

    if edit_config_path:
        checks.extend(validate_edit_config_bounds(load_edit_config(edit_config_path)))

    status = "pass"
    if any(check["status"] == "fail" for check in checks):
        status = "fail"
    elif any(check["status"] == "warn" for check in checks):
        status = "warn"

    report = {
        "status": status,
        "input": str(input_path),
        "metadata": {
            "durationSec": round(duration, 3),
            "videoCodec": video_stream.get("codec_name"),
            "audioCodec": audio_streams[0].get("codec_name") if audio_streams else None,
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "pixFmt": video_stream.get("pix_fmt"),
        },
        "frameSamples": frame_samples,
        "checks": checks,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def make_check(name: str, passed: bool, pass_message: str, fail_message: str, warn_only: bool = False) -> dict:
    if passed:
        return {"name": name, "status": "pass", "message": pass_message}
    return {"name": name, "status": "warn" if warn_only else "fail", "message": fail_message}


def sample_frame_quality(input_path: Path, duration: float, max_black_ratio: float) -> list[dict]:
    if duration <= 0:
        return []
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required for frame validation.")
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required for frame validation.") from exc

    sample_times = sorted({max(0.0, min(duration - 0.05, duration * ratio)) for ratio in (0.2, 0.5, 0.8)})
    samples: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="render-qa-") as temp_dir:
        temp_path = Path(temp_dir)
        for index, sample_time in enumerate(sample_times, start=1):
            frame_path = temp_path / f"frame-{index:02d}.png"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    f"{sample_time:.3f}",
                    "-i",
                    str(input_path),
                    "-frames:v",
                    "1",
                    str(frame_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            image = Image.open(frame_path).convert("RGB").resize((180, 320))
            pixels = list(image.getdata())
            black_pixels = sum(1 for red, green, blue in pixels if red < 16 and green < 16 and blue < 16)
            brightness = sum((red + green + blue) / 3 for red, green, blue in pixels) / max(len(pixels), 1)
            samples.append(
                {
                    "timeSec": round(sample_time, 3),
                    "blackRatio": round(black_pixels / max(len(pixels), 1), 4),
                    "meanBrightness": round(brightness, 2),
                    "threshold": max_black_ratio,
                }
            )
    return samples


def validate_edit_config_bounds(edit_config: dict) -> list[dict]:
    checks: list[dict] = []
    bounds = estimate_text_bounds(edit_config.get("textLayers", []))
    for item in bounds:
        left, top, right, bottom = item["bounds"]
        checks.append(
            make_check(
                f"text_bounds_{item['id']}",
                left >= 0 and top >= 0 and right <= 1080 and bottom <= 1920,
                f"Text layer {item['id']} stays inside the canvas.",
                f"Text layer {item['id']} may leave the canvas: {item['bounds']}.",
            )
        )

    for index, current in enumerate(bounds):
        for other in bounds[index + 1 :]:
            overlap_ratio = bounds_overlap_ratio(current["bounds"], other["bounds"])
            checks.append(
                make_check(
                    f"text_overlap_{current['id']}_{other['id']}",
                    overlap_ratio <= 0.15,
                    f"Text layers {current['id']} and {other['id']} do not overlap.",
                    f"Text layers {current['id']} and {other['id']} overlap by {overlap_ratio:.2f}.",
                    warn_only=True,
                )
            )
    return checks


def estimate_text_bounds(text_layers: list[dict]) -> list[dict]:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError("Pillow is required for text validation.") from exc

    image = Image.new("RGB", (1080, 1920))
    draw = ImageDraw.Draw(image)
    font_path = find_fontfile()
    bounds: list[dict] = []
    for layer in text_layers:
        if not layer.get("visible", True):
            continue
        text = str(layer.get("text", "")).strip()
        if not text:
            continue
        font_size = int(layer.get("fontSize", 54))
        font = ImageFont.truetype(str(font_path), font_size) if font_path else ImageFont.load_default()
        lines = wrap_text(text, font, int(layer.get("maxWidth", 920)), draw)
        if not lines:
            continue
        line_gap = max(6, int(font_size * 0.16))
        widths = [text_bbox(draw, line, font)[2] for line in lines]
        heights = [text_bbox(draw, line, font)[3] for line in lines]
        width = max(widths)
        height = sum(heights) + line_gap * max(len(lines) - 1, 0)
        x = float(layer.get("x", 540))
        y = float(layer.get("y", 140))
        anchor = str(layer.get("anchor", "center"))
        align = str(layer.get("align", "center"))
        if anchor == "center" or align == "center":
            left = x - width / 2
        elif anchor == "right" or align == "right":
            left = x - width
        else:
            left = x
        top = y
        if str(layer.get("verticalAnchor", "top")) == "center":
            top = y - height / 2
        bounds.append(
            {
                "id": str(layer.get("id", layer.get("type", "text"))),
                "bounds": [round(left, 2), round(top, 2), round(left + width, 2), round(top + height, 2)],
            }
        )
    return bounds


def bounds_overlap_ratio(first: list[float], second: list[float]) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    if right <= left or bottom <= top:
        return 0.0
    overlap = (right - left) * (bottom - top)
    first_area = max((first[2] - first[0]) * (first[3] - first[1]), 1.0)
    second_area = max((second[2] - second[0]) * (second[3] - second[1]), 1.0)
    return round(overlap / min(first_area, second_area), 4)


def extract_audio(input_path: Path, out_path: Path) -> None:
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required for extracting audio.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(out_path),
    ]
    subprocess.run(command, check=True)


def generate_sample_video(out_path: Path, duration: int) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required for generating sample media.")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size=1280x720:rate=30:duration={duration}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={duration}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "28",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-pix_fmt",
        "yuv420p",
        str(out_path),
    ]
    subprocess.run(command, check=True)


def write_default_edit_config(candidate: ClipCandidate, out_path: Path, channel: str) -> None:
    payload = {
        "canvas": {"width": 1080, "height": 1920},
        "layout": "letterbox",
        "safeZonePreset": "youtube_shorts",
        "showSafeZone": True,
        "showGrid": True,
        "cropConfig": {
            "trackingMode": "manual",
            "focusX": 0.5,
            "focusY": 0.5,
            "zoom": 1.0,
            "speakerTrackingEnabled": False,
            "faceTrackingEnabled": False,
        },
        "subtitleEnabled": True,
        "subtitleStyle": {
            "fontFamily": DEFAULT_FONT_FAMILY,
            "fontSize": 48,
            "fontWeight": 700,
            "color": "#ffffff",
            "strokeColor": "#000000",
            "strokeWidth": 3,
            "backgroundEnabled": True,
            "backgroundColor": "#000000",
            "backgroundOpacity": 172,
            "backgroundRadius": 14,
            "paddingX": 22,
            "paddingY": 10,
            "maxWidth": 900,
            "maxLines": 2,
            "lineGap": 8,
            "x": 540,
            "y": 1220,
            "anchor": "center",
            "align": "center",
            "positionPreset": "lower",
        },
        "clip": {
            "startSec": candidate.start_sec,
            "endSec": candidate.end_sec,
            "durationSec": candidate.duration_sec,
        },
        "textLayers": [
            {
                "id": "title",
                "type": "title",
                "text": candidate.title,
                "visible": True,
                "x": 540,
                "y": 150,
                "anchor": "center",
                "fontFamily": DEFAULT_FONT_FAMILY,
                "fontSize": 72,
                "fontWeight": 800,
                "color": "#ffffff",
                "strokeColor": "#000000",
                "strokeWidth": 4,
                "backgroundEnabled": False,
                "backgroundColor": "#000000",
                "maxWidth": 920,
                "align": "center",
            },
            {
                "id": "channel",
                "type": "channel",
                "text": channel,
                "visible": True,
                "x": 540,
                "y": 1740,
                "anchor": "center",
                "fontFamily": DEFAULT_FONT_FAMILY,
                "fontSize": 42,
                "fontWeight": 700,
                "color": "#ffffff",
                "strokeColor": "#000000",
                "strokeWidth": 3,
                "backgroundEnabled": False,
                "backgroundColor": "#000000",
                "maxWidth": 860,
                "align": "center",
            },
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def render_all_clips(
    input_path: Path,
    candidates_path: Path,
    out_dir: Path,
    edit_config_dir: Path,
    channel: str,
    layout: str,
    limit: int | None,
    transcript_path: Path | None,
) -> list[dict]:
    candidates = load_candidates(candidates_path)
    if limit is not None:
        candidates = candidates[:limit]

    out_dir.mkdir(parents=True, exist_ok=True)
    edit_config_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []

    for index, candidate in enumerate(candidates, start=1):
        stem = f"clip-{index:03d}"
        edit_config_path = edit_config_dir / f"{stem}.json"
        output_path = out_dir / f"{stem}.mp4"
        write_default_edit_config(candidate, edit_config_path, channel)
        edit_config = load_edit_config(edit_config_path)
        edit_config["layout"] = layout
        edit_config_path.write_text(json.dumps(edit_config, ensure_ascii=False, indent=2), encoding="utf-8")
        render_clip(input_path, candidate, output_path, layout, edit_config_path, transcript_path)
        manifest.append(
            {
                "index": index - 1,
                "title": candidate.title,
                "category": candidate.category,
                "startSec": candidate.start_sec,
                "endSec": candidate.end_sec,
                "durationSec": candidate.duration_sec,
                "hashtags": candidate.hashtags,
                "editConfig": str(edit_config_path),
                "output": str(output_path),
                "subtitles": transcript_path is not None,
                "transcript": str(transcript_path) if transcript_path else None,
            }
        )

    return manifest


def escape_drawtext(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")


def cmd_probe(args: argparse.Namespace) -> int:
    probe_video(Path(args.input), Path(args.out))
    print(f"Saved metadata to {args.out}")
    return 0


def cmd_youtube_info(args: argparse.Namespace) -> int:
    try:
        info = youtube_info(args.url, Path(args.out))
        print(f"Saved YouTube metadata to {args.out}")
        print(f"title={info.get('title')}")
        print(f"duration={info.get('duration_string') or info.get('duration')}")
        return 0
    except Exception as exc:
        return handle_cli_failure(
            args,
            step="youtube_info",
            error=exc,
            retry_command="youtube-info",
            retry_args={"url": args.url, "out": args.out},
            url=args.url,
        )


def cmd_download_youtube(args: argparse.Namespace) -> int:
    try:
        output = download_youtube(args.url, Path(args.out), args.max_height)
        print(f"Saved YouTube video to {output}")
        return 0
    except Exception as exc:
        return handle_cli_failure(
            args,
            step="download_youtube",
            error=exc,
            retry_command="download-youtube",
            retry_args={"url": args.url, "out": args.out, "maxHeight": args.max_height},
            url=args.url,
        )


def cmd_fetch_transcript(args: argparse.Namespace) -> int:
    try:
        languages = [language.strip() for language in args.languages.split(",") if language.strip()]
        fetch_youtube_transcript(args.url, Path(args.out), languages)
        print(f"Saved YouTube transcript to {args.out}")
        return 0
    except Exception as exc:
        return handle_cli_failure(
            args,
            step="fetch_transcript",
            error=exc,
            retry_command="fetch-transcript",
            retry_args={"url": args.url, "out": args.out, "languages": args.languages},
            url=args.url,
        )


def cmd_extract_audio(args: argparse.Namespace) -> int:
    extract_audio(Path(args.input), Path(args.out))
    print(f"Saved audio to {args.out}")
    return 0


def cmd_generate_sample(args: argparse.Namespace) -> int:
    generate_sample_video(Path(args.out), args.duration)
    print(f"Saved sample video to {args.out}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    segments = parse_transcript(Path(args.transcript))
    candidates = analyze_segments(
        segments,
        max_candidates=args.max_candidates,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
    )
    write_candidates(candidates, Path(args.out))
    print(f"Saved {len(candidates)} candidates to {args.out}")
    for index, candidate in enumerate(candidates, start=1):
        print(
            f"{index}. {format_time(candidate.start_sec)}-{format_time(candidate.end_sec)} "
            f"{candidate.title} score={candidate.score}"
        )
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    candidate = load_candidate(Path(args.candidate), args.index)
    edit_config_path = Path(args.edit_config) if args.edit_config else None
    transcript_path = Path(args.transcript) if args.transcript else None
    render_clip(Path(args.input), candidate, Path(args.out), args.layout, edit_config_path, transcript_path)
    print(f"Rendered {args.out}")
    return 0


def cmd_init_edit(args: argparse.Namespace) -> int:
    candidate = load_candidate(Path(args.candidate), args.index)
    write_default_edit_config(candidate, Path(args.out), args.channel)
    print(f"Saved edit config to {args.out}")
    return 0


def cmd_render_all(args: argparse.Namespace) -> int:
    manifest = render_all_clips(
        input_path=Path(args.input),
        candidates_path=Path(args.candidate),
        out_dir=Path(args.out_dir),
        edit_config_dir=Path(args.edit_config_dir),
        channel=args.channel,
        layout=args.layout,
        limit=args.limit,
        transcript_path=Path(args.transcript) if args.transcript else None,
    )
    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"renders": manifest}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Rendered {len(manifest)} clips")
    print(f"Saved manifest to {manifest_path}")
    return 0


def cmd_validate_render(args: argparse.Namespace) -> int:
    report = validate_render(
        input_path=Path(args.input),
        out_path=Path(args.out),
        edit_config_path=Path(args.edit_config) if args.edit_config else None,
        expected_width=args.expected_width,
        expected_height=args.expected_height,
        min_duration=args.min_duration,
        max_black_ratio=args.max_black_ratio,
    )
    print(f"Validation {report['status']}: {args.input}")
    print(f"Saved validation report to {args.out}")
    return 1 if report["status"] == "fail" else 0


def format_time(seconds: float) -> str:
    minute = int(seconds // 60)
    second = int(seconds % 60)
    return f"{minute:02d}:{second:02d}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clipper_pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    probe = subparsers.add_parser("probe", help="Save ffprobe metadata for a video.")
    probe.add_argument("--input", required=True)
    probe.add_argument("--out", required=True)
    probe.set_defaults(func=cmd_probe)

    yt_info = subparsers.add_parser("youtube-info", help="Save metadata for a YouTube URL.")
    yt_info.add_argument("--url", required=True)
    yt_info.add_argument("--out", required=True)
    yt_info.add_argument("--failure-out")
    yt_info.set_defaults(func=cmd_youtube_info)

    yt_download = subparsers.add_parser("download-youtube", help="Download a YouTube URL as local media.")
    yt_download.add_argument("--url", required=True)
    yt_download.add_argument("--out", required=True)
    yt_download.add_argument("--max-height", type=int, default=720)
    yt_download.add_argument("--failure-out")
    yt_download.set_defaults(func=cmd_download_youtube)

    yt_transcript = subparsers.add_parser("fetch-transcript", help="Fetch timestamped YouTube transcript text.")
    yt_transcript.add_argument("--url", required=True)
    yt_transcript.add_argument("--out", required=True)
    yt_transcript.add_argument("--languages", default="ko,en")
    yt_transcript.add_argument("--failure-out")
    yt_transcript.set_defaults(func=cmd_fetch_transcript)

    extract = subparsers.add_parser("extract-audio", help="Extract 16 kHz mono WAV audio from a video.")
    extract.add_argument("--input", required=True)
    extract.add_argument("--out", required=True)
    extract.set_defaults(func=cmd_extract_audio)

    sample = subparsers.add_parser("generate-sample", help="Generate a synthetic sample video for pipeline tests.")
    sample.add_argument("--out", required=True)
    sample.add_argument("--duration", type=int, default=130)
    sample.set_defaults(func=cmd_generate_sample)

    analyze = subparsers.add_parser("analyze", help="Generate clip candidates from a timestamped transcript.")
    analyze.add_argument("--transcript", required=True)
    analyze.add_argument("--out", required=True)
    analyze.add_argument("--max-candidates", type=int, default=6)
    analyze.add_argument("--min-duration", type=int, default=20)
    analyze.add_argument("--max-duration", type=int, default=60)
    analyze.set_defaults(func=cmd_analyze)

    render = subparsers.add_parser("render", help="Render one candidate into a 9:16 MP4.")
    render.add_argument("--input", required=True)
    render.add_argument("--candidate", required=True)
    render.add_argument("--index", type=int, default=0)
    render.add_argument("--out", required=True)
    render.add_argument("--layout", choices=["letterbox", "crop"], default="letterbox")
    render.add_argument("--edit-config")
    render.add_argument("--transcript")
    render.set_defaults(func=cmd_render)

    render_all = subparsers.add_parser("render-all", help="Render multiple candidates and save a manifest.")
    render_all.add_argument("--input", required=True)
    render_all.add_argument("--candidate", required=True)
    render_all.add_argument("--out-dir", required=True)
    render_all.add_argument("--edit-config-dir", required=True)
    render_all.add_argument("--manifest", required=True)
    render_all.add_argument("--channel", default="CHANNEL")
    render_all.add_argument("--layout", choices=["letterbox", "crop"], default="letterbox")
    render_all.add_argument("--limit", type=int)
    render_all.add_argument("--transcript")
    render_all.set_defaults(func=cmd_render_all)

    validate = subparsers.add_parser("validate-render", help="Validate rendered MP4 quality and write a JSON report.")
    validate.add_argument("--input", required=True)
    validate.add_argument("--out", required=True)
    validate.add_argument("--edit-config")
    validate.add_argument("--expected-width", type=int, default=1080)
    validate.add_argument("--expected-height", type=int, default=1920)
    validate.add_argument("--min-duration", type=float, default=1.0)
    validate.add_argument("--max-black-ratio", type=float, default=0.92)
    validate.set_defaults(func=cmd_validate_render)

    init_edit = subparsers.add_parser("init-edit", help="Create a default edit config for one candidate.")
    init_edit.add_argument("--candidate", required=True)
    init_edit.add_argument("--index", type=int, default=0)
    init_edit.add_argument("--channel", default="CHANNEL")
    init_edit.add_argument("--out", required=True)
    init_edit.set_defaults(func=cmd_init_edit)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
