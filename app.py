
import os
import secrets
from urllib.parse import urlencode

import requests
from flask import Flask, redirect, request, session, render_template_string

app = Flask(__name__)
app.secret_key = os.environ.get("WEB_SECRET_KEY", "").strip()

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
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }}</title>
<style>
*{box-sizing:border-box}
body{
 margin:0;min-height:100vh;display:grid;place-items:center;
 padding:22px;background:radial-gradient(ellipse at top,#292c55,#1e1f22 65%);
 color:#f2f3f5;font-family:system-ui,sans-serif
}
.card{
 width:min(100%,430px);padding:32px;border-radius:24px;
 background:#2b2d31;text-align:center;box-shadow:0 20px 70px #0006
}
.logo{
 width:76px;height:76px;margin:0 auto 20px;border-radius:24px;
 background:#5865f2;display:grid;place-items:center;
 font-size:40px;font-weight:900
}
h1{font-size:25px;margin:0 0 12px}
p{color:#b5bac1;line-height:1.7;margin:0 0 24px}
.btn{
 display:block;padding:14px 18px;border-radius:10px;
 background:#5865f2;color:white;text-decoration:none;font-weight:750
}
.btn:hover{background:#4752c4}
.note{font-size:12px;color:#949ba4;margin-top:18px}
</style>
</head>
<body>
<main class="card">
<div class="logo">D</div>
<h1>{{ title }}</h1>
<p>{{ message }}</p>
{% if login %}
<a class="btn" href="/login">Discord로 인증하기</a>
{% endif %}
<div class="note">Discord OAuth2 계정 인증</div>
</main>
</body>
</html>
"""


def page(title, message, login=False, status=200):
    return (
        render_template_string(
            HTML,
            title=title,
            message=message,
            login=login,
        ),
        status,
    )


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


def discord_error(response):
    """Discord API 오류의 상태 코드와 메시지를 기록한다."""
    try:
        data = response.json()
    except ValueError:
        data = {"message": response.text[:300]}

    # 응답 본문에는 비밀값을 출력하지 않는다.
    app.logger.error(
        "Discord API error: HTTP %s; response=%s",
        response.status_code,
        data,
    )
    return data


@app.get("/")
def index():
    missing = missing_config()

    if missing:
        app.logger.error(
            "Missing environment variables: %s",
            ", ".join(missing),
        )
        return page(
            "설정이 필요합니다",
            "관리자가 서버 환경변수를 확인해야 합니다.",
            status=503,
        )

    return page(
        "Discord 인증 센터",
        "아래 버튼으로 Discord 계정을 인증하세요. "
        "대상 서버에 가입되어 있어야 verify 역할을 받을 수 있습니다.",
        True,
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/login")
def login():
    if missing_config():
        return page(
            "설정이 필요합니다",
            "서버 환경변수를 확인해 주세요.",
            status=503,
        )

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

    return redirect(
        "https://discord.com/oauth2/authorize?" + urlencode(params)
    )


@app.get("/callback")
def callback():
    # 사용자가 Discord 인증을 취소했는지 먼저 확인한다.
    if request.args.get("error"):
        session.pop("oauth_state", None)
        return page(
            "인증 취소",
            "Discord 인증이 취소되었습니다.",
            True,
            400,
        )

    code = request.args.get("code", "")
    returned_state = request.args.get("state", "")
    expected_state = session.pop("oauth_state", None)

    if (
        not expected_state
        or not returned_state
        or not secrets.compare_digest(expected_state, returned_state)
    ):
        return page(
            "인증 실패",
            "인증 요청이 만료되었거나 올바르지 않습니다. 다시 시도해 주세요.",
            True,
            400,
        )

    if not code:
        return page(
            "인증 실패",
            "Discord에서 인증 코드를 받지 못했습니다.",
            True,
            400,
        )

    try:
        # 1. OAuth2 인증 코드를 액세스 토큰으로 교환
        token_res = requests.post(
            f"{API}/oauth2/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded"
            },
            timeout=15,
        )

        if not token_res.ok:
            discord_error(token_res)
            return page(
                "로그인 처리 실패",
                "Discord 로그인 토큰을 받지 못했습니다. "
                "관리자가 OAuth2 설정을 확인해야 합니다.",
                True,
                502,
            )

        token_data = token_res.json()
        access_token = token_data.get("access_token")

        if not access_token:
            app.logger.error("OAuth2 response has no access_token")
            return page(
                "로그인 처리 실패",
                "Discord에서 인증 토큰을 받지 못했습니다.",
                True,
                502,
            )

        # 2. 로그인한 Discord 사용자 정보 확인
        user_res = requests.get(
            f"{API}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )

        if not user_res.ok:
            discord_error(user_res)
            return page(
                "사용자 확인 실패",
                "Discord 사용자 정보를 확인하지 못했습니다.",
                True,
                502,
            )

        user_data = user_res.json()
        user_id = str(user_data["id"])

        # 3. 봇 토큰으로 대상 서버의 멤버인지 확인
        headers = {"Authorization": f"Bot {BOT_TOKEN}"}

        member = requests.get(
            f"{API}/guilds/{GUILD_ID}/members/{user_id}",
            headers=headers,
            timeout=15,
        )

        if member.status_code == 404:
            return page(
                "서버 가입 필요",
                "먼저 인증 대상 Discord 서버에 가입한 뒤 다시 인증해 주세요.",
                True,
                403,
            )

        if not member.ok:
            discord_error(member)
            return page(
                "서버 확인 실패",
                "봇이 서버 멤버를 확인하지 못했습니다. "
                "Render 로그를 확인해 주세요.",
                True,
                502,
            )

        # 4. 인증 역할 지급
        role = requests.put(
            f"{API}/guilds/{GUILD_ID}/members/{user_id}/roles/{ROLE_ID}",
            headers=headers,
            timeout=15,
        )

        if not role.ok:
            error_data = discord_error(role)
            error_code = error_data.get("code")
            error_message = error_data.get("message", "알 수 없는 오류")

            # 역할 지급 실패 원인을 브라우저에도 간단히 표시
            if role.status_code == 401:
                message = (
                    "봇 토큰이 유효하지 않습니다. "
                    "관리자가 Render의 DISCORD_TOKEN을 확인해야 합니다."
                )
            elif role.status_code == 403:
                message = (
                    "Discord가 역할 지급을 거부했습니다. "
                    "봇 권한과 역할 계층을 확인해 주세요."
                )
            elif role.status_code == 404:
                message = (
                    "서버 또는 역할을 찾지 못했습니다. "
                    "서버 ID와 역할 ID를 확인해 주세요."
                )
            else:
                message = (
                    f"Discord 역할 지급 실패 "
                    f"(HTTP {role.status_code}, 코드 {error_code}). "
                    "관리자가 Render 로그를 확인해야 합니다."
                )

            # 원인 분석용. 토큰과 인증 코드는 기록하지 않는다.
            app.logger.error(
                "Role assignment failed: HTTP %s, code=%s, message=%s",
                role.status_code,
                error_code,
                error_message,
            )

            return page(
                "역할 지급 실패",
                message,
                True,
                502,
            )

        app.logger.info("Role assigned successfully for user ID %s", user_id)

        return page(
            "인증 완료!",
            "Discord 인증에 성공했고 verify 역할이 지급되었습니다.",
        )

    except requests.Timeout:
        app.logger.exception("Discord API request timed out")
        return page(
            "요청 시간 초과",
            "Discord 서버 응답이 늦습니다. 잠시 후 다시 시도해 주세요.",
            True,
            502,
        )

    except requests.RequestException:
        app.logger.exception("Discord API request failed")
        return page(
            "인증 처리 오류",
            "Discord API 요청에 실패했습니다. 관리자에게 문의해 주세요.",
            True,
            502,
        )

    except (KeyError, ValueError):
        app.logger.exception("Unexpected Discord API response")
        return page(
            "인증 처리 오류",
            "Discord 응답을 처리하지 못했습니다. 관리자에게 문의해 주세요.",
            True,
            502,
        )


if __name__ == "__main__":
    if not app.secret_key:
        raise RuntimeError("WEB_SECRET_KEY 환경변수가 필요합니다.")

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "10000")),
        debug=False,
    )
