# GCP Credentials Review

검수 기준: 2026-05-21 KST

## 확인한 프로젝트

```text
project_id: noahsecond
account: noahlovesu@gmail.com
project_number: 877416316336
state: ACTIVE
```

## API 활성화 상태

다음 API가 이미 활성화되어 있다.

```text
drive.googleapis.com    ENABLED
youtube.googleapis.com  ENABLED
```

따라서 Google Drive API와 YouTube Data API를 새로 켤 필요는 없다.

## 기존 credentials.json 검수

현재 파일:

```text
/Users/noahai/Desktop/Auto-Up Project/credentials.json
```

검수 결과:

```text
type: installed / Desktop OAuth client
project_id: noahsecond
redirect_uris: http://localhost
client_id: present
client_secret: present
```

결론: 이 파일은 현재 GCP 프로젝트 `noahsecond`와 맞는 Desktop app OAuth client다. 새로 다운로드한 `credentials.json`을 만들 필요 없이 이 파일을 계속 참조하면 된다.

현재 업로더 설정:

```yaml
drive_ingest:
  drive_credentials_json: "/Users/noahai/Desktop/Auto-Up Project/credentials.json"
  drive_token_json: "./secrets/drive_token.json"
  drive_scopes:
    - "https://www.googleapis.com/auth/drive.readonly"

auth:
  credentials_json: "/Users/noahai/Desktop/Auto-Up Project/credentials.json"
  token_json: "/Users/noahai/Desktop/Auto-Up Project/token.json"
```

## 지금 필요한 단계

`credentials.json` 발급 단계는 완료된 것으로 보고, 다음은 Drive 전용 토큰 생성이다.

실행:

```bash
cd "/Users/noahai/Desktop/youtube shorts uploader codex"
PYTHONPATH=src python3 -m uploader.cli drive-auth --config config.yaml
```

이 명령은 브라우저를 열고 Google 계정 권한 확인을 요청한다. 성공하면 아래 파일이 생긴다.

```text
/Users/noahai/Desktop/youtube shorts uploader codex/secrets/drive_token.json
```

## OAuth 동의 화면에서 막힐 경우

브라우저 인증 중 `access blocked`, `앱이 확인되지 않음`, `test user` 관련 메시지가 뜨면 GCP 콘솔에서 아래를 확인한다.

1. `OAuth consent screen`
2. Publishing status가 Testing이면 `Test users`에 `noahlovesu@gmail.com` 추가
3. Scopes에 아래 Drive scope 포함

```text
https://www.googleapis.com/auth/drive.readonly
```

읽기 전용으로 충분하다. 현재 설계는 Drive에서 파일을 읽어 로컬 캐시에 내려받는 방식이며, Drive 폴더 이동/삭제는 하지 않는다.

## 날짜 폴더 업로드 기준

Drive 토큰이 만들어지면 앱은 아래 루트에서 실행 날짜 폴더를 찾는다.

```text
NoahAI Shorts Upload Hub
folder_id: 1gR0cVVGvS_0zziSG1gmclDetTZQSpYR8
```

예:

```text
2026-05-22 실행 -> NoahAI Shorts Upload Hub/20260522
```

테스트:

```bash
PYTHONPATH=src python3 -m uploader.cli scan --config config.yaml --date 20260522
```

`20260522` 폴더가 없으면 Drive 후보는 0개로 처리된다.
