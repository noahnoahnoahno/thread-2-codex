#!/bin/zsh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.macmini.env"

find_python() {
  local candidate version major minor
  for candidate in python3.14 python3.13 python3.12 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      version="$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
      major="${version%%.*}"
      minor="${version#*.}"
      if [ "$major" = "3" ] && [ "${minor:-0}" -ge 12 ]; then
        command -v "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

cd "$PROJECT_DIR"

PYTHON_BIN="$(find_python || true)"
if [ -z "$PYTHON_BIN" ]; then
  echo "Python 3.12 or newer is required."
  echo "Install it with Homebrew on the Mac mini:"
  echo "  brew install python@3.12"
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  umask 077
  token="$(/usr/bin/openssl rand -hex 18 2>/dev/null || "$PYTHON_BIN" -c 'import secrets; print(secrets.token_hex(18))')"
  {
    printf 'UPLOADER_ADMIN_TOKEN=%s\n' "$token"
    printf 'HOST=0.0.0.0\n'
    printf 'PORT=8782\n'
  } > "$ENV_FILE"
fi

set -a
source "$ENV_FILE"
set +a

export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8782}"

if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
  venv_version="$("$PROJECT_DIR/.venv/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
  venv_major="${venv_version%%.*}"
  venv_minor="${venv_version#*.}"
  if [ "$venv_major" != "3" ] || [ "${venv_minor:-0}" -lt 12 ]; then
    rm -rf "$PROJECT_DIR/.venv"
  fi
fi

if [ ! -d "$PROJECT_DIR/.venv" ]; then
  "$PYTHON_BIN" -m venv "$PROJECT_DIR/.venv"
fi

"$PROJECT_DIR/.venv/bin/python" -m pip install --upgrade pip
"$PROJECT_DIR/.venv/bin/python" -m pip install -e "$PROJECT_DIR"

echo
echo "Thread-2 uploader is starting."
echo "Mac mini local URL: http://127.0.0.1:${PORT}/web/index.html"
echo "Same Wi-Fi URL:      http://$(/bin/hostname -s).local:${PORT}/web/index.html"
echo "Admin token file:    $ENV_FILE"
echo

exec "$PROJECT_DIR/.venv/bin/python" -m uploader.cli serve --host "$HOST" --port "$PORT"
