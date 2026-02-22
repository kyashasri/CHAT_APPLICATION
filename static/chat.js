var socket = io();

function sendMessage() {
    var messageInput = document.getElementById("message");
    var message = messageInput.value;

    if (message.trim() === "") return;

    socket.emit("send_message", {
        message: message,
        name: username
    });

    messageInput.value = "";
}

socket.on("receive_message", function(data) {
    var chatBox = document.getElementById("chat-box");

    chatBox.innerHTML += `
        <p><strong>${data.name}</strong> (${data.timestamp}): ${data.message}</p>
    `;

    chatBox.scrollTop = chatBox.scrollHeight;
});
