# AI Shorts Clipper Project

YouTube 주소를 입력하면 롱폼 영상을 분석해 쇼츠 후보를 추천하고, 사람이 빠르게 검수/편집한 뒤 MP4로 렌더링하는 프로그램을 만들기 위한 프로젝트입니다.

## 운영 방향

이 프로젝트는 웹 배포 대상에서 제외하고 랩탑 로컬 앱으로만 사용합니다.

- DigitalOcean `thread-2.ningning.kr` 배포는 종료합니다.
- Mac mini 하이브리드 워커 운영도 더 이상 사용하지 않습니다.
- 실제 사용은 랩탑에서 로컬 서버를 켜고 `http://127.0.0.1:8787`로 접속하는 방식입니다.
- YouTube 다운로드, 자막 처리, 렌더링은 모두 랩탑 로컬 환경에서 실행합니다.

## 현재 완료

- 대상 YouTube 영상의 한국어 자동 자막 추출
- 자막 기반 기능 분석
- 구현 가능 여부 정리
- MVP 워크플로우 설계
- 백로그와 아키텍처 초안 작성
- 샘플 클립 후보 작성
- YouTube URL 기반 메타데이터/다운로드/자막/렌더링 파이프라인 구현

## 주요 파일

- `youtube_sORoHYP7HRU_transcript_ko.txt`: 분석 대상 영상 자막
- `docs/video-analysis.md`: 자막 기반 기능 분석
- `docs/workflow.md`: 사용자/시스템 워크플로우
- `docs/concrete-workflow.md`: 실제 개발 단계별 워크플로우와 실행 명령
- `docs/options-and-development.md`: 영상 속 옵션 전체 정리와 디벨롭 방향
- `docs/editor-feature-analysis.md`: 타이틀 배치, 글자 입력, 레이아웃, 가이드 기능 분석
- `docs/ui-feature-implementation-spec.md`: 스크린캡처 기반 UI/기능 구현 설명서
- `docs/sample-clip-candidates.md`: 현재 영상 기준 샘플 후보
- `project/backlog.md`: 구현 백로그
- `project/architecture.md`: 기술 아키텍처 초안
- `project/phase-1-status.md`: 현재 시작된 Phase 1 진행 상태
- `project/youtube-url-test-WZBMyztg2ts.md`: 제공 YouTube URL 기반 테스트 결과
- `web/index.html`: URL 입력, 처리 상태, 실패 화면 프로토타입

## UI 프로토타입

실제 로컬 작업 실행 서버를 시작합니다.

```bash
python3 -m clipper_pipeline.server --host 127.0.0.1 --port 8787
```

브라우저에서 접속합니다.

[http://127.0.0.1:8787](http://127.0.0.1:8787)

현재 포함된 화면:

- YouTube URL 입력
- 영상 확인 카드
- 5단계 처리 상태
- 실패 화면
- `처음으로` / `다시 실행` 액션
- 분석 완료 후 AI 추천 후킹 구간 카드 리스트
- YouTube Most Replayed 또는 후킹 점수 fallback 기반 `가장 많이 본 구간` 필수 포함
- 궁금증/대비/증거/고통점/개인 경험/숫자/저가치 구간 패널티 기반 후보 점수화
- 후보 선택/해제
- 전체 선택/전체 해제
- 후보 상세 편집 패널
- 상세 편집 좌측 9:16 영상 미리보기
- 제목/해시태그/레이아웃/자막 스타일 프론트 상태 편집
- 제목 위치/크기/색상/외곽선 편집
- 채널명 입력/표시 토글/크기 편집
- 세로 크롭 포커스/줌과 세이프존 표시 토글
- 선택된 후보 edit-config 저장
- 선택된 후보 MP4 재렌더링
- 선택된 클립 최종 저장: `/Users/noahai/Desktop/randers-clips/YYYY-MM-DD/`
- 업로드 에이전트용 클립별 JSON 메타데이터와 날짜별 업로드 manifest 생성

현재 API:

- `POST /api/jobs`: URL 기반 작업 실행
- `GET /api/jobs/{id}`: 작업 상태 조회
- 작업 완료 시 `result.clips`에 후보 6개 반환
- `POST /api/jobs/{id}/render-selected`: 선택 후보 렌더링

## 하이브리드 웹앱 운영

이전에는 DigitalOcean App Platform에서 웹 화면과 작업 대기열을 운영하고, YouTube 다운로드/분석/렌더링은 집의 Mac mini 워커에서 실행하는 하이브리드 구조를 테스트했습니다.

현재는 운영 방향을 랩탑 로컬 전용으로 변경했으므로 이 구조는 사용하지 않습니다. 참고 기록은 `docs/hybrid-worker.md`에 남겨둡니다.

## 현재 실행 가능한 명령

YouTube 주소의 메타데이터를 확인합니다.

```bash
python3 -m clipper_pipeline youtube-info \
  --url "https://www.youtube.com/watch?v=WZBMyztg2ts" \
  --out runs/youtube-WZBMyztg2ts/youtube-info.json \
  --failure-out runs/youtube-WZBMyztg2ts/failure-state.json
```

YouTube 자막을 가져옵니다.

```bash
python3 -m clipper_pipeline fetch-transcript \
  --url "https://www.youtube.com/watch?v=WZBMyztg2ts" \
  --out runs/youtube-WZBMyztg2ts/transcript.txt \
  --languages "ko,en" \
  --failure-out runs/youtube-WZBMyztg2ts/failure-state.json
```

YouTube 영상을 다운로드합니다.

```bash
python3 -m clipper_pipeline download-youtube \
  --url "https://www.youtube.com/watch?v=WZBMyztg2ts" \
  --out runs/youtube-WZBMyztg2ts/input.mp4 \
  --max-height 720 \
  --failure-out runs/youtube-WZBMyztg2ts/failure-state.json
```

YouTube 처리 단계가 실패하면 traceback을 노출하지 않고 `failure-state.json`에 실패 화면 상태를 저장합니다. 이 상태에는 `처음으로` 액션과 `다시 실행` 액션이 들어갑니다.

자막에서 쇼츠 후보를 생성합니다.

```bash
python3 -m clipper_pipeline analyze \
  --transcript runs/youtube-WZBMyztg2ts/transcript.txt \
  --out runs/youtube-WZBMyztg2ts/candidates.json
```

후보 하나의 기본 편집 설정을 생성합니다.

```bash
python3 -m clipper_pipeline init-edit \
  --candidate runs/youtube-WZBMyztg2ts/candidates.json \
  --index 0 \
  --channel "ZeroCho TV" \
  --out runs/youtube-WZBMyztg2ts/edit-config.json
```

후보 하나를 9:16 MP4로 렌더링합니다.

```bash
python3 -m clipper_pipeline render \
  --input runs/youtube-WZBMyztg2ts/input.mp4 \
  --candidate runs/youtube-WZBMyztg2ts/candidates.json \
  --index 0 \
  --edit-config runs/youtube-WZBMyztg2ts/edit-config.json \
  --transcript runs/youtube-WZBMyztg2ts/transcript.txt \
  --out runs/youtube-WZBMyztg2ts/renders/clip-001.mp4
```

`edit-config.json`의 `subtitleStyle`에서 자동 자막 스타일을 조정할 수 있습니다. 현재 지원 값은 `fontFamily`, `fontSize`, `color`, `strokeColor`, `strokeWidth`, `backgroundEnabled`, `backgroundColor`, `backgroundOpacity`, `maxWidth`, `maxLines`, `x`, `y`, `anchor`, `align`입니다. 기본 폰트는 랩톱에 설치된 `NEXON Lv1 Gothic`입니다.

세로 크롭은 `layout`을 `crop`으로 바꾸고 `cropConfig`에서 조정합니다. 현재 지원 값은 `trackingMode`, `focusX`, `focusY`, `zoom`, `speakerTrackingEnabled`, `faceTrackingEnabled`입니다. `focusX/focusY`는 0.0부터 1.0까지의 화면 초점 비율이고, `zoom`은 1.0부터 2.0까지로 제한됩니다.

후보 6개를 일괄 렌더링합니다.

```bash
python3 -m clipper_pipeline render-all \
  --input runs/youtube-WZBMyztg2ts/input.mp4 \
  --candidate runs/youtube-WZBMyztg2ts/candidates.json \
  --out-dir runs/youtube-WZBMyztg2ts/batch-renders \
  --edit-config-dir runs/youtube-WZBMyztg2ts/batch-edit-configs \
  --manifest runs/youtube-WZBMyztg2ts/render-manifest.json \
  --channel "ZeroCho TV" \
  --layout letterbox \
  --transcript runs/youtube-WZBMyztg2ts/transcript.txt
```

렌더 결과물을 자동 검수합니다.

```bash
python3 -m clipper_pipeline validate-render \
  --input runs/youtube-WZBMyztg2ts/renders/clip-002-crop-right.mp4 \
  --edit-config runs/youtube-WZBMyztg2ts/edit-config-crop.json \
  --out runs/youtube-WZBMyztg2ts/validation-crop-right.json
```

검수 항목은 영상/오디오 스트림, 1080x1920 해상도, 길이, `yuv420p` 픽셀 포맷, 샘플 프레임 검은 화면 비율, 텍스트 레이어 캔버스 이탈/겹침입니다.

## 다음 작업

1. 후보 점수/제목 생성을 LLM 기반으로 고도화
2. 화자/얼굴 자동 추적 크롭 구현
3. 웹 편집기 UI 구현
4. 자막 없음 케이스에서 Whisper 대체 전사 연결
5. MP4 다운로드/내보내기 UX 구현

초기 MVP는 YouTube 주소 입력을 기본으로 하되, 사용 권한이 있는 영상 처리를 전제로 합니다.
