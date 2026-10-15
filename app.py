import csv, hmac, io, os, re, secrets, sqlite3, time
from datetime import datetime, timezone
from functools import wraps

from werkzeug.middleware.proxy_fix import ProxyFix
from flask import (Flask, Response, abort, g, jsonify, redirect, render_template,
                   request, send_from_directory, session, url_for)

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE, "wolfx.db"))

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(BASE, "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "500"))
ALLOWED_VIDEO = {".mp4", ".webm", ".mov", ".m4v"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
PRODUCTION = os.environ.get("PRODUCTION") == "1"
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me")
if PRODUCTION and (app.secret_key == "dev-only-change-me" or len(app.secret_key) < 24
                   or ADMIN_PASSWORD == "change-me" or len(ADMIN_PASSWORD) < 8):
    raise RuntimeError("PRODUCTION=1 needs a real SECRET_KEY (24+ chars) and ADMIN_PASSWORD (8+ chars).")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=PRODUCTION)
if os.environ.get("TRUST_PROXY") == "1":  # behind nginx: use the real client IP / https
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


def same(a, b):
    """Constant-time compare that also works with non-ASCII text."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# ---------- database ----------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, phone TEXT NOT NULL, email TEXT,
            program TEXT, message TEXT, created_at TEXT NOT NULL)""")


    with sqlite3.connect(DB_PATH) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS programs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, position INTEGER NOT NULL DEFAULT 0,
            title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', topics TEXT NOT NULL DEFAULT '',
            featured INTEGER NOT NULL DEFAULT 0, coming_soon INTEGER NOT NULL DEFAULT 0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS mentors (
            id INTEGER PRIMARY KEY AUTOINCREMENT, position INTEGER NOT NULL DEFAULT 0,
            name TEXT NOT NULL, role TEXT NOT NULL DEFAULT '')""")
        if not c.execute("SELECT 1 FROM programs").fetchone():
            c.executemany("INSERT INTO programs (position,title,description,topics,featured,coming_soon) VALUES (?,?,?,?,?,?)", [
                (1, "Trading Fundamentals", "Understand the essential concepts, terminology, market structure and risk basics.", "Market Basics\nTrading Terminology\nRisk Management", 0, 0),
                (2, "Technical Analysis", "Learn how to study price action, charts and technical concepts through practical examples.", "Chart Reading\nTechnical Tools\nMarket Analysis", 1, 0),
                (3, "Advanced Track", "A future advanced track for learners who have completed the academy foundations.", "Advanced Concepts\nStrategy Development\nPerformance Review", 0, 1)])
        if not c.execute("SELECT 1 FROM mentors").fetchone():
            c.executemany("INSERT INTO mentors (position,name,role) VALUES (?,?,?)", [
                (1, "Mentor Name", "Trading & Market Analysis"), (2, "Mentor Name", "Technical Analysis"), (3, "Mentor Name", "Risk Management")])


    with sqlite3.connect(DB_PATH) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, position INTEGER NOT NULL DEFAULT 0,
            title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            filename TEXT NOT NULL, is_public INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL)""")


init_db()


# ---------- public ----------
@app.get("/")
def index():
    return render_template("index.html")


# ---------- public JSON API ----------
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
_hits = {}  # ip -> recent POST timestamps (in-memory, per process)


def api_json(payload):
    resp = jsonify(payload)
    resp.headers["Cache-Control"] = "public, max-age=30"
    return resp


@app.after_request
def add_cors(resp):
    origin = request.headers.get("Origin")
    if request.path.startswith("/api/") and origin and ("*" in CORS_ORIGINS or origin in CORS_ORIGINS):
        resp.headers["Access-Control-Allow-Origin"] = "*" if "*" in CORS_ORIGINS else origin
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Vary"] = "Origin"
    return resp


@app.errorhandler(404)
def not_found(_):
    if request.path.startswith("/api/"):
        return jsonify(error="Not found"), 404
    return "Not found", 404


@app.get("/api/health")
def api_health():
    return jsonify(status="ok")


@app.get("/api/programs")
def api_programs():
    rows = db().execute("SELECT * FROM programs ORDER BY position, id").fetchall()
    return api_json([{
        "id": r["id"], "title": r["title"], "description": r["description"],
        "topics": [t.strip() for t in r["topics"].splitlines() if t.strip()],
        "featured": bool(r["featured"]), "coming_soon": bool(r["coming_soon"]),
    } for r in rows])


@app.get("/api/mentors")
def api_mentors():
    rows = db().execute("SELECT * FROM mentors ORDER BY position, id").fetchall()
    return api_json([{"id": r["id"], "name": r["name"], "role": r["role"]} for r in rows])


@app.get("/api/videos")
def api_videos():
    rows = db().execute("SELECT * FROM videos WHERE is_public=1 ORDER BY position, id").fetchall()
    return api_json([{
        "id": r["id"], "title": r["title"], "description": r["description"],
        "url": f"/media/video/{r['id']}", "created_at": r["created_at"],
    } for r in rows])


@app.get("/media/video/<int:vid>")
def media_video(vid):
    v = db().execute("SELECT * FROM videos WHERE id=?", (vid,)).fetchone()
    if not v or not (v["is_public"] or session.get("admin")):
        abort(404)
    return send_from_directory(UPLOAD_DIR, v["filename"], conditional=True, max_age=3600)


@app.errorhandler(413)
def too_large(_):
    return f"File too large (max {MAX_UPLOAD_MB} MB).", 413


@app.post("/api/register")
def register():
    now = time.time()
    recent = [t for t in _hits.get(request.remote_addr, []) if now - t < 600]
    if len(recent) >= 5:
        return jsonify(error="Too many attempts. Please try again in a few minutes."), 429
    _hits[request.remote_addr] = recent + [now]

    data = request.get_json(silent=True) or {}
    if data.get("website"):  # honeypot: bots fill this
        return jsonify(ok=True)

    name = (data.get("name") or "").strip()[:120]
    phone = re.sub(r"[^\d+]", "", data.get("phone") or "")[:30]
    email = (data.get("email") or "").strip()[:200]
    program = (data.get("program") or "").strip()[:80]
    message = (data.get("message") or "").strip()[:1000]

    if len(name) < 2:
        return jsonify(error="Please enter your name."), 400
    if len(re.sub(r"\D", "", phone)) < 8:
        return jsonify(error="Please enter a valid phone number."), 400
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify(error="Please enter a valid email."), 400

    db().execute(
        "INSERT INTO leads (name, phone, email, program, message, created_at) VALUES (?,?,?,?,?,?)",
        (name, phone, email, program, message, datetime.now(timezone.utc).isoformat(timespec="seconds")))
    db().commit()
    return jsonify(ok=True), 201


# ---------- admin ----------
@app.context_processor
def inject_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return {"csrf": session["csrf"]}


@app.before_request
def check_csrf():
    if request.method == "POST" and request.path.startswith("/admin"):
        if not same(request.form.get("csrf", ""), session.get("csrf", "x")):
            return "Invalid CSRF token", 400


def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("admin"):
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper


_login_fails = {}


@app.route("/admin/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        now = time.time()
        fails = [t for t in _login_fails.get(request.remote_addr, []) if now - t < 600]
        if len(fails) >= 5:
            return render_template("login.html", error="Too many attempts. Try again in 10 minutes."), 429
        if same(request.form.get("password", ""), ADMIN_PASSWORD):
            _login_fails.pop(request.remote_addr, None)
            session["admin"] = True
            return redirect(url_for("admin"))
        _login_fails[request.remote_addr] = fails + [now]
        error = "Wrong password"
    return render_template("login.html", error=error)


@app.get("/admin/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/admin")
@admin_required
def admin():
    leads = db().execute("SELECT * FROM leads ORDER BY id DESC").fetchall()
    return render_template("admin.html", leads=leads)


@app.post("/admin/delete/<int:lead_id>")
@admin_required
def delete(lead_id):
    db().execute("DELETE FROM leads WHERE id=?", (lead_id,))
    db().commit()
    return redirect(url_for("admin"))


def _flag(name):
    return 1 if request.form.get(name) else 0


def _int(name, default=0):
    try:
        return int(request.form.get(name, default))
    except ValueError:
        return default


@app.get("/admin/programs")
@admin_required
def programs_admin():
    rows = db().execute("SELECT * FROM programs ORDER BY position, id").fetchall()
    return render_template("admin_programs.html", rows=rows)


@app.post("/admin/programs/save")
@admin_required
def programs_save():
    f = request.form
    title = f.get("title", "").strip()[:120]
    if title:
        vals = (title, f.get("description", "").strip()[:600], f.get("topics", "").strip()[:600],
                _flag("featured"), _flag("coming_soon"), _int("position"))
        pid = f.get("id")
        if pid:
            db().execute("UPDATE programs SET title=?,description=?,topics=?,featured=?,coming_soon=?,position=? WHERE id=?", vals + (pid,))
        else:
            db().execute("INSERT INTO programs (title,description,topics,featured,coming_soon,position) VALUES (?,?,?,?,?,?)", vals)
        db().commit()
    return redirect(url_for("programs_admin"))


@app.post("/admin/programs/delete/<int:pid>")
@admin_required
def programs_delete(pid):
    db().execute("DELETE FROM programs WHERE id=?", (pid,))
    db().commit()
    return redirect(url_for("programs_admin"))


@app.get("/admin/mentors")
@admin_required
def mentors_admin():
    rows = db().execute("SELECT * FROM mentors ORDER BY position, id").fetchall()
    return render_template("admin_mentors.html", rows=rows)


@app.post("/admin/mentors/save")
@admin_required
def mentors_save():
    f = request.form
    name = f.get("name", "").strip()[:120]
    if name:
        vals = (name, f.get("role", "").strip()[:160], _int("position"))
        mid = f.get("id")
        if mid:
            db().execute("UPDATE mentors SET name=?,role=?,position=? WHERE id=?", vals + (mid,))
        else:
            db().execute("INSERT INTO mentors (name,role,position) VALUES (?,?,?)", vals)
        db().commit()
    return redirect(url_for("mentors_admin"))


@app.post("/admin/mentors/delete/<int:mid>")
@admin_required
def mentors_delete(mid):
    db().execute("DELETE FROM mentors WHERE id=?", (mid,))
    db().commit()
    return redirect(url_for("mentors_admin"))


@app.get("/admin/videos")
@admin_required
def videos_admin():
    rows = db().execute("SELECT * FROM videos ORDER BY position, id").fetchall()
    return render_template("admin_videos.html", rows=rows, max_mb=MAX_UPLOAD_MB,
                           error=request.args.get("error"))


@app.post("/admin/videos/upload")
@admin_required
def videos_upload():
    f = request.files.get("video")
    title = request.form.get("title", "").strip()[:150]
    ext = os.path.splitext(f.filename)[1].lower() if f and f.filename else ""
    if not f or ext not in ALLOWED_VIDEO:
        return redirect(url_for("videos_admin", error="Choose an MP4, WebM, MOV or M4V file."))
    if not title:
        title = os.path.splitext(f.filename)[0][:150]
    name = secrets.token_hex(12) + ext
    f.save(os.path.join(UPLOAD_DIR, name))
    db().execute(
        "INSERT INTO videos (title,description,filename,is_public,position,created_at) VALUES (?,?,?,?,?,?)",
        (title, request.form.get("description", "").strip()[:600], name, _flag("is_public"),
         _int("position", 99), datetime.now(timezone.utc).isoformat(timespec="seconds")))
    db().commit()
    return redirect(url_for("videos_admin"))


@app.post("/admin/videos/save")
@admin_required
def videos_save():
    f = request.form
    title = f.get("title", "").strip()[:150]
    if title:
        db().execute("UPDATE videos SET title=?,description=?,is_public=?,position=? WHERE id=?",
                     (title, f.get("description", "").strip()[:600], _flag("is_public"),
                      _int("position"), f.get("id")))
        db().commit()
    return redirect(url_for("videos_admin"))


@app.post("/admin/videos/delete/<int:vid>")
@admin_required
def videos_delete(vid):
    v = db().execute("SELECT filename FROM videos WHERE id=?", (vid,)).fetchone()
    if v:
        try:
            os.remove(os.path.join(UPLOAD_DIR, v["filename"]))
        except FileNotFoundError:
            pass
        db().execute("DELETE FROM videos WHERE id=?", (vid,))
        db().commit()
    return redirect(url_for("videos_admin"))


@app.get("/admin/export.csv")
@admin_required
def export():
    rows = db().execute("SELECT * FROM leads ORDER BY id").fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(rows[0].keys() if rows else ["id", "name", "phone", "email", "program", "message", "created_at"])
    for r in rows:
        w.writerow(list(r))
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=leads.csv"})


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=5000)
