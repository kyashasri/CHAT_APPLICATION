from flask import Flask, render_template, request, redirect, url_for, session
from flask_mail import Mail, Message
from flask_pymongo import PyMongo
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import datetime, timedelta
from bson import ObjectId
import os
import random

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")

# ==============================
# SocketIO
# ==============================
socketio = SocketIO(app, cors_allowed_origins="*")

# ==============================
# MongoDB
# ==============================
app.config["MONGO_URI"] = os.getenv("MONGO_URI")
mongo = PyMongo(app)

users_collection = mongo.db.users
chats_collection = mongo.db.chats
messages_collection = mongo.db.messages
groups_collection = mongo.db.groups

# ==============================
# Mail Config
# ==============================
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_USERNAME")

mail = Mail(app)

# ====================================================
# REGISTER
# ====================================================
@app.route("/", methods=["GET", "POST"])
def register():
    if session.get("logged_in"):
        return redirect(url_for("home"))

    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        if users_collection.find_one({"email": email}):
            return redirect(url_for("register", error="Email already registered!"))

        otp = random.randint(100000, 999999)

        session["otp"] = str(otp)
        session["name"] = name
        session["email"] = email
        session["password"] = password
        session["otp_expiry"] = (datetime.now() + timedelta(minutes=2)).timestamp()

        try:
            msg = Message("Your OTP Code", recipients=[email])
            msg.body = f"Your OTP is: {otp}"
            mail.send(msg)

            return redirect(url_for("verify", success="OTP sent to your email"))
        except Exception as e:
            return f"Mail Error: {e}"

    return render_template("index.html")

# ====================================================
# VERIFY OTP
# ====================================================
@app.route("/verify", methods=["GET", "POST"])
def verify():
    if request.method == "POST":
        entered_otp = request.form["otp"]

        expiry_time = session.get("otp_expiry")

        if not expiry_time or datetime.now().timestamp() > expiry_time:
            session.pop("otp", None)
            session.pop("otp_expiry", None)
            return redirect(url_for("register", error="OTP expired! Please register again."))

        if entered_otp == session.get("otp"):
            hashed_password = generate_password_hash(session["password"])

            users_collection.insert_one({
                "name": session["name"],
                "email": session["email"],
                "password": hashed_password
            })

            session.pop("otp", None)
            session.pop("otp_expiry", None)
            session["logged_in"] = True

            return redirect(url_for("home"))
        else:
            return redirect(url_for("verify", error="Invalid OTP"))

    return render_template("verify.html",
                           expiry=session.get("otp_expiry"))
# ====================================================
# LOGIN
# ====================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("home"))

    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = users_collection.find_one({"email": email})

        if user and check_password_hash(user["password"], password):
            session["logged_in"] = True
            session["name"] = user["name"]
            session["email"] = user["email"]
            return redirect(url_for("home"))
        else:
            return redirect(url_for("login", error="Invalid Email or Password"))

    return render_template("login.html")

# ====================================================
# FORGOT PASSWORD
# ====================================================
@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"]

        user = users_collection.find_one({"email": email})
        if not user:
            return redirect(url_for("forgot_password", error="Email not registered!"))

        otp = random.randint(100000, 999999)

        session["reset_otp"] = str(otp)
        session["reset_email"] = email
        session["reset_otp_expiry"] = (datetime.now() + timedelta(minutes=2)).timestamp()

        try:
            msg = Message("Password Reset OTP", recipients=[email])
            msg.body = f"Your Password Reset OTP is: {otp}\nValid for 2 minutes."
            mail.send(msg)

            return redirect(url_for("verify_reset_otp", success="OTP sent to your email (Valid 2 minutes)"))
        except Exception as e:
            return f"Mail Error: {e}"

    return render_template("forgot_password.html")
# ====================================================
# VERIFY RESET OTP
# ====================================================
@app.route("/verify_reset_otp", methods=["GET", "POST"])
def verify_reset_otp():
    if request.method == "POST":
        entered_otp = request.form["otp"]

        expiry_time = session.get("reset_otp_expiry")

        if not expiry_time or datetime.now().timestamp() > expiry_time:
            session.pop("reset_otp", None)
            session.pop("reset_email", None)
            session.pop("reset_otp_expiry", None)
            return redirect(url_for("forgot_password", error="OTP expired! Please request again."))

        if entered_otp == session.get("reset_otp"):
            return redirect(url_for("reset_password"))
        else:
            return redirect(url_for("verify_reset_otp", error="Invalid OTP"))

    return render_template("verify_reset_otp.html",
                           expiry=session.get("reset_otp_expiry"))
# ====================================================
# RESET PASSWORD
# ====================================================
@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        new_password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if new_password != confirm_password:
            return redirect(url_for("reset_password", error="Passwords do not match!"))

        hashed_password = generate_password_hash(new_password)

        users_collection.update_one(
            {"email": session.get("reset_email")},
            {"$set": {"password": hashed_password}}
        )

        session.pop("reset_otp", None)
        session.pop("reset_email", None)

        return redirect(url_for("login", success="Password updated successfully!"))

    return render_template("reset_password.html")

# ====================================================
# HOME
# ====================================================
@app.route("/home")
def home():
    if not session.get("logged_in"):
        return redirect(url_for("register"))

    groups = list(groups_collection.find({"members": session["email"]}))

    chats = []
    private_chats = chats_collection.find({
        "type": "private",
        "members": session["email"]
    })

    for chat in private_chats:
        other_email = [m for m in chat["members"] if m != session["email"]][0]
        user = users_collection.find_one({"email": other_email})

        chats.append({
            "_id": chat["_id"],
            "name": user["name"] if user else other_email
        })

    return render_template("home.html",
                           name=session.get("name"),
                           groups=groups,
                           chats=chats)

# ====================================================
# CREATE PRIVATE CHAT
# ====================================================
@app.route("/create_chat", methods=["POST"])
def create_chat():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    current_user = session["email"]
    searched_email = request.form["email"].strip()

    if current_user == searched_email:
        return redirect(url_for("home", error="You cannot chat with yourself"))

    user = users_collection.find_one({"email": searched_email})
    if not user:
        return redirect(url_for("home", error="User not registered!"))

    existing_chat = chats_collection.find_one({
        "type": "private",
        "members": {"$all": [current_user, searched_email]}
    })

    if existing_chat:
        return redirect(url_for("chat", chat_id=str(existing_chat["_id"])))

    new_chat = {
        "type": "private",
        "members": [current_user, searched_email],
        "created_at": datetime.now()
    }

    result = chats_collection.insert_one(new_chat)
    return redirect(url_for("chat", chat_id=str(result.inserted_id)))

# ====================================================
# PRIVATE CHAT PAGE
# ====================================================
@app.route("/chat/<chat_id>")
def chat(chat_id):
    if not session.get("logged_in"):
        return redirect(url_for("register"))

    chat_data = chats_collection.find_one({"_id": ObjectId(chat_id)})

    if not chat_data or session["email"] not in chat_data["members"]:
        return redirect(url_for("home", error="Unauthorized access"))

    messages = list(messages_collection.find(
        {"chat_id": ObjectId(chat_id)}
    ).sort("_id", 1))

    return render_template("chat.html",
                           name=session.get("name"),
                           messages=messages,
                           chat_id=chat_id)

# ====================================================
# CREATE GROUP
# ====================================================
@app.route("/create_group", methods=["POST"])
def create_group():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    group_name = request.form["group_name"]
    members = request.form.getlist("members[]")

    valid_members = []
    invalid_members = []

    for m in members:
        m = m.strip()
        if not m:
            continue

        user = users_collection.find_one({"email": m})
        if user:
            valid_members.append(m)
        else:
            invalid_members.append(m)

    if invalid_members:
        error_msg = "These users are not registered: " + ", ".join(invalid_members)
        return redirect(url_for("home", error=error_msg))

    valid_members.append(session["email"])

    group = {
        "type": "group",
        "name": group_name,
        "members": valid_members,
        "created_at": datetime.now()
    }

    groups_collection.insert_one(group)

    return redirect(url_for("home", success="Group created successfully!"))

# ====================================================
# GROUP CHAT PAGE
# ====================================================
@app.route("/group/<group_id>")
def group_chat(group_id):
    if not session.get("logged_in"):
        return redirect(url_for("register"))

    group = groups_collection.find_one({"_id": ObjectId(group_id)})

    if not group or session["email"] not in group["members"]:
        return redirect(url_for("home", error="Unauthorized access"))

    messages = list(messages_collection.find(
        {"group_id": ObjectId(group_id)}
    ).sort("_id", 1))

    return render_template("group_chat.html",
                           group=group,
                           messages=messages,
                           group_id=group_id)

# ====================================================
# SOCKET EVENTS
# ====================================================
@socketio.on("join_room")
def handle_join(data):
    join_room(data["chat_id"])

@socketio.on("send_message")
def handle_message(data):
    msg_data = {
        "chat_id": ObjectId(data["chat_id"]),
        "sender": data["sender"],
        "text": data["message"],
        "timestamp": datetime.now()
    }

    messages_collection.insert_one(msg_data)

    emit("receive_message", {
        "message": data["message"],
        "sender": data["sender"],
        "timestamp": msg_data["timestamp"].strftime("%H:%M")
    }, room=data["chat_id"])

@socketio.on("join_group")
def join_group_socket(data):
    join_room(data["group_id"])

@socketio.on("send_group_message")
def handle_group_message(data):
    msg_data = {
        "group_id": ObjectId(data["group_id"]),
        "sender": data["sender"],
        "sender_name": data["sender_name"],
        "text": data["message"],
        "timestamp": datetime.now()
    }

    messages_collection.insert_one(msg_data)

    emit("receive_group_message", {
        "message": data["message"],
        "sender": data["sender"],
        "sender_name": data["sender_name"],
        "timestamp": msg_data["timestamp"].strftime("%H:%M")
    }, room=data["group_id"])

# ====================================================
# LOGOUT
# ====================================================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("register"))

# ====================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)
