# Discord 인증 웹사이트

## 환경변수
- `DISCORD_CLIENT_ID`: Developer Portal → General Information → Application ID
- `DISCORD_CLIENT_SECRET`: Developer Portal → OAuth2 → Client Secret
- `DISCORD_TOKEN`: Developer Portal → Bot → Token
- `DEV_GUILD_ID`: 대상 Discord 서버 ID
- `VERIFY_ROLE_ID`: verify 역할 ID
- `WEB_SECRET_KEY`: 강력한 무작위 문자열. Render Blueprint에서는 자동 생성
- `OAUTH_REDIRECT_URI`: `https://서비스이름.onrender.com/callback`

## Discord 설정
1. Developer Portal에서 애플리케이션을 선택합니다.
2. OAuth2 → Redirects에 실제 `https://서비스이름.onrender.com/callback` 주소를 등록합니다.
3. 봇을 대상 서버에 초대합니다.
4. 봇에 Manage Roles 권한을 주고 봇 역할을 verify 역할보다 위로 올립니다.

## Render 배포
1. 프로젝트 파일을 GitHub 저장소에 업로드합니다. 토큰이나 `.env` 파일은 올리지 마세요.
2. Render에서 New → Web Service를 선택하고 저장소를 연결합니다.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `gunicorn app:app`
5. Environment에 위 환경변수를 추가합니다.
6. Render가 제공하는 HTTPS 주소를 받은 뒤 `OAUTH_REDIRECT_URI`를 `https://실제주소.onrender.com/callback`으로 설정하고 Discord Redirects에도 똑같이 등록합니다.
7. 환경변수 저장 후 재배포합니다.

웹사이트는 `identify`만 요청하며 Discord 비밀번호를 받거나 저장하지 않습니다. 사용자는 대상 서버에 이미 가입해 있어야 합니다. 무료 호스팅은 절전 또는 사용량 제한이 있을 수 있습니다.
