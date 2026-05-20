from __future__ import annotations

import json
import os
import re
import shutil
import ssl
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PYPI_YTDLP_URL = "https://pypi.org/pypi/yt-dlp/json"
APP_SUPPORT_NAME = "AI Shorts Clipper"


@dataclass(frozen=True)
class YtDlpUpdateStatus:
    current_version: str | None
    latest_version: str | None
    updated: bool
    active_path: str | None
    warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "updated": self.updated,
            "active_path": self.active_path,
            "warning": self.warning,
        }


def ensure_ytdlp_current(
    app_data_dir: str | Path | None = None,
    timeout_sec: float = 8,
    reporter: Any | None = None,
) -> YtDlpUpdateStatus:
    vendor_root = _vendor_root(app_data_dir)
    active_path = activate_vendor_ytdlp(vendor_root)
    current_version = get_active_ytdlp_version()

    try:
        latest_payload = fetch_latest_ytdlp_payload(timeout_sec=timeout_sec)
        latest_version = str(latest_payload["info"]["version"])
        if current_version and not _is_newer_version(latest_version, current_version):
            _report(reporter, f"yt-dlp is current: {current_version}")
            return YtDlpUpdateStatus(current_version, latest_version, False, active_path)

        wheel_url = _select_wheel_url(latest_payload, latest_version)
        installed_path = install_ytdlp_wheel(wheel_url, latest_version, vendor_root, timeout_sec=timeout_sec)
        active_path = activate_ytdlp_path(installed_path)
        current_version = get_active_ytdlp_version()
        _report(reporter, f"yt-dlp updated to {current_version or latest_version}")
        return YtDlpUpdateStatus(current_version, latest_version, True, active_path)
    except Exception as exc:
        warning = f"yt-dlp update check failed: {exc}"
        _report(reporter, warning)
        return YtDlpUpdateStatus(current_version, None, False, active_path, warning=warning)


def default_app_data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_SUPPORT_NAME
    if os.name == "nt":
        root = os.environ.get("APPDATA")
        return Path(root) / APP_SUPPORT_NAME if root else Path.home() / "AppData" / "Roaming" / APP_SUPPORT_NAME
    root = os.environ.get("XDG_DATA_HOME")
    return Path(root) / "ai-shorts-clipper" if root else Path.home() / ".local" / "share" / "ai-shorts-clipper"


def activate_vendor_ytdlp(vendor_root: Path) -> str | None:
    current_file = vendor_root / "current.txt"
    if not current_file.exists():
        return None
    version_dir_name = current_file.read_text(encoding="utf-8").strip()
    if not version_dir_name:
        return None
    version_dir = vendor_root / version_dir_name
    if not version_dir.exists():
        return None
    return activate_ytdlp_path(version_dir)


def activate_ytdlp_path(path: str | Path) -> str:
    path = str(Path(path).resolve())
    if path not in sys.path:
        sys.path.insert(0, path)
    _purge_ytdlp_modules()
    return path


def get_active_ytdlp_version() -> str | None:
    try:
        from yt_dlp.version import __version__
    except Exception:
        return None
    return str(__version__)


def fetch_latest_ytdlp_payload(timeout_sec: float = 8) -> dict[str, Any]:
    request = urllib.request.Request(PYPI_YTDLP_URL, headers={"User-Agent": "ai-shorts-clipper/0.1"})
    with urllib.request.urlopen(request, timeout=timeout_sec, context=_ssl_context()) as response:
        return json.loads(response.read().decode("utf-8"))


def install_ytdlp_wheel(
    wheel_url: str,
    version: str,
    vendor_root: str | Path,
    timeout_sec: float = 30,
) -> Path:
    vendor_root = Path(vendor_root)
    vendor_root.mkdir(parents=True, exist_ok=True)
    version_dir = vendor_root / _version_dir_name(version)
    if version_dir.exists() and (version_dir / "yt_dlp").exists():
        (vendor_root / "current.txt").write_text(version_dir.name, encoding="utf-8")
        return version_dir

    with tempfile.TemporaryDirectory(prefix="yt-dlp-wheel-") as temp_name:
        temp_dir = Path(temp_name)
        wheel_path = temp_dir / "yt_dlp.whl"
        _download_file(wheel_url, wheel_path, timeout_sec=timeout_sec)
        staging_dir = temp_dir / "staging"
        staging_dir.mkdir()
        _safe_extract_zip(wheel_path, staging_dir)
        if not (staging_dir / "yt_dlp").exists():
            raise RuntimeError("Downloaded yt-dlp wheel did not contain the yt_dlp package.")
        if version_dir.exists():
            shutil.rmtree(version_dir)
        shutil.move(str(staging_dir), version_dir)

    (vendor_root / "current.txt").write_text(version_dir.name, encoding="utf-8")
    _prune_old_versions(vendor_root, keep=version_dir.name)
    return version_dir


def _vendor_root(app_data_dir: str | Path | None) -> Path:
    root = Path(app_data_dir).expanduser() if app_data_dir else default_app_data_dir()
    return root / "vendor" / "yt-dlp"


def _select_wheel_url(payload: dict[str, Any], version: str) -> str:
    files = payload.get("releases", {}).get(version, [])
    for item in files:
        filename = str(item.get("filename", ""))
        if item.get("packagetype") == "bdist_wheel" and filename.endswith(".whl"):
            return str(item["url"])
    for item in payload.get("urls", []):
        filename = str(item.get("filename", ""))
        if item.get("packagetype") == "bdist_wheel" and filename.endswith(".whl"):
            return str(item["url"])
    raise RuntimeError(f"No yt-dlp wheel found for version {version}.")


def _download_file(url: str, output_path: Path, timeout_sec: float) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "ai-shorts-clipper/0.1"})
    with urllib.request.urlopen(request, timeout=timeout_sec, context=_ssl_context()) as response:
        output_path.write_bytes(response.read())


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def _safe_extract_zip(zip_path: Path, target_dir: Path) -> None:
    target_root = target_dir.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            member_path = (target_dir / member.filename).resolve()
            if target_root not in {member_path, *member_path.parents}:
                raise RuntimeError(f"Unsafe path in yt-dlp wheel: {member.filename}")
        archive.extractall(target_dir)


def _is_newer_version(candidate: str, current: str) -> bool:
    candidate_parts = _version_parts(candidate)
    current_parts = _version_parts(current)
    if candidate_parts and current_parts:
        length = max(len(candidate_parts), len(current_parts))
        return candidate_parts + (0,) * (length - len(candidate_parts)) > current_parts + (0,) * (
            length - len(current_parts)
        )
    return candidate > current


def _version_parts(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", value))


def _version_dir_name(version: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", version).strip("._-")
    return f"yt_dlp_{safe}"


def _purge_ytdlp_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "yt_dlp" or module_name.startswith("yt_dlp."):
            sys.modules.pop(module_name, None)


def _prune_old_versions(vendor_root: Path, keep: str) -> None:
    for path in vendor_root.iterdir():
        if path.name == keep or path.name == "current.txt" or not path.is_dir():
            continue
        if path.name.startswith("yt_dlp_"):
            shutil.rmtree(path, ignore_errors=True)


def _report(reporter: Any | None, message: str) -> None:
    if reporter is not None:
        reporter(message)
