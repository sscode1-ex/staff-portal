from flask import Flask, request, jsonify, render_template, abort
from supabase import create_client
import os
import uuid
import requests

app = Flask(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
FIREBASE_SERVER_KEY = os.environ.get("FIREBASE_SERVER_KEY")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

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

@app.route("/api/send", methods=["POST"])
def send_message():
    pw = request.headers.get("X-Admin-Password")
    if pw != ADMIN_PASSWORD:
        abort(401)

    data = request.json
    title = data.get("title", "Staff Update").strip()
    body = data.get("body", "").strip()
    target = data.get("target", "all")  # "all" or staff id

    if not body:
        return jsonify({"error": "Message required"}), 400

    # Save message to DB
    msg_record = {"title": title, "body": body, "target": target}
    supabase.table("messages").insert(msg_record).execute()

    # Get FCM tokens
    if target == "all":
        res = supabase.table("staff").select("fcm_token").not_.is_("fcm_token", "null").execute()
        tokens = [r["fcm_token"] for r in res.data if r["fcm_token"]]
    else:
        res = supabase.table("staff").select("fcm_token").eq("id", target).execute()
        tokens = [r["fcm_token"] for r in res.data if r["fcm_token"]]

    sent = 0
    errors = []
    for token in tokens:
        result = send_fcm(token, title, body)
        if result:
            sent += 1
        else:
            errors.append(token)

    return jsonify({"sent": sent, "total": len(tokens), "errors": len(errors)})

def send_fcm(fcm_token, title, body):
    url = "https://fcm.googleapis.com/fcm/send"
    headers = {
        "Authorization": f"key={FIREBASE_SERVER_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "to": fcm_token,
        "notification": {
            "title": title,
            "body": body,
            "icon": "/static/icon.png",
            "click_action": "/"
        },
        "data": {
            "title": title,
            "body": body
        }
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        result = r.json()
        return result.get("success", 0) == 1
    except Exception as e:
        print(f"FCM error: {e}")
        return False

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
    supabase.table("staff").update({"fcm_token": fcm_token}).eq("token", token).execute()
    return jsonify({"ok": True})

@app.route("/api/messages/public", methods=["GET"])
def public_messages():
    # Staff can read recent messages (last 20)
    token = request.args.get("token")
    if not token:
        abort(401)
    res_staff = supabase.table("staff").select("id").eq("token", token).execute()
    if not res_staff.data:
        abort(401)
    staff_id = str(res_staff.data[0]["id"])

    res = supabase.table("messages").select("*").or_(f"target.eq.all,target.eq.{staff_id}").order("created_at", desc=True).limit(20).execute()
    return jsonify(res.data)

if __name__ == "__main__":
    app.run(debug=True)
