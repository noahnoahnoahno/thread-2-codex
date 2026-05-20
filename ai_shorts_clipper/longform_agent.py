from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


RIGHTS_DECISIONS = {
    "reference_only",
    "allowed_import",
    "needs_permission",
    "produce_original",
    "blocked",
}


@dataclass(frozen=True)
class BenchmarkReference:
    title: str
    channel_name: str = ""
    url: str = ""
    platform: str = "youtube"
    views: int | None = None
    channel_age_days: int | None = None
    published_within_days: int | None = None
    topic: str = ""
    hook_type: str = ""
    proof_numbers: list[str] = field(default_factory=list)
    comment_energy: int = 0
    visual_style: str = ""
    rights_decision: str = "reference_only"
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.rights_decision not in RIGHTS_DECISIONS:
            raise ValueError(f"Unknown rights decision: {self.rights_decision}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReferenceScore:
    reference: BenchmarkReference
    score: int
    signals: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference.to_dict(),
            "score": self.score,
            "signals": self.signals,
            "warnings": self.warnings,
        }


@dataclass(frozen=True)
class EconomyLongformBrief:
    topic: str
    target_viewer: str
    viewer_question: str
    selected_angle: str
    tutorial_analysis: dict[str, Any]
    selected_references: list[ReferenceScore]
    rejected_references: list[ReferenceScore]
    research_checklist: list[str]
    chapter_outline: list[str]
    prompts: dict[str, str]
    production_handoff: list[str]
    review_warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "target_viewer": self.target_viewer,
            "viewer_question": self.viewer_question,
            "selected_angle": self.selected_angle,
            "tutorial_analysis": self.tutorial_analysis,
            "selected_references": [item.to_dict() for item in self.selected_references],
            "rejected_references": [item.to_dict() for item in self.rejected_references],
            "research_checklist": self.research_checklist,
            "chapter_outline": self.chapter_outline,
            "prompts": self.prompts,
            "production_handoff": self.production_handoff,
            "review_warnings": self.review_warnings,
        }


def analyze_tutorial_transcript(transcript: str) -> dict[str, Any]:
    text = " ".join(transcript.split())
    stages = [
        {
            "stage": "topic_selection",
            "finding": "핫한 경제 뉴스에서 출발하고, 시크릿 모드 YouTube 검색으로 기존 알고리즘 영향을 줄입니다.",
            "automation": "뉴스 후보 5개, 검색어, 필터 조건, 선택 이유를 Research Brief에 저장합니다.",
        },
        {
            "stage": "benchmark_reference",
            "finding": "이번 달/인기도/조회수 기준으로 이미 검증된 영상 구조를 학습합니다.",
            "automation": "조회수, 채널 연령, 제목 프레임, 후킹 유형, 댓글 질문을 BenchmarkReference로 기록합니다.",
        },
        {
            "stage": "script_generation",
            "finding": "한 번에 긴 원고를 쓰지 않고 소재 분석, 3막 8장 뼈대, 장별 본문으로 나눕니다.",
            "automation": "outline prompt와 chapter prompt를 분리해 15-30분 원고의 품질 하락을 줄입니다.",
        },
        {
            "stage": "image_prompting",
            "finding": "완성 원고를 문장 단위 이미지 프롬프트로 변환하고 영어 프롬프트만 줄바꿈 정리합니다.",
            "automation": "문장별 visual beat, image prompt, style, ratio를 CSV/JSON으로 내보냅니다.",
        },
        {
            "stage": "voice_and_editing",
            "finding": "AI TTS와 자동 자막 나누기, 이미지 배치로 얼굴/목소리 노출 없는 제작 흐름을 만듭니다.",
            "automation": "TTS voice, subtitle length, asset folder, intro motion 여부를 production handoff로 저장합니다.",
        },
        {
            "stage": "intro_motion",
            "finding": "도입 30초는 정지 이미지보다 루프 영상으로 이탈을 줄이는 구조를 권합니다.",
            "automation": "초반 5개 이미지에 motion_required 플래그를 붙입니다.",
        },
    ]
    detected_signals = {
        "proof_numbers": sum(token in text for token in ("100만", "127만", "296만", "수천만", "15분", "70시간")),
        "free_tool_positioning": "무료" in text,
        "low_barrier_claim": any(token in text for token in ("왕초보", "클릭 몇 번", "편집도 못")),
        "rights_sensitive": any(token in text for token in ("재사용", "수익화", "다운로드")),
        "income_claim": any(token in text for token in ("수익", "수천만", "돈", "광고")),
    }
    return {
        "format": "AI 경제 롱폼 제작 튜토리얼",
        "core_thesis": "핫뉴스 기반 주제 선정, 성공 영상 구조 분석, 장별 원고 생성, 이미지/TTS/편집 자동화를 묶어 진입장벽을 낮춘다는 메시지입니다.",
        "retention_pattern": [
            "성과 숫자로 시작",
            "초보자의 불안을 대신 말하기",
            "무료 자료와 자동화 보상 제시",
            "단계별 화면 시연",
            "마지막에 현실적 기대치와 다음 행동 제시",
        ],
        "stages": stages,
        "detected_signals": detected_signals,
        "risk_notes": [
            "수익/광고비 단정 표현은 과장 광고로 보일 수 있어 증빙과 조건을 분리해야 합니다.",
            "벤치마킹 영상은 구조 학습용이며, 미디어 재사용은 별도 권한 없이는 금지합니다.",
            "경제 주제는 최신 통계와 출처 검증이 원고 승인 조건이어야 합니다.",
        ],
    }


def score_reference(reference: BenchmarkReference) -> ReferenceScore:
    score = 0
    signals: list[str] = []
    warnings: list[str] = []

    if reference.views is not None:
        if reference.views >= 1_000_000:
            score += 4
            signals.append("1M+ 조회수")
        elif reference.views >= 300_000:
            score += 3
            signals.append("30만+ 조회수")
        elif reference.views >= 100_000:
            score += 2
            signals.append("10만+ 조회수")

    if reference.channel_age_days is not None and reference.channel_age_days <= 120:
        score += 2
        signals.append("신규 채널 성과")

    if reference.published_within_days is not None and reference.published_within_days <= 31:
        score += 2
        signals.append("최근 31일 내 성과")

    if reference.hook_type:
        score += 1
        signals.append(f"후킹 유형: {reference.hook_type}")

    if reference.proof_numbers:
        score += min(3, len(reference.proof_numbers))
        signals.append("성과/통계 숫자 포함")

    if reference.comment_energy >= 4:
        score += 2
        signals.append("댓글 질문/논쟁 강함")
    elif reference.comment_energy >= 2:
        score += 1
        signals.append("댓글 반응 있음")

    if reference.visual_style:
        score += 1
        signals.append(f"시각 스타일: {reference.visual_style}")

    if reference.rights_decision != "reference_only":
        warnings.append("레퍼런스 연구 목적이라면 기본값은 reference_only가 안전합니다.")

    if any(token in reference.title for token in ("수익", "돈", "광고", "폭락", "급등", "투자")):
        warnings.append("경제/수익 주장은 원고에서 출처와 조건을 별도로 검증해야 합니다.")

    if not signals:
        warnings.append("벤치마킹 신호가 부족해 레퍼런스 우선순위를 낮춥니다.")

    return ReferenceScore(reference=reference, score=score, signals=signals, warnings=warnings)


def build_economy_longform_brief(
    topic: str,
    *,
    target_viewer: str = "경제 이슈는 궁금하지만 전문 용어와 투자 판단은 부담스러운 한국 시청자",
    references: list[BenchmarkReference] | None = None,
    tutorial_transcript: str = "",
) -> EconomyLongformBrief:
    scored = sorted(
        [score_reference(reference) for reference in references or []],
        key=lambda item: item.score,
        reverse=True,
    )
    selected = [item for item in scored if item.score >= 5 and item.reference.rights_decision == "reference_only"][:5]
    rejected = [item for item in scored if item not in selected]
    tutorial_analysis = analyze_tutorial_transcript(tutorial_transcript)
    viewer_question = f"{topic}이 내 자산, 집값, 일자리, 물가에 어떤 영향을 주는지 알고 싶다"
    selected_angle = f"{topic}을 숫자 한 개와 생활 변화 한 개로 시작해, 원인-승자/패자-앞으로의 시나리오로 풀어낸다"

    return EconomyLongformBrief(
        topic=topic,
        target_viewer=target_viewer,
        viewer_question=viewer_question,
        selected_angle=selected_angle,
        tutorial_analysis=tutorial_analysis,
        selected_references=selected,
        rejected_references=rejected,
        research_checklist=research_checklist(topic),
        chapter_outline=chapter_outline(topic),
        prompts=script_prompts(topic, target_viewer, selected_angle),
        production_handoff=production_handoff(),
        review_warnings=review_warnings(),
    )


def research_checklist(topic: str) -> list[str]:
    return [
        f"오늘 날짜 기준 {topic} 관련 뉴스 5개를 찾고 출처, 발행일, 숫자를 기록합니다.",
        "YouTube 시크릿 모드 또는 개인화가 적은 환경에서 주제 검색 후 이번 달/조회수 높은 순으로 확인합니다.",
        "조회수, 채널 개설 시점, 영상 길이, 제목 프레임, 썸네일 약속, 첫 30초 후킹을 기록합니다.",
        "댓글 상위 20개에서 반복 질문, 반박, 더 알고 싶은 지점을 뽑습니다.",
        "레퍼런스는 기본적으로 reference_only로 분류하고, 원고에는 구조와 시청자 질문만 반영합니다.",
        "통계, 정책, 기업/기관 발언, 가격/금리/환율 등 변동 정보는 최신 출처로 재확인합니다.",
    ]


def chapter_outline(topic: str) -> list[str]:
    return [
        f"1장: {topic}을 한 문장 충격 질문과 핵심 숫자로 열기",
        "2장: 왜 지금 이 문제가 터졌는지 배경 압축",
        "3장: 사람들이 가장 오해하는 지점 정리",
        "4장: 승자와 패자, 돈의 이동 설명",
        "5장: 과거 비슷한 사건과 다른 점 비교",
        "6장: 앞으로 가능한 3가지 시나리오",
        "7장: 일반 시청자가 체크해야 할 생활 지표",
        "8장: 결론, 과장 없는 주의점, 다음 영상으로 이어지는 질문",
    ]


def script_prompts(topic: str, target_viewer: str, selected_angle: str) -> dict[str, str]:
    return {
        "reference_analysis": (
            "아래 레퍼런스 영상들은 구조 학습용이다. 문장, 썸네일 문구, 채널 정체성은 복제하지 말고 "
            "주제 각도, 첫 30초 후킹, 챕터 전환, 댓글 질문만 분석해라.\n"
            f"주제: {topic}\n타깃 시청자: {target_viewer}\n출력: 표로 hook, promise, proof, pacing, viewer question, avoid-copying-note를 정리."
        ),
        "outline": (
            f"{topic}에 대한 15-30분 경제 롱폼 원고의 3막 8장 뼈대를 작성해라.\n"
            f"선택 각도: {selected_angle}\n"
            "각 장은 500자 이내로, 장마다 확인해야 할 사실/통계 출처와 시청자 궁금증을 포함해라."
        ),
        "chapter_script": (
            "아래 장 요약을 1,200-1,600자 분량의 한국어 내레이션 원고로 확장해라.\n"
            "조건: 첫 문장은 질문/숫자/반전 중 하나로 시작한다. 투자 권유처럼 말하지 않는다. "
            "검증 안 된 수치는 [출처확인] 태그를 붙인다. 문장은 TTS가 읽기 쉽게 짧게 쓴다."
        ),
        "image_prompts": (
            "완성 원고를 1-2문장 단위 visual beat로 나누고, 각 beat마다 영어 이미지 생성 프롬프트를 작성해라.\n"
            "스타일: 고급 경제 다큐 애니메이션, 명확한 상징, 16:9, 텍스트 없음. "
            "출력은 sentence_ko, image_prompt_en, motion_required, fact_overlay_note 열을 가진 표로 작성."
        ),
        "fact_review": (
            "아래 원고에서 경제/투자/수익/정책/통계 주장을 모두 추출해 fact_review 표로 정리해라. "
            "열: claim, source_needed, risk_level, rewrite_if_unverified."
        ),
    }


def production_handoff() -> list[str]:
    return [
        "도입 30초는 motion_required=true 이미지 5개를 루프 영상으로 변환합니다.",
        "중반부는 8-15초마다 이미지 또는 차트 느낌의 장면을 교체합니다.",
        "TTS 자막은 22-28자 단위로 자동 줄바꿈하고, 숫자는 화면 첫 줄에 남깁니다.",
        "수익/광고/투자 관련 문장은 자막 또는 고정댓글에서 조건과 한계를 분리합니다.",
        "최종 내보내기 전 fact_review의 high risk 항목을 사람이 승인합니다.",
    ]


def review_warnings() -> list[str]:
    return [
        "성공 채널의 영상은 벤치마킹 대상이지 재사용 소스가 아닙니다.",
        "경제 주제는 최신 뉴스, 정책, 금리, 환율, 가격 정보가 바뀔 수 있어 제작 당일 재확인이 필요합니다.",
        "수익 가능성, 광고 단가, 조회수 예측은 보장 표현을 피하고 사례/조건/리스크를 함께 말해야 합니다.",
        "AI 이미지와 TTS만으로 만든 영상도 사실성, 출처, 저작권, 플랫폼 정책 검수를 통과해야 합니다.",
    ]


def parse_reference_row(row: str) -> BenchmarkReference:
    parts = [part.strip() for part in row.split("|")]
    if not parts or not parts[0]:
        raise ValueError("Reference row must start with a title")
    values = parts + [""] * (8 - len(parts))
    title, channel_name, views, age_days, url, hook_type, proof_numbers, visual_style = values[:8]
    return BenchmarkReference(
        title=title,
        channel_name=channel_name,
        views=int(views.replace(",", "")) if views else None,
        channel_age_days=int(age_days) if age_days else None,
        url=url,
        hook_type=hook_type,
        proof_numbers=[item.strip() for item in proof_numbers.split(",") if item.strip()],
        visual_style=visual_style,
    )


def load_references(path: str | Path) -> list[BenchmarkReference]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Reference JSON must be a list")
    return [BenchmarkReference(**item) for item in payload]


def write_brief_outputs(brief: EconomyLongformBrief, output_dir: str | Path) -> tuple[Path, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "economy_longform_brief.json"
    markdown_path = destination / "economy_longform_brief.md"
    json_path.write_text(json.dumps(brief.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_brief_markdown(brief), encoding="utf-8")
    return json_path, markdown_path


def render_brief_markdown(brief: EconomyLongformBrief) -> str:
    lines = [
        f"# Economy Longform Brief: {brief.topic}",
        "",
        "## Positioning",
        "",
        f"- Target viewer: {brief.target_viewer}",
        f"- Viewer question: {brief.viewer_question}",
        f"- Selected angle: {brief.selected_angle}",
        "",
        "## Tutorial Pattern",
        "",
        f"- Core thesis: {brief.tutorial_analysis['core_thesis']}",
        "- Retention pattern:",
    ]
    lines.extend(f"  - {item}" for item in brief.tutorial_analysis["retention_pattern"])
    lines.extend(["", "## Selected References", ""])
    if brief.selected_references:
        lines.append("| Score | Title | Channel | Signals | Warnings |")
        lines.append("| --- | --- | --- | --- | --- |")
        for item in brief.selected_references:
            lines.append(
                f"| {item.score} | {item.reference.title} | {item.reference.channel_name or '-'} | "
                f"{'; '.join(item.signals) or '-'} | {'; '.join(item.warnings) or '-'} |"
            )
    else:
        lines.append("No references selected yet. Add fresh YouTube/search results before production.")

    lines.extend(["", "## Research Checklist", ""])
    lines.extend(f"- {item}" for item in brief.research_checklist)
    lines.extend(["", "## Chapter Outline", ""])
    lines.extend(f"- {item}" for item in brief.chapter_outline)
    lines.extend(["", "## Prompts", ""])
    for name, prompt in brief.prompts.items():
        lines.extend([f"### {name}", "", prompt, ""])
    lines.extend(["## Production Handoff", ""])
    lines.extend(f"- {item}" for item in brief.production_handoff)
    lines.extend(["", "## Review Warnings", ""])
    lines.extend(f"- {item}" for item in brief.review_warnings)
    lines.append("")
    return "\n".join(lines)
