# Thread 2 Codex

`thread-2.ningning.kr`에 배포할 두 번째 웹앱입니다.

원본 프로젝트는 `03 롱폼 to 쇼츠 자동변환기`이며, 로컬 FFmpeg/자막 분석 기반 쇼츠 후보 추천 및 렌더링 앱입니다. 이 저장소는 공개 배포 가능한 제품 소개형 운영 대시보드로 포팅한 버전입니다.

## 배포 설정

- Platform: DigitalOcean App Platform
- Resource type: Static Site
- Build command: `npm run build`
- Output directory: `dist`
- Domain: `thread-2.ningning.kr`

## 보안 메모

원본 앱의 로컬 영상 파일, 출력 MP4, API 키, 다운로드/렌더링 로그는 저장소에 포함하지 않습니다. 실제 영상 처리 기능은 서버형 백엔드와 작업 큐로 분리해야 합니다.
