from __future__ import annotations

import os
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List

import aiohttp

INTENT_URL = os.getenv("INTENT_URL", "http://127.0.0.1:5002").rstrip("/")
THOUGHTS_URL = os.getenv("THOUGHTS_URL", "http://127.0.0.1:5003").rstrip("/")
CORE_URL = os.getenv("KOBOLD_URL", "http://127.0.0.1:5001").rstrip("/")

STOP_CORE = ["<|im_end|>", "<|im_start|>user"]


@dataclass
class Intent:
    intent: str
    confidence: float
    flags: Dict[str, Any]


@dataclass
class Plan:
    goal: str
    steps: List[str]
    tool_calls: List[Dict[str, Any]]


@dataclass
class Outcome:
    intent: Intent
    plan: Dict[str, Any]
    emotion: str
    final: str


def _json_only(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    body = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.I | re.M)
    m = re.search(r"\{.*\}", body, flags=re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except Exception:
        return {}


class LLMClient:
    def __init__(self, base: str, session: aiohttp.ClientSession):
        self.base = base
        self.sess = session

    async def gen(
        self,
        prompt: str,
        *,
        max_len: int = 256,
        ctx: int = 4096,
        temp: float = 0.7,
        top_p: float = 0.9,
        stop: List[str] | None = None,
        timeout: int = 30,
    ) -> str:
        payload = {
            "prompt": prompt,
            "max_context_length": ctx,
            "max_length": max_len,
            "temperature": temp,
            "top_p": top_p,
            "typical_p": 1.0,
            "rep_pen": 1.1,
            "rep_pen_range": 128,
            "stop_sequence": stop or [],
            "frmttriminc": True,
        }
        async with self.sess.post(
            f"{self.base}/api/v1/generate", json=payload, timeout=timeout
        ) as r:
            r.raise_for_status()
            js = await r.json()
        return (js.get("results", [{}])[0].get("text") or "").strip()


class Orchestrator:
    def __init__(self, system_prompt: str, global_memory: str, session: aiohttp.ClientSession):
        self.system = system_prompt
        self.gmem = global_memory
        self.intent = LLMClient(INTENT_URL, session)
        self.planner = LLMClient(THOUGHTS_URL, session)
        self.core = LLMClient(CORE_URL, session)
        self._intent_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}

    async def classify(self, text: str) -> Intent:
        key = text.strip().lower()
        now = time.time()
        hit = self._intent_cache.get(key)
        if hit and hit[0] > now:
            js = hit[1]
        else:
            prompt = (
                "Return ONLY compact JSON.\n"
                "Schema:{\"intent\":\"greeting|question|instruction|config|memory|image|moderation|admin|other\","\
                "\"confidence\":0.0,\"flags\":{\"needs_image\":false,\"needs_admin\":false,\"risky\":false}}\n"
                f"Message:\"{text}\"\nJSON:"
            )
            out = await self.intent.gen(prompt, max_len=160, ctx=1024, temp=0.2, top_p=0.95)
            js = _json_only(out) or {"intent": "other", "confidence": 0.5, "flags": {}}
            self._intent_cache[key] = (now + 60, js)
        js.setdefault("flags", {})
        js["flags"].setdefault("needs_image", False)
        c = float(js.get("confidence", 0))
        if c < 0.55:
            js["intent"] = "other"
            js["confidence"] = 0.55
        return Intent(js["intent"], js["confidence"], js["flags"])

    async def plan(self, message: str, intent: Intent) -> Dict[str, Any]:
        prompt = (
            "Plan the reply. Output ONLY JSON (no prose).\n"
            "Schema:{\"goal\":\"str\",\"steps\":[\"...\"],\"tool_calls\":[{\"name\":\"str\",\"when\":\"str\",\"args\":{}}],"
            "\"queries\":[],\"tone_hint\":\"str\",\"risks\":[\"...\"],\"final_suggestion\":\"str\"}\n"
            f"Intent:{json.dumps(intent.__dict__, ensure_ascii=False)}\n"
            f"Message:{json.dumps(message, ensure_ascii=False)}\nJSON:"
        )
        out = await self.planner.gen(prompt, max_len=220, ctx=1536, temp=0.4, top_p=0.9)
        js = _json_only(out)
        if not js:
            out = await self.planner.gen(
                prompt + "\nONLY JSON. DO NOT ADD TEXT.",
                max_len=180,
                ctx=1536,
                temp=0.2,
                top_p=0.9,
            )
            js = _json_only(out) or {
                "goal": "answer user",
                "steps": [],
                "tool_calls": [],
                "queries": [],
                "tone_hint": "neutral",
                "risks": [],
                "final_suggestion": "",
            }
        return js

    async def emotion(self, message: str, plan: Dict[str, Any]) -> str:
        hint = plan.get("tone_hint") or ""
        prompt = (
            "Return a <=10 word tone hint. No quotes.\n"
            f"Context tone_hint:{hint}\nMessage:{message}\nHint:"
        )
        out = await self.intent.gen(prompt, max_len=20, ctx=512, temp=0.7, top_p=0.9)
        return (out.splitlines()[0] if out else "calm & precise")[:48]

    def _chatml(
        self,
        history: List[Dict[str, str]],
        user_text: str,
        intent: Intent,
        plan: Dict[str, Any],
        tone: str,
        kb: str,
        summary: str,
    ) -> str:
        sys = [self.system]
        if self.gmem:
            sys.append("\n# Shared Memory\n" + self.gmem.strip())
        if summary:
            sys.append("\n# Conversation Summary\n" + summary.strip())
        if kb:
            sys.append("\n# Galaxy Online 2\n" + kb)
        sys.append(f"\n[INTERNAL intent]{json.dumps(intent.__dict__, ensure_ascii=False)}")
        sys.append(f"[INTERNAL plan]{json.dumps(plan, ensure_ascii=False)}")
        sys.append(f"[INTERNAL tone]{tone}")

        def block(role: str, content: str) -> str:
            return f"<|im_start|>{role}\n{content}\n<|im_end|>"

        parts = [block("system", "\n".join(sys).strip())]
        for t in history[-20:]:
            role = t.get("role", "user")
            if role not in ("user", "assistant"):
                role = "user"
            parts.append(block(role, t.get("content", "")))
        parts.append(block("user", user_text))
        parts.append("<|im_start|>assistant\n")
        return "\n".join(parts)

    async def core_reply(
        self,
        history: List[Dict[str, str]],
        user_text: str,
        intent: Intent,
        plan: Dict[str, Any],
        tone: str,
        kb: str,
        summary: str,
    ) -> str:
        prompt = self._chatml(history, user_text, intent, plan, tone, kb, summary)
        out = await self.core.gen(
            prompt,
            max_len=350,
            ctx=8192,
            temp=0.75,
            top_p=0.9,
            stop=STOP_CORE,
        )
        return out or "_(no text)_"

    async def coherence(self, message: str, reply: str) -> bool:
        prompt = (
            "Answer YES if the assistant reply directly addresses the user message, otherwise NO.\n"
            f"Message: {message}\nReply: {reply}\nAnswer:"
        )
        out = await self.intent.gen(prompt, max_len=6, ctx=512, temp=0.0, top_p=0.5)
        return out.strip().lower().startswith("y")

    async def handle(
        self,
        user_id: int,
        history: List[Dict[str, str]],
        user_text: str,
        kb: str = "",
        summary: str = "",
    ) -> Outcome:
        it = await self.classify(user_text)
        pl = await self.plan(user_text, it)
        em = await self.emotion(user_text, pl)
        for _ in range(2):
            final = await self.core_reply(history, user_text, it, pl, em, kb, summary)
            if await self.coherence(user_text, final):
                break
        return Outcome(it, pl, em, final)
