# YouTube Shorts Auto Uploader Workflow

리서치 기준: 2026-05-12 KST

## 1. 프로젝트 목표

데스크탑의 지정 폴더를 감시하다가 각 프로젝트의 결과물이 날짜별 폴더에 저장되면, 날짜 폴더 안의 영상과 메타데이터(`tag`, `hook`, `title`, `description`)를 읽어 YouTube Shorts에 맞게 검증, SEO 최적화, 업로드, 기록, 성과 피드백까지 자동화한다.

이 프로젝트는 기존 `movie to shorts codex` 결과물 구조도 1차 입력으로 지원한다. 현재 확인된 산출물은 `runs/YYYYMMDD-HHMMSS/final_shorts_*.mp4`, `clips.json`, `highlights.json` 형식이다.

## 2. 공식 제약 요약

- Shorts 판정: 2024-10-15 이후 일반 채널 기준으로 정사각형 또는 세로 비율 영상이 3분 이하이면 Shorts로 분류될 수 있다. 공식 아티스트 채널은 2025-12-08 이후 같은 기준이 적용된다.
- 업로드 API: YouTube Data API `videos.insert`는 영상을 업로드하고 `snippet.title`, `snippet.description`, `snippet.tags[]`, `snippet.categoryId`, `status.privacyStatus`, `status.publishAt`, `status.selfDeclaredMadeForKids`, `status.containsSyntheticMedia` 등을 설정할 수 있다.
- 공개 제한: 2020-07-28 이후 생성된 미검증 API 프로젝트에서 `videos.insert`로 올린 영상은 비공개로 제한된다. 공개 업로드를 자동화하려면 API Compliance Audit이 필요하다.
- 쿼터: YouTube Data API 기본 일일 쿼터는 10,000 units이며, 현재 `videos.insert`는 100 units로 표시된다. 업로드 전 잘못된 요청도 쿼터를 쓰므로 로컬 검증을 강하게 해야 한다.
- 메타데이터 제한: 제목은 최대 100자, 설명은 최대 5000 bytes, tags 배열은 전체 500자 제한이다.
- 일정 공개: `status.publishAt`은 `privacyStatus=private`일 때만 설정 가능하고, 과거 시각이면 즉시 공개 효과가 난다.
- 채널 업로드 제한: YouTube는 24시간 업로드 제한을 채널/국가/히스토리 등에 따라 다르게 적용한다. 제한 발생 시 24시간 후 재시도해야 한다.
- 정책: API 사용 서비스는 사용자 동의, 개인정보 보호, 데이터 삭제 요청 처리, 커뮤니티 가이드라인 준수 확인을 포함해야 한다.

## 3. 추천 기술 스택

- 언어: Python 3.12+
  이유: 기존 쇼츠 생성 프로젝트가 Python 기반이고, 파일 감시, ffprobe 검증, JSON 처리, CLI 자동화가 단순하다.
- 업로드: `google-api-python-client`, `google-auth-oauthlib`, resumable upload
  이유: OAuth 사용자 동의, 토큰 갱신, 대용량 업로드 재개를 안정적으로 처리한다.
- 파일 감시: `watchdog`
  이유: 날짜 폴더 생성/파일 저장 완료 이벤트를 로컬에서 가볍게 처리한다.
- 영상 검증: `ffprobe` / `ffmpeg`
  이유: 길이, 해상도, 회전 메타데이터, 코덱, 무음/손상 여부를 업로드 전에 확인한다.
- 메타데이터 스키마: Pydantic 또는 JSON Schema
  이유: `title`, `description`, `tags`, `privacy`, `scheduleAt` 같은 필드를 업로드 전 엄격히 검증한다.
- SEO 생성: OpenAI API Structured Outputs 또는 로컬 템플릿 폴백
  이유: 제목/설명/태그 후보를 JSON 스키마로 고정해 자동 업로드 전에 검수 가능한 형태로 만든다. 대량 사전 생성은 Batch API로 비용을 낮출 수 있다.
- 저장소: SQLite
  이유: 업로드 큐, 중복 방지 해시, YouTube videoId, 실패 이력, 성과 데이터를 가볍게 기록한다.
- 실행 방식: CLI 우선, 이후 로컬 대시보드 추가
  이유: 처음에는 안정적인 자동 업로드가 핵심이고, UI는 업로드 승인/로그 확인용으로 나중에 붙이는 편이 빠르다.

## 4. 입력 폴더 계약

기본 감시 루트:

```text
/Users/noahai/Desktop/shorts upload inbox/
  project-name/
    2026-05-12/
      final_shorts_1.mp4
      final_shorts_2.mp4
      upload.json
      clips.json
      highlights.json
```

권장 `upload.json`:

```json
{
  "project": "movie to shorts codex",
  "date": "2026-05-12",
  "items": [
    {
      "video": "final_shorts_1.mp4",
      "title": "AI 영상 편집, 5분 만에 쇼츠 10개?",
      "hook": "단 5분 만에 쇼츠 10개를 만드는 장면",
      "description": "AI 영상 편집의 핵심 장면을 짧게 정리했습니다.",
      "tags": ["AI 영상 편집", "쇼츠 자동화", "유튜브 쇼츠"],
      "hashtags": ["#Shorts", "#AI영상편집", "#쇼츠"],
      "categoryId": "24",
      "privacyStatus": "private",
      "publishAt": "2026-05-12T21:00:00+09:00",
      "selfDeclaredMadeForKids": false,
      "containsSyntheticMedia": false,
      "hasPaidProductPlacement": false,
      "notifySubscribers": false
    }
  ]
}
```

폴백 입력도 지원한다.

- `tag.txt`, `hook.txt`, `title.txt`, `description.txt`
- `clips.json`의 `title`, `hashtags`, `transcript`, `public_signals`
- `highlights.json`의 `movie`, `clips`, `scene_matches`
- 영상 파일명 규칙: `final_shorts_{clip_number}.mp4`

## 5. 전체 워크플로우

### Step 1. Watch & Detect

`watchdog`가 감시 루트 아래 새 날짜 폴더를 감지한다. 영상과 JSON/TXT 파일이 모두 안정화될 때까지 파일 크기를 2회 이상 비교해 쓰기 완료 상태를 확인한다.

출력:

- `queue` 테이블에 `pending` 작업 생성
- 날짜 폴더에 `.upload-lock` 생성
- 중복 방지용 video SHA-256 저장

### Step 2. Ingest & Normalize

입력 우선순위는 `upload.json` -> 개별 txt -> 기존 `clips.json/highlights.json` 순서다. 모든 입력을 내부 표준 모델 `UploadItem`으로 변환한다.

표준 모델:

```json
{
  "videoPath": "/absolute/path/final_shorts_1.mp4",
  "sourceProject": "movie to shorts codex",
  "sourceDate": "2026-05-12",
  "clipNumber": 1,
  "rawTitle": "",
  "rawHook": "",
  "rawDescription": "",
  "rawTags": [],
  "transcript": "",
  "publicSignals": {},
  "policyFlags": {}
}
```

### Step 3. Local Video Gate

업로드 전에 `ffprobe`로 다음을 확인한다.

- 길이: 180초 이하
- 비율: height >= width, 권장 1080x1920 또는 720x1280
- 파일 크기: 2KB 초과, 손상/빈 mov 제외
- 컨테이너/코덱: mp4/h264/aac 우선, 문제 시 ffmpeg로 재인코딩
- 오디오 권리: Shorts Audio Library 음악을 외부 상업 업로드에 쓴 경우 정책 리스크 표시

검증 실패 시 업로드하지 않고 `needs_review`로 이동한다.

### Step 4. SEO Metadata Builder

목표는 “과장 없이 클릭할 이유가 선명한 제목 + 첫 두 줄이 강한 설명 + 과하지 않은 해시태그 + 500자 이하 backend tags”다.

생성 규칙:

- 제목: 100자 이하, 핵심 키워드 앞쪽 배치, 불필요한 해시태그는 제목에 넣지 않음
- 설명: 첫 문장에 핵심 키워드와 hook 반영, 3-5개 해시태그를 끝에 배치
- Backend tags: 오탈자/동의어/긴꼬리 키워드 중심으로 5-8개, 전체 500자 이하
- `#Shorts`는 설명 해시태그 후보에 포함하되, Shorts 판정 자체는 비율/길이 검증을 기준으로 한다
- YouTube Help가 말하듯 제목/썸네일/설명이 tags보다 더 중요하므로 tags는 보조 신호로 취급한다
- 태그 나열을 설명에 과도하게 넣지 않는다

LLM 출력 스키마:

```json
{
  "title": "string <= 100 chars",
  "description": "string <= 5000 bytes",
  "tags": ["string"],
  "hashtags": ["#Shorts"],
  "categoryId": "24",
  "rationale": "short reason",
  "riskNotes": []
}
```

### Step 5. Human-Safe Review Gate

초기 버전은 기본값을 `private` 또는 `unlisted`로 둔다. 공개 자동화는 API 프로젝트 검증과 채널 운영 테스트 후 켠다.

자동 승인 가능 조건:

- 모든 검증 통과
- 제목/설명/태그 제한 통과
- 중복 업로드 아님
- `madeForKids`, 합성 미디어, 유료광고 여부가 명시됨
- API 프로젝트가 공개 업로드 가능한 상태이거나 `privacyStatus=private`

검토 필요 조건:

- 영화/방송/음악 등 저작권 리스크가 높은 소스
- 1분 초과 Shorts에 Content ID claim 가능성이 높은 음악 포함
- 합성/변조 미디어 여부 불명확
- paid product placement 여부 불명확
- 제목이 사실과 다르게 보이는 경우

### Step 6. YouTube Upload

`videos.insert(part="snippet,status,paidProductPlacementDetails")`로 업로드한다. 대용량 안정성을 위해 resumable upload를 사용한다.

요청에 포함할 값:

- `snippet.title`
- `snippet.description`
- `snippet.tags`
- `snippet.categoryId`
- `snippet.defaultLanguage`
- `status.privacyStatus`
- `status.publishAt`, 예약 공개일 때만
- `status.selfDeclaredMadeForKids`
- `status.containsSyntheticMedia`
- `paidProductPlacementDetails.hasPaidProductPlacement`

업로드 중 실패하면 같은 작업 ID로 재개하고, 재개 불가 오류는 exponential backoff 후 재시도한다. `dailyLimitExceeded`, `uploadLimitExceeded` 계열은 다음날로 연기한다.

### Step 7. Post-Upload Verification

업로드 후 `videos.list(part="snippet,status,contentDetails,processingDetails")`로 상태를 확인한다.

기록:

- YouTube `videoId`
- 업로드 시각
- privacy/publication 상태
- 처리 상태
- 최종 title/description/tags
- 로컬 video hash
- 소스 프로젝트/날짜/clip 번호

날짜 폴더에는 `upload_result.json`을 쓴다.

### Step 8. Analytics Feedback Loop

업로드 후 2시간, 24시간, 72시간 단위로 지표를 수집한다. Shorts viewCount는 2025-03-31부터 재생/반복 시작 기준으로 반환되므로 이전 방식의 watch-time 기준과 섞지 않는다.

수집 후보:

- `statistics.viewCount`
- `statistics.likeCount`
- `statistics.commentCount`
- 게시 후 시간
- 제목 패턴
- hook 유형
- tags/hashtags
- 길이/비율
- 기존 `public_signals`

분석 결과는 다음 업로드의 SEO 생성 프롬프트에 반영한다. 단, YouTube API 정책상 API 데이터와 외부 추정치를 섞어 공식 지표처럼 표시하지 않는다.

## 6. 디렉터리 구조

```text
youtube shorts uploader codex/
  docs/
    workflow.md
  src/
    uploader/
      config.py
      watcher.py
      ingest.py
      schemas.py
      video_probe.py
      seo.py
      youtube_client.py
      queue_db.py
      scheduler.py
      analytics.py
      cli.py
  tests/
    test_ingest.py
    test_video_probe.py
    test_seo_schema.py
    test_queue_db.py
  config.example.yaml
  pyproject.toml
  README.md
```

## 7. 구현 순서

1. 프로젝트 스캐폴드와 `UploadItem`/`UploadResult` 스키마 작성
2. 기존 `movie to shorts codex` 결과물용 ingest 어댑터 작성
3. `ffprobe` 기반 Shorts 검증기 작성
4. SQLite 큐와 중복 방지 해시 구현
5. SEO 메타데이터 생성기 구현: 템플릿 폴백 먼저, LLM Structured Outputs는 옵션
6. YouTube OAuth 초기 인증 CLI 구현
7. `videos.insert` private 업로드 테스트
8. 업로드 후 `videos.list` 검증 및 `upload_result.json` 기록
9. watcher 자동 감지 연결
10. 예약 공개, 재시도, 분석 피드백 루프 추가

## 8. 운영 기본값

```yaml
watch_root: "/Users/noahai/Desktop/shorts upload inbox"
default_privacy_status: "private"
default_category_id: "24"
default_language: "ko"
notify_subscribers: false
max_uploads_per_day: 20
min_seconds_between_uploads: 900
require_review_for_public: true
youtube_oauth_client_secret: "./secrets/client_secret.json"
token_store: "./secrets/youtube_token.json"
database: "./data/uploader.sqlite3"
```

## 9. 성공 기준

- 날짜 폴더에 영상과 메타데이터를 넣으면 자동으로 큐에 들어간다.
- Shorts 기준에 맞지 않는 영상은 업로드 전에 차단된다.
- 제목/설명/tags 제한을 넘는 항목은 자동 수정 또는 검토 대기로 간다.
- YouTube에 private 업로드가 성공하고 `videoId`가 로컬에 기록된다.
- 같은 영상은 해시 기준으로 중복 업로드되지 않는다.
- 업로드 실패는 원인과 다음 행동이 로그에 남는다.
- 24시간 후 성과 데이터가 다음 제목/설명 생성 규칙에 반영된다.

## 10. 참고 자료

- [YouTube Data API videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert)
- [YouTube Data API video resource](https://developers.google.com/youtube/v3/docs/videos)
- [YouTube Data API quota costs](https://developers.google.com/youtube/v3/determine_quota_cost)
- [YouTube three-minute Shorts Help](https://support.google.com/youtube/answer/15424877?hl=en)
- [YouTube upload errors Help](https://help.youtube.com/support/youtube/bin/answer.py?answer=166815&hl=en-US)
- [YouTube video tags Help](https://help.youtube.com/support/youtube/bin/answer.py?answer=146402&ctx=share)
- [YouTube API Services Developer Policies](https://developers.google.com/youtube/terms/developer-policies)
- [Complying with YouTube Developer Policies](https://developers.google.com/youtube/terms/developer-policies-guide)
- [OpenAI Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs)
- [OpenAI Batch API](https://platform.openai.com/docs/guides/batch)
