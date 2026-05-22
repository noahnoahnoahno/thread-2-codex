from __future__ import annotations

import argparse
import io
import json
import mimetypes
import os
import threading
import time
import uuid
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from .cli import (
    analyze_segments,
    build_failure_state,
    download_youtube,
    extract_audio,
    extract_most_replayed_range,
    extract_youtube_id,
    fetch_youtube_transcript,
    load_candidate,
    parse_transcript,
    render_clip,
    write_candidates,
    write_default_edit_config,
    youtube_info,
)


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
RUNS_DIR = Path(os.getenv("CLIPPER_RUNS_DIR", ROOT / "runs"))
EXPORTS_DIR = Path(os.getenv("CLIPPER_EXPORTS_DIR", ROOT / "exports"))
APP_VERSION = "2026-05-22-hybrid-candidate-format-v2"
JOB_MODE = os.getenv("CLIPPER_JOB_MODE", "local")
WORKER_TOKEN = os.getenv("CLIPPER_WORKER_TOKEN", "")


STEP_DEFINITIONS = [
    ("download_youtube", "영상 다운로드"),
    ("extract_audio", "오디오 추출"),
    ("fetch_transcript", "음성 인식"),
    ("analyze", "AI 분석"),
    ("render", "클립 생성"),
]


JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def create_job(url: str) -> dict:
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "url": url,
        "status": "queued",
        "currentStep": None,
        "progress": 0,
        "steps": [
            {"key": key, "label": label, "status": "pending", "progress": 0}
            for key, label in STEP_DEFINITIONS
        ],
        "failure": None,
        "result": None,
        "createdAt": time.time(),
        "updatedAt": time.time(),
    }
    with JOBS_LOCK:
        JOBS[job_id] = job
    if JOB_MODE == "hybrid":
        set_step(job_id, "download_youtube", "queued", 0)
    else:
        thread = threading.Thread(target=run_job, args=(job_id,), daemon=True)
        thread.start()
    return job


def get_job(job_id: str) -> dict | None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        return json.loads(json.dumps(job, ensure_ascii=False)) if job else None


def mutate_job(job_id: str, update) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        update(job)
        job["updatedAt"] = time.time()
        job["progress"] = calculate_overall_progress(job)


def calculate_overall_progress(job: dict) -> int:
    total = sum(float(step.get("progress", 0)) for step in job["steps"])
    return int(round(total / max(len(job["steps"]), 1)))


def set_step(job_id: str, key: str, status: str, progress: int) -> None:
    def update(job: dict) -> None:
        if status == "failed":
            job["status"] = "failed"
        elif status in {"queued", "pending"}:
            job["status"] = "queued"
        else:
            job["status"] = "running"
        job["currentStep"] = key
        for step in job["steps"]:
            if step["key"] == key:
                step["status"] = status
                step["progress"] = progress

    mutate_job(job_id, update)


def complete_step(job_id: str, key: str) -> None:
    set_step(job_id, key, "done", 100)


def authorize_worker(headers) -> bool:
    if not WORKER_TOKEN:
        return False
    auth_header = headers.get("Authorization", "")
    return auth_header == f"Bearer {WORKER_TOKEN}"


def next_worker_job() -> dict | None:
    with JOBS_LOCK:
        queued = [
            job
            for job in JOBS.values()
            if job.get("status") == "queued" and not job.get("workerStartedAt")
        ]
        if not queued:
            return None
        job = sorted(queued, key=lambda item: item.get("createdAt", 0))[0]
        job["workerStartedAt"] = time.time()
        job["status"] = "running"
        job["currentStep"] = "download_youtube"
        for step in job["steps"]:
            if step["key"] == "download_youtube":
                step["status"] = "running"
                step["progress"] = max(int(step.get("progress", 0)), 2)
        job["progress"] = calculate_overall_progress(job)
        return json.loads(json.dumps(job, ensure_ascii=False))


def apply_worker_status(job_id: str, payload: dict) -> dict:
    def update(job: dict) -> None:
        if payload.get("status"):
            job["status"] = payload["status"]
        if payload.get("currentStep") is not None:
            job["currentStep"] = payload["currentStep"]
        if payload.get("failure") is not None:
            job["failure"] = payload["failure"]
        incoming_steps = payload.get("steps")
        if isinstance(incoming_steps, list):
            by_key = {step.get("key"): step for step in incoming_steps}
            for step in job["steps"]:
                incoming = by_key.get(step["key"])
                if incoming:
                    step["status"] = incoming.get("status", step["status"])
                    step["progress"] = incoming.get("progress", step["progress"])
        step_key = payload.get("step")
        if step_key:
            for step in job["steps"]:
                if step["key"] == step_key:
                    step["status"] = payload.get("stepStatus", step["status"])
                    step["progress"] = payload.get("stepProgress", step["progress"])

    mutate_job(job_id, update)
    job = get_job(job_id)
    if not job:
        raise ValueError("Job not found")
    return job


def complete_worker_job(job_id: str, body: bytes) -> dict:
    job = get_job(job_id)
    if not job:
        raise ValueError("Job not found")

    run_dir = (RUNS_DIR / f"worker-{job_id}").resolve()
    if run_dir.exists():
        for child in sorted(run_dir.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
    run_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        for member in archive.infolist():
            target = (run_dir / member.filename).resolve()
            if run_dir not in target.parents and target != run_dir:
                raise ValueError("Invalid worker archive path")
        archive.extractall(run_dir)

    handoff_path = run_dir / "handoff.json"
    if not handoff_path.exists():
        raise ValueError("Worker archive is missing handoff.json")
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    files = handoff.get("files") if isinstance(handoff.get("files"), dict) else {}

    input_path = run_dir / str(files.get("input") or "input.mp4")
    candidates_path = run_dir / str(files.get("candidates") or "candidates.json")
    edit_config_path = run_dir / str(files.get("editConfig") or "edit-config-web.json")
    render_path = run_dir / str(files.get("render") or "renders/clip-001-web.mp4")

    def update(job_data: dict) -> None:
        for step in job_data["steps"]:
            step["status"] = "done"
            step["progress"] = 100
        job_data["status"] = "done"
        job_data["currentStep"] = None
        job_data["failure"] = None
        job_data["result"] = {
            "runDir": str(run_dir),
            "title": handoff.get("title"),
            "channel": handoff.get("channel"),
            "inputUrl": media_url(input_path),
            "candidatesPath": str(candidates_path),
            "clips": handoff.get("clips") or [],
            "editConfig": str(edit_config_path),
            "render": str(render_path),
            "renderUrl": media_url(render_path),
            "processedBy": handoff.get("workerId") or "hybrid-worker",
        }

    mutate_job(job_id, update)
    completed = get_job(job_id)
    if not completed:
        raise ValueError("Job not found")
    return completed


def serialize_candidate(candidate, index: int) -> dict:
    return {
        "index": index,
        "startSec": candidate.start_sec,
        "endSec": candidate.end_sec,
        "durationSec": candidate.duration_sec,
        "category": candidate.category,
        "title": candidate.title,
        "reason": candidate.reason,
        "hashtags": candidate.hashtags,
        "score": candidate.score,
        "sourceText": candidate.source_text,
        "mostReplayed": candidate.most_replayed,
        "replaySource": candidate.replay_source,
        "replayScore": candidate.replay_score,
        "selected": True,
    }


def subtitle_y_for_position(position: str) -> int:
    return {
        "upper": 860,
        "middle": 1040,
        "lower": 1220,
    }.get(position, 1220)


def title_y_for_position(position: str) -> int:
    return {
        "top": 150,
        "middle": 780,
        "lower": 1180,
    }.get(position, 150)


def canvas_y_from_percent(value: object, minimum: float, maximum: float, fallback: float) -> int:
    percent = clamp_float(value, minimum, maximum, fallback)
    return int(round(1920 * percent / 100))


def layer_anchor_for_align(align: str) -> tuple[int, str]:
    if align == "left":
        return 100, "left"
    if align == "right":
        return 980, "right"
    return 540, "center"


def clamp_int(value: object, minimum: int, maximum: int, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = fallback
    return max(minimum, min(maximum, number))


def clamp_float(value: object, minimum: float, maximum: float, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = fallback
    return max(minimum, min(maximum, number))


def safe_color(value: object, fallback: str = "#ffffff") -> str:
    text = str(value or "").strip()
    if len(text) == 7 and text.startswith("#"):
        return text
    return fallback


def media_url(path: Path | str) -> str:
    file_path = Path(path).resolve()
    try:
        relative = file_path.relative_to(ROOT)
    except ValueError:
        try:
            relative = file_path.relative_to(EXPORTS_DIR)
        except ValueError:
            return ""
        return "/exports/" + quote(str(relative), safe="/")
    return "/media/" + quote(str(relative), safe="/")


def safe_filename_part(value: object, fallback: str = "clip") -> str:
    text = str(value or "").strip().lower()
    output = []
    for char in text:
        if char.isalnum():
            output.append(char)
        elif char in {" ", "-", "_"}:
            output.append("-")
    normalized = "".join(output).strip("-")
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized[:80] or fallback


def write_upload_metadata(
    *,
    path: Path,
    job: dict,
    result: dict,
    candidate,
    index: int,
    config: dict,
    output_path: Path,
    edit_config_path: Path,
    created_at: datetime,
) -> dict:
    metadata = {
        "schemaVersion": 1,
        "createdAt": created_at.isoformat(timespec="seconds"),
        "publishDate": created_at.strftime("%Y-%m-%d"),
        "sourceUrl": job.get("url"),
        "sourceTitle": result.get("title"),
        "sourceChannel": result.get("channel"),
        "clipIndex": index,
        "title": config["textLayers"][0]["text"],
        "hashtags": config.get("hashtags", []),
        "startSec": candidate.start_sec,
        "endSec": candidate.end_sec,
        "durationSec": candidate.duration_sec,
        "layout": config["layout"],
        "videoPath": str(output_path),
        "videoUrl": media_url(output_path),
        "editConfig": str(edit_config_path),
        "uploadStatus": "pending",
    }
    path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def write_web_edit_config(candidate, out_path: Path, channel: str, draft: dict) -> dict:
    write_default_edit_config(candidate, out_path, channel)
    config = json.loads(out_path.read_text(encoding="utf-8"))
    title = str(draft.get("title") or candidate.title)
    hashtags = draft.get("hashtags") if isinstance(draft.get("hashtags"), list) else candidate.hashtags
    layout = str(draft.get("layout") or "letterbox")
    subtitle_size = clamp_int(draft.get("subtitleSize"), 34, 72, 48)
    subtitle_position = str(draft.get("subtitlePosition") or "lower")
    title_size = clamp_int(draft.get("titleSize"), 44, 96, 72)
    title_position = str(draft.get("titlePosition") or "top")
    title_y = canvas_y_from_percent(draft.get("titleY"), 8.0, 88.0, 12.0)
    subtitle_y = canvas_y_from_percent(draft.get("subtitleY"), 18.0, 88.0, 72.0)
    title_align = str(draft.get("titleAlign") or "center")
    title_color = safe_color(draft.get("titleColor"))
    title_stroke = bool(draft.get("titleStroke", True))
    channel_enabled = bool(draft.get("channelEnabled", True))
    channel_name = str(draft.get("channelName") or channel)
    channel_size = clamp_int(draft.get("channelSize"), 28, 58, 42)

    config["layout"] = layout if layout in {"letterbox", "crop"} else "letterbox"
    config["hashtags"] = hashtags
    config["showSafeZone"] = bool(draft.get("showSafeZone", True))
    config["cropConfig"]["focusX"] = clamp_float(draft.get("cropFocusX"), 0.0, 1.0, 0.5)
    config["cropConfig"]["focusY"] = clamp_float(draft.get("cropFocusY"), 0.0, 1.0, 0.5)
    config["cropConfig"]["zoom"] = clamp_float(draft.get("cropZoom"), 1.0, 2.0, 1.0)
    config["subtitleStyle"]["fontSize"] = subtitle_size
    config["subtitleStyle"]["positionPreset"] = subtitle_position
    config["subtitleStyle"]["y"] = subtitle_y
    config["subtitleStyle"]["backgroundEnabled"] = bool(draft.get("subtitleBackground", True))
    for layer in config.get("textLayers", []):
        if layer.get("id") == "title":
            title_x, title_anchor = layer_anchor_for_align(title_align)
            layer["text"] = title
            layer["x"] = title_x
            layer["y"] = title_y
            layer["anchor"] = title_anchor
            layer["align"] = title_align if title_align in {"left", "center", "right"} else "center"
            layer["fontSize"] = title_size
            layer["color"] = title_color
            layer["strokeWidth"] = 4 if title_stroke else 0
        if layer.get("id") == "channel":
            layer["visible"] = channel_enabled
            layer["text"] = channel_name
            layer["fontSize"] = channel_size

    out_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return config


def render_selected_clips(job_id: str, payload: dict) -> dict:
    job = get_job(job_id)
    if not job:
        raise ValueError("Job not found")
    if job.get("status") != "done" or not job.get("result"):
        raise ValueError("Job is not ready for selected rendering")

    result = job["result"]
    run_dir = Path(result["runDir"])
    input_path = run_dir / "input.mp4"
    transcript_path = run_dir / "transcript.txt"
    candidates_path = Path(result["candidatesPath"])
    channel = str(result.get("channel") or "CHANNEL")
    requested_clips = payload.get("clips") if isinstance(payload.get("clips"), list) else []
    if not requested_clips:
        raise ValueError("No selected clips provided")

    created_at = datetime.now()
    export_date = created_at.strftime("%Y-%m-%d")
    export_token = created_at.strftime("%H%M%S")
    video_id = safe_filename_part(run_dir.name.removeprefix("youtube-"), "youtube")
    edit_config_dir = run_dir / "web-edit-configs"
    render_dir = EXPORTS_DIR / export_date
    edit_config_dir.mkdir(parents=True, exist_ok=True)
    render_dir.mkdir(parents=True, exist_ok=True)

    renders: list[dict] = []
    for draft in requested_clips:
        index = int(draft.get("index") or 0)
        if index < 1:
            raise ValueError(f"Invalid clip index: {index}")
        candidate = load_candidate(candidates_path, index - 1)
        stem = f"{video_id}-{job_id}-clip-{index:03d}-{export_token}"
        edit_config_path = edit_config_dir / f"{stem}.json"
        output_path = render_dir / f"{stem}.mp4"
        metadata_path = render_dir / f"{stem}.json"
        config = write_web_edit_config(candidate, edit_config_path, channel, draft)
        render_clip(input_path, candidate, output_path, config["layout"], edit_config_path, transcript_path)
        metadata = write_upload_metadata(
            path=metadata_path,
            job=job,
            result=result,
            candidate=candidate,
            index=index,
            config=config,
            output_path=output_path,
            edit_config_path=edit_config_path,
            created_at=created_at,
        )
        renders.append(
            {
                "index": index,
                "title": config["textLayers"][0]["text"],
                "hashtags": config.get("hashtags", []),
                "layout": config["layout"],
                "exportDate": export_date,
                "editConfig": str(edit_config_path),
                "output": str(output_path),
                "metadata": str(metadata_path),
                "outputUrl": media_url(output_path),
                "uploadMetadata": metadata,
            }
        )

    manifest = {
        "jobId": job_id,
        "renderedAt": time.time(),
        "exportDate": export_date,
        "exportDir": str(render_dir),
        "count": len(renders),
        "renders": renders,
    }
    manifest_path = render_dir / f"upload-manifest-{job_id}-{export_token}.json"
    manifest["manifest"] = str(manifest_path)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def update(job_data: dict) -> None:
        job_data["result"]["selectedRender"] = manifest

    mutate_job(job_id, update)
    return manifest


def fail_job(job_id: str, step: str, error: Exception, retry_args: dict, url: str) -> None:
    failure = build_failure_state(
        step=step,
        error=error,
        retry_command="start-job",
        retry_args=retry_args,
        url=url,
    )
    def update(job: dict) -> None:
        job["status"] = "failed"
        job["currentStep"] = step
        job["failure"] = failure
        for item in job["steps"]:
            if item["key"] == step:
                item["status"] = "failed"

    mutate_job(job_id, update)


def run_job(job_id: str) -> None:
    job = get_job(job_id)
    if not job:
        return

    url = str(job["url"]).strip()
    try:
        try:
            video_id = extract_youtube_id(url)
        except Exception:
            video_id = f"job-{job_id}"
        run_dir = RUNS_DIR / f"youtube-{video_id}"
        run_dir.mkdir(parents=True, exist_ok=True)

        info_path = run_dir / "youtube-info.json"
        input_path = run_dir / "input.mp4"
        audio_path = run_dir / "audio.wav"
        transcript_path = run_dir / "transcript.txt"
        candidates_path = run_dir / "candidates.json"
        edit_config_path = run_dir / "edit-config-web.json"
        render_path = run_dir / "renders" / "clip-001-web.mp4"

        set_step(job_id, "download_youtube", "running", 8)
        info = youtube_info(url, info_path)
        set_step(job_id, "download_youtube", "running", 32)
        if not input_path.exists():
            download_youtube(url, input_path, 720)
        complete_step(job_id, "download_youtube")

        set_step(job_id, "extract_audio", "running", 30)
        if not audio_path.exists():
            extract_audio(input_path, audio_path)
        complete_step(job_id, "extract_audio")

        set_step(job_id, "fetch_transcript", "running", 30)
        if not transcript_path.exists():
            fetch_youtube_transcript(url, transcript_path, ["ko", "en"])
        complete_step(job_id, "fetch_transcript")

        set_step(job_id, "analyze", "running", 40)
        segments = parse_transcript(transcript_path)
        candidates = analyze_segments(
            segments,
            max_candidates=6,
            most_replayed_range=extract_most_replayed_range(info),
        )
        write_candidates(candidates, candidates_path)
        complete_step(job_id, "analyze")

        set_step(job_id, "render", "running", 35)
        candidate = load_candidate(candidates_path, 0)
        channel = str(info.get("channel") or "CHANNEL")
        write_default_edit_config(candidate, edit_config_path, channel)
        render_clip(input_path, candidate, render_path, "letterbox", edit_config_path, transcript_path)
        complete_step(job_id, "render")

        def update(job: dict) -> None:
            job["status"] = "done"
            job["currentStep"] = None
            job["result"] = {
                "runDir": str(run_dir),
                "title": info.get("title"),
                "channel": info.get("channel"),
                "inputUrl": media_url(input_path),
                "candidatesPath": str(candidates_path),
                "clips": [serialize_candidate(item, index) for index, item in enumerate(candidates, start=1)],
                "editConfig": str(edit_config_path),
                "render": str(render_path),
                "renderUrl": media_url(render_path),
            }

        mutate_job(job_id, update)
    except Exception as exc:
        failing_step = get_job(job_id).get("currentStep") or "download_youtube"
        fail_job(job_id, failing_step, exc, {"url": url}, url)


class ClipperRequestHandler(BaseHTTPRequestHandler):
    server_version = "ClipperHTTP/0.1"

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html", "/api/health"}:
            self.send_response(200)
            self.end_headers()
            return
        self.send_error(404)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self.send_json({"status": "ok"})
            return
        if parsed.path == "/api/version":
            self.send_json({"version": APP_VERSION})
            return
        if parsed.path == "/api/worker/jobs/next":
            if not authorize_worker(self.headers):
                self.send_json({"error": "Worker token is missing or invalid"}, status=401)
                return
            self.send_json({"job": next_worker_job()})
            return
        if parsed.path.startswith("/api/jobs/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            job = get_job(job_id)
            if not job:
                self.send_json({"error": "Job not found"}, status=404)
                return
            self.send_json(job)
            return
        if parsed.path.startswith("/media/"):
            self.serve_media(parsed.path)
            return
        if parsed.path.startswith("/exports/"):
            self.serve_export(parsed.path)
            return

        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        parts = parsed.path.strip("/").split("/")
        if len(parts) == 5 and parts[0] == "api" and parts[1] == "worker" and parts[2] == "jobs":
            if not authorize_worker(self.headers):
                self.send_json({"error": "Worker token is missing or invalid"}, status=401)
                return
            job_id = parts[3]
            try:
                if parts[4] == "status":
                    self.send_json(apply_worker_status(job_id, self.read_json()))
                    return
                if parts[4] == "complete":
                    self.send_json(complete_worker_job(job_id, self.read_body()))
                    return
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=400)
                return

        if parsed.path == "/api/jobs":
            payload = self.read_json()
            url = str(payload.get("url", "")).strip()
            if not url:
                self.send_json({"error": "url is required"}, status=400)
                return
            job = create_job(url)
            self.send_json(job, status=201)
            return
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "jobs" and parts[3] == "render-selected":
            payload = self.read_json()
            try:
                result = render_selected_clips(parts[2], payload)
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=400)
                return
            self.send_json(result)
            return
        self.send_json({"error": "Not found"}, status=404)

    def read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def read_json(self) -> dict:
        raw = self.read_body()
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_static(self, request_path: str) -> None:
        path = unquote(request_path)
        if path in {"", "/"}:
            path = "/index.html"
        file_path = (WEB_DIR / path.lstrip("/")).resolve()
        if WEB_DIR not in file_path.parents and file_path != WEB_DIR:
            self.send_error(403)
            return
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404)
            return
        body = file_path.read_bytes()
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_media(self, request_path: str) -> None:
        relative = unquote(request_path.removeprefix("/media/"))
        file_path = (ROOT / relative).resolve()
        if ROOT not in file_path.parents and file_path != ROOT:
            self.send_error(403)
            return
        self.serve_file_path(file_path)

    def serve_export(self, request_path: str) -> None:
        relative = unquote(request_path.removeprefix("/exports/"))
        file_path = (EXPORTS_DIR / relative).resolve()
        if EXPORTS_DIR not in file_path.parents and file_path != EXPORTS_DIR:
            self.send_error(403)
            return
        self.serve_file_path(file_path)

    def serve_file_path(self, file_path: Path) -> None:
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        file_size = file_path.stat().st_size
        range_header = self.headers.get("Range")
        if range_header and range_header.startswith("bytes="):
            start_text, _, end_text = range_header.removeprefix("bytes=").partition("-")
            start = int(start_text or 0)
            end = int(end_text) if end_text else file_size - 1
            end = min(end, file_size - 1)
            if start > end:
                self.send_error(416)
                return
            length = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            with file_path.open("rb") as handle:
                handle.seek(start)
                self.wfile.write(handle.read(length))
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(file_size))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        with file_path.open("rb") as handle:
            self.wfile.write(handle.read())

    def log_message(self, format: str, *args: object) -> None:
        print(f"[server] {self.address_string()} - {format % args}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="clipper_pipeline.server")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8787")))
    args = parser.parse_args(argv)

    server = ThreadingHTTPServer((args.host, args.port), ClipperRequestHandler)
    print(f"Serving AI Shorts Clipper at http://{args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
