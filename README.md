# 롱폼 to 쇼츠 자동변환기

`thread-2.ningning.kr`에 배포할 두 번째 웹앱입니다.

원본 프로젝트는 `롱폼 to 쇼츠 자동변환기`이며, 로컬 FFmpeg/자막 분석 기반 쇼츠 후보 추천 및 렌더링 앱입니다. 이 저장소는 원본 Python 분석/렌더링 로직을 포함한 서버형 웹앱입니다.

## 실제 기능

- URL 권한 검사: 원본 `inspect_allowed_url` 로직 사용
- 자막 분석: `.srt`, `.vtt`, `[mm:ss]` 텍스트 자막 업로드 후 후보 클립 JSON 생성
- 영상 렌더링: 영상 파일과 자막 파일 업로드 후 FFmpeg로 9:16 MP4 생성
- 결과 다운로드: 후보 JSON과 렌더링 MP4를 ZIP으로 다운로드

## 배포 설정

- Platform: DigitalOcean App Platform
- Resource type: Web Service
- Deployment: Dockerfile
- HTTP port: `8080`
- Domain: `thread-2.ningning.kr`

## 보안 메모

원본 앱의 로컬 영상 파일, 출력 MP4, API 키, 다운로드/렌더링 로그는 저장소에 포함하지 않습니다. 업로드된 파일과 렌더링 결과는 서버 임시 작업 폴더에 저장됩니다.
