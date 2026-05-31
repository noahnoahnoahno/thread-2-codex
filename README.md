# YouTube Shorts Uploader Codex

베타 목업입니다. 실제 YouTube 업로드 전 단계까지 수행합니다.

## 지금 되는 것

- `randers-clips` 날짜 폴더 스캔
- `movie to shorts codex/runs` 스캔
- 후보 영상을 내부 `UploadItem`으로 정규화
- `ffprobe`가 있으면 길이/비율/해상도 검사
- SHA-256 기반 중복 방지 DB 생성
- 자막/제목/해시태그 기반 SEO 메타데이터 목업 생성
- 로컬 대시보드 생성

## 실행

```bash
python3 -m uploader.cli scan --config config.yaml --limit 80
python3 -m uploader.cli scan --config config.yaml --date 20260522
python3 -m uploader.cli drive-auth --config config.yaml
python3 -m uploader.cli drive-setup-folders --config config.yaml
python3 -m uploader.cli drive-write-templates --config config.yaml --date 20260531
python3 -m uploader.cli youtube-channels --config config.yaml
python3 -m uploader.cli youtube-auth --config config.yaml --channel ningning
python3 -m uploader.cli youtube-auth --config config.yaml --channel mosongeeai
python3 -m uploader.cli trigger-upload --config config.yaml --date 20260531
python3 -m uploader.cli trigger-upload --config config.yaml --date 20260531 --execute --allow-review
python3 -m uploader.cli upload-private --config config.yaml --channel noahs-channel --allow-review
python3 -m uploader.cli serve --port 8765
```

대시보드:

```text
http://127.0.0.1:8765/web/index.html
```

## 인증

`config.yaml`은 기존 실패 프로젝트의 인증 파일을 참조합니다.

```yaml
credentials_json: "/Users/noahai/Desktop/Auto-Up Project/credentials.json"
token_json: "/Users/noahai/Desktop/Auto-Up Project/token.json"
```

베타 목업은 토큰을 사용해 업로드하지 않습니다. 다음 단계에서 `private` 업로드를 붙입니다.

Drive 입력은 `NoahAI Shorts Upload Hub/YYYYMMDD` 폴더를 실행 날짜 기준으로 찾습니다.
예를 들어 2026-05-22에 실행하면 Drive 루트 내부의 `20260522` 폴더만 스캔합니다.

## 이미지로 JSON 자동 생성

JSON을 직접 만들지 않고, 영상과 같은 이름의 캡처 이미지를 올릴 수 있습니다.

```text
20260522/
  noah'channel/
    test01.mp4
    test01.png
```

앱은 `test01.png`를 분석해서 로컬 캐시에 `test01.generated.json`을 만듭니다.
한 번 생성된 `test01.generated.json`은 다음 스캔에서 재사용하므로 같은 이미지를 계속 API로 다시 분석하지 않습니다.

Gemini를 쓰려면 환경변수를 설정합니다.

```bash
export GEMINI_API_KEY="..."
# 또는
export GOOGLE_API_KEY="..."
```

키가 없으면 파일명 기반 폴백 메타데이터를 만들고 검토 필요로 표시합니다.

메타데이터 생성 규칙:

- 제목은 후킹 가능해야 합니다.
- 첫눈에 시청자가 왜 봐야 하는지 보여줘야 합니다.
- 설명 첫 줄에는 장면 맥락과 검색 키워드가 자연스럽게 들어가야 합니다.
- SEO tags는 장면, 행동, 분위기, 트렌드 키워드 중심으로 구성합니다.
- 이모지, 불꽃, 장식문자, 허위 과장, 선정적 표현은 쓰지 않습니다.

## 다채널 업로드

가장 쉬운 방식은 날짜 폴더 내부에 채널별 폴더를 만드는 것입니다.

```text
NoahAI Shorts Upload Hub/
  20260522/
    noah'channel/
      test01.mp4
      test01.json
    답정사/
      test02.mp4
      test02.json
    낭만통신사/
      test03.mp4
      test03.json
```

같은 이름 JSON 양식:

```json
{
  "project": "google-drive-date-folder",
  "date": "20260531",
  "video": "test01.mp4",
  "channel": "",
  "title": "시청자가 바로 클릭할 이유가 보이는 후킹형 제목",
  "hook": "첫 문장에 궁금증, 반전, 핵심 행동, 장면 긴장감 중 하나를 넣습니다.",
  "description": "첫 두 줄에 핵심 장면과 검색 키워드를 자연스럽게 넣습니다.",
  "tags": ["유튜브 쇼츠", "쇼츠 하이라이트", "장면 키워드"],
  "hashtags": ["#Shorts", "#쇼츠", "#하이라이트"],
  "transcript": "",
  "requires_review": false,
  "selfDeclaredMadeForKids": false,
  "containsSyntheticMedia": false,
  "hasPaidProductPlacement": false
}
```

프로젝트 안에도 템플릿이 있습니다.

```text
templates/same_name_metadata_template.json
templates/upload_json_template.json
```

대시보드의 `JSON 양식 배포` 버튼이나 아래 명령을 쓰면 각 Drive 채널 폴더에 `_metadata_template.json`을 넣습니다.

```bash
python3 -m uploader.cli drive-write-templates --config config.yaml --date 20260531
```

폴더명 매핑:

```text
noah'channel -> noahs-channel
답정사 -> dapjeongsa
낭만통신사 -> nangman-tongsinsa
ningning -> nature-asmr
Nature ASMR 4K Real Soundscapes -> nature-asmr
Vogue City -> vogue-city
AmuseAsia -> amuseasia
투썸무비 -> twosome-movie
mosongeeai -> mosongeeai
```

`ningning` 계정은 `Nature ASMR 4K Real Soundscapes`, `Vogue City`, `AmuseAsia`, `투썸무비` 채널의 credentials로 사용하고, `mosongeeai`는 `mosongeeAi` 채널의 credentials로 사용합니다.

```text
secrets/ningning_youtube_credentials.json
secrets/mosongeeai_youtube_credentials.json
```

각 계정의 실제 YouTube 채널은 `youtube-auth`에서 OAuth 채널 선택 후 토큰으로 확정합니다.

더 세밀하게 지정해야 할 때만 `upload.json`의 item에 `channel`을 넣습니다.

```json
{
  "items": [
    {"video": "test01.mp4", "channel": "noahs-channel", "title": "A 채널 제목"},
    {"video": "test02.mp4", "channel": "channel-b", "title": "B 채널 제목"}
  ]
}
```

같은 영상도 채널이 다르면 별도 업로드로 허용하고, 같은 채널에 같은 영상 해시가 있으면 중복으로 차단합니다.

## 업로드 트리거

트리거는 Google Drive 날짜 폴더를 기준으로 작동합니다.

```text
NoahAI Shorts Upload Hub/
  20260531/
    noah's channel/
    답정사/
    낭만통신사/
    Nature ASMR 4K Real Soundscapes/
    Vogue City/
    AmuseAsia/
    투썸무비/
    mosongeeai/
```

미리보기:

```bash
python3 -m uploader.cli trigger-upload --config config.yaml --date 20260531
```

실제 업로드:

```bash
python3 -m uploader.cli trigger-upload --config config.yaml --date 20260531 --execute --allow-review
```

트리거는 먼저 날짜/채널 폴더를 생성 또는 확인하고, 각 채널 폴더 안의 업로드 가능한 영상을 해당 채널 토큰으로 private 업로드합니다. 같은 채널에 같은 영상 해시가 이미 업로드된 경우는 중복으로 차단합니다.
