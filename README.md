# WOLFX Academy – Flask backend + JSON API

## Run
```
pip install -r requirements.txt
export SECRET_KEY=... ADMIN_PASSWORD=...
python app.py            # dev  ->  http://localhost:5000
gunicorn app:app --timeout 600   # production
```

## Public API (JSON)
| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | `{"status":"ok"}` |
| GET | `/api/programs` | `[{id,title,description,topics[],featured,coming_soon}]` |
| GET | `/api/mentors` | `[{id,name,role}]` |
| GET | `/api/videos` | public videos only: `[{id,title,description,url,created_at}]` (`url` is relative, e.g. `/media/video/3`) |
| POST | `/api/register` | body `{name, phone, email?, program?, message?}` → `201 {ok:true}` or `4xx {error}` |

Errors are always `{"error": "..."}`. `/api/register` is limited to 5 requests / 10 min per IP.

## Frontend hosted on another domain?
1. Set `CORS_ORIGINS=https://your-frontend.com` (comma separated, or `*`) on the backend.
2. In the HTML set `window.WOLFX_API_BASE = "https://your-api.com"`.

## Admin
`/admin` (password from `ADMIN_PASSWORD`): registrations, programs, mentors, videos.
Env: `DB_PATH`, `UPLOAD_DIR`, `MAX_UPLOAD_MB`, `CORS_ORIGINS`.
