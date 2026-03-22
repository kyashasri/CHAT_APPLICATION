import eventlet
eventlet.monkey_patch()

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
import requests   # ADD THIS LINE
from werkzeug.utils import secure_filename
from flask import request, jsonify



load_dotenv()


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
# ==============================
# File Upload Config
# ==============================
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB limit

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
posts_collection = mongo.db.posts



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
                "password": hashed_password,
                "bio": "",
                "profile_pic": "/static/default.png"
                })

            session.pop("otp", None)
            session.pop("otp_expiry", None)
            session["logged_in"] = True

            return redirect(url_for("home"))
        else:
            return redirect(url_for("verify", error="Invalid OTP"))

    return render_template("verify.html",
                           expiry=session.get("otp_expiry"))

## Model connection
# ====================================================
# Model connection


# ✅ ADD THIS HERE 👇
def check_toxic_text(message):
    try:
        API_URL = "https://yashasri-04-hate-speech.hf.space/run/predict"

        response = requests.post(
            API_URL,
            json={"data": [message]},
            timeout=10
        )

        result = response.json()
        print("FULL API RESPONSE:", result)

        # 🔥 SAFE PARSING
        prediction = result.get("data", [{}])[0].get("class", "Not Abusive")

        print("PREDICTION:", prediction)

        return {"class": prediction}

    except Exception as e:
        print("ERROR:", e)
        return {"class": "Not Abusive"}
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
            session["profile_pic"] = user.get("profile_pic")
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
    user = users_collection.find_one({"email": session["email"]})
    session["profile_pic"] = user.get("profile_pic")
    session["name"] = user.get("name")

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
            "name": user["name"] if user else other_email,
            "profile_pic": user.get("profile_pic") if user else None
            })

    posts = list(posts_collection.find()
             .sort("created_at",-1)
             .limit(5))
    return render_template("home.html",
                       name=session.get("name"),
                       groups=groups,
                       chats=chats,
                       posts=posts)

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

    # 🔥 Get other user's name
    other_email = [m for m in chat_data["members"] if m != session["email"]][0]
    other_user = users_collection.find_one({"email": other_email})
    other_name = other_user["name"] if other_user else other_email

    messages = list(messages_collection.find(
        {"chat_id": ObjectId(chat_id)}
    ).sort("_id", 1))

    return render_template("chat.html",
                           name=other_name,   # ✅ Only this changed
                           messages=messages,
                           chat_id=chat_id)
# ====================================================
# DELETE PRIVATE CHAT
# ====================================================
@app.route("/delete_chat/<chat_id>", methods=["POST"])
def delete_chat(chat_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    chat = chats_collection.find_one({"_id": ObjectId(chat_id)})

    if not chat or session["email"] not in chat["members"]:
        return redirect(url_for("home", error="Unauthorized action"))

    # Delete all messages of this chat
    messages_collection.delete_many({"chat_id": ObjectId(chat_id)})

    # Delete chat
    chats_collection.delete_one({"_id": ObjectId(chat_id)})

    return redirect(url_for("home", success="Chat deleted successfully!"))
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
# DELETE GROUP
# ====================================================
@app.route("/delete_group/<group_id>", methods=["POST"])
def delete_group(group_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    group = groups_collection.find_one({"_id": ObjectId(group_id)})

    if not group or session["email"] not in group["members"]:
        return redirect(url_for("home", error="Unauthorized action"))

    # Delete group messages
    messages_collection.delete_many({"group_id": ObjectId(group_id)})

    # Delete group
    groups_collection.delete_one({"_id": ObjectId(group_id)})

    return redirect(url_for("home", success="Group deleted successfully!"))

# ====================================================
# SOCKET EVENTS
# ====================================================
@socketio.on("join_room")
def handle_join(data):
    join_room(data["chat_id"])

import threading

import threading

@socketio.on("send_message")
def handle_message(data):
    threading.Thread(target=process_message, args=(data,)).start()


def process_message(data):
    message = data["message"]
    user = data["user"]
    chat_id = data.get("chat_id")

    # ✅ CHECK TOXICITY
    result = check_toxic_text(message)
    prediction = str(result.get("class", "")).lower()

    if prediction.lower() == "abusive":
        message = "<i style='color:red;'>⚠️ Abusive message</i>"

    # ✅ SAVE MESSAGE
    msg_data = {
        "chat_id": ObjectId(chat_id),
        "sender": user,
        "text": message,
        "timestamp": datetime.now(),
        "status": "sent"
    }

    result_db = messages_collection.insert_one(msg_data)

    # ✅ SEND TO ROOM
    socketio.emit("receive_message", {
    "message_id": str(result_db.inserted_id),
    "sender": user,   # ✅ FIXED
    "message": message,
    "timestamp": msg_data["timestamp"].strftime("%H:%M")
}, room=chat_id)
    
    

@socketio.on("join_group")
def join_group_socket(data):
    join_room(data["group_id"])

@socketio.on("send_group_message")
def handle_group_message(data):
    message = data["message"]
    group_id = data["group_id"]

    # ✅ CHECK TOXICITY
    result = check_toxic_text(message)

    prediction = str(result.get("class", "")).lower()

    if prediction.lower() == "abusive":
        message = "<i style='color:red;'>⚠️ Abusive message</i>"

    msg_data = {
        "group_id": ObjectId(group_id),
        "sender": data["sender"],
        "sender_name": data["sender_name"],
        "text": message,
        "timestamp": datetime.now()
    }

    result_db = messages_collection.insert_one(msg_data)

    socketio.emit("receive_group_message", {
        "message_id": str(result_db.inserted_id),
        "group_id": group_id,
        "message": message,
        "sender": data["sender"],
        "sender_name": data["sender_name"],
        "timestamp": msg_data["timestamp"].strftime("%H:%M")
    }, room=group_id)


@socketio.on("delete_message")
def delete_message(data):
    message_id = data["message_id"]
    room_id = data["room_id"]

    message = messages_collection.find_one({
    "_id": ObjectId(message_id),
    "sender": session["email"]
})

    if message:
        messages_collection.delete_one({"_id": ObjectId(message_id)})

        emit("message_deleted", {
            "message_id": message_id
        }, room=room_id)
@socketio.on("message_read")
def message_read(data):

    message_id = data["message_id"]
    chat_id = data["chat_id"]

    messages_collection.update_one(
        {"_id": ObjectId(message_id)},
        {"$set": {"status": "read"}}
    )

    socketio.emit(
        "message_read_update",
        {"message_id": message_id},
        room=chat_id
    )
# ====================================================
# DELETE GROUP MESSAGE
# ====================================================
@socketio.on("delete_group_message")
def delete_group_message(data):

    message_id = data["message_id"]
    group_id = data["group_id"]

    message = messages_collection.find_one({"_id": ObjectId(message_id)})

    if message:
        messages_collection.delete_one({"_id": ObjectId(message_id)})

        emit(
            "group_message_deleted",
            {"message_id": message_id},
            room=group_id
        )
# ====================================================
# FILE UPLOAD
# ====================================================
@app.route("/upload", methods=["POST"])
def upload_file():
    if not session.get("logged_in"):
        return {"error": "Unauthorized"}, 401

    file = request.files.get("file")
    chat_id = request.form.get("chat_id")
    group_id = request.form.get("group_id")

    if not file:
        return {"error": "No file"}, 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

    file.save(filepath)

    file_url = "/" + filepath.replace("\\", "/")

    
    msg_data = {
    "sender": session["email"],
    "file_url": file_url,
    "file_name": filename,
    "timestamp": datetime.now(),
    "status": "sent"
    }
    if chat_id:
        msg_data["chat_id"] = ObjectId(chat_id)
        room = chat_id
    else:
        msg_data["group_id"] = ObjectId(group_id)
        msg_data["sender_name"] = session["name"]
        room = group_id

    result = messages_collection.insert_one(msg_data)

    socketio.emit("receive_file", {
        "message_id": str(result.inserted_id),
        "file_url": file_url,
        "file_name": filename,
        "sender": session["email"],
        "sender_name": session.get("name"),
        "timestamp": msg_data["timestamp"].strftime("%H:%M")
    }, room=room)

    return {"success": True}

# ====================================================
# LOGOUT
# ====================================================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("register"))

@app.route("/ai_chat", methods=["POST"])
def ai_chat():
    try:
        data = request.get_json()
        message = data.get("message")

        response = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={
                "model": "phi3",
                "prompt": message,
                "stream": False,
                "options": {
                    "num_predict": 60
                }
            },
            timeout=300
        )

        result = response.json()
        reply = result.get("response", "No response from AI")

        return jsonify({"reply": reply})

    except Exception as e:
        return jsonify({"reply": f"AI error: {str(e)}"})
# ==============================
# PROFILE PAGE
# ==============================
@app.route("/profile")
def profile():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    user = users_collection.find_one({"email": session["email"]})

    return render_template("profile.html", user=user)
# ==============================
# UPDATE PROFILE
# ==============================
@app.route("/update_profile", methods=["POST"])
def update_profile():

    if not session.get("logged_in"):
        return jsonify({"success": False})

    name = request.form.get("name")
    bio = request.form.get("bio")

    update_data = {
        "name": name,
        "bio": bio
    }

    file = request.files.get("profile_pic")

    if file and file.filename != "":
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)
        profile_url = "/" + filepath.replace("\\", "/")
        update_data["profile_pic"] = profile_url
        session["profile_pic"] = profile_url   # ⭐ ADD THIS LINE
    else:
        profile_url = None

    users_collection.update_one(
        {"email": session["email"]},
        {"$set": update_data}
    )

    session["name"] = name

    return jsonify({
        "success": True,
        "name": name,
        "profile_pic": profile_url
    })
# ==============================
# CREATE POST
# ==============================
@app.route("/create_post", methods=["POST"])
def create_post():

    if not session.get("logged_in"):
        return redirect(url_for("login"))

    text = request.form.get("text")
    file = request.files.get("image")

    image_url = None

    if file and file.filename != "":
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)
        image_url = "/" + filepath.replace("\\", "/")

    post = {
    "user_email": session["email"],
    "user_name": session["name"],
    "profile_pic": session.get("profile_pic"),
    "text": text,
    "image": image_url,
    "likes": [],        
    "comments": [],     
    "created_at": datetime.now()
    }

    result = posts_collection.insert_one(post)
    socketio.emit("new_post",{
        "id":str(result.inserted_id),
        "user":post["user_name"],
        "text":post["text"],
        "image":post["image"]
        })

    return redirect(url_for("home"))
@app.route("/like_post/<post_id>", methods=["POST"])
def like_post(post_id):

    if not session.get("logged_in"):
        return jsonify({"success": False})

    user = session["email"]

    post = posts_collection.find_one({"_id": ObjectId(post_id)})

    if user in post.get("likes", []):
        posts_collection.update_one(
            {"_id": ObjectId(post_id)},
            {"$pull": {"likes": user}}
        )
        liked = False
    else:
        posts_collection.update_one(
            {"_id": ObjectId(post_id)},
            {"$push": {"likes": user}}
        )
        liked = True

    updated_post = posts_collection.find_one({"_id": ObjectId(post_id)})

    return jsonify({
        "liked": liked,
        "count": len(updated_post["likes"])
    })

################ Comments 
@app.route("/comment_post/<post_id>", methods=["POST"])
def comment_post(post_id):

    if not session.get("logged_in"):
        return jsonify({"success": False})
####
    text = request.json.get("text")

    # 🔥 ADD THIS (abusive check)
    result = check_toxic_text(text)
    prediction = str(result.get("class", "")).lower()

    if prediction.lower() == "abusive":
        text = "<i style='color:red;'>⚠️ Abusive comment!</i>"

    comment = {
        "user": session["name"],
        "text": text,
        "time": datetime.now()
    }

    posts_collection.update_one(
        {"_id": ObjectId(post_id)},
        {"$push": {"comments": comment}}
    )

    post = posts_collection.find_one({"_id": ObjectId(post_id)})

    return jsonify({
        "user": comment["user"],
        "text": comment["text"],
        "index": len(post["comments"]) - 1   # ✅ VERY IMPORTANT
    })

@app.route("/delete_comment/<post_id>/<int:index>", methods=["POST"])
def delete_comment(post_id, index):

    if not session.get("logged_in"):
        return jsonify({"success": False})

    post = posts_collection.find_one({"_id": ObjectId(post_id)})

    if not post:
        return jsonify({"success": False})

    comments = post.get("comments", [])

    # Check valid index
    if index < 0 or index >= len(comments):
        return jsonify({"success": False})

    # Only allow user to delete their own comment
    if comments[index]["user"] != session["name"]:
        return jsonify({"success": False})

    # Remove comment
    comments.pop(index)

    posts_collection.update_one(
        {"_id": ObjectId(post_id)},
        {"$set": {"comments": comments}}
    )

    return jsonify({"success": True})


@app.route("/delete_post/<post_id>", methods=["POST"])
def delete_post(post_id):

    post = posts_collection.find_one({"_id":ObjectId(post_id)})

    if post["user_email"] != session["email"]:
        return jsonify({"success":False})

    posts_collection.delete_one({"_id":ObjectId(post_id)})

    return jsonify({"success":True})
@app.route("/load_posts")
def load_posts():

    page = int(request.args.get("page",0))
    limit = 5

    posts = list(posts_collection.find()
                 .sort("created_at",-1)
                 .skip(page*limit)
                 .limit(limit))

    for p in posts:
        p["_id"]=str(p["_id"])

    return jsonify(posts)
@app.route("/check_user", methods=["POST"])
def check_user():
    data = request.get_json()
    email = data.get("email")

    user = users_collection.find_one({"email": email})

    return jsonify({"exists": bool(user)})

# ====================================================


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)
