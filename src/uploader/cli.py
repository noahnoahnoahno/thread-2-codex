from __future__ import annotations

import argparse
import json
import http.server
import os
import re
import socketserver
from pathlib import Path

from .config import load_config
from .dedupe import DedupeStore
from .drive_ingest import build_drive_service, setup_drive_upload_folders, write_drive_metadata_templates
from .jsonio import write_json
from .report import build_report, write_report_files
from .trigger import candidate_to_objects, run_upload_trigger
from .youtube_client import build_youtube_service, get_authenticated_channel, upload_private_video


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube Shorts uploader beta mockup")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Scan configured folders and generate the beta dashboard report")
    scan.add_argument("--config", default="config.yaml")
    scan.add_argument("--limit", type=int, default=80)
    scan.add_argument("--date", help="Drive date folder override, e.g. 20260522")
    scan.add_argument("--no-record-seen", action="store_true")

    auth = sub.add_parser("drive-auth", help="Create or refresh the Google Drive token")
    auth.add_argument("--config", default="config.yaml")

    drive_setup = sub.add_parser("drive-setup-folders", help="Create the date and channel folders in Google Drive")
    drive_setup.add_argument("--config", default="config.yaml")
    drive_setup.add_argument("--date", help="Drive date folder override, e.g. 20260522")

    drive_templates = sub.add_parser("drive-write-templates", help="Write metadata template JSON into each Drive channel folder")
    drive_templates.add_argument("--config", default="config.yaml")
    drive_templates.add_argument("--date", help="Drive date folder override, e.g. 20260522")

    yt_auth = sub.add_parser("youtube-auth", help="Create or refresh a YouTube token for a channel key")
    yt_auth.add_argument("--config", default="config.yaml")
    yt_auth.add_argument("--channel", required=True)

    yt_channels = sub.add_parser("youtube-channels", help="Show configured channels and token status")
    yt_channels.add_argument("--config", default="config.yaml")
    yt_channels.add_argument("--verify", action="store_true", help="Call YouTube channels.list for each token")

    upload = sub.add_parser("upload-private", help="Upload one prepared candidate to YouTube as private")
    upload.add_argument("--config", default="config.yaml")
    upload.add_argument("--date", help="Drive date folder override, e.g. 20260522")
    upload.add_argument("--source", choices=["drive", "all"], default="drive")
    upload.add_argument("--channel", help="Override target channel key")
    upload.add_argument("--index", type=int, default=1, help="1-based index among matching candidates")
    upload.add_argument("--allow-review", action="store_true", help="Allow private upload even when review is required")

    trigger = sub.add_parser("trigger-upload", help="Run the Drive date-folder upload trigger")
    trigger.add_argument("--config", default="config.yaml")
    trigger.add_argument("--date", help="Drive date folder override, e.g. 20260531")
    trigger.add_argument("--execute", action="store_true", help="Actually upload videos. Without this, only preview.")
    trigger.add_argument("--allow-review", action="store_true", help="Allow private upload even when review is required")
    trigger.add_argument("--limit", type=int, help="Maximum scan candidates")
    trigger.add_argument("--channels", help="Comma-separated channel keys to include")

    serve = sub.add_parser("serve", help="Serve the local dashboard")
    serve.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))

    args = parser.parse_args()
    if args.command == "scan":
        config_path = Path(args.config)
        if not config_path.is_absolute():
            config_path = PROJECT_ROOT / config_path
        config = load_config(config_path)
        report = build_report(
            config,
            limit=args.limit,
            record_seen=not args.no_record_seen,
            target_date=args.date,
        )
        write_report_files(report, PROJECT_ROOT)
        summary = report["summary"]
        print("Beta mockup report generated")
        print(f"- total: {summary['total']}")
        print(f"- ready: {summary['ready']}")
        print(f"- review: {summary['review']}")
        print(f"- videoFail: {summary['videoFail']}")
        drive = report.get("drive", {})
        print(f"- drive date: {drive.get('target_date')}")
        print(f"- drive date folder found: {drive.get('date_folder_found')}")
        if drive.get("error"):
            print(f"- drive note: {drive.get('error')}")
        print(f"- report: {PROJECT_ROOT / 'data' / 'mockup_report.json'}")
        print(f"- dashboard: {PROJECT_ROOT / 'web' / 'index.html'}")
    elif args.command == "drive-auth":
        config_path = Path(args.config)
        if not config_path.is_absolute():
            config_path = PROJECT_ROOT / config_path
        config = load_config(config_path)
        build_drive_service(config, allow_interactive=True)
        print("Drive token is ready.")
    elif args.command == "drive-setup-folders":
        config_path = Path(args.config)
        if not config_path.is_absolute():
            config_path = PROJECT_ROOT / config_path
        config = load_config(config_path)
        result = setup_drive_upload_folders(config, target_date=args.date)
        print(f"Drive folders ready for {result['date']}")
        date_folder = result["date_folder"]
        print(
            f"- date folder: {date_folder['name']} "
            f"({date_folder['id']}) created={date_folder['created']}"
        )
        for channel in result["channels"]:
            if channel.get("error"):
                print(f"- {channel['channel_key']}: error={channel['error']}")
                continue
            print(
                f"- {channel['channel_key']}: {channel['folder_name']} "
                f"({channel['folder_id']}) created={channel['created']}"
            )
    elif args.command == "drive-write-templates":
        config_path = Path(args.config)
        if not config_path.is_absolute():
            config_path = PROJECT_ROOT / config_path
        config = load_config(config_path)
        result = write_drive_metadata_templates(config, target_date=args.date)
        print(f"Drive metadata templates ready for {result['date']}")
        for channel in result["channels"]:
            if channel.get("error"):
                print(f"- {channel['channel_key']}: error={channel['error']}")
                continue
            state = "updated" if channel.get("updated") else "created" if channel.get("created") else "ready"
            print(f"- {channel['channel_key']}: {channel['template_name']} {state}")
    elif args.command == "youtube-auth":
        config_path = Path(args.config)
        if not config_path.is_absolute():
            config_path = PROJECT_ROOT / config_path
        config = load_config(config_path)
        build_youtube_service(config, channel_key=args.channel, allow_interactive=True)
        try:
            channel = get_authenticated_channel(config, channel_key=args.channel)
            expected = config.get("channels", {}).get("items", {}).get(args.channel, {})
            expected_title = str(expected.get("expected_title", expected.get("title", "")) or "").strip()
            expected_id = str(expected.get("expected_channel_id", expected.get("channel_id", "")) or "").strip()
            if not authenticated_channel_matches(channel, expected_title, expected_id):
                token = Path(expected.get("token_json", ""))
                if token and not token.is_absolute():
                    token = PROJECT_ROOT / token
                if token.exists():
                    token.unlink()
                raise SystemExit(
                    "인증된 채널이 설정과 다릅니다. "
                    f"expected={expected_title or expected_id}, actual={channel['title']} ({channel['id']}). "
                    "토큰을 삭제했으니 올바른 채널을 선택해서 다시 인증하세요."
                )
            duplicate_key = duplicate_configured_channel_key(config, args.channel, str(channel.get("id") or ""))
            if duplicate_key:
                token = Path(expected.get("token_json", ""))
                if token and not token.is_absolute():
                    token = PROJECT_ROOT / token
                if token.exists():
                    token.unlink()
                raise SystemExit(
                    "이미 다른 채널 키에 연결된 YouTube 채널입니다. "
                    f"actual={channel['title']} ({channel['id']}), existing_key={duplicate_key}. "
                    "중복 토큰을 삭제했습니다."
                )
            print(f"YouTube token ready for {args.channel}: {channel['title']} ({channel['id']})")
        except Exception as exc:
            print(f"YouTube token ready for {args.channel}. Channel verification skipped: {exc}")
    elif args.command == "youtube-channels":
        config_path = Path(args.config)
        if not config_path.is_absolute():
            config_path = PROJECT_ROOT / config_path
        config = load_config(config_path)
        channels = config.get("channels", {})
        default = channels.get("default")
        for key, channel in channels.get("items", {}).items():
            token = Path(channel.get("token_json", ""))
            if not token.is_absolute():
                token = PROJECT_ROOT / token
            marker = "default" if key == default else ""
            line = f"{key}\t{channel.get('title', '')}\t{channel.get('channel_id', '')}\ttoken={'yes' if token.exists() else 'no'}\t{marker}"
            if args.verify and token.exists():
                try:
                    actual = get_authenticated_channel(config, channel_key=key)
                    line += f"\tactual={actual['title']} ({actual['id']})"
                except Exception as exc:
                    line += f"\tverify_error={exc}"
            print(line)
    elif args.command == "upload-private":
        config_path = Path(args.config)
        if not config_path.is_absolute():
            config_path = PROJECT_ROOT / config_path
        config = load_config(config_path)
        report = build_report(config, limit=200, record_seen=False, target_date=args.date)
        candidates = report.get("candidates", [])
        if args.source == "drive":
            candidates = [
                candidate
                for candidate in candidates
                if candidate.get("item", {}).get("adapter") == "google_drive_date"
            ]
        candidates = [
            candidate
            for candidate in candidates
            if candidate.get("video_probe", {}).get("ok")
            and candidate.get("duplicate_status") not in {"duplicate"}
        ]
        if not candidates:
            raise SystemExit("업로드 가능한 후보가 없습니다.")
        if args.index < 1 or args.index > len(candidates):
            raise SystemExit(f"--index 범위가 잘못되었습니다. 후보 수: {len(candidates)}")
        selected = candidates[args.index - 1]
        if selected.get("item", {}).get("policy", {}).get("requires_review") and not args.allow_review:
            raise SystemExit("이 후보는 검토 필요 상태입니다. private 테스트 업로드는 --allow-review를 명시하세요.")
        item, seo = candidate_to_objects(selected)
        print(f"Uploading private test video: {seo.title}")
        channel_key = args.channel or item.target_channel or config.get("channels", {}).get("default")
        response = upload_private_video(config, item, seo, channel_key=channel_key)
        video_id = response["id"]
        db_path = config.get("dedupe", {}).get("database", "./data/upload_queue.sqlite3")
        store = DedupeStore(db_path, default_channel=str(config.get("channels", {}).get("default") or "default"))
        try:
            store.mark_uploaded(item, selected["video_sha256"], video_id)
        finally:
            store.close()
        result = {
            "youtube_video_id": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "privacyStatus": "private",
            "title": seo.title,
            "channel_key": channel_key,
            "channel_id": response.get("snippet", {}).get("channelId"),
            "channel_title": response.get("snippet", {}).get("channelTitle"),
            "source_video": item.video_path,
            "response": response,
        }
        result_path = PROJECT_ROOT / "data" / f"upload_result_{video_id}.json"
        write_json(result_path, result)
        print(f"Upload complete: https://www.youtube.com/watch?v={video_id}")
        print(f"Result: {result_path}")
    elif args.command == "trigger-upload":
        config_path = Path(args.config)
        if not config_path.is_absolute():
            config_path = PROJECT_ROOT / config_path
        config = load_config(config_path)
        channel_filter = parse_channel_filter(args.channels)
        result = run_upload_trigger(
            config,
            target_date=args.date,
            execute=args.execute,
            allow_review=args.allow_review,
            limit=args.limit,
            channel_filter=channel_filter,
        )
        mode = "EXECUTE" if result["execute"] else "DRY-RUN"
        print(f"Upload trigger {mode} complete for {result['date']}")
        print(f"- candidates: {result['candidate_count']}")
        print(f"- uploaded: {result['uploaded_count']}")
        print(f"- skipped: {result['skipped_count']}")
        print(f"- failed: {result['failed_count']}")
        for uploaded in result["uploaded"]:
            print(f"- uploaded {uploaded['channel_key']}: {uploaded['url']}")
        for failed in result["failed"]:
            print(f"- failed {failed['channel_key']}: {failed['error']}")
        print(f"- report: {result['report']}")
    elif args.command == "serve":
        serve_dashboard(args.host, args.port)


def serve_dashboard(host: str, port: int) -> None:
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self) -> None:
            if self.path == "/health":
                self.send_json(200, {"ok": True, "service": "youtube-shorts-uploader"})
                return
            if self.path in {"/", ""}:
                self.send_response(302)
                self.send_header("Location", "/web/index.html")
                self.end_headers()
                return
            super().do_GET()

        def do_POST(self) -> None:
            try:
                admin_token = os.environ.get("UPLOADER_ADMIN_TOKEN", "").strip()
                if admin_token and self.headers.get("X-Uploader-Admin-Token", "") != admin_token:
                    self.send_json(401, {"ok": False, "error": "관리자 토큰이 필요합니다."})
                    return
                length = int(self.headers.get("Content-Length", "0") or "0")
                payload = {}
                if length:
                    payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                response = handle_dashboard_action(self.path, payload)
                self.send_json(200, response)
            except Exception as exc:
                self.send_json(500, {"ok": False, "error": str(exc)})

        def send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    with ReusableTCPServer((host, port), Handler) as httpd:
        print(f"Serving dashboard at http://{host}:{port}/web/index.html")
        httpd.serve_forever()


def handle_dashboard_action(path: str, payload: dict) -> dict:
    config = load_config(PROJECT_ROOT / "config.yaml")
    date = str(payload.get("date") or "").strip() or None
    if path == "/api/scan":
        report = build_report(config, limit=int(payload.get("limit") or 120), record_seen=False, target_date=date)
        write_report_files(report, PROJECT_ROOT)
        return {"ok": True, "summary": report.get("summary", {}), "drive": report.get("drive", {})}
    if path == "/api/drive-setup":
        result = setup_drive_upload_folders(config, target_date=date)
        return {"ok": True, "result": result}
    if path == "/api/drive-templates":
        result = write_drive_metadata_templates(config, target_date=date)
        return {"ok": True, "result": result}
    if path == "/api/trigger-preview":
        result = run_upload_trigger(config, target_date=date, execute=False, allow_review=bool(payload.get("allow_review")))
        return {"ok": True, "result": compact_trigger_result(result)}
    if path == "/api/trigger-execute":
        result = run_upload_trigger(config, target_date=date, execute=True, allow_review=bool(payload.get("allow_review")))
        return {"ok": True, "result": compact_trigger_result(result)}
    return {"ok": False, "error": f"unknown action: {path}"}


def compact_trigger_result(result: dict) -> dict:
    return {
        "date": result.get("date"),
        "execute": result.get("execute"),
        "allow_review": result.get("allow_review"),
        "candidate_count": result.get("candidate_count"),
        "uploaded_count": result.get("uploaded_count"),
        "skipped_count": result.get("skipped_count"),
        "failed_count": result.get("failed_count"),
        "uploaded": [
            {
                "channel_key": item.get("channel_key"),
                "title": item.get("title"),
                "url": item.get("url"),
            }
            for item in result.get("uploaded", [])
        ],
        "skipped": result.get("skipped", [])[:50],
        "failed": result.get("failed", []),
        "report": result.get("report"),
    }


def authenticated_channel_matches(channel: dict, expected_title: str, expected_id: str) -> bool:
    if expected_id and channel.get("id") == expected_id:
        return True
    if not expected_title:
        return True
    return normalize_channel_title(str(channel.get("title") or "")) == normalize_channel_title(expected_title)


def duplicate_configured_channel_key(config: dict, current_key: str, actual_channel_id: str) -> str:
    if not actual_channel_id:
        return ""
    for key, channel in config.get("channels", {}).get("items", {}).items():
        if key == current_key:
            continue
        if str(channel.get("channel_id") or "") == actual_channel_id:
            return str(key)
    return ""


def normalize_channel_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip().casefold()


def parse_channel_filter(value: str | None) -> set[str] | None:
    if not value:
        return None
    channels = {part.strip() for part in value.split(",") if part.strip()}
    return channels or None


if __name__ == "__main__":
    main()
