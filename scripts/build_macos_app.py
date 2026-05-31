from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw


VERSION = "0.1.0"
APP_NAME = f"YouTube Shorts Uploader Codex v{VERSION}"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESKTOP = Path.home() / "Desktop"
APP_PATH = DESKTOP / f"{APP_NAME}.app"
BUILD_DIR = PROJECT_ROOT / "build" / "macos-app"
ICONSET = BUILD_DIR / "AppIcon.iconset"


def main() -> None:
    if APP_PATH.exists():
        shutil.rmtree(APP_PATH)
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    (APP_PATH / "Contents" / "MacOS").mkdir(parents=True)
    (APP_PATH / "Contents" / "Resources").mkdir(parents=True)
    ICONSET.mkdir(parents=True)

    source_icon = BUILD_DIR / "app_icon_1024.png"
    create_icon_source(source_icon)
    create_icns(source_icon, APP_PATH / "Contents" / "Resources" / "AppIcon.icns")
    write_info_plist(APP_PATH / "Contents" / "Info.plist")
    write_launcher(APP_PATH / "Contents" / "MacOS" / APP_NAME)
    print(APP_PATH)


def create_icon_source(path: Path) -> None:
    size = 1024
    image = Image.new("RGBA", (size, size), "#0d3b4c")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((72, 72, 952, 952), radius=190, fill="#0d3b4c")
    draw.rounded_rectangle((150, 176, 874, 768), radius=86, fill="#f8fafc")
    draw.rounded_rectangle((210, 242, 814, 702), radius=54, fill="#132f41")

    play = [(390, 352), (390, 594), (602, 473)]
    draw.polygon(play, fill="#ffffff")

    draw.rounded_rectangle((348, 732, 676, 824), radius=46, fill="#18a999")
    draw.polygon([(512, 610), (384, 740), (458, 740), (458, 864), (566, 864), (566, 740), (640, 740)], fill="#18a999")
    draw.line((258, 304, 766, 304), fill="#18a999", width=28)
    draw.line((258, 650, 766, 650), fill="#315c9c", width=28)

    image.save(path)


def create_icns(source_icon: Path, output_icns: Path) -> None:
    sizes = [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]
    for filename, size in sizes:
        subprocess.run(
            ["sips", "-z", str(size), str(size), str(source_icon), "--out", str(ICONSET / filename)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    subprocess.run(["iconutil", "-c", "icns", str(ICONSET), "-o", str(output_icns)], check=True)


def write_info_plist(path: Path) -> None:
    info = {
        "CFBundleDevelopmentRegion": "ko",
        "CFBundleDisplayName": APP_NAME,
        "CFBundleExecutable": APP_NAME,
        "CFBundleIconFile": "AppIcon",
        "CFBundleIdentifier": "com.noahai.youtube-shorts-uploader-codex",
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": APP_NAME,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
    }
    with path.open("wb") as file:
        plistlib.dump(info, file)


def write_launcher(path: Path) -> None:
    script = f"""#!/bin/zsh
set -e

PROJECT_DIR={shell_quote(str(PROJECT_ROOT))}
PORT="${{YTSU_PORT:-8765}}"
MAX_PORT=$((PORT + 30))

cd "$PROJECT_DIR"

while /usr/bin/nc -z 127.0.0.1 "$PORT" >/dev/null 2>&1; do
  PORT=$((PORT + 1))
  if [ "$PORT" -gt "$MAX_PORT" ]; then
    /usr/bin/osascript -e 'display alert "YouTube Shorts Uploader" message "사용 가능한 로컬 포트를 찾지 못했습니다."'
    exit 1
  fi
done

URL="http://127.0.0.1:${{PORT}}/web/index.html"

(
  sleep 1.2
  /usr/bin/open "$URL"
) &

export PYTHONPATH="$PROJECT_DIR/src"
exec /usr/bin/env python3 -m uploader.cli serve --port "$PORT"
"""
    path.write_text(script, encoding="utf-8")
    os.chmod(path, 0o755)


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


if __name__ == "__main__":
    main()
