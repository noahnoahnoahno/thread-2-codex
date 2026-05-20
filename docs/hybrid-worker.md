# Thread 2 Hybrid Worker

DigitalOcean App Platform은 웹 화면, 작업 접수, 상태 표시를 담당합니다. YouTube 다운로드와 영상 렌더링은 집의 Mac mini에서 실행되는 워커가 처리합니다.

## 왜 필요한가

DigitalOcean 서버 IP에서는 YouTube가 봇 확인을 요구할 수 있습니다. Mac mini는 집 인터넷망과 로그인된 브라우저 쿠키를 사용할 수 있으므로, 다운로드 성공률이 훨씬 높습니다.

## DigitalOcean 환경 변수

앱의 환경 변수에 아래 값을 추가합니다.

```bash
CLIPPER_JOB_MODE=hybrid
CLIPPER_WORKER_TOKEN=긴-랜덤-토큰
```

`CLIPPER_JOB_MODE=hybrid`는 Dockerfile에도 들어가 있지만, App Platform 설정에서도 보이면 그대로 두면 됩니다. `CLIPPER_WORKER_TOKEN`은 웹앱과 Mac mini 워커가 서로 맞는지 확인하는 비밀번호입니다.

## Mac mini 최초 설치

Desktop에 이 프로젝트 폴더가 iCloud로 동기화된 뒤 Mac mini에서 실행합니다.

```bash
cd "$HOME/Desktop/99 웹앱 배포하기 codex/thread-2 codex"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Chrome에 YouTube 로그인이 되어 있다면 아래처럼 실행합니다.

```bash
export CLIPPER_SERVER_URL="https://thread-2.ningning.kr"
export CLIPPER_WORKER_TOKEN="DigitalOcean에 넣은 같은 토큰"
export YT_DLP_COOKIES_FROM_BROWSER="chrome"
python -m clipper_pipeline.hybrid_worker
```

한 번만 테스트하려면 마지막 줄에 `--once`를 붙입니다.

```bash
python -m clipper_pipeline.hybrid_worker --once
```

## 운영 방식

1. 웹앱에서 YouTube URL을 입력합니다.
2. DigitalOcean은 작업을 `queued` 상태로 저장합니다.
3. Mac mini 워커가 작업을 가져갑니다.
4. Mac mini가 YouTube 다운로드, 자막, 분석, 첫 렌더링을 수행합니다.
5. 결과 파일을 웹앱에 업로드합니다.
6. 웹앱에서 후보 선택, 편집, 다운로드 흐름을 이어갑니다.

## 주의

- Mac mini가 꺼져 있으면 새 작업은 대기 상태로 남습니다.
- Chrome 쿠키를 쓰려면 Mac mini의 Chrome에서 YouTube 로그인이 되어 있어야 합니다.
- 긴 영상은 결과 업로드 파일이 커질 수 있습니다. 업로드 한계에 걸리면 다음 단계에서 “Mac mini가 최종 렌더까지 처리하고 웹앱은 결과만 표시”하는 구조로 더 분리합니다.
