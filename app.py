"""Task 7: Advanced API usage - OAuth 2.0, external API integration,
rate limiting and error handling (Flask + GitHub API)."""
import os, secrets, time, threading
from collections import defaultdict, deque
from functools import wraps
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from flask import Flask, jsonify, redirect, request, session, url_for
from werkzeug.exceptions import HTTPException

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(16))

from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=os.environ.get("PRODUCTION") == "1")

CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
AUTH_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
API_BASE = "https://api.github.com"


# ---------- Step 3a: rate limiting (sliding window, per client) ----------
class RateLimiter:
    def __init__(self, limit, window):
        self.limit, self.window = limit, window
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key):
        now = time.time()
        with self.lock:
            q = self.hits[key]
            while q and q[0] <= now - self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False, int(q[0] + self.window - now) + 1, 0
            q.append(now)
            return True, 0, self.limit - len(q)


def rate_limit(limit=5, window=60):
    limiter = RateLimiter(limit, window)

    def decorator(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            key = session.get("user") or request.remote_addr
            ok, retry_after, remaining = limiter.check(key)
            if not ok:
                resp = jsonify(error="rate_limit_exceeded",
                               message=f"Max {limit} requests per {window}s",
                               retry_after=retry_after)
                resp.status_code = 429
                resp.headers["Retry-After"] = str(retry_after)
                return resp
            resp = app.make_response(fn(*a, **kw))
            resp.headers["X-RateLimit-Limit"] = str(limit)
            resp.headers["X-RateLimit-Remaining"] = str(remaining)
            return resp
        return wrapper
    return decorator


# ---------- Step 3b: resilient client for the external API ----------
class UpstreamError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def build_session():
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5,  # waits 0.5s, 1s, 2s
                  status_forcelist=[500, 502, 503, 504],
                  allowed_methods=["GET"], respect_retry_after_header=True)
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers["Accept"] = "application/vnd.github+json"
    return s

http = build_session()


def github_get(path, token=None, params=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        r = http.get(f"{API_BASE}{path}", headers=headers, params=params, timeout=(3, 8))
    except requests.Timeout:
        raise UpstreamError("GitHub timed out", 504)
    except requests.ConnectionError:
        raise UpstreamError("Could not reach GitHub", 503)
    if r.status_code == 401:
        raise UpstreamError("Token invalid or expired - log in again", 401)
    if r.status_code == 404:
        raise UpstreamError("Resource not found", 404)
    if r.status_code in (403, 429) and r.headers.get("X-RateLimit-Remaining") == "0":
        reset = int(r.headers.get("X-RateLimit-Reset", time.time() + 60))
        raise UpstreamError(f"GitHub rate limit hit; resets in {max(0, int(reset - time.time()))}s", 429)
    if not r.ok:
        raise UpstreamError(f"GitHub error {r.status_code}", 502)
    return r.json()


# ---------- Step 1 + 2: OAuth 2.0 authorization code flow ----------
@app.route("/")
def index():
    return jsonify(message="Task 7 demo", logged_in=bool(session.get("token")),
                   endpoints=["/login", "/logout", "/api/me", "/api/repos", "/api/users/<name>"])


@app.route("/login")
def login():
    if not CLIENT_ID:
        raise UpstreamError("Set GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET first", 500)
    session["state"] = secrets.token_urlsafe(16)   # CSRF protection
    qs = urlencode({"client_id": CLIENT_ID, "scope": "read:user public_repo",
                    "state": session["state"],
                    "redirect_uri": url_for("callback", _external=True)})
    return redirect(f"{AUTH_URL}?{qs}")


@app.route("/callback")
def callback():
    if request.args.get("error"):
        raise UpstreamError(f"Authorization denied: {request.args['error']}", 403)
    if not request.args.get("state") or request.args["state"] != session.pop("state", None):
        raise UpstreamError("State mismatch (possible CSRF)", 400)
    try:
        r = requests.post(TOKEN_URL, headers={"Accept": "application/json"}, timeout=8,
                          data={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
                                "code": request.args.get("code")})
        data = r.json()
    except (requests.RequestException, ValueError):
        raise UpstreamError("Token exchange failed", 502)
    if "access_token" not in data:
        raise UpstreamError(data.get("error_description", "No access token returned"), 400)
    session["token"] = data["access_token"]
    session["user"] = github_get("/user", data["access_token"])["login"]
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    return jsonify(message="logged out")


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("token"):
            raise UpstreamError("Not authenticated - visit /login", 401)
        return fn(*a, **kw)
    return wrapper


@app.route("/api/me")
@login_required
@rate_limit(limit=10, window=60)
def me():
    u = github_get("/user", session["token"])
    return jsonify(login=u["login"], name=u["name"], public_repos=u["public_repos"])


@app.route("/api/repos")
@login_required
@rate_limit(limit=5, window=60)
def repos():
    data = github_get("/user/repos", session["token"], {"sort": "updated", "per_page": 5})
    return jsonify([{"name": r["name"], "stars": r["stargazers_count"], "url": r["html_url"]} for r in data])


@app.route("/api/users/<name>")           # public, no OAuth needed
@rate_limit(limit=3, window=30)
def public_user(name):
    u = github_get(f"/users/{name}", session.get("token"))
    return jsonify(login=u["login"], followers=u["followers"], public_repos=u["public_repos"])


# ---------- Step 3c: centralised error handling ----------
@app.errorhandler(UpstreamError)
def handle_upstream(e):
    return jsonify(error="upstream_or_auth_error", message=str(e)), e.status


@app.errorhandler(HTTPException)
def handle_http(e):
    return jsonify(error=e.name, message=e.description), e.code


@app.errorhandler(Exception)
def handle_unexpected(e):
    app.logger.exception("Unhandled error")
    return jsonify(error="internal_error", message="Something went wrong"), 500


if __name__ == "__main__":
    app.run(debug=False, port=5000)
