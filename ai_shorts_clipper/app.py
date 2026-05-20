from __future__ import annotations

import sys

from ai_shorts_clipper.ytdlp_update import ensure_ytdlp_current


def main() -> None:
    ensure_ytdlp_current(reporter=lambda message: print(f"[startup] {message}", file=sys.stderr))

    from ai_shorts_clipper.cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
