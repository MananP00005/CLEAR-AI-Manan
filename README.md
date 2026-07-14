# CLEAR-AI

**Sprout** is CLEAR-AI's friendly AI chatbot that teaches children (ages 6–16)
about pollution prevention — waste sorting, recycling, and everyday
eco-friendly habits — through natural conversation, built for a research study
on what children learn from talking with an AI about the environment.

(CLEAR = Classification, Learning, Education, and Action for Reduction)

---

## Features

- 💬 **Real conversation, not one-shot detection** — ask Sprout anything about
  pollution prevention, and ask follow-up questions.
- 📷 **Photo understanding** — send a picture of trash, recycling, or litter;
  Sprout identifies it and explains how to dispose of it, and you can keep
  asking questions about that same photo afterward.
- 🎤 **Voice input** — record a voice message and Sprout transcribes and
  responds to it.
- 🔊 **Voice output** — every reply can be read aloud; toggle it on/off, or
  replay any individual message.
- 🧾 **Per-participant transcript logging** — every child enters a participant
  ID before chatting; the full conversation (with timestamps) is appended to
  that participant's own log file, so accidental tab closes during testing
  don't lose data — re-entering the same ID picks up the same log.
- 🛡️ **Stays on topic** — off-topic questions get a warm redirect back to
  pollution prevention; genuine emergencies or signs of distress are always
  handled first, calmly, before anything else.

---

## Prerequisites

- Python 3.10+
- Node.js 22+
- A free [Groq API key](https://console.groq.com/keys)

---

## Setup

### 1. Clone the repository

```
git clone <your-repo-url>
cd CLEAR-AI
```

### 2. Create and activate a virtual environment

```
python3 -m venv CLEAR-env
source CLEAR-env/bin/activate
```

### 3. Install backend dependencies

```
pip install -r requirements.txt
```

### 4. Add your Groq API key

```
cd server
cp .env.example .env
```

Open `server/.env` and paste your key after `GROQ_API_KEYS=`. You can list
multiple comma-separated keys for automatic rotation if one hits its free-tier
rate limit.

### 5. Install frontend dependencies

```
cd client
npm install
cd ..
```

---

## Run the App

### 1. Start the backend

```
cd server
source ../CLEAR-env/bin/activate
uvicorn main:app --reload
```

Backend runs at `http://localhost:8000`

### 2. Start the frontend

In a separate terminal:

```
cd client
npm run dev
```

Frontend runs at `http://localhost:5173`

### 3. Use it

Open `http://localhost:5173`, enter a participant ID, and start chatting with
Sprout — ask questions, send a photo, or use the mic to send a voice message.

---

## Run with Docker

The whole stack (frontend, backend) runs as two containers via Docker Compose:

```
GROQ_API_KEYS=your_key_here docker compose up -d --build
```

(Or put `GROQ_API_KEYS=your_key_here` in a `.env` file at the repo root —
Docker Compose reads it automatically.)

Once it's up, visit `http://localhost`. See [DEPLOY.md](DEPLOY.md) for
deploying this to a GCP Compute Engine VM.

## Conversation Logs

Every participant's conversation is appended to `server/chat_logs/{id}.txt` as
plain text with a timestamp on every line, e.g.:

```
[2026-07-13 10:02:11] === SESSION START ===
[2026-07-13 10:02:20] CHILD: what happens if I throw a bottle in the ocean?
[2026-07-13 10:02:22] CLEAR-AI: Great question! ...
```

Re-entering the same participant ID later appends to the same file instead of
starting a new one — this is intentional, so a child accidentally closing the
tab mid-study doesn't lose their transcript. In Docker, this directory is a
named volume (`chat_logs_data`) so it survives container restarts.

## Kid-Safe Content

Sprout's system prompt (`server/main.py`) keeps every reply scoped to
pollution prevention and age-appropriate for 6–16 year olds, redirects
off-topic questions warmly instead of answering them, and checks for signs of
a medical emergency or emotional distress before anything else — safety always
comes before the lesson.

## Voice

Voice input (STT) and output (TTS) both run through Groq (Whisper for
transcription, a Groq TTS voice for replies) — generated server-side so it
sounds consistent and actually works on every browser/tablet, rather than
depending on each device's own (often missing) speech engine.

---

## Related Project

[Talk2Breathe](https://github.com/MananP00005/Talk2Breathe-Manan) — a sibling
chatbot ("Breezy") for smoking-prevention education, built on the same
FastAPI + Groq architecture.
