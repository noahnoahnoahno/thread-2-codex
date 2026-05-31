# Multi-Channel Upload Strategy

검수 기준: 2026-05-22 KST

## 현재 업로드 채널

최근 테스트 업로드 결과:

```text
channelTitle: noah's channel
channelId: UC5T05J8gaT28_K9v2kZLFwA
videoId: S9K42JdRU90
```

## 핵심 원칙

일반 YouTube 계정/브랜드 채널 운영에서는 채널마다 OAuth 토큰을 분리한다.

YouTube Data API의 `videos.insert`는 “요청에 사용한 OAuth 토큰이 선택한 채널”에 업로드한다. 일반 계정은 API 요청에서 임의의 채널 ID를 지정해 업로드할 수 없다. 채널 ID를 파라미터로 지정하는 `onBehalfOfContentOwnerChannel` 방식은 YouTube CMS/콘텐츠 파트너 전용이다.

따라서 실무 구조는 다음이 맞다.

```text
채널 A -> token A
채널 B -> token B
채널 C -> token C
```

## 권장 config 구조

```yaml
channels:
  default: noahs-channel
  items:
    noahs-channel:
      title: "noah's channel"
      channel_id: "UC5T05J8gaT28_K9v2kZLFwA"
      token_json: "/Users/noahai/Desktop/Auto-Up Project/token.json"
      credentials_json: "/Users/noahai/Desktop/Auto-Up Project/credentials.json"
      scopes:
        - "https://www.googleapis.com/auth/youtube.upload"
        - "https://www.googleapis.com/auth/youtube.readonly"
    channel-b:
      title: "Channel B"
      channel_id: ""
      token_json: "./secrets/youtube_channel_b.json"
      credentials_json: "/Users/noahai/Desktop/Auto-Up Project/credentials.json"
      scopes:
        - "https://www.googleapis.com/auth/youtube.upload"
        - "https://www.googleapis.com/auth/youtube.readonly"
```

## Drive 폴더 라우팅

운영자가 쓰기 쉬운 기본 방식은 Drive 폴더명으로 채널을 나누는 것이다.

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

앱은 날짜 폴더 바로 아래 첫 번째 폴더명을 채널 폴더명으로 해석한다.

현재 매핑:

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

이 방식이면 `upload.json`에 채널을 매번 쓰지 않아도 된다.

## upload.json 라우팅

여러 영상을 각각 다른 채널로 보내려면 item에 `channel`을 넣는다.

```json
{
  "project": "daily-shorts",
  "date": "20260522",
  "items": [
    {
      "video": "test01.mp4",
      "channel": "noahs-channel",
      "title": "첫 번째 쇼츠"
    },
    {
      "video": "test02.mp4",
      "channel": "channel-b",
      "title": "두 번째 쇼츠"
    }
  ]
}
```

`channel`이 없으면 상위 Drive 채널 폴더명을 사용하고, 그것도 없으면 `channels.default`로 업로드한다.

## 같은 영상을 여러 채널에 동시 업로드

두 가지 방식이 있다.

### 1. upload.json에 item을 채널별로 반복

```json
{
  "items": [
    {"video": "test01.mp4", "channel": "noahs-channel", "title": "A 채널 제목"},
    {"video": "test01.mp4", "channel": "channel-b", "title": "B 채널 제목"}
  ]
}
```

장점: 채널별 제목/설명/태그를 다르게 줄 수 있다.

### 2. 배포 그룹 사용

```json
{
  "items": [
    {
      "video": "test01.mp4",
      "channels": ["noahs-channel", "channel-b"],
      "title": "공통 제목"
    }
  ]
}
```

장점: 입력이 짧다. 단점: 채널별 SEO 차별화가 약하다.

초기 구현은 Drive 채널 폴더를 권장한다. 같은 영상을 여러 채널에 보내야 할 때만 item 반복 방식을 쓴다.

## 중복 방지

다채널에서는 같은 영상이라도 채널이 다르면 업로드가 허용되어야 한다.

기존:

```text
video_sha256
```

개선:

```text
channel_key + video_sha256
```

판정:

- 같은 채널 + 같은 영상 해시: 중복 차단
- 다른 채널 + 같은 영상 해시: 허용
- 같은 채널 + 같은 source fingerprint + 다른 해시: 재렌더 가능성, 검토 필요

## 인증 플로우

채널별로 한 번씩 실행한다.

```bash
python3 -m uploader.cli youtube-auth --channel noahs-channel
python3 -m uploader.cli youtube-auth --channel channel-b
python3 -m uploader.cli youtube-auth --channel nature-asmr
python3 -m uploader.cli youtube-auth --channel mosongeeai
```

브라우저에서 Google 계정/브랜드 채널을 선택하면 해당 채널용 토큰이 저장된다.

`ningning` 계정은 `Nature ASMR 4K Real Soundscapes`, `Vogue City`, `AmuseAsia`, `투썸무비` 채널의 OAuth client로 사용하고, `mosongeeai` 계정은 `mosongeeAi` 채널의 OAuth client로 사용한다.

```text
ningning -> ./secrets/ningning_youtube_credentials.json
mosongeeai -> ./secrets/mosongeeai_youtube_credentials.json
```

mosongeeai 계정에 채널이 여러 개 있으면 채널별 key를 추가하되 같은 credentials 파일을 공유하고 token 파일만 분리한다.

```text
mosongeeai-channel-a -> credentials: mosongeeai_youtube_credentials.json, token: youtube_mosongeeai_channel_a.json
mosongeeai-channel-b -> credentials: mosongeeai_youtube_credentials.json, token: youtube_mosongeeai_channel_b.json
```

OAuth 화면에서 `403 org_internal`이 나오면 해당 Google Cloud 프로젝트의 Audience가 `Internal`이다. 개인 Gmail 또는 조직 밖 계정으로 인증하려면 Google Auth Platform의 Audience를 `External`로 바꾸고, Testing 상태에서는 인증할 Gmail을 Test users에 추가한다. 이 설정 변경은 기존 downloaded credentials JSON의 `client_id/client_secret` 자체를 바꾸지 않으므로 같은 JSON을 계속 쓸 수 있다.

## 운영 권장

처음에는 모든 채널 업로드를 `private`로 한다.

1. `private` 업로드
2. 대시보드에서 channelTitle/channelId 확인
3. 잘못된 채널이면 토큰 삭제 후 다시 인증
4. 채널별 업로드 성공 기록 확인
5. 이후 예약 공개 또는 수동 공개
