import os
import secrets
from urllib.parse import urlencode

import requests
from flask import Flask, redirect, request, session, render_template_string

app = Flask(__name__)
app.secret_key = os.environ.get("WEB_SECRET_KEY", "")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=600,
)

CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "").strip()
BOT_TOKEN = os.environ.get("DISCORD_TOKEN", "").strip()
GUILD_ID = os.environ.get("DEV_GUILD_ID", "").strip()
ROLE_ID = os.environ.get("VERIFY_ROLE_ID", "").strip()
REDIRECT_URI = os.environ.get("OAUTH_REDIRECT_URI", "").strip()
API = "https://discord.com/api/v10"

HTML = """
<!doctype html><html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }}</title><style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:22px;background:radial-gradient(ellipse at top,#292c55,#1e1f22 65%);color:#f2f3f5;font-family:system-ui,sans-serif}
.card{width:min(100%,430px);padding:32px;border-radius:24px;background:#2b2d31;text-align:center;box-shadow:0 20px 70px #0006}
.logo{width:76px;height:76px;margin:0 auto 20px;border-radius:24px;background:#5865f2;display:grid;place-items:center;font-size:40px;font-weight:900}
h1{font-size:25px;margin:0 0 12px}p{color:#b5bac1;line-height:1.7;margin:0 0 24px}
.btn{display:block;padding:14px 18px;border-radius:10px;background:#5865f2;color:white;text-decoration:none;font-weight:750}
.btn:hover{background:#4752c4}.note{font-size:12px;color:#949ba4;margin-top:18px}
</style></head><body><main class="card"><div class="logo">D</div><h1>{{ title }}</h1><p>{{ message }}</p>{% if login %}<a class="btn" href="/login">Discord로 인증하기</a>{% endif %}<div class="note">Discord OAuth2 계정 인증</div></main></body></html>
"""

def page(title, message, login=False, status=200):
    return render_template_string(HTML, title=title, message=message, login=login), status

def missing_config():
    values = {
        "WEB_SECRET_KEY": app.secret_key,
        "DISCORD_CLIENT_ID": CLIENT_ID,
        "DISCORD_CLIENT_SECRET": CLIENT_SECRET,
        "DISCORD_TOKEN": BOT_TOKEN,
        "DEV_GUILD_ID": GUILD_ID,
        "VERIFY_ROLE_ID": ROLE_ID,
        "OAUTH_REDIRECT_URI": REDIRECT_URI,
    }
    return [key for key, value in values.items() if not value]

@app.get("/")
def index():
    missing = missing_config()
    if missing:
        app.logger.error("Missing environment variables: %s", ", ".join(missing))
        return page("설정이 필요합니다", "관리자가 서버 환경변수를 확인해야 합니다.", status=503)
    return page("Discord 인증 센터", "아래 버튼으로 Discord 계정을 인증하세요. 대상 서버에 가입되어 있어야 verify 역할을 받을 수 있습니다.", True)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/login")
def login():
    if missing_config():
        return page("설정이 필요합니다", "서버 환경변수를 확인해 주세요.", status=503)
    state = secrets.token_urlsafe(32)
    session.clear()
    session["oauth_state"] = state
    session.permanent = True
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "identify",
        "state": state,
    }
    return redirect("https://discord.com/oauth2/authorize?" + urlencode(params))

@app.get("/callback")
def callback():
    code = request.args.get("code", "")
    returned_state = request.args.get("state", "")
    expected_state = session.pop("oauth_state", None)
    if not expected_state or not secrets.compare_digest(expected_state, returned_state):
        return page("인증 실패", "인증 요청이 만료되었거나 올바르지 않습니다. 다시 시도해 주세요.", True, 400)
    if request.args.get("error"):
        return page("인증 취소", "Discord 인증이 취소되었습니다.", True, 400)
    if not code:
        return page("인증 실패", "Discord에서 인증 코드를 받지 못했습니다.", True, 400)

    try:
        token_res = requests.post(
            f"{API}/oauth2/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        token_res.raise_for_status()
        access_token = token_res.json()["access_token"]

        user_res = requests.get(
            f"{API}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        user_res.raise_for_status()
        user_id = str(user_res.json()["id"])

        headers = {"Authorization": f"Bot {BOT_TOKEN}"}
        member = requests.get(
            f"{API}/guilds/{GUILD_ID}/members/{user_id}",
            headers=headers, timeout=15
        )
        if member.status_code == 404:
            return page("서버 가입 필요", "먼저 인증 대상 Discord 서버에 가입한 뒤 다시 인증해 주세요.", True, 403)
        member.raise_for_status()

        role = requests.put(
            f"{API}/guilds/{GUILD_ID}/members/{user_id}/roles/{ROLE_ID}",
            headers=headers, timeout=15
        )
        if role.status_code in (401, 403):
            app.logger.error("Role assignment denied; check bot token, Manage Roles permission, and role hierarchy.")
            return page("역할 지급 실패", "봇 권한과 역할 위치를 관리자에게 확인해 주세요.", status=502)
        role.raise_for_status()
        return page("인증 완료!", "Discord 인증에 성공했고 verify 역할이 지급되었습니다.")
    except requests.RequestException:
        app.logger.exception("Discord API request failed")
        return page("인증 처리 오류", "Discord API 요청에 실패했습니다. 관리자에게 문의해 주세요.", True, 502)

if __name__ == "__main__":
    if not app.secret_key:
        raise RuntimeError("WEB_SECRET_KEY 환경변수가 필요합니다.")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")), debug=False)
