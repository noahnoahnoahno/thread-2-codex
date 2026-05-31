# Integration Strategy

리서치/점검 기준: 2026-05-12 KST

## 결론

각 생성 프로젝트를 전부 다시 수정할 필요는 없다. 새 `youtube shorts uploader codex` 프로젝트가 각 프로젝트 폴더를 찾아 읽는 어댑터 구조로 가는 편이 맞다.

다만 장기적으로는 각 생성 프로젝트에 공통 `upload.json` 또는 `upload-manifest.json`을 내보내는 작은 변경을 추가하면 유지보수가 더 쉬워진다. 즉, 지금은 업로더에서 흡수하고, 나중에 생성 프로젝트들이 같은 계약으로 맞춰가면 된다.

## 현재 확인된 프로젝트별 상태

### 1. 실패했던 업로드 자동화

경로: `/Users/noahai/Desktop/Auto-Up Project`

확인된 파일:

- `auto_upload.py`
- `credentials.json`
- `token.json`
- `requirements.txt`
- `README.md`

재사용할 것:

- `credentials.json`
- `token.json`
- OAuth scope: `https://www.googleapis.com/auth/youtube.upload`

버릴/개선할 것:

- 오늘 날짜 폴더만 보는 구조
- `.md + mp4` 한 쌍만 찾는 구조
- 중복 방지 없음
- Shorts 길이/비율 검증 없음
- 업로드 결과 기록 부족
- SEO 메타데이터 생성/버전 관리 없음

새 업로더에서는 인증 JSON을 복사하지 않고 `config.yaml`에서 기존 경로를 참조한다.

### 2. 롱폼 to 쇼츠 계열

관련 경로:

- `/Users/noahai/Desktop/put adress-auto`
- `/Users/noahai/Desktop/randers-clips`

확인된 저장 구조:

```text
/Users/noahai/Desktop/randers-clips/2026-05-08/
  upload-manifest-*.json
  *-clip-*.mp4
  *-clip-*.json
```

개별 clip JSON에 있는 값:

- `sourceUrl`
- `sourceTitle`
- `sourceChannel`
- `clipIndex`
- `title`
- `hashtags`
- `startSec`
- `endSec`
- `durationSec`
- `videoPath`
- `uploadStatus`

부족한 값:

- SEO 설명문
- backend tags
- hook의 독립 필드
- transcript 또는 subtitle segment
- made for kids / synthetic media / paid placement
- 업로드 성공 후 YouTube `videoId`

업로더 처리 방식:

- manifest 또는 clip JSON을 읽어 `UploadItem`으로 정규화
- `editConfig`, `transcript.txt`, `candidates.json`, `youtube-info.json`를 찾아 자막/후킹 근거를 보강
- 부족한 설명문/tags는 SEO Builder가 생성
- 원본 YouTube URL이 있으면 중복/저작권 리스크 메모로 저장

### 3. 영화 to 쇼츠 계열

경로: `/Users/noahai/Desktop/movie to shorts codex`

확인된 저장 구조:

```text
/Users/noahai/Desktop/movie to shorts codex/runs/20260512-010757/
  final_shorts_1.mp4
  clips.json
  highlights.json
  scene_matches.json
  web_research_brief.json
```

`clips.json`/`highlights.json`에 있는 값:

- `clip_number`
- `title`
- `reason`
- `hashtags`
- `transcript`
- `source_transcript`
- `ko_transcript`
- `public_signals`
- 영화 제목/연도 추정값

부족한 값:

- YouTube 설명문
- backend tags
- 업로드 정책 필드
- 영상별 publish schedule
- 중복 업로드 기록

업로더 처리 방식:

- `final_shorts_{clip_number}.mp4`와 `clips[].clip_number`를 매칭
- `ko_transcript` 또는 `display_transcript`를 SEO 생성 입력으로 사용
- `reason`, `public_signals`, `scene_matches`를 제목/설명 생성 근거로 사용
- 영화/방송 저작권 리스크가 있으므로 기본값은 `private` 또는 `needs_review`

## 공통 정규화 모델

모든 어댑터는 최종적으로 아래 내부 모델로 바꾼다.

```json
{
  "sourceProject": "movie to shorts codex",
  "sourceRoot": "/absolute/project/path",
  "sourceRunDir": "/absolute/run/or/date/path",
  "videoPath": "/absolute/path/final_shorts_1.mp4",
  "clipIndex": 1,
  "sourceUrl": "",
  "sourceTitle": "",
  "sourceChannel": "",
  "titleSeed": "",
  "hookSeed": "",
  "descriptionSeed": "",
  "hashtagsSeed": [],
  "tagsSeed": [],
  "transcript": "",
  "startSec": null,
  "endSec": null,
  "durationSec": null,
  "publicSignals": {},
  "policy": {
    "selfDeclaredMadeForKids": false,
    "containsSyntheticMedia": false,
    "hasPaidProductPlacement": false,
    "requiresReview": true
  }
}
```

## SEO 결과물 관리

SEO 생성 결과는 업로드 직전 데이터와 분리해서 저장한다.

날짜/런 폴더에 저장:

```text
seo_metadata.json
upload_result.json
```

SQLite에 저장:

- `seo_metadata`
- `upload_jobs`
- `uploaded_videos`
- `source_fingerprints`
- `analytics_snapshots`

`seo_metadata` 필드:

- source hash
- video hash
- title
- description
- backend tags
- description hashtags
- 생성 모델/템플릿 버전
- 생성 시각
- 검증 결과
- 사람이 수정한 최종값 여부

## 업로드 중복 방지

중복 방지는 3단계로 한다.

1. 파일 해시: 영상 파일 SHA-256
2. 소스 지문: `sourceProject + sourceUrl/sourceTitle + clipIndex + startSec + endSec`
3. YouTube 결과: 업로드 성공 후 `videoId` 저장

같은 파일 해시가 이미 `uploaded`이면 업로드하지 않는다. 같은 소스 지문이 있는데 영상 해시만 다르면 `needs_review`로 보낸다. 재렌더링일 수 있기 때문이다.

## 각 프로젝트를 수정해야 하는가?

지금 당장은 아니다.

추천 순서:

1. 새 업로더에서 기존 산출물 구조를 읽는 어댑터를 먼저 만든다.
2. 업로더가 SEO 생성, 중복 방지, 업로드 결과 기록을 중앙에서 관리한다.
3. 실제 운영하며 어떤 필드가 반복적으로 부족한지 본다.
4. 그때 `롱폼 to 쇼츠`, `영화 to 쇼츠`에 공통 `upload.json` export만 아주 작게 추가한다.

이렇게 하면 기존 프로젝트를 깨지 않고도 바로 업로드 자동화가 가능하고, 나중에 필요한 부분만 유기적으로 디벨롭할 수 있다.

## 다음 구현 단위

1. `config.yaml` 로더
2. `randers_manifest` 어댑터
3. `movie_runs` 어댑터
4. SHA-256 중복 DB
5. SEO metadata store
6. `Auto-Up Project` 인증 경로를 쓰는 YouTube client
7. dry-run 리포트: 업로드 전에 “무엇을 올릴지” 표로 확인
