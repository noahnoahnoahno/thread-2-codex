# Thread-2 Mac mini 운영 가이드

스레드-2는 DigitalOcean 유료 Web Service 대신 집의 맥미니에서 백엔드 서버를 계속 실행하는 방식으로 운영합니다.

## 구조

- 메인 게이트: `ningning.kr`
- 스레드-2 실제 앱: 맥미니에서 실행되는 로컬 Python 서버
- 기본 포트: `8782`
- 로컬 주소: `http://127.0.0.1:8782/web/index.html`
- 같은 와이파이 주소: `http://맥미니이름.local:8782/web/index.html`

## 맥미니에서 최초 1회 실행

1. iCloud Desktop 동기화가 끝났는지 확인합니다.
2. 맥미니에서 터미널을 열고 실행합니다.

```bash
cd "$HOME/Desktop/youtube shorts uploader codex"
chmod +x scripts/*.command scripts/thread2_uploader_launchd.zsh
./scripts/install_macmini_launchd.command
```

설치가 끝나면 아래 주소를 맥미니 브라우저에서 엽니다.

```text
http://127.0.0.1:8782/web/index.html
```

노트북이 같은 와이파이에 있으면 아래 형식으로 접속합니다.

```text
http://맥미니이름.local:8782/web/index.html
```

## 관리자 토큰

첫 실행 시 `.macmini.env` 파일이 자동 생성됩니다.

```text
UPLOADER_ADMIN_TOKEN=...
HOST=0.0.0.0
PORT=8782
```

웹 화면에서 폴더 확인, 스캔 갱신, Private 업로드 같은 버튼을 누를 때 관리자 토큰을 묻습니다. `.macmini.env` 안의 `UPLOADER_ADMIN_TOKEN` 값을 입력하면 됩니다.

## 자동 실행 확인

상태 확인:

```bash
launchctl print "gui/$(id -u)/kr.ningning.thread2-uploader"
```

로그 확인:

```bash
tail -f "$HOME/Desktop/youtube shorts uploader codex/logs/thread2-uploader.out.log"
tail -f "$HOME/Desktop/youtube shorts uploader codex/logs/thread2-uploader.err.log"
```

재시작:

```bash
launchctl kickstart -k "gui/$(id -u)/kr.ningning.thread2-uploader"
```

중지 및 제거:

```bash
cd "$HOME/Desktop/youtube shorts uploader codex"
./scripts/uninstall_macmini_launchd.command
```

## 맥미니 전원 설정

맥미니가 잠자기에 들어가면 서버도 멈출 수 있습니다.

- 시스템 설정 > 잠금 화면 또는 배터리/전원에서 잠자기 시간을 길게 설정
- 가능하면 전원 연결 상태로 상시 운영
- 네트워크가 끊기지 않도록 와이파이보다 유선 LAN 권장

## 외부 접속

같은 집 네트워크 안에서만 쓰면 추가 설정이 필요 없습니다.

집 밖에서도 `thread-2.ningning.kr`로 접속하려면 다음 중 하나가 필요합니다.

- Cloudflare Tunnel: 추천. 공유기 포트 개방 없이 무료로 공개 가능
- Tailscale Funnel: 간단하지만 별도 Funnel 주소를 쓰는 흐름이 더 자연스러움
- 공유기 포트포워딩: 가능하지만 보안과 유동 IP 관리가 번거로움

현재 단계에서는 맥미니 로컬 운영을 먼저 안정화하고, 외부 접속은 Cloudflare Tunnel 방식으로 별도 설정하는 것이 가장 안전합니다.
