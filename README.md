# Task 7: Advanced API Usage and External API Integration

**Live demo:** https://task7-api-demo-1.onrender.com
**Source code:** https://github.com/NIKITA0420-coder/task7-api-demo

> Hosted on Render's free tier, so the first request after a period of inactivity can take about a minute.

A small Flask app that demonstrates OAuth 2.0 (GitHub), integration with an external API (GitHub REST API),
rate limiting and error handling.

## Try the live app
| URL | What it shows |
|---|---|
| https://task7-api-demo-1.onrender.com/login | Starts the GitHub OAuth login |
| https://task7-api-demo-1.onrender.com/api/me | Your GitHub profile (needs login) |
| https://task7-api-demo-1.onrender.com/api/repos | Your 5 latest repos (needs login) |
| https://task7-api-demo-1.onrender.com/api/users/octocat | Public profile; refresh 4 times in 30s to see the 429 |
| https://task7-api-demo-1.onrender.com/api/users/thisuserdoesnotexist12345 | Clean 404 error |
| https://task7-api-demo-1.onrender.com/logout | Ends the session; `/api/me` then returns 401 |

## 1. OAuth 2.0 concepts
| Term | Meaning |
|---|---|
| Resource owner | The user who owns the data |
| Client | This app |
| Authorization server | Issues tokens (GitHub) |
| Resource server | The API holding the data (api.github.com) |
| Scope | Limited permissions requested (`read:user public_repo`) |
| Access token | Short-lived credential sent as `Authorization: Bearer <token>` |
| Refresh token | Used to get new access tokens without logging in again |

**Authorization Code flow (used here):**
1. App redirects the user to GitHub with a random `state` value.
2. User logs in and approves the requested scopes.
3. GitHub redirects back to `/callback` with a `code` and the same `state`.
4. App checks `state` (CSRF protection), then exchanges `code` + client secret for an access token.
5. App calls the GitHub API with the token.

Notes:
- Public clients (SPAs, mobile apps) should use PKCE instead of a client secret.
- Other grants: Client Credentials (server-to-server), Device Code (TVs, CLIs). Implicit flow is deprecated.
- OAuth 2.0 is for authorization; OpenID Connect adds authentication.
- API keys identify an app; OAuth tokens represent a user's scoped, revocable consent.

## 2. External API integration
| Endpoint | Description | Auth |
|---|---|---|
| `/login`, `/callback`, `/logout` | OAuth flow and session | - |
| `/api/me` | Logged-in user's GitHub profile | OAuth |
| `/api/repos` | 5 most recently updated repos | OAuth |
| `/api/users/<name>` | Public profile of any user | Optional (uses token if logged in) |

Using the OAuth token raises GitHub's limit from 60 to 5,000 requests per hour.

## 3. Advanced features
- **Rate limiting:** sliding window per user/IP. Returns `429` with `Retry-After` and `X-RateLimit-*` headers.
  Limits: `/api/me` 10/min, `/api/repos` 5/min, `/api/users/<name>` 3 per 30s.
- **Resilient client:** timeouts, retries with exponential backoff on 5xx, `Retry-After` respected, and
  GitHub's own rate-limit headers translated into a clean 429.
- **Error handling:** centralized JSON error handlers (timeout -> 504, connection error -> 503,
  401, 404, 429, unexpected -> 500).

## Run locally
1. Create a GitHub OAuth App at https://github.com/settings/developers
   - Homepage URL: `http://localhost:5000`
   - Callback URL: `http://localhost:5000/callback`
2. Install and run (Windows Command Prompt):
   ```
   py -m pip install flask requests pytest
   set GITHUB_CLIENT_ID=your_client_id
   set GITHUB_CLIENT_SECRET=your_client_secret
   set SECRET_KEY=anything
   py app.py
   ```
   (PowerShell: use `$env:GITHUB_CLIENT_ID="..."` instead of `set`.)
3. Open `http://localhost:5000/login` (use `localhost`, not `127.0.0.1`), then try `/api/me` and `/api/repos`.
4. Hit `/api/users/octocat` 4 times within 30 seconds to see the 429 response.
5. Run tests: `py -m pytest -q`

## Deploy (Render)
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app --workers 1 --threads 4`
- Environment variables: `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `SECRET_KEY`, `PRODUCTION=1`
- Add `https://<your-app>.onrender.com/callback` as a redirect URI in the GitHub OAuth app.
- Use one worker: the rate limiter stores counters in memory. For multiple workers, use Redis.

## Security notes
- Secrets are read from environment variables and are never committed to the repo.
- Regenerate the client secret if it is ever exposed.
