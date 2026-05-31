from __future__ import annotations

import base64
from pathlib import Path


SOURCE_FILES = {
    "UPLOADER_SECRET_AUTO_UP_CREDENTIALS_JSON_B64": Path("/Users/noahai/Desktop/Auto-Up Project/credentials.json"),
    "UPLOADER_SECRET_AUTO_UP_TOKEN_JSON_B64": Path("/Users/noahai/Desktop/Auto-Up Project/token.json"),
    "UPLOADER_SECRET_DRIVE_TOKEN_JSON_B64": Path("secrets/drive_token.json"),
    "UPLOADER_SECRET_NINGNING_YOUTUBE_CREDENTIALS_JSON_B64": Path("secrets/ningning_youtube_credentials.json"),
    "UPLOADER_SECRET_MOSONGEEAI_YOUTUBE_CREDENTIALS_JSON_B64": Path("secrets/mosongeeai_youtube_credentials.json"),
    "UPLOADER_SECRET_YOUTUBE_DAPJEONGSA_JSON_B64": Path("secrets/youtube_dapjeongsa.json"),
    "UPLOADER_SECRET_YOUTUBE_NANGMAN_TONGSINSA_JSON_B64": Path("secrets/youtube_nangman_tongsinsa.json"),
    "UPLOADER_SECRET_YOUTUBE_NINGNING_JSON_B64": Path("secrets/youtube_ningning.json"),
    "UPLOADER_SECRET_YOUTUBE_AMUSEASIA_JSON_B64": Path("secrets/youtube_amuseasia.json"),
    "UPLOADER_SECRET_YOUTUBE_VOGUE_CITY_JSON_B64": Path("secrets/youtube_vogue_city.json"),
    "UPLOADER_SECRET_YOUTUBE_TWOSOME_MOVIE_JSON_B64": Path("secrets/youtube_twosome_movie.json"),
    "UPLOADER_SECRET_YOUTUBE_MOSONGEEAI_JSON_B64": Path("secrets/youtube_mosongeeai.json"),
}


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    original_root = Path("/Users/noahai/Desktop/youtube shorts uploader codex")
    for env_name, source in SOURCE_FILES.items():
        path = source if source.is_absolute() else project_root / source
        if not path.exists() and not source.is_absolute():
            path = original_root / source
        if not path.exists():
            print(f"# missing: {env_name} <- {path}")
            continue
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        print(f"{env_name}={encoded}")


if __name__ == "__main__":
    main()
