from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mail import Mail, Message
from flask_pymongo import PyMongo
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import datetime
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
            flash("Email already registered!")
            return redirect(url_for("register"))

        otp = random.randint(100000, 999999)

        session["otp"] = str(otp)
        session["name"] = name
        session["email"] = email
        session["password"] = password

        try:
            msg = Message("Your OTP Code", recipients=[email])
            msg.body = f"Your OTP is: {otp}"
            mail.send(msg)

            flash("OTP sent to email!")
            return redirect(url_for("verify"))
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

        if entered_otp == session.get("otp"):
            hashed_password = generate_password_hash(session["password"])

            users_collection.insert_one({
                "name": session["name"],
                "email": session["email"],
                "password": hashed_password
            })

            session.pop("otp", None)
            session["logged_in"] = True

            return redirect(url_for("home"))
        else:
            flash("Invalid OTP")

    return render_template("verify.html")

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
            flash("Invalid Email or Password")

    return render_template("login.html")

# ====================================================
# HOME
# ====================================================
@app.route("/home")
def home():
    if not session.get("logged_in"):
        return redirect(url_for("register"))
    return render_template("home.html", name=session.get("name"))

# ====================================================
# CREATE PRIVATE CHAT
# ====================================================
@app.route("/create_chat", methods=["POST"])
def create_chat():
    if not session.get("logged_in"):
        return {"error": "Not logged in"}, 401

    current_user = session["email"]
    searched_email = request.form["email"]

    if current_user == searched_email:
        return {"error": "You cannot chat with yourself"}, 400

    user = users_collection.find_one({"email": searched_email})
    if not user:
        return {"error": "User not found"}, 404

    existing_chat = chats_collection.find_one({
        "type": "private",
        "members": {"$all": [current_user, searched_email]}
    })

    if existing_chat:
        return redirect(url_for("chat", chat_id=str(existing_chat["_id"])))

    new_chat = {
        "type": "private",
        "members": [current_user, searched_email],
        "created_at": datetime.utcnow()
    }

    result = chats_collection.insert_one(new_chat)
    return redirect(url_for("chat", chat_id=str(result.inserted_id)))

# ====================================================
# CHAT PAGE
# ====================================================
@app.route("/chat/<chat_id>")
def chat(chat_id):
    if not session.get("logged_in"):
        return redirect(url_for("register"))

    messages = list(messages_collection.find(
        {"chat_id": ObjectId(chat_id)}
    ).sort("timestamp", 1))

    for msg in messages:
        msg["timestamp"] = msg["timestamp"].strftime("%H:%M")

    return render_template("chat.html",
                           name=session.get("name"),
                           messages=messages,
                           chat_id=chat_id)

# ====================================================
# SOCKET EVENTS
# ====================================================

@socketio.on("join_room")
def handle_join(data):
    join_room(data["chat_id"])

@socketio.on("send_message")
def handle_message(data):
    message = data["message"]
    sender = data["sender"]
    chat_id = data["chat_id"]

    msg_data = {
        "chat_id": ObjectId(chat_id),
        "sender": sender,
        "text": message,
        "timestamp": datetime.utcnow()
    }

    messages_collection.insert_one(msg_data)

    formatted_time = msg_data["timestamp"].strftime("%H:%M")

    emit("receive_message", {
        "message": message,
        "sender": sender,
        "timestamp": formatted_time
    }, room=chat_id)

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




