from __future__ import annotations

import argparse
import io
import json
import os
import socket
import time
import zipfile
from dataclasses import asdict
from pathlib import Path

import requests

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


DEFAULT_SERVER = "https://thread-2.ningning.kr"


def serialize_candidate(candidate, index: int) -> dict:
    payload = asdict(candidate)
    return {
        "index": index,
        "startSec": payload["start_sec"],
        "endSec": payload["end_sec"],
        "durationSec": payload["duration_sec"],
        "category": payload["category"],
        "title": payload["title"],
        "reason": payload["reason"],
        "hashtags": payload["hashtags"],
        "score": payload["score"],
        "sourceText": payload["source_text"],
        "mostReplayed": payload["most_replayed"],
        "replaySource": payload["replay_source"],
        "replayScore": payload["replay_score"],
        "selected": True,
    }


class WorkerClient:
    def __init__(self, server_url: str, token: str, timeout: int = 60) -> None:
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def next_job(self) -> dict | None:
        response = self.session.get(f"{self.server_url}/api/worker/jobs/next", timeout=self.timeout)
        response.raise_for_status()
        return response.json().get("job")

    def status(
        self,
        job_id: str,
        *,
        step: str,
        step_status: str,
        step_progress: int,
        status: str = "running",
        failure: dict | None = None,
    ) -> None:
        payload = {
            "status": status,
            "currentStep": step,
            "step": step,
            "stepStatus": step_status,
            "stepProgress": step_progress,
            "failure": failure,
        }
        response = self.session.post(
            f"{self.server_url}/api/worker/jobs/{job_id}/status",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()

    def complete(self, job_id: str, archive: bytes) -> None:
        response = self.session.post(
            f"{self.server_url}/api/worker/jobs/{job_id}/complete",
            data=archive,
            headers={"Content-Type": "application/zip"},
            timeout=900,
        )
        response.raise_for_status()


def process_job(job: dict, client: WorkerClient, work_root: Path, worker_id: str) -> None:
    job_id = str(job["id"])
    url = str(job["url"]).strip()
    try:
        try:
            video_id = extract_youtube_id(url)
        except Exception:
            video_id = f"job-{job_id}"
        run_dir = work_root / f"youtube-{video_id}-{job_id}"
        run_dir.mkdir(parents=True, exist_ok=True)

        info_path = run_dir / "youtube-info.json"
        input_path = run_dir / "input.mp4"
        audio_path = run_dir / "audio.wav"
        transcript_path = run_dir / "transcript.txt"
        candidates_path = run_dir / "candidates.json"
        edit_config_path = run_dir / "edit-config-web.json"
        render_path = run_dir / "renders" / "clip-001-web.mp4"

        client.status(job_id, step="download_youtube", step_status="running", step_progress=8)
        info = youtube_info(url, info_path)
        client.status(job_id, step="download_youtube", step_status="running", step_progress=32)
        if not input_path.exists():
            download_youtube(url, input_path, 720)
        client.status(job_id, step="download_youtube", step_status="done", step_progress=100)

        client.status(job_id, step="extract_audio", step_status="running", step_progress=30)
        if not audio_path.exists():
            extract_audio(input_path, audio_path)
        client.status(job_id, step="extract_audio", step_status="done", step_progress=100)

        client.status(job_id, step="fetch_transcript", step_status="running", step_progress=30)
        if not transcript_path.exists():
            fetch_youtube_transcript(url, transcript_path, ["ko", "en"])
        client.status(job_id, step="fetch_transcript", step_status="done", step_progress=100)

        client.status(job_id, step="analyze", step_status="running", step_progress=40)
        segments = parse_transcript(transcript_path)
        candidates = analyze_segments(
            segments,
            max_candidates=6,
            most_replayed_range=extract_most_replayed_range(info),
        )
        write_candidates(candidates, candidates_path)
        client.status(job_id, step="analyze", step_status="done", step_progress=100)

        client.status(job_id, step="render", step_status="running", step_progress=35)
        candidate = load_candidate(candidates_path, 0)
        channel = str(info.get("channel") or "CHANNEL")
        write_default_edit_config(candidate, edit_config_path, channel)
        render_clip(input_path, candidate, render_path, "letterbox", edit_config_path, transcript_path)
        client.status(job_id, step="render", step_status="done", step_progress=100)

        archive = build_handoff_archive(
            run_dir=run_dir,
            title=info.get("title"),
            channel=info.get("channel"),
            worker_id=worker_id,
            candidates=candidates,
            paths={
                "info": info_path,
                "input": input_path,
                "transcript": transcript_path,
                "candidates": candidates_path,
                "editConfig": edit_config_path,
                "render": render_path,
            },
        )
        client.complete(job_id, archive)
        print(f"[worker] completed {job_id}: {url}")
    except Exception as exc:
        step = "download_youtube"
        try:
            step = str(job.get("currentStep") or step)
            failure = build_failure_state(
                step=step,
                error=exc,
                retry_command="start-job",
                retry_args={"url": url},
                url=url,
            )
            client.status(
                job_id,
                step=step,
                step_status="failed",
                step_progress=0,
                status="failed",
                failure=failure,
            )
        finally:
            print(f"[worker] failed {job_id}: {exc}")


def build_handoff_archive(
    *,
    run_dir: Path,
    title: object,
    channel: object,
    worker_id: str,
    candidates: list,
    paths: dict[str, Path],
) -> bytes:
    handoff = {
        "title": title,
        "channel": channel,
        "workerId": worker_id,
        "clips": [serialize_candidate(candidate, index) for index, candidate in enumerate(candidates, start=1)],
        "files": {
            key: str(path.relative_to(run_dir))
            for key, path in paths.items()
            if path.exists()
        },
    }
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("handoff.json", json.dumps(handoff, ensure_ascii=False, indent=2))
        for path in paths.values():
            if path.exists():
                archive.write(path, path.relative_to(run_dir))
    return archive_buffer.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="clipper_pipeline.hybrid_worker")
    parser.add_argument("--server", default=os.getenv("CLIPPER_SERVER_URL", DEFAULT_SERVER))
    parser.add_argument("--token", default=os.getenv("CLIPPER_WORKER_TOKEN", ""))
    parser.add_argument("--work-dir", default=os.getenv("CLIPPER_WORKER_DIR", "~/Desktop/thread-2-worker-runs"))
    parser.add_argument("--interval", type=float, default=float(os.getenv("CLIPPER_WORKER_INTERVAL", "5")))
    parser.add_argument("--worker-id", default=os.getenv("CLIPPER_WORKER_ID", socket.gethostname()))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)

    if not args.token:
        raise SystemExit("CLIPPER_WORKER_TOKEN or --token is required.")

    work_root = Path(args.work_dir).expanduser()
    work_root.mkdir(parents=True, exist_ok=True)
    client = WorkerClient(args.server, args.token)
    print(f"[worker] polling {args.server} as {args.worker_id}")

    while True:
        job = client.next_job()
        if job:
            print(f"[worker] picked {job['id']}: {job.get('url')}")
            process_job(job, client, work_root, args.worker_id)
        elif args.once:
            return 0
        else:
            time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
