from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
import zipfile
import asyncio
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ai_shorts_clipper.analyzer import recommend_clips
from ai_shorts_clipper.media_ingest import extract_with_ytdlp, flow_to_json, inspect_allowed_url, import_to_json
from ai_shorts_clipper.render import render_candidates
from ai_shorts_clipper.transcript import load_transcript


APP_ROOT = Path(__file__).resolve().parent
DIST_DIR = APP_ROOT / "dist"
JOBS_DIR = Path(os.getenv("THREAD2_JOBS_DIR", tempfile.gettempdir())) / "thread2-jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="롱폼 to 쇼츠 자동변환기")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/inspect-url")
async def inspect_url(payload: dict[str, str]) -> dict:
    url = (payload.get("url") or "").strip()
    permission_state = payload.get("permission_state") or "needs_review"
    if not url:
        raise HTTPException(status_code=400, detail="URL을 입력하세요.")
    flow = inspect_allowed_url(url, permission_state=permission_state)
    return json.loads(flow_to_json(flow))


@app.post("/api/extract-url")
async def extract_url(payload: dict[str, object]) -> dict:
    url = str(payload.get("url") or "").strip()
    permission_state = str(payload.get("permission_state") or "needs_review")
    extractor_enabled = bool(payload.get("extractor_enabled"))
    if not url:
        raise HTTPException(status_code=400, detail="URL을 입력하세요.")

    job_dir = _new_job_dir()
    output_dir = job_dir / "originals"
    try:
        source_import = await asyncio.to_thread(
            extract_with_ytdlp,
            url,
            output_dir,
            permission_state,
            extractor_enabled,
        )
        payload_dict = json.loads(import_to_json(source_import))
        source_path = Path(source_import.source_path)
        source_json_path = job_dir / "source.json"
        source_json_path.write_text(json.dumps(payload_dict, ensure_ascii=False, indent=2), encoding="utf-8")
        zip_path = job_dir / "source-import.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(source_json_path, "source.json")
            if source_path.exists():
                archive.write(source_path, f"originals/{source_path.name}")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "job_id": job_dir.name,
        "download_url": f"/api/jobs/{job_dir.name}/source-download",
        "source_import": payload_dict,
    }


@app.post("/api/analyze")
async def analyze_subtitles(
    subtitles: Annotated[UploadFile, File(...)],
    count: Annotated[int, Form()] = 6,
    min_duration: Annotated[float, Form()] = 18,
    max_duration: Annotated[float, Form()] = 60,
) -> dict:
    job_dir = _new_job_dir()
    subtitle_path = await _save_upload(subtitles, job_dir)
    try:
        return _analyze_file(subtitle_path, count, min_duration, max_duration)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/render")
async def render_shorts(
    background_tasks: BackgroundTasks,
    video: Annotated[UploadFile, File(...)],
    subtitles: Annotated[UploadFile, File(...)],
    count: Annotated[int, Form()] = 6,
    min_duration: Annotated[float, Form()] = 18,
    max_duration: Annotated[float, Form()] = 60,
    layout: Annotated[str, Form()] = "crop",
    burn_subtitles: Annotated[bool, Form()] = False,
    render_limit: Annotated[int, Form()] = 3,
) -> dict:
    if layout not in {"crop", "letterbox"}:
        raise HTTPException(status_code=400, detail="layout은 crop 또는 letterbox만 가능합니다.")

    job_dir = _new_job_dir()
    video_path = await _save_upload(video, job_dir)
    subtitle_path = await _save_upload(subtitles, job_dir)

    try:
        analysis = _analyze_file(subtitle_path, count, min_duration, max_duration)
        candidates_path = job_dir / "candidates.json"
        candidates_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_job_status(
            job_dir,
            {
                "job_id": job_dir.name,
                "status": "queued",
                "message": "렌더링 대기 중입니다.",
                "clip_count": len(analysis["clips"]),
                "rendered_count": 0,
                "download_url": f"/api/jobs/{job_dir.name}/download",
                "clips": analysis["clips"],
            },
        )
        background_tasks.add_task(
            _run_render_job,
            job_dir,
            video_path,
            subtitle_path,
            count,
            min_duration,
            max_duration,
            layout,
            burn_subtitles,
            render_limit,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "job_id": job_dir.name,
        "status": "queued",
        "clip_count": len(analysis["clips"]),
        "rendered_count": 0,
        "status_url": f"/api/jobs/{job_dir.name}/status",
        "download_url": f"/api/jobs/{job_dir.name}/download",
        "clips": analysis["clips"],
    }


@app.get("/api/jobs/{job_id}/status")
def render_job_status(job_id: str) -> dict:
    if not _valid_job_id(job_id):
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return _read_job_status(job_dir)


@app.get("/api/jobs/{job_id}/download")
def download_job(job_id: str) -> FileResponse:
    if not _valid_job_id(job_id):
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    job_dir = JOBS_DIR / job_id
    if job_dir.exists():
        status_payload = _read_job_status(job_dir)
        if status_payload.get("status") in {"queued", "running"}:
            raise HTTPException(status_code=425, detail="렌더링이 아직 진행 중입니다.")
        if status_payload.get("status") == "failed":
            raise HTTPException(status_code=500, detail=status_payload.get("error") or "렌더링에 실패했습니다.")
    zip_path = JOBS_DIR / job_id / "shorts-output.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="다운로드 파일을 찾을 수 없습니다.")
    return FileResponse(zip_path, media_type="application/zip", filename="shorts-output.zip")


@app.get("/api/jobs/{job_id}/source-download")
def download_source_job(job_id: str) -> FileResponse:
    if not _valid_job_id(job_id):
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    zip_path = JOBS_DIR / job_id / "source-import.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="다운로드 파일을 찾을 수 없습니다.")
    return FileResponse(zip_path, media_type="application/zip", filename="source-import.zip")


def _new_job_dir() -> Path:
    job_dir = JOBS_DIR / uuid.uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=False)
    return job_dir


async def _save_upload(upload: UploadFile, directory: Path) -> Path:
    suffix = Path(upload.filename or "").suffix
    path = directory / f"{uuid.uuid4().hex}{suffix}"
    with path.open("wb") as file:
        shutil.copyfileobj(upload.file, file)
    await upload.close()
    return path


def _analyze_file(
    subtitle_path: Path,
    count: int,
    min_duration: float,
    max_duration: float,
) -> dict:
    segments = load_transcript(subtitle_path)
    candidates = recommend_clips(
        segments,
        count=count,
        min_duration=min_duration,
        max_duration=max_duration,
    )
    return {
        "source_subtitles": subtitle_path.name,
        "clip_count": len(candidates),
        "clips": [candidate.to_dict() for candidate in candidates],
    }


def _run_render_job(
    job_dir: Path,
    video_path: Path,
    subtitle_path: Path,
    count: int,
    min_duration: float,
    max_duration: float,
    layout: str,
    burn_subtitles: bool,
    render_limit: int,
) -> None:
    output_dir = job_dir / "renders"
    try:
        _write_job_status(
            job_dir,
            {
                **_read_job_status(job_dir),
                "status": "running",
                "message": "FFmpeg 렌더링 중입니다.",
            },
        )
        segments = load_transcript(subtitle_path)
        clip_candidates = recommend_clips(
            segments,
            count=count,
            min_duration=min_duration,
            max_duration=max_duration,
        )
        rendered = render_candidates(
            video_path,
            clip_candidates,
            output_dir,
            segments=segments,
            layout=layout,
            burn_subtitles=burn_subtitles,
            limit=render_limit,
        )
        candidates_path = job_dir / "candidates.json"
        zip_path = job_dir / "shorts-output.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(candidates_path, "candidates.json")
            for index, path in enumerate(rendered, start=1):
                archive.write(path, f"renders/clip_{index:02}.mp4")
            for index, srt_path in enumerate(sorted(output_dir.glob("*.srt")), start=1):
                archive.write(srt_path, f"renders/clip_{index:02}.srt")
        _write_job_status(
            job_dir,
            {
                **_read_job_status(job_dir),
                "status": "succeeded",
                "message": "렌더링 완료",
                "rendered_count": len(rendered),
            },
        )
    except Exception as exc:
        _write_job_status(
            job_dir,
            {
                **_read_job_status(job_dir),
                "status": "failed",
                "message": "렌더링 실패",
                "error": str(exc),
            },
        )


def _status_path(job_dir: Path) -> Path:
    return job_dir / "status.json"


def _read_job_status(job_dir: Path) -> dict:
    path = _status_path(job_dir)
    if not path.exists():
        return {"job_id": job_dir.name, "status": "unknown", "message": "작업 상태 파일이 없습니다."}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_job_status(job_dir: Path, payload: dict) -> None:
    path = _status_path(job_dir)
    tmp_path = job_dir / "status.tmp.json"
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _valid_job_id(job_id: str) -> bool:
    return len(job_id) == 32 and all(char in "0123456789abcdef" for char in job_id)


if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="static")
