# Thread 2 Laptop-Only Operation

스레드-2 `롱폼 to 쇼츠 자동변환기`는 웹 배포를 중단하고 랩탑 로컬 앱으로만 사용합니다.

## 결정 사항

- `thread-2.ningning.kr` 웹앱은 삭제 대상입니다.
- DigitalOcean App Platform의 Static Site/Web Service 운영은 사용하지 않습니다.
- Mac mini 하이브리드 워커도 사용하지 않습니다.
- YouTube 다운로드, 분석, 렌더링은 랩탑 로컬 환경에서 실행합니다.

## 실행 방법

```bash
cd "/Users/noahai/Desktop/99 웹앱 배포하기 codex/thread-2 codex"
python3 -m clipper_pipeline.server --host 127.0.0.1 --port 8787
```

브라우저에서 엽니다.

```text
http://127.0.0.1:8787
```

## 정리 기준

- 웹 배포용 환경 변수와 워커 토큰은 더 이상 필요하지 않습니다.
- `docs/hybrid-worker.md`와 `run-macmini-worker.command`는 과거 실험 기록입니다.
- 게이트 화면에서는 스레드-2를 외부 링크가 아닌 `랩탑 로컬 앱`으로 표시합니다.
