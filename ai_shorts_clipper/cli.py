from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analyzer import recommend_clips
from .longform_agent import (
    build_economy_longform_brief,
    load_references,
    parse_reference_row,
    write_brief_outputs,
)
from .media_ingest import (
    extract_with_ytdlp,
    flow_to_json,
    import_external_handoff,
    import_to_json,
    inspect_allowed_url,
)
from .render import candidates_from_json, render_candidates
from .transcript import load_transcript


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ai-shorts-clipper",
        description="Create shorts candidates from offline video subtitles.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze subtitles and write clip candidates JSON.")
    add_analysis_args(analyze_parser)

    render_parser = subparsers.add_parser("render", help="Render MP4 shorts from candidate JSON.")
    render_parser.add_argument("--video", required=True, help="Source video path.")
    render_parser.add_argument("--subtitles", help="Subtitle path for optional burned captions.")
    render_parser.add_argument("--candidates", required=True, help="Candidates JSON path.")
    render_parser.add_argument("--output-dir", default="outputs/renders", help="Directory for MP4 outputs.")
    render_parser.add_argument("--layout", choices=["crop", "letterbox"], default="crop")
    render_parser.add_argument("--burn-subtitles", action="store_true")
    render_parser.add_argument("--limit", type=int, help="Render only the first N candidates.")

    run_parser = subparsers.add_parser("run", help="Analyze subtitles and render candidates in one command.")
    add_analysis_args(run_parser)
    run_parser.add_argument("--video", required=True, help="Source video path.")
    run_parser.add_argument("--layout", choices=["crop", "letterbox"], default="crop")
    run_parser.add_argument("--burn-subtitles", action="store_true")
    run_parser.add_argument("--render-limit", type=int, help="Render only the first N candidates.")

    inspect_parser = subparsers.add_parser("inspect-url", help="Inspect a platform URL without downloading media.")
    inspect_parser.add_argument("url", help="YouTube, TikTok, Douyin, or Threads URL.")
    inspect_parser.add_argument(
        "--permission-state",
        default="needs_review",
        choices=["user_owned", "licensed", "platform_export", "embed_only", "needs_review", "blocked"],
        help="Known permission state for the source.",
    )

    extract_parser = subparsers.add_parser("extract-url", help="Optionally extract an allowed URL after permission review.")
    extract_parser.add_argument("url", help="YouTube, TikTok, Douyin, or Threads URL.")
    extract_parser.add_argument("--output-dir", default="outputs/originals", help="Directory for imported source media.")
    extract_parser.add_argument(
        "--permission-state",
        required=True,
        choices=["user_owned", "licensed", "platform_export"],
        help="Required rights confirmation for optional extraction.",
    )
    extract_parser.add_argument(
        "--enable-extractor",
        action="store_true",
        help="Explicitly enable the yt-dlp extractor after permission review.",
    )

    import_parser = subparsers.add_parser(
        "import-source",
        help="Validate a source.json handoff from an external downloader/importer.",
    )
    import_parser.add_argument("path", help="Path to source.json or its containing job directory.")

    longform_parser = subparsers.add_parser(
        "longform-agent",
        help="Create an economy long-form benchmark, script, and production brief.",
    )
    longform_parser.add_argument("--topic", required=True, help="Economy long-form topic to develop.")
    longform_parser.add_argument(
        "--target-viewer",
        default="경제 이슈는 궁금하지만 전문 용어와 투자 판단은 부담스러운 한국 시청자",
        help="Target viewer description.",
    )
    longform_parser.add_argument(
        "--reference",
        action="append",
        default=[],
        help="Benchmark row: title|channel|views|channel_age_days|url|hook_type|proof_numbers|visual_style",
    )
    longform_parser.add_argument("--reference-json", help="JSON list of benchmark reference objects.")
    longform_parser.add_argument(
        "--tutorial-transcript",
        help="Optional transcript file for deriving tutorial workflow signals.",
    )
    longform_parser.add_argument("--output-dir", default="outputs/longform-agent", help="Output directory.")

    args = parser.parse_args()
    if args.command == "analyze":
        candidates_path = analyze_command(args)
        print(f"Wrote candidates: {candidates_path}")
    elif args.command == "render":
        render_command(args)
    elif args.command == "run":
        candidates_path = analyze_command(args)
        render_args = argparse.Namespace(
            video=args.video,
            subtitles=args.subtitles,
            candidates=str(candidates_path),
            output_dir=str(Path(args.output_dir) / "renders"),
            layout=args.layout,
            burn_subtitles=args.burn_subtitles,
            limit=args.render_limit,
        )
        render_command(render_args)
    elif args.command == "inspect-url":
        flow = inspect_allowed_url(args.url, permission_state=args.permission_state)
        print(flow_to_json(flow))
    elif args.command == "extract-url":
        try:
            source_import = extract_with_ytdlp(
                args.url,
                args.output_dir,
                permission_state=args.permission_state,
                extractor_enabled=args.enable_extractor,
            )
        except (PermissionError, RuntimeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        print(import_to_json(source_import))
    elif args.command == "import-source":
        try:
            source_import = import_external_handoff(args.path)
        except (FileNotFoundError, PermissionError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        print(import_to_json(source_import))
    elif args.command == "longform-agent":
        references = []
        if args.reference_json:
            references.extend(load_references(args.reference_json))
        references.extend(parse_reference_row(row) for row in args.reference)
        tutorial_transcript = (
            Path(args.tutorial_transcript).read_text(encoding="utf-8")
            if args.tutorial_transcript
            else ""
        )
        brief = build_economy_longform_brief(
            args.topic,
            target_viewer=args.target_viewer,
            references=references,
            tutorial_transcript=tutorial_transcript,
        )
        json_path, markdown_path = write_brief_outputs(brief, args.output_dir)
        print(f"Wrote long-form brief JSON: {json_path}")
        print(f"Wrote long-form brief Markdown: {markdown_path}")


def add_analysis_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--subtitles", required=True, help="SRT, VTT, or [mm:ss] transcript path.")
    parser.add_argument("--output-dir", default="outputs", help="Directory for analysis outputs.")
    parser.add_argument("--count", type=int, default=6, help="Number of clip candidates.")
    parser.add_argument("--min-duration", type=float, default=18, help="Minimum clip length in seconds.")
    parser.add_argument("--max-duration", type=float, default=60, help="Maximum clip length in seconds.")


def analyze_command(args: argparse.Namespace) -> Path:
    segments = load_transcript(args.subtitles)
    candidates = recommend_clips(
        segments,
        count=args.count,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "candidates.json"
    payload = {
        "source_subtitles": str(Path(args.subtitles).resolve()),
        "clip_count": len(candidates),
        "clips": [candidate.to_dict() for candidate in candidates],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def render_command(args: argparse.Namespace) -> None:
    segments = load_transcript(args.subtitles) if args.subtitles else None
    candidates = candidates_from_json(args.candidates)
    rendered = render_candidates(
        args.video,
        candidates,
        args.output_dir,
        segments=segments,
        layout=args.layout,
        burn_subtitles=args.burn_subtitles,
        limit=args.limit,
    )
    for path in rendered:
        print(f"Rendered: {path}")


if __name__ == "__main__":
    main()
