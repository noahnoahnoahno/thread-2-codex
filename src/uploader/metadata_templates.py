from __future__ import annotations

from datetime import datetime
from typing import Any


TEMPLATE_FILENAME = "_metadata_template.json"


def same_name_metadata_template(
    *,
    channel_key: str = "",
    channel_title: str = "",
    date: str = "",
) -> dict[str, Any]:
    return {
        "project": "google-drive-date-folder",
        "date": date or datetime.now().strftime("%Y%m%d"),
        "video": "same-name-as-video.mp4",
        "channel": channel_key,
        "channel_title": channel_title,
        "title": "시청자가 바로 클릭할 이유가 보이는 후킹형 제목",
        "hook": "첫 문장에 궁금증, 반전, 핵심 행동, 장면 긴장감 중 하나를 넣습니다.",
        "description": (
            "첫 두 줄에 핵심 장면과 검색 키워드를 자연스럽게 넣습니다.\n"
            "영상 맥락, 주요 행동, 채널 주제와 연결되는 문장을 추가합니다."
        ),
        "tags": [
            "유튜브 쇼츠",
            "쇼츠 하이라이트",
            "장면 키워드",
            "행동 키워드",
            "채널 키워드",
        ],
        "hashtags": ["#Shorts", "#쇼츠", "#하이라이트"],
        "transcript": "",
        "requires_review": False,
        "review_reason": "",
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": False,
        "hasPaidProductPlacement": False,
    }


def upload_json_template(*, date: str = "") -> dict[str, Any]:
    return {
        "project": "google-drive-date-folder",
        "date": date or datetime.now().strftime("%Y%m%d"),
        "items": [
            {
                "video": "same-name-as-video.mp4",
                "channel": "",
                "title": "시청자가 바로 클릭할 이유가 보이는 후킹형 제목",
                "hook": "궁금증, 반전, 핵심 행동, 장면 긴장감 중 하나를 첫 문장에 넣습니다.",
                "description": "검색 키워드와 장면 맥락이 자연스럽게 들어간 설명입니다.",
                "tags": ["유튜브 쇼츠", "쇼츠 하이라이트", "장면 키워드"],
                "hashtags": ["#Shorts", "#쇼츠", "#하이라이트"],
                "transcript": "",
                "requires_review": False,
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia": False,
                "hasPaidProductPlacement": False,
            }
        ],
    }
