import json
import unittest
from pathlib import Path

from clipper_pipeline.cli import (
    TranscriptSegment,
    analyze_segments,
    bounds_overlap_ratio,
    build_sentence_blocks,
    build_failure_state,
    build_overlay_filter,
    build_video_filter,
    create_subtitle_overlays,
    estimate_text_bounds,
    is_sentence_end,
    score_window,
    parse_transcript,
    write_default_edit_config,
)


class TranscriptAnalysisTest(unittest.TestCase):
    def test_parse_transcript_reads_timestamped_lines(self) -> None:
        segments = parse_transcript(Path("youtube_sORoHYP7HRU_transcript_ko.txt"))

        self.assertGreater(len(segments), 100)
        self.assertEqual(segments[0].start_sec, 0)
        self.assertIn("클립", segments[0].text)

    def test_analyze_segments_returns_candidates(self) -> None:
        segments = parse_transcript(Path("youtube_sORoHYP7HRU_transcript_ko.txt"))
        candidates = analyze_segments(segments, max_candidates=6)

        self.assertGreaterEqual(len(candidates), 1)
        self.assertLessEqual(len(candidates), 6)
        self.assertTrue(all(candidate.duration_sec >= 20 for candidate in candidates))
        self.assertTrue(all(candidate.duration_sec <= 45 for candidate in candidates))
        self.assertTrue(all(candidate.title for candidate in candidates))
        self.assertTrue(all(is_sentence_end(candidate.source_text) for candidate in candidates))
        self.assertEqual(sum(1 for candidate in candidates if candidate.most_replayed), 1)

    def test_sentence_blocks_are_candidate_units(self) -> None:
        segments = parse_transcript(Path("youtube_sORoHYP7HRU_transcript_ko.txt"))
        blocks = build_sentence_blocks(segments)

        self.assertGreater(len(blocks), 1)
        self.assertTrue(all(is_sentence_end(block.text) for block in blocks[:-1]))

    def test_long_unpunctuated_blocks_are_split(self) -> None:
        segments = [
            # No sentence-ending phrase on purpose: ASR often behaves this way.
            *[
                type("Segment", (), {"start_sec": float(i * 5), "end_sec": float(i * 5 + 5), "text": "블로그 키워드 GPT 자동화 수익 설명"})()
                for i in range(14)
            ]
        ]
        blocks = build_sentence_blocks(segments)

        self.assertGreater(len(blocks), 1)
        self.assertTrue(all(block.end_sec - block.start_sec <= 45 for block in blocks))

    def test_analyze_segments_forces_heatmap_candidate(self) -> None:
        segments = parse_transcript(Path("youtube_sORoHYP7HRU_transcript_ko.txt"))
        candidates = analyze_segments(
            segments,
            max_candidates=6,
            most_replayed_range=(120.0, 140.0, 0.95),
        )

        most_replayed = [candidate for candidate in candidates if candidate.most_replayed]
        self.assertEqual(len(most_replayed), 1)
        self.assertEqual(most_replayed[0].replay_source, "youtube_heatmap")
        self.assertTrue(most_replayed[0].start_sec <= 140.0)
        self.assertTrue(most_replayed[0].end_sec >= 120.0)

    def test_most_replayed_fallback_marks_top_hook_score(self) -> None:
        segments = [
            TranscriptSegment(0, 10, "안녕하세요 오늘은 간단히 설명을 시작합니다"),
            TranscriptSegment(10, 22, "일반적인 기능 흐름을 차근차근 살펴봅니다"),
            TranscriptSegment(22, 34, "이 부분은 참고용 설명이라 후킹이 약합니다"),
            TranscriptSegment(80, 92, "중요한 건 대부분 사람들이 GPT 자동화의 진짜 문제를 놓친다는 점입니다"),
            TranscriptSegment(92, 106, "하지만 실제로 블로그 키워드 수익 자동화는 여기서 반전이 생깁니다."),
        ]

        candidates = analyze_segments(segments, max_candidates=6)
        most_replayed = [candidate for candidate in candidates if candidate.most_replayed]

        self.assertEqual(len(most_replayed), 1)
        self.assertEqual(most_replayed[0].score, max(candidate.score for candidate in candidates))
        self.assertEqual(most_replayed[0].replay_source, "hook_score_fallback")

    def test_score_window_rewards_hook_features(self) -> None:
        plain = score_window("안녕하세요 오늘도 시작하겠습니다", 1.0, 20.0, 0.0, 600.0)
        hook = score_window("근데 진짜 문제는 비용입니다. 결론부터 말하면 이 방법이 가능한 이유가 있어요.", 1.0, 20.0, 120.0, 600.0)

        self.assertGreater(hook, plain)

    def test_score_window_rewards_turning_point_and_attention(self) -> None:
        plain = score_window("기능을 순서대로 설명하고 화면을 보여드립니다.", 1.0, 24.0, 180.0, 900.0)
        turning_point = score_window(
            "중요한 건 대부분 사람들이 이 반전 포인트를 놓친다는 점입니다. 사실 문제는 여기서 시작됩니다.",
            1.0,
            24.0,
            180.0,
            900.0,
        )

        self.assertGreater(turning_point, plain)


    def test_write_default_edit_config_contains_text_layers(self) -> None:
        segments = parse_transcript(Path("youtube_sORoHYP7HRU_transcript_ko.txt"))
        candidate = analyze_segments(segments, max_candidates=1)[0]
        output = Path("runs/test/edit-config.json")

        write_default_edit_config(candidate, output, "테스트 채널")
        body = output.read_text(encoding="utf-8")

        self.assertIn('"layout": "letterbox"', body)
        self.assertIn('"cropConfig"', body)
        self.assertIn('"type": "title"', body)
        self.assertIn('"type": "channel"', body)
        self.assertIn('"subtitleEnabled": true', body)
        self.assertIn('"subtitleStyle"', body)
        self.assertIn('"fontFamily": "NEXON Lv1 Gothic"', body)
        self.assertIn("테스트 채널", body)

    def test_create_subtitle_overlays_for_clip_range(self) -> None:
        output_dir = Path("runs/test/subtitle-overlays")
        overlays = create_subtitle_overlays(
            transcript_path=Path("youtube_sORoHYP7HRU_transcript_ko.txt"),
            start_sec=98,
            end_sec=105,
            duration=7,
            directory=output_dir,
            style={
                "fontSize": 40,
                "color": "#ff0000",
                "backgroundEnabled": False,
                "x": 540,
                "y": 1280,
            },
        )

        self.assertGreater(len(overlays), 0)
        self.assertTrue(all(item["path"].exists() for item in overlays))
        self.assertTrue(all(0 <= item["start"] < item["end"] <= 7 for item in overlays))
        for item in overlays:
            item["path"].unlink(missing_ok=True)

    def test_build_overlay_filter_adds_subtitle_enable(self) -> None:
        filter_graph = build_overlay_filter(
            "scale=1080:1920",
            [{"path": Path("subtitle.png"), "start": 0.5, "end": 2.5}],
        )

        self.assertIn("overlay=0:0", filter_graph)
        self.assertIn("between(t,0.500,2.500)", filter_graph)

    def test_build_video_filter_uses_crop_focus_and_zoom(self) -> None:
        filter_graph = build_video_filter(
            "crop",
            {"focusX": 0.25, "focusY": 0.75, "zoom": 1.2},
        )

        self.assertIn("scale=1296:2304:force_original_aspect_ratio=increase", filter_graph)
        self.assertIn("crop=1080:1920:(iw-ow)*0.250:(ih-oh)*0.750", filter_graph)

    def test_build_video_filter_clamps_crop_config(self) -> None:
        filter_graph = build_video_filter(
            "crop",
            {"focusX": -1, "focusY": 4, "zoom": 3},
        )

        self.assertIn("scale=2160:3840:force_original_aspect_ratio=increase", filter_graph)
        self.assertIn("crop=1080:1920:(iw-ow)*0.000:(ih-oh)*1.000", filter_graph)

    def test_estimate_text_bounds_for_default_layers(self) -> None:
        segments = parse_transcript(Path("youtube_sORoHYP7HRU_transcript_ko.txt"))
        candidate = analyze_segments(segments, max_candidates=1)[0]
        output = Path("runs/test/edit-config.json")
        write_default_edit_config(candidate, output, "테스트 채널")

        payload = json.loads(output.read_text(encoding="utf-8"))
        bounds = estimate_text_bounds(payload["textLayers"])

        self.assertEqual(len(bounds), 2)
        self.assertTrue(all(item["bounds"][0] >= 0 for item in bounds))
        self.assertTrue(all(item["bounds"][2] <= 1080 for item in bounds))

    def test_bounds_overlap_ratio_detects_overlap(self) -> None:
        self.assertGreater(bounds_overlap_ratio([0, 0, 100, 100], [50, 50, 150, 150]), 0)
        self.assertEqual(bounds_overlap_ratio([0, 0, 100, 100], [120, 120, 150, 150]), 0)

    def test_build_failure_state_contains_restart_and_retry_actions(self) -> None:
        state = build_failure_state(
            step="download_youtube",
            error=RuntimeError("download failed"),
            retry_command="download-youtube",
            retry_args={"url": "bad-url", "out": "runs/test/input.mp4"},
            url="bad-url",
        )

        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["display"]["title"], "영상 다운로드 실패")
        actions = {action["id"]: action for action in state["display"]["actions"]}
        self.assertEqual(actions["restart"]["target"], "url_input")
        self.assertEqual(actions["retry"]["command"], "download-youtube")

    def test_load_candidate_accepts_hybrid_camel_case_payload(self) -> None:
        output = Path("runs/test/camel-candidate.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "clips": [
                        {
                            "startSec": 1.5,
                            "endSec": 29.5,
                            "durationSec": 28.0,
                            "category": "general",
                            "title": "테스트 클립",
                            "reason": "하이브리드 워커 후보",
                            "hashtags": ["#test"],
                            "score": 9.1,
                            "sourceText": "후보 문장",
                            "mostReplayed": True,
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        from clipper_pipeline.cli import load_candidate

        candidate = load_candidate(output, 0)

        self.assertEqual(candidate.start_sec, 1.5)
        self.assertEqual(candidate.end_sec, 29.5)
        self.assertEqual(candidate.duration_sec, 28.0)
        self.assertEqual(candidate.source_text, "후보 문장")
        self.assertTrue(candidate.most_replayed)


if __name__ == "__main__":
    unittest.main()
