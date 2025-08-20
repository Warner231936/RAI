"""Minimal web UI to chat with Requiem via a browser."""

from __future__ import annotations

from flask import Flask, jsonify, render_template_string, request

from core import build_prompt, generate_response, update_memory


app = Flask(__name__)

INDEX_HTML = """
<!doctype html>
<title>Requiem Web Chat</title>
<h1>Requiem</h1>
<div id="log" style="height:300px; overflow-y:auto; border:1px solid #ccc; padding:5px;"></div>
<input id="user" placeholder="username"> <input id="msg" placeholder="message">
<button onclick="send()">Send</button>
<script>
async function send(){
  const user=document.getElementById('user').value;
  const message=document.getElementById('msg').value;
  const res=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user,message})});
  const data=await res.json();
  const log=document.getElementById('log');
  log.innerHTML+=`<p><b>${user}:</b> ${message}</p>`;
  log.innerHTML+=`<p><b>AI:</b> ${data.reply}</p>`;
  log.scrollTop=log.scrollHeight;
  document.getElementById('msg').value='';
}
</script>
"""


@app.get("/")
def index():
    return render_template_string(INDEX_HTML)


@app.post("/chat")
def chat():
    data = request.get_json(force=True)
    user = data.get("user")
    message = data.get("message")
    if not user or not message:
        return jsonify({"error": "user and message required"}), 400

    prompt = build_prompt(user, message)
    try:
        reply = generate_response(prompt)
    except Exception as exc:  # pragma: no cover - network errors
        return jsonify({"error": str(exc)}), 500

    update_memory(user, message, reply)
    return jsonify({"reply": reply})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

