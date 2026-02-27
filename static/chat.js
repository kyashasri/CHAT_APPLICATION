// ================================
// SOCKET CONNECTION
// ================================
var socket = io();

var username = document.body.getAttribute("data-username");
var chat_id = document.body.getAttribute("data-chatid");

var chatBox = document.getElementById("chat-box");
var messageInput = document.getElementById("message");

// Join room
socket.emit("join_room", { chat_id: chat_id });


// ================================
// SEND MESSAGE
// ================================
function sendMessage() {
    var message = messageInput.value;

    if (message.trim() === "") return;

    // Show message immediately on sender side
    chatBox.innerHTML += `
        <div class="message sender">
            <div class="bubble">
                ${message}
                <div class="time">Now</div>
            </div>
        </div>
    `;

    chatBox.scrollTop = chatBox.scrollHeight;

    // Emit to server
    socket.emit("send_message", {
        message: message,
        sender: username,
        chat_id: chat_id
    });

    messageInput.value = "";
}


// ================================
// RECEIVE MESSAGE
// ================================
socket.on("receive_message", function(data) {

    // Avoid duplicate rendering for sender
    if (data.sender === username) return;

    chatBox.innerHTML += `
        <div class="message receiver">
            <div class="bubble">
                ${data.message}
                <div class="time">${data.timestamp}</div>
            </div>
        </div>
    `;

    chatBox.scrollTop = chatBox.scrollHeight;
});


// ================================
// AUTO SCROLL ON LOAD
// ================================
window.onload = function() {
    chatBox.scrollTop = chatBox.scrollHeight;
};


// ================================
// ENTER KEY SUPPORT
// ================================
messageInput.addEventListener("keypress", function(event) {
    if (event.key === "Enter") {
        event.preventDefault();
        sendMessage();
    }
});
