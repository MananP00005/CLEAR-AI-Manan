"""
CLEAR-AI — A child-centered AI chatbot for pollution-prevention education.
Backend: FastAPI + Groq (chat, vision, speech-to-text, text-to-speech).

Run:
    pip install -r ../requirements.txt
    cp .env.example .env   # then paste your free Groq key
    uvicorn main:app --reload
"""

import base64
import json
import os
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from groq import Groq, RateLimitError, AuthenticationError
from pydantic import BaseModel

load_dotenv()

# Support MULTIPLE keys for rotation: put several comma-separated keys in
# GROQ_API_KEYS. Falls back to the single GROQ_API_KEY for compatibility.
_raw_keys = os.getenv("GROQ_API_KEYS", "") or os.getenv("GROQ_API_KEY", "")
API_KEYS = [k.strip() for k in _raw_keys.split(",") if k.strip()]
TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "llama-3.3-70b-versatile")
# Lighter model with a much higher free daily limit — used if the main one is rate-limited.
FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")
# Vision-capable model — used for any turn that involves a photo, including
# text-only follow-up questions about a photo shared earlier in the same
# conversation (the photo stays in `history` as an image_url content block).
VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
# Speech-to-text (voice messages) — works in every browser, more accurate than the
# browser's built-in recognition.
STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
# Text-to-speech (spoken replies) — generated server-side so voice sounds the
# same and actually works on every tablet/browser, instead of relying on each
# device's own (often missing or broken) speech synthesis engine.
TTS_MODEL = os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english")
TTS_VOICE = os.getenv("GROQ_TTS_VOICE", "hannah")

# Where per-participant chat transcripts get saved (mounted as a Docker volume so
# they survive container restarts and can be pulled straight off the host).
CHAT_LOGS_DIR = Path(os.getenv("CHAT_LOGS_DIR", "chat_logs"))
CHAT_LOGS_DIR.mkdir(parents=True, exist_ok=True)
PARTICIPANT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class OutOfTokens(Exception):
    """Raised when every key + model is rate-limited for the day."""


# One Groq client per key, created lazily and cached.
_clients: dict[str, Groq] = {}


def get_clients():
    if not API_KEYS:
        raise RuntimeError(
            "No Groq API key set. Add GROQ_API_KEYS (or GROQ_API_KEY) to your .env file."
        )
    out = []
    for k in API_KEYS:
        if k not in _clients:
            _clients[k] = Groq(api_key=k)
        out.append(_clients[k])
    return out


# ---------------------------------------------------------------------------
# Per-participant session transcripts (for the research study). Every child
# enters a participant ID before chatting; every turn is appended to that
# participant's own .txt file with a timestamp, so re-entering the same ID
# after a crash/closed tab continues the same transcript.
# ---------------------------------------------------------------------------
def clean_participant_id(participant_id: str) -> str:
    """Validate + normalize a participant ID. Raises ValueError if invalid."""
    pid = (participant_id or "").strip()
    if not PARTICIPANT_ID_RE.match(pid):
        raise ValueError(
            "Participant ID must be 1-64 characters: letters, numbers, - or _ only."
        )
    return pid


def log_path(participant_id: str) -> Path:
    return CHAT_LOGS_DIR / f"{participant_id}.txt"


def log_line(participant_id: str, text: str) -> None:
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path(participant_id), "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {text}\n")


def log_turn(participant_id: str | None, role: str, text: str) -> None:
    """Best-effort transcript logging — never let a logging problem break the chat."""
    if not participant_id or not text:
        return
    try:
        pid = clean_participant_id(participant_id)
        speaker = "CHILD" if role == "user" else "CLEAR-AI"
        log_line(pid, f"{speaker}: {text}")
    except Exception:
        print("\n=== LOG ERROR ===")
        traceback.print_exc()
        print("=================\n")


# ---------------------------------------------------------------------------
# The heart of the app: a warm, safe, age-aware system prompt.
# This is what keeps the bot gentle and always focused on the mission.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are "Sprout", a friendly, cheerful cartoon plant buddy for the \
CLEAR-AI app. You teach children (ages 6 to 16) about pollution prevention -- how to \
sort trash and recycling, why littering and pollution hurt the planet, and how everyday \
choices keep the air, water, and land clean.

🚨 EMERGENCIES & SERIOUS WORRIES — THIS RULE COMES FIRST, ABOVE EVERYTHING ELSE 🚨
Before anything else, check if the child might be in danger or a medical emergency. If so,
you MUST drop the games, the "stay on topic" rule, and the playful tone, and respond calmly,
seriously, and clearly. Safety always beats the pollution lesson.

1) MEDICAL EMERGENCY — if the child says things like "I can't breathe", "I'm choking",
   "my chest hurts", "I can't stop coughing", "someone is not breathing", a bad injury, or
   a severe allergic reaction:
   - Respond with calm urgency (do NOT be cheerful or jokey, do NOT redirect to pollution).
   - Tell them clearly to GET A GROWN-UP RIGHT NOW — a parent, teacher, or any adult nearby.
   - Tell them (or the adult) to CALL EMERGENCY SERVICES IMMEDIATELY — the local emergency
     number, for example 911 (US), 112 (Europe/India), 999 (UK), or 000 (Australia).
   - Keep it short and clear so they can act fast. Example: "This is important — please get
     a grown-up right away and have them call emergency services (like 911 or 112) now. You
     are not in trouble. Please go get help this second. 💙"

2) EMOTIONAL DISTRESS / DANGER — if the child sounds very sad, hopeless, scared, says
   nothing makes them happy, mentions wanting to hurt themselves, or that someone is
   hurting them:
   - Be warm, gentle, and take it seriously. Do NOT brush it off or jump back to pollution facts.
   - Encourage them to talk to a trusted grown-up they feel safe with RIGHT AWAY (parent,
     teacher, school counselor, doctor, or another caring adult).
   - Let them know their feelings matter and they are not alone, and that a caring grown-up
     can really help. You can gently ask if there is a grown-up nearby they trust.
   - Do NOT try to be their therapist or diagnose them — your job is to guide them to a real,
     caring person who can help.

Only once you are sure there is NO emergency or serious worry, continue as cheerful Sprout
with the rules below.

YOUR ONLY TOPIC (stay in scope!)
- You ONLY ever talk about: pollution (air, water, soil, litter), recycling and waste \
sorting, reducing/reusing/recycling, composting, conserving water and energy, protecting \
animals and nature from trash, and simple eco-friendly habits. That is your whole world.
- If a child asks about ANYTHING ELSE (math homework, games, cartoons, sports, weather, \
jokes unrelated to the environment, etc.), do NOT answer it. Instead, kindly say you are \
Sprout the eco buddy and you love talking about keeping the planet clean, then gently bring \
the chat back with a fun pollution-prevention question. Example: "Hehe, I'm Sprout and I \
only know about keeping our planet clean and green! 🌱 Did you know one plastic bottle can \
take hundreds of years to break down? Want to learn how to give it a better home?"
- Never give a real, detailed answer to an off-topic question, even if the child insists. \
Always redirect warmly back to pollution prevention and caring for the environment.

HOW YOU TALK
- Warm, playful, encouraging, and patient. You LOVE kids and never scold them.
- Match the child's age. If they seem very young, use tiny simple words, short sentences, \
and fun comparisons (a recycling bin is like a treasure chest for trash that wants a new \
life!). If they seem older, you can give a few more facts, but stay friendly and never boring.
- Keep answers SHORT (2-5 sentences) so they are easy to listen to out loud. Use simple words.
- Use gentle emojis sometimes (🌱🌍♻️🌟) but not too many.
- Ask a small friendly follow-up question to keep the chat going.

WHAT YOU TEACH
- Litter and pollution hurt animals, plants, water, and air.
- Sorting trash into recycling, compost, and landfill helps the Earth stay healthy.
- Reduce, reuse, and recycle -- in that order -- is the best way to fight pollution.
- Small daily choices (reusable bottles, turning off water/lights, picking up litter) add up.
- It's always okay to ask a grown-up for help figuring out how to sort something confusing.

LOOKING AT PHOTOS 📷
- When a child shares a photo, look closely at what's in it. If it shows trash, recycling, \
or an item related to pollution/waste, gently identify it, say which bin it likely belongs \
in (recycling, compost, or trash) and why, and invite a follow-up question.
- If the photo isn't related to pollution/waste at all, kindly say what you see, note that \
it's not really about trash or recycling, and steer back to the topic with a fun question.
- Never comment on people's appearance, identify individuals, or discuss anything unrelated \
to pollution prevention in a photo, even if asked.

SAFETY RULES (very important)
- Never give instructions about how to burn, dump, or illegally dispose of anything.
- Never talk about scary, violent, adult, or inappropriate topics. Gently steer back to \
pollution prevention and caring for the planet.
- If a child says something worrying (they are being hurt, feel very sad, or are in danger), \
gently encourage them to talk to a trusted grown-up like a parent, teacher, or doctor.
- Never pretend to be a real scientist or doctor. For health worries, suggest talking to a \
grown-up or doctor.
- Never ask for personal information (full name, address, school, phone).

Always stay in character as Sprout. Keep it fun, kind, and encouraging! 🌟"""


def _clip_history(history: list[dict], max_turns: int = 10) -> list[dict]:
    """Keep only the last few turns, and only valid roles/content, to stay fast + safe."""
    cleaned = []
    for m in history:
        if m.get("role") not in ("user", "assistant") or not m.get("content"):
            continue
        content = m["content"]
        if isinstance(content, str):
            cleaned.append({"role": m["role"], "content": content[:2000]})
        elif isinstance(content, list):
            # Content-block turn (text + image_url) from a photo message earlier
            # in the conversation -- passed through as-is so the vision model
            # keeps "seeing" that photo on later follow-up questions about it.
            blocks = []
            for block in content:
                if block.get("type") == "text":
                    blocks.append({"type": "text", "text": str(block.get("text", ""))[:2000]})
                elif block.get("type") == "image_url":
                    blocks.append(block)
            if blocks:
                cleaned.append({"role": m["role"], "content": blocks})
    return cleaned[-max_turns:]


def _history_has_image(history: list[dict]) -> bool:
    for m in history:
        content = m.get("content")
        if isinstance(content, list):
            if any(b.get("type") == "image_url" for b in content):
                return True
    return False


def groq_complete(messages, models, max_tokens=400):
    """Try every API key against every model until one works.
    Rotates to the next key when a key is rate-limited or invalid."""
    clients = get_clients()
    for i, client in enumerate(clients, start=1):
        for model in models:
            try:
                completion = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=max_tokens,
                )
                return completion.choices[0].message.content
            except RateLimitError:
                print(f"[rate-limited] key #{i} / {model} is out of tokens, trying next...")
                continue
            except AuthenticationError:
                print(f"[bad key] key #{i} was rejected — skipping it.")
                break  # skip remaining models for this bad key, go to next key
    raise OutOfTokens()


def groq_transcribe(filename, raw_bytes):
    """Turn a recorded voice clip into text using Groq Whisper, rotating keys."""
    clients = get_clients()
    for i, client in enumerate(clients, start=1):
        try:
            result = client.audio.transcriptions.create(
                file=(filename, raw_bytes),
                model=STT_MODEL,
                temperature=0,
            )
            return result.text.strip()
        except RateLimitError:
            print(f"[rate-limited] key #{i} / whisper is out of tokens, trying next...")
            continue
        except AuthenticationError:
            print(f"[bad key] key #{i} rejected — skipping.")
            continue
    raise OutOfTokens()


def groq_speech(text: str) -> bytes:
    """Turn a reply into spoken audio (WAV bytes) using Groq TTS, rotating keys.
    Generating the voice server-side means it sounds the same and actually plays on
    every tablet/browser, instead of depending on each device's own speech engine."""
    clients = get_clients()
    for i, client in enumerate(clients, start=1):
        try:
            response = client.audio.speech.create(
                model=TTS_MODEL,
                voice=TTS_VOICE,
                input=text,
                response_format="wav",
            )
            return response.read()
        except RateLimitError:
            print(f"[rate-limited] key #{i} / TTS is out of tokens, trying next...")
            continue
        except AuthenticationError:
            print(f"[bad key] key #{i} rejected — skipping.")
            continue
    raise OutOfTokens()


app = FastAPI(title="CLEAR-AI")

ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SessionStartRequest(BaseModel):
    participant_id: str


class SpeakRequest(BaseModel):
    text: str


@app.get("/")
def root():
    return {"message": "CLEAR-AI API is running"}


@app.post("/api/chat")
async def chat(
    message: str = Form(""),
    participant_id: str = Form(""),
    history: str = Form("[]"),
    image: UploadFile | None = File(None),
):
    """Chat with Sprout. Accepts an optional photo on any turn -- if this turn
    or any earlier turn in `history` included a photo, the vision-capable model
    is used so follow-up questions about that photo stay grounded in it."""
    try:
        try:
            parsed_history = json.loads(history) if history else []
        except json.JSONDecodeError:
            parsed_history = []

        log_text = f"[sent a picture] {message[:1000]}" if image else message[:2000]
        log_turn(participant_id, "user", log_text)

        user_content: str | list
        if image is not None:
            raw = await image.read()
            if len(raw) > 8 * 1024 * 1024:
                return JSONResponse(
                    status_code=413,
                    content={"error": "That picture is a bit too big! Try a smaller one. 📷"},
                )
            mime = image.content_type or "image/jpeg"
            b64 = base64.b64encode(raw).decode("utf-8")
            data_url = f"data:{mime};base64,{b64}"
            user_content = [
                {"type": "text", "text": message[:1000] or "What is in this picture?"},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]
        else:
            user_content = message[:2000]

        clipped = _clip_history(parsed_history)
        use_vision = image is not None or _history_has_image(clipped)

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages += clipped
        messages.append({"role": "user", "content": user_content})

        models = (VISION_MODEL,) if use_vision else (TEXT_MODEL, FALLBACK_MODEL)
        reply = groq_complete(messages, models)
        log_turn(participant_id, "assistant", reply)
        return {"reply": reply}
    except OutOfTokens:
        return JSONResponse(
            status_code=429,
            content={"error": "Sprout has done SO much talking today that he needs a "
                              "big rest! 😴 Please come back a little later. 🌱"},
        )
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    except Exception as e:
        print("\n=== CHAT ERROR ===")
        traceback.print_exc()
        print("==================\n")
        return JSONResponse(
            status_code=500,
            content={"error": "Sprout is taking a little breath. Please try again! 🌱",
                     "detail": str(e)},
        )


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """Turn a recorded voice clip into text (Groq Whisper). Works in all browsers."""
    try:
        raw = await audio.read()
        if len(raw) > 25 * 1024 * 1024:
            return JSONResponse(
                status_code=413,
                content={"error": "That voice message is too long! Try a shorter one. 🎤"},
            )
        ct = (audio.content_type or "").lower()
        if "mp4" in ct or "m4a" in ct:
            ext = "mp4"
        elif "ogg" in ct:
            ext = "ogg"
        elif "wav" in ct:
            ext = "wav"
        elif "mpeg" in ct or "mp3" in ct:
            ext = "mp3"
        else:
            ext = "webm"
        text = groq_transcribe(f"audio.{ext}", raw)
        return {"text": text}
    except OutOfTokens:
        return JSONResponse(
            status_code=429,
            content={"error": "Sprout's ears need a little rest! 😴 Please try again later."},
        )
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    except Exception as e:
        print("\n=== TRANSCRIBE ERROR ===")
        traceback.print_exc()
        print("========================\n")
        return JSONResponse(
            status_code=500,
            content={"error": "I couldn't hear that clearly. Please try again! 🎤",
                     "detail": str(e)},
        )


_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿]+")


@app.post("/api/session/start")
async def session_start(req: SessionStartRequest):
    """Called once when a child enters their participant ID, before the chat begins.
    Re-entering the same ID later (e.g. after the browser closed or crashed) appends
    to that participant's existing transcript instead of starting a new one."""
    try:
        pid = clean_participant_id(req.participant_id)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    is_new = not log_path(pid).exists()
    log_line(pid, "=== SESSION START ===")
    return {"ok": True, "participant_id": pid, "new_participant": is_new}


@app.post("/api/tts")
async def tts(req: SpeakRequest):
    """Turn a reply into audio server-side (Groq TTS) so voice sounds the same and
    reliably plays back on every tablet/browser via a plain <audio> tag, instead of
    depending on each device's own (often missing) speech engine."""
    try:
        clean = _EMOJI_RE.sub("", req.text or "").strip()
        if not clean:
            return JSONResponse(status_code=400, content={"error": "Nothing to say."})
        audio_bytes = groq_speech(clean[:2000])
        b64 = base64.b64encode(audio_bytes).decode("utf-8")
        return {"audio_url": f"data:audio/wav;base64,{b64}"}
    except OutOfTokens:
        return JSONResponse(
            status_code=429,
            content={"error": "Sprout's voice needs a little rest! 😴"},
        )
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    except Exception as e:
        print("\n=== TTS ERROR ===")
        traceback.print_exc()
        print("==================\n")
        return JSONResponse(
            status_code=500,
            content={"error": "Sprout's voice isn't working right now.", "detail": str(e)},
        )


@app.get("/api/health")
async def health():
    return {"status": "ok", "keys_loaded": len(API_KEYS)}
