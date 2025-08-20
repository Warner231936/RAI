"""Minimal web UI to chat with Requiem via a browser."""

from __future__ import annotations


import asyncio
from base64 import b64encode
from typing import Any, Dict

from flask import Flask, jsonify, render_template_string, request

import aiohttp

from core import (
    GLOBAL_MEMORY,
    SYSTEM_PROMPT,
    detect_language,
    get_user_entry,
    lookup_go2,
    translate_text,
    txt2img,
    update_memory,
)
from orchestrator import Orchestrator



app = Flask(__name__)


_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)
_SESSION = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300))
_ORCH = Orchestrator(SYSTEM_PROMPT, GLOBAL_MEMORY, _SESSION)

INDEX_HTML = """
<!doctype html>
<title>Requiem Web Chat</title>
<h1>Requiem</h1>
<div id="log" style="height:300px; overflow-y:auto; border:1px solid #ccc; padding:5px;"></div>
<input id="user" placeholder="username"> <input id="msg" placeholder="message">
<button onclick="send()">Send</button>

<br>
<input id="imgprompt" placeholder="image prompt">
<button onclick="img()">Image</button>

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

async function img(){
  const prompt=document.getElementById('imgprompt').value;
  const res=await fetch('/img',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt})});
  const data=await res.json();
  const log=document.getElementById('log');
  if(data.image){
    log.innerHTML+=`<p><b>Image:</b><br><img src="data:image/png;base64,${data.image}" width="256"/></p>`;
  }else{
    log.innerHTML+=`<p><b>IMG ERROR:</b> ${data.error}</p>`;
  }
  log.scrollTop=log.scrollHeight;
  document.getElementById('imgprompt').value='';
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


    entry = get_user_entry(user)
    lang = detect_language(message)
    msg_en = translate_text(message, lang, "en")
    kb = lookup_go2(msg_en)
    try:
        result = _LOOP.run_until_complete(
            _ORCH.handle(user, entry["history"], msg_en, kb, entry.get("summary", ""))
        )
    except Exception as exc:  # pragma: no cover - network errors
        return jsonify({"error": str(exc)}), 500

    reply_en = result.final
    reply = translate_text(reply_en, "en", lang)
    update_memory(user, msg_en, reply_en)
    resp: Dict[str, Any] = {"reply": reply}
    if result.intent.flags.get("needs_image"):
        try:
            png = txt2img(message)
            resp["image"] = b64encode(png).decode("ascii")
        except Exception as exc:  # pragma: no cover - network errors
            resp["error"] = str(exc)
    return jsonify(resp)


@app.post("/img")
def img():
    data = request.get_json(force=True)
    prompt = data.get("prompt")
    if not prompt:
        return jsonify({"error": "prompt required"}), 400
    try:
        png = txt2img(prompt)
    except Exception as exc:  # pragma: no cover - network errors
        return jsonify({"error": str(exc)}), 500
    return jsonify({"image": b64encode(png).decode("ascii")})

    prompt = build_prompt(user, message)
    try:
        reply = generate_response(prompt)
    except Exception as exc:  # pragma: no cover - network errors
        return jsonify({"error": str(exc)}), 500

    update_memory(user, message, reply)
    return jsonify({"reply": reply})



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

