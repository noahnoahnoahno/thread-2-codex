# Google Drive Date Folder Ingest Plan

검수 기준: 2026-05-21 KST

## 결론

Google Drive 입력은 전용 루트 폴더 내부의 `YYYYMMDD` 날짜 폴더를 기준으로 처리한다.

확정 루트:

```text
NoahAI Shorts Upload Hub
https://drive.google.com/drive/folders/1gR0cVVGvS_0zziSG1gmclDetTZQSpYR8
```

앱이 실행되는 날짜가 `2026-05-22`이면 Drive에서 아래 폴더만 찾는다.

```text
NoahAI Shorts Upload Hub/20260522
```

그 폴더 안의 최종 쇼츠 영상과 메타데이터를 업로드 후보로 만든다. 날짜가 다르면 자동 업로드 대상이 아니다.

## 폴더 구조

권장 구조:

```text
NoahAI Shorts Upload Hub/
  20260522/
    noah'channel/
      final_shorts_1.mp4
      final_shorts_1.json
    답정사/
      final_shorts_2.mp4
      final_shorts_2.json
    낭만통신사/
      final_shorts_3.mp4
      final_shorts_3.json
```

날짜 폴더 바로 아래에 영상을 놓으면 기본 채널(`noahs-channel`)로 처리한다.

프로젝트별 폴더를 쓰고 싶다면 채널 폴더 아래에 한 단계 더 둘 수 있다.

```text
NoahAI Shorts Upload Hub/
  20260522/
    답정사/
      movie-to-shorts/
        final_shorts_1.mp4
        clips.json
        highlights.json
      longform-to-shorts/
        clip-001.mp4
        clip-001.json
        upload-manifest.json
```

앱은 기본적으로 날짜 폴더 안을 2단계 깊이까지 본다.

## 채널 폴더명 매핑

폴더명이 업로드 채널을 결정한다.

현재 매핑:

```text
noah'channel, noah's channel, noah channel -> noahs-channel
답정사 -> dapjeongsa
낭만통신사 -> nangman-tongsinsa
ningning -> nature-asmr
Nature ASMR 4K Real Soundscapes -> nature-asmr
Vogue City -> vogue-city
AmuseAsia -> amuseasia
투썸무비 -> twosome-movie
mosongeeai -> mosongeeai
```

알 수 없는 폴더명은 후보로 잡되 `requires_review=true`로 표시한다. 실제 업로드하려면 `config.yaml`의 `channels.items`에 해당 폴더명을 추가해야 한다.

## 날짜 판정

기본값:

```yaml
timezone: "Asia/Seoul"
date_folder_format: "%Y%m%d"
target_date: ""
```

`target_date`가 비어 있으면 앱 실행 시점의 `Asia/Seoul` 날짜를 사용한다.

테스트나 예약 실행 검증은 CLI에서 날짜를 강제로 줄 수 있다.

```bash
python3 -m uploader.cli scan --config config.yaml --date 20260522
```

## 검색 방식

전체 Drive를 검색하지 않는다. 루트 폴더 ID 내부에서만 날짜 폴더를 찾는다.

날짜 폴더 검색:

```text
'1gR0cVVGvS_0zziSG1gmclDetTZQSpYR8' in parents
and name = '20260522'
and mimeType = 'application/vnd.google-apps.folder'
and trashed = false
```

날짜 폴더 내부 파일 검색:

```text
'{dateFolderId}' in parents
and trashed = false
and (
  mimeType contains 'video/'
  or mimeType = 'application/json'
  or mimeType = 'text/plain'
)
```

하위 채널/프로젝트 폴더가 있으면 그 폴더 내부도 같은 방식으로 검색한다. 첫 번째 하위 폴더명이 채널 폴더명이다.

## 파일 계약

최소:

```text
final_shorts_1.mp4
```

권장:

```text
final_shorts_1.mp4
upload.json
```

JSON을 직접 만들지 않는 방식:

```text
test01.mp4
test01.png
```

영상과 같은 이름의 캡처 이미지가 있으면 앱이 로컬 캐시에 `test01.generated.json`을 자동 생성한다.
생성된 JSON은 다음 스캔에서 먼저 재사용한다.

우선순위:

1. `upload.json`
2. 같은 이름 JSON: `test01.json`
3. 로컬 캐시에 이미 생성된 같은 이름 JSON: `test01.generated.json`
4. 같은 이름 캡처 이미지: `test01.png`, `test01.jpg`, `test01.webp`
5. 파일명 기반 폴백

이미지 기반 생성은 Gemini API를 선택적으로 사용한다.

```bash
export GEMINI_API_KEY="..."
```

키가 없으면 파일명 기반의 보수적인 폴백 메타데이터를 만들고 `requires_review=true`로 둔다.

각 채널 폴더에 `_metadata_template.json` 양식을 배포할 수 있다.

```bash
python3 -m uploader.cli drive-write-templates --config config.yaml --date 20260531
```

이미지 분석 규칙:

- 이미지는 생성하지 않고 분석만 한다.
- 제목/설명에 이모지, 불꽃, 하트, 장식문자를 넣지 않는다.
- 선정적/외모 품평식 표현을 피하고 장면/행동 중심으로 쓴다.
- 제목은 후킹 가능해야 하고, 시청자가 왜 봐야 하는지 즉시 알 수 있어야 한다.
- 설명 첫 두 줄은 장면 맥락, 핵심 행동, 검색 키워드를 자연스럽게 포함해야 한다.
- SEO tags는 장면, 행동, 분위기, 트렌드 키워드 중심으로 구성한다.
- 클릭을 유도하되 이미지에서 확인되지 않는 허위 과장이나 낚시 표현은 금지한다.
- 최종 업로드 전에는 검토 필요 상태로 둔다.

`upload.json` 예시:

```json
{
  "project": "movie-to-shorts",
  "date": "20260522",
  "items": [
    {
      "video": "final_shorts_1.mp4",
      "channel": "dapjeongsa",
      "title": "곧 항공시간이 10,000시간 넘는 거 아니에요?",
      "hook": "숫자와 질문으로 시작하는 긴장감 있는 장면",
      "description": "",
      "tags": [],
      "hashtags": ["#Shorts", "#영화쇼츠"],
      "privacyStatus": "private",
      "selfDeclaredMadeForKids": false,
      "containsSyntheticMedia": false,
      "hasPaidProductPlacement": false
    }
  ]
}
```

`channel`을 생략하면 상위 채널 폴더명으로 결정한다. 상위 폴더명도 없으면 기본 채널로 간다.

폴백 메타데이터:

- `clips.json`
- `highlights.json`
- `*-clip-*.json`
- `upload-manifest*.json`
- `title.txt`, `hook.txt`, `description.txt`, `tag.txt`

메타데이터가 없으면 파일명과 자막/JSON 폴백 없이 기본 SEO 목업을 만든 뒤 `requires_review=true`로 둔다.

## 다운로드 방식

YouTube Data API는 Drive URL을 직접 업로드하지 않는다. Drive 파일을 로컬 캐시에 다운로드한 뒤 YouTube에 업로드한다.

흐름:

1. 실행 날짜 계산
2. Drive 루트에서 `YYYYMMDD` 폴더 검색
3. 날짜 폴더 내부의 영상/JSON/TXT 검색
4. 같은 이름 이미지가 있으면 함께 검색
5. `data/drive_cache/YYYYMMDD/{fileId}/`로 다운로드
6. JSON이 없으면 이미지 기반 `*.generated.json` 생성
7. 기존 로컬 어댑터와 같은 `UploadItem`으로 정규화
8. `ffprobe` Shorts 검증
9. SEO 메타데이터 생성
10. SHA-256, Drive `md5Checksum`, source fingerprint로 중복 확인
11. YouTube에는 로컬 캐시 파일을 resumable upload

## 인증

기존 YouTube 업로드 토큰:

```text
/Users/noahai/Desktop/Auto-Up Project/token.json
```

이 토큰은 YouTube 업로드 scope만 갖고 있으므로 Drive 읽기에는 사용할 수 없다.

Drive용 별도 토큰:

```text
./secrets/drive_token.json
```

권장 scope:

```text
https://www.googleapis.com/auth/drive.readonly
```

초기에는 읽기 전용만 사용한다. 업로드 성공 후 Drive 폴더 이동은 나중에 `drive.file` 또는 쓰기 scope를 별도로 검토한다.

## 업로드 기준

앱 실행 날짜와 같은 날짜 폴더만 업로드 후보가 된다.

예:

- 2026-05-21 실행: `20260521`만 스캔
- 2026-05-22 실행: `20260522`만 스캔
- `20260522` 폴더가 없으면 업로드 후보 0개
- `20260522` 폴더가 있어도 영상이 없으면 업로드 후보 0개

## 업로드 트리거

트리거는 날짜 폴더 내부의 채널 폴더를 업로드 단위로 삼는다.

```text
NoahAI Shorts Upload Hub/
  YYYYMMDD/
    noah's channel/
    답정사/
    낭만통신사/
    Nature ASMR 4K Real Soundscapes/
    Vogue City/
    AmuseAsia/
    투썸무비/
    mosongeeai/
```

트리거 실행 순서:

1. `drive-setup-folders`와 같은 로직으로 날짜/채널 폴더가 모두 있는지 확인하고 없으면 만든다.
2. 실행 날짜와 같은 `YYYYMMDD` 폴더만 스캔한다.
3. 첫 번째 하위 폴더명을 채널 폴더명으로 해석한다.
4. 채널 토큰, 영상 검증, 중복 방지, 검토 상태를 확인한다.
5. `--execute`가 없으면 dry-run 결과만 만든다.
6. `--execute`가 있으면 private 업로드를 순차 실행한다.

```bash
python3 -m uploader.cli trigger-upload --config config.yaml --date 20260531
python3 -m uploader.cli trigger-upload --config config.yaml --date 20260531 --execute --allow-review
```

## 다음 구현 순서

1. `drive-auth` CLI로 Drive read-only 토큰 생성
2. `scan --date YYYYMMDD` 옵션 구현
3. Drive 루트 내부 날짜 폴더 검색
4. 날짜 폴더 파일 다운로드
5. 대시보드에 Drive 후보 통합
6. 이후 `private` YouTube 업로드 연결

## 참고 공식 문서

- [Google Drive API: Search for files and folders](https://developers.google.com/workspace/drive/api/guides/search-files)
- [Google Drive API: files.get](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/get)
- [Gemini API: Image understanding](https://ai.google.dev/gemini-api/docs/vision)
