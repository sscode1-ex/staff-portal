from flask import Flask, request, jsonify, render_template, abort
from supabase import create_client
import firebase_admin
from firebase_admin import credentials, messaging
import os
import uuid
import json

app = Flask(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
FIREBASE_CREDENTIALS = os.environ.get("FIREBASE_CREDENTIALS")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── FIREBASE INIT ──────────────────────────────────────────────────────────────
if FIREBASE_CREDENTIALS:
    cred_dict = json.loads(FIREBASE_CREDENTIALS)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

# ── ADMIN PANEL ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("admin.html")

@app.route("/api/auth", methods=["POST"])
def auth():
    data = request.json
    if data.get("password") == ADMIN_PASSWORD:
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 401

@app.route("/api/staff", methods=["GET"])
def get_staff():
    pw = request.headers.get("X-Admin-Password")
    if pw != ADMIN_PASSWORD:
        abort(401)
    res = supabase.table("staff").select("*").order("name").execute()
    return jsonify(res.data)

@app.route("/api/staff", methods=["POST"])
def add_staff():
    pw = request.headers.get("X-Admin-Password")
    if pw != ADMIN_PASSWORD:
        abort(401)
    data = request.json
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name required"}), 400
    token = str(uuid.uuid4()).replace("-", "")[:12]
    record = {"name": name, "token": token, "fcm_token": None}
    res = supabase.table("staff").insert(record).execute()
    return jsonify(res.data[0])

@app.route("/api/staff/<int:staff_id>", methods=["DELETE"])
def delete_staff(staff_id):
    pw = request.headers.get("X-Admin-Password")
    if pw != ADMIN_PASSWORD:
        abort(401)
    supabase.table("staff").delete().eq("id", staff_id).execute()
    return jsonify({"ok": True})

@app.route("/api/messages", methods=["GET"])
def get_messages():
    pw = request.headers.get("X-Admin-Password")
    if pw != ADMIN_PASSWORD:
        abort(401)
    res = supabase.table("messages").select("*").order("created_at", desc=True).limit(50).execute()
    return jsonify(res.data)

@app.route("/api/replies", methods=["GET"])
def get_replies():
    pw = request.headers.get("X-Admin-Password")
    if pw != ADMIN_PASSWORD:
        abort(401)
    res = supabase.table("replies").select("*").order("created_at", desc=True).limit(100).execute()
    return jsonify(res.data)

@app.route("/api/send", methods=["POST"])
def send_message():
    pw = request.headers.get("X-Admin-Password")
    if pw != ADMIN_PASSWORD:
        abort(401)

    data = request.json
    title = data.get("title", "Staff Update").strip()
    body = data.get("body", "").strip()
    target = data.get("target", "all")

    if not body:
        return jsonify({"error": "Message required"}), 400

    # Save message to DB
    msg_res = supabase.table("messages").insert({"title": title, "body": body, "target": target}).execute()

    # Get FCM tokens
    if target == "all":
        res = supabase.table("staff").select("id,fcm_token").not_.is_("fcm_token", "null").execute()
    else:
        res = supabase.table("staff").select("id,fcm_token").eq("id", target).execute()

    staff_rows = [r for r in res.data if r["fcm_token"]]

    sent = 0
    errors = 0
    dead_tokens = []

    for row in staff_rows:
        try:
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                webpush=messaging.WebpushConfig(
                    notification=messaging.WebpushNotification(
                        title=title,
                        body=body,
                        icon="/static/icon.png",
                    ),
                    fcm_options=messaging.WebpushFCMOptions(link="/")
                ),
                token=row["fcm_token"],
            )
            messaging.send(message)
            sent += 1
        except Exception as e:
            err_str = str(e)
            print(f"FCM send error: {err_str}")
            # If token is invalid/expired, clear it so staff re-registers
            if "registration-token-not-registered" in err_str or "invalid-registration-token" in err_str:
                dead_tokens.append(row["id"])
            errors += 1

    # Clear dead tokens so staff gets prompted to re-enable
    for staff_id in dead_tokens:
        supabase.table("staff").update({"fcm_token": None}).eq("id", staff_id).execute()

    return jsonify({"sent": sent, "total": len(staff_rows), "errors": errors})

# ── STAFF PORTAL ───────────────────────────────────────────────────────────────

@app.route("/s/<token>")
def staff_page(token):
    res = supabase.table("staff").select("*").eq("token", token).execute()
    if not res.data:
        abort(404)
    staff = res.data[0]
    return render_template("staff.html", staff=staff)

@app.route("/api/register-fcm", methods=["POST"])
def register_fcm():
    data = request.json
    token = data.get("token")
    fcm_token = data.get("fcm_token")
    if not token or not fcm_token:
        return jsonify({"error": "Missing fields"}), 400
    # Always update — never skip even if already registered
    supabase.table("staff").update({"fcm_token": fcm_token}).eq("token", token).execute()
    return jsonify({"ok": True})

@app.route("/api/messages/public", methods=["GET"])
def public_messages():
    token = request.args.get("token")
    if not token:
        abort(401)
    res_staff = supabase.table("staff").select("id,fcm_token").eq("token", token).execute()
    if not res_staff.data:
        abort(401)
    staff_id = str(res_staff.data[0]["id"])

    # Auto re-register check — return fcm status so frontend knows
    has_token = bool(res_staff.data[0]["fcm_token"])

    res = supabase.table("messages").select("*").or_(f"target.eq.all,target.eq.{staff_id}").order("created_at", desc=True).limit(20).execute()
    return jsonify({"messages": res.data, "has_token": has_token})

@app.route("/api/reply", methods=["POST"])
def post_reply():
    data = request.json
    token = data.get("token")
    message_id = data.get("message_id")
    body = data.get("body", "").strip()

    if not token or not body:
        return jsonify({"error": "Missing fields"}), 400

    res_staff = supabase.table("staff").select("id,name").eq("token", token).execute()
    if not res_staff.data:
        abort(401)

    staff = res_staff.data[0]
    supabase.table("replies").insert({
        "message_id": message_id,
        "staff_id": staff["id"],
        "staff_name": staff["name"],
        "body": body
    }).execute()

    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(debug=True)
