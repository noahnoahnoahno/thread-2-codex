from __future__ import annotations

import math
import re
from collections import Counter

from .models import ClipCandidate, TranscriptSegment


HOOK_PATTERNS: dict[str, list[str]] = {
    "surprise": ["대박", "충격", "진짜", "와", "어메이징", "놀라", "가능한가", "미쳤"],
    "utility": ["방법", "툴", "자동", "효율", "만들", "분석", "추출", "다운로드", "생성"],
    "question": ["?", "뭔가요", "건가요", "있나요", "좋을까요", "왜", "어떻게"],
    "contrast": ["근데", "하지만", "반대로", "문제", "리스크", "실패", "오히려"],
    "specificity": ["3", "5", "6", "10", "15", "30", "60", "단계", "초", "개", "%", "억", "만"],
    "emotion": ["무료", "구독자", "신청", "필요", "좋", "유용", "중요", "핵심", "빡", "화"],
    "proof": ["수익", "조회수", "인증", "달성", "입금", "성과", "벌", "뷰", "구독자"],
}

PRODUCTION_SIGNAL_PATTERNS: dict[str, list[str]] = {
    "proof": ["수익", "조회수", "인증", "달성", "입금", "벌", "돈", "월", "억", "만원", "달러", "뷰"],
    "conflict": ["빡", "화", "실패", "수습", "문제", "안 되겠다", "삭제", "항소", "위험", "벌을"],
    "utility": ["방법", "꿀팁", "단축키", "사전 설정", "프리셋", "무음", "자막", "TTS", "편집"],
    "tts_opportunity": ["TTS", "표정", "말이 없", "슬로우", "감정", "떠오", "확대"],
    "social_proof": ["이분", "분들", "배우", "성과", "인증", "감사", "후기", "직장인", "50대", "육아"],
    "rights_sensitive": ["저작권", "출처", "허락", "채널 삭제", "재사용", "스포", "잡", "신고"],
    "novelty": ["신선", "요즘", "핫한", "처음", "비밀", "새", "다르게"],
}

PROOF_RE = re.compile(
    r"\d[\d,.\s]*(?:억|천|만|원|달러|뷰|개|초|시간|년|개월|명|%)|월\s*\d|월천"
)

STOPWORDS = {
    "네",
    "그",
    "이",
    "저",
    "것",
    "수",
    "좀",
    "아",
    "어",
    "저희",
    "여러분",
    "있",
    "하",
    "되",
    "같",
    "합니다",
    "맞습니다",
}


def recommend_clips(
    segments: list[TranscriptSegment],
    count: int = 6,
    min_duration: float = 18,
    max_duration: float = 60,
) -> list[ClipCandidate]:
    if not segments:
        return []

    windows = build_windows(segments, min_duration, max_duration)
    scored = [score_window(window, index) for index, window in enumerate(windows)]
    scored.sort(key=lambda item: item.score, reverse=True)

    selected: list[ClipCandidate] = []
    for candidate in scored:
        if overlaps_existing(candidate, selected):
            continue
        selected.append(candidate)
        if len(selected) >= count:
            break

    selected.sort(key=lambda item: item.start_sec)
    return selected


def build_windows(
    segments: list[TranscriptSegment],
    min_duration: float,
    max_duration: float,
) -> list[list[TranscriptSegment]]:
    windows: list[list[TranscriptSegment]] = []
    for start_index in range(0, len(segments), 2):
        window: list[TranscriptSegment] = []
        for segment in segments[start_index:]:
            window.append(segment)
            duration = window[-1].end_sec - window[0].start_sec
            if duration >= min_duration:
                windows.append(trim_to_sentence(window, max_duration))
            if duration >= max_duration:
                break
    return windows


def trim_to_sentence(
    window: list[TranscriptSegment],
    max_duration: float,
) -> list[TranscriptSegment]:
    trimmed: list[TranscriptSegment] = []
    for segment in window:
        if trimmed and segment.end_sec - trimmed[0].start_sec > max_duration:
            break
        trimmed.append(segment)
    return trimmed or window[:1]


def score_window(window: list[TranscriptSegment], index: int) -> ClipCandidate:
    text = " ".join(segment.text for segment in window)
    duration = max(1.0, window[-1].end_sec - window[0].start_sec)
    hook_hits = hook_type_hits(text)
    production_signals = production_signal_hits(text, window)
    hook_score = sum(hook_hits.values()) * 1.4
    production_score = production_signal_score(production_signals)
    density_score = min(10.0, len(text) / duration / 2.4)
    dialog_score = min(6.0, count_dialog_turns(window) / duration * 20)
    keyword_score = repeated_keyword_score(text)
    length_score = length_preference_score(duration)
    start_bonus = 1.2 if index < 16 else 0.0
    score = (
        hook_score
        + production_score
        + density_score
        + dialog_score
        + keyword_score
        + length_score
        + start_bonus
    )
    confidence = 1 / (1 + math.exp(-(score - 17) / 4.5))

    title = make_title(text)
    reason = make_reason(hook_hits, production_signals, duration)
    hashtags = make_hashtags(text, hook_hits, production_signals)
    return ClipCandidate(
        start_sec=round(window[0].start_sec, 2),
        end_sec=round(window[-1].end_sec, 2),
        title=title,
        reason=reason,
        hashtags=hashtags,
        confidence=round(confidence, 2),
        score=round(score, 2),
        transcript=text,
        hook_types=sorted(hook_hits, key=hook_hits.get, reverse=True),
        production_signals=production_signals,
        edit_notes=make_edit_notes(text, production_signals, duration),
        review_warnings=make_review_warnings(text, production_signals),
    )


def hook_type_hits(text: str) -> dict[str, int]:
    hits: dict[str, int] = {}
    for hook_type, patterns in HOOK_PATTERNS.items():
        count = sum(text.count(pattern) for pattern in patterns)
        if count:
            hits[hook_type] = count
    return hits


def production_signal_hits(
    text: str,
    window: list[TranscriptSegment],
) -> dict[str, int]:
    hits: dict[str, int] = {}
    for signal, patterns in PRODUCTION_SIGNAL_PATTERNS.items():
        count = sum(text.count(pattern) for pattern in patterns)
        if count:
            hits[signal] = count

    proof_count = len(PROOF_RE.findall(text))
    if proof_count:
        hits["proof"] = hits.get("proof", 0) + proof_count

    short_reactions = sum(1 for segment in window if len(segment.text) <= 10)
    if short_reactions >= 2:
        hits["reaction_density"] = short_reactions

    return dict(sorted(hits.items(), key=lambda item: item[1], reverse=True))


def production_signal_score(signals: dict[str, int]) -> float:
    weights = {
        "proof": 1.7,
        "conflict": 1.4,
        "utility": 1.5,
        "tts_opportunity": 1.1,
        "social_proof": 1.3,
        "rights_sensitive": 0.2,
        "novelty": 1.0,
        "reaction_density": 0.9,
    }
    score = sum(min(count, 5) * weights.get(signal, 0.8) for signal, count in signals.items())
    return min(12.0, score)


def count_dialog_turns(window: list[TranscriptSegment]) -> int:
    joined = " ".join(segment.text for segment in window)
    explicit_turns = joined.count(">>")
    short_ack_turns = sum(1 for segment in window if len(segment.text) <= 12)
    return explicit_turns + short_ack_turns


def repeated_keyword_score(text: str) -> float:
    tokens = [
        token
        for token in re.findall(r"[가-힣A-Za-z0-9]{2,}", text)
        if token not in STOPWORDS
    ]
    if not tokens:
        return 0.0
    counts = Counter(tokens)
    repeated = sum(count for _, count in counts.most_common(8) if count >= 2)
    return min(8.0, repeated * 0.8)


def length_preference_score(duration: float) -> float:
    if 25 <= duration <= 45:
        return 5.0
    if 18 <= duration < 25 or 45 < duration <= 60:
        return 3.0
    return 0.8


def overlaps_existing(candidate: ClipCandidate, selected: list[ClipCandidate]) -> bool:
    for item in selected:
        overlap = max(0.0, min(candidate.end_sec, item.end_sec) - max(candidate.start_sec, item.start_sec))
        shorter = min(candidate.duration_sec, item.duration_sec)
        if shorter and overlap / shorter > 0.45:
            return True
    return False


def make_title(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?。])\s+|(?<=요)\s+|(?<=다)\s+", cleaned)
    for sentence in sentences:
        sentence = sentence.strip()
        if 12 <= len(sentence) <= 44:
            return sentence
    return cleaned[:42].rstrip() + ("..." if len(cleaned) > 42 else "")


def make_reason(
    hook_hits: dict[str, int],
    production_signals: dict[str, int],
    duration: float,
) -> str:
    labels = {
        "surprise": "감탄/놀라움 표현",
        "utility": "실용 정보",
        "question": "질문형 후킹",
        "contrast": "문제 제기나 반전",
        "specificity": "숫자와 구체성",
        "emotion": "감정/혜택 표현",
        "proof": "성과/인증 신호",
    }
    production_labels = {
        "proof": "성과 숫자",
        "conflict": "갈등/감정 변화",
        "utility": "실무 팁",
        "tts_opportunity": "TTS 삽입 여지",
        "social_proof": "사회적 증거",
        "novelty": "신선한 소재",
        "reaction_density": "짧은 리액션",
    }
    ranked = sorted(hook_hits, key=hook_hits.get, reverse=True)
    ranked_signals = [
        signal
        for signal in sorted(production_signals, key=production_signals.get, reverse=True)
        if signal != "rights_sensitive"
    ]
    if ranked:
        reasons = ", ".join(labels[item] for item in ranked[:3])
        if ranked_signals:
            signal_text = ", ".join(production_labels[item] for item in ranked_signals[:2])
            return f"{reasons}이 뚜렷하고 {signal_text}가 있어 {duration:.0f}초 안에 독립 클립으로 소비하기 좋습니다."
        return f"{reasons}이 뚜렷하고 {duration:.0f}초 안에 독립 클립으로 소비하기 좋습니다."
    return f"발화 밀도가 높고 {duration:.0f}초 안에 하나의 메시지로 정리됩니다."


def make_hashtags(
    text: str,
    hook_hits: dict[str, int],
    production_signals: dict[str, int],
) -> list[str]:
    hashtags = ["#쇼츠", "#AI편집"]
    if "utility" in hook_hits:
        hashtags.append("#영상편집")
    if "question" in hook_hits:
        hashtags.append("#콘텐츠제작")
    if "emotion" in hook_hits:
        hashtags.append("#유튜브성장")
    if "proof" in production_signals:
        hashtags.append("#수익인증")
    if "social_proof" in production_signals:
        hashtags.append("#부업")
    if "무료" in text:
        hashtags.append("#무료툴")
    return list(dict.fromkeys(hashtags))[:5]


def make_edit_notes(
    text: str,
    production_signals: dict[str, int],
    duration: float,
) -> list[str]:
    notes: list[str] = []
    if "proof" in production_signals:
        notes.append("숫자/성과 표현은 첫 자막이나 제목에 유지하세요.")
    if "conflict" in production_signals:
        notes.append("감정이 터지는 지점부터 시작하도록 앞 설명을 짧게 줄이세요.")
    if "utility" in production_signals:
        notes.append("단축키, 설정값, 작업 순서를 화면 자막으로 명확히 보여주세요.")
    if "tts_opportunity" in production_signals:
        notes.append("말이 비는 표정 구간에는 짧은 TTS로 감정이나 맥락을 보강하세요.")
    if "reaction_density" in production_signals:
        notes.append("짧은 리액션은 살리고 침묵과 반복어를 우선 제거하세요.")
    if duration > 45:
        notes.append("45초가 넘으므로 중간 설명을 한 번 더 압축할 수 있는지 확인하세요.")
    if not notes:
        notes.append("첫 1초 안에 볼 이유가 드러나도록 시작점을 검수하세요.")
    return notes


def make_review_warnings(
    text: str,
    production_signals: dict[str, int],
) -> list[str]:
    warnings: list[str] = []
    if "rights_sensitive" in production_signals:
        warnings.append("저작권, 출처, 재사용 언급이 있으므로 원본 권한과 플랫폼 약관을 사람이 확인해야 합니다.")
    if "proof" in production_signals and any(token in text for token in ("수익", "입금", "벌", "달성")):
        warnings.append("수익/성과 표현은 과장 없이 원문 맥락과 증빙 가능성을 확인하세요.")
    if "TTS" in text:
        warnings.append("TTS 문구가 실제 출연자 발언처럼 오해되지 않게 표시하세요.")
    return warnings
