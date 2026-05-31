# 맥미니 Codex에 전달할 메시지

아래 내용을 맥미니의 Codex에 그대로 전달하세요.

```text
/Users/noahai/Desktop/youtube shorts uploader codex 폴더의 스레드-2 자동 쇼츠 업로드 앱을 맥미니 상시 운영용으로 실행해줘.

해야 할 일:
1. iCloud 동기화가 끝났는지 폴더와 secrets 파일 존재 여부를 확인한다.
2. 아래 명령을 실행한다.
   cd "$HOME/Desktop/youtube shorts uploader codex"
   chmod +x scripts/*.command scripts/thread2_uploader_launchd.zsh
   ./scripts/install_macmini_launchd.command
3. http://127.0.0.1:8782/web/index.html 접속이 되는지 확인한다.
4. /health가 정상인지 확인한다.
5. launchd 서비스 kr.ningning.thread2-uploader가 로드되었는지 확인한다.
6. 문제가 있으면 logs/thread2-uploader.err.log 내용을 확인해서 원인을 알려준다.

주의:
- DigitalOcean은 사용하지 않는다.
- 이 앱은 맥미니가 백엔드 서버 역할을 한다.
- 맥미니가 꺼지거나 잠자기에 들어가면 접속이 안 된다.
```
