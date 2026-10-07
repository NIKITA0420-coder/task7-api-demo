# Task 7: Advanced API Usage and External API Integration

## 1. OAuth 2.0 concepts
| Term | Meaning |
|---|---|
| Resource owner | The user who owns the data |
| Client | Your app |
| Authorization server | Issues tokens (GitHub, Google...) |
| Resource server | The API holding the data (api.github.com) |
| Scope | Limited permissions requested (`read:user`) |
| Access token | Short-lived credential sent as `Authorization: Bearer <token>` |
| Refresh token | Used to get new access tokens without re-login |

**Authorization Code flow** (used here): app redirects user to the provider -> user consents ->
provider redirects back with `code` + `state` -> app exchanges `code` (with client secret) for an access token.
- `state` prevents CSRF. Public clients (SPAs/mobile) should add **PKCE**.
- Other grants: Client Credentials (server-to-server), Device Code (TVs/CLIs). Implicit flow is deprecated.
- OAuth 2.0 = authorization. **OpenID Connect** adds authentication (ID token).
- API keys identify an app; OAuth tokens represent a user's delegated, scoped, revocable consent.

## 2. Integration
Uses the GitHub REST API: `/user`, `/user/repos` (OAuth) and `/users/<name>` (public).

## 3. Advanced features
- **Rate limiting**: sliding window per user/IP -> `429` + `Retry-After`, `X-RateLimit-*` headers.
- **Resilient client**: timeouts, retries with exponential backoff on 5xx, `Retry-After` respected, handles upstream rate limit headers.
- **Error handling**: central JSON error handlers; maps timeout->504, connection->503, 401, 404, 429.

## Run
1. Create an OAuth App at github.com/settings/developers; callback URL `http://localhost:5000/callback`.
2. ```
   pip install flask requests pytest
   export GITHUB_CLIENT_ID=... GITHUB_CLIENT_SECRET=... SECRET_KEY=anything
   python app.py
   ```
3. Visit `/login`, then `/api/me`, `/api/repos`. Hit `/api/users/octocat` 4 times fast to see the 429.
4. Tests: `pytest -q`
