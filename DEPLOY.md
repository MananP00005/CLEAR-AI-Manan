# Deploying CLEAR-AI to GCP

This deploys the whole stack (Vue frontend, FastAPI + Groq backend) as two
Docker containers on a single Compute Engine VM via `docker-compose.yml`. None
of the commands below have been run for you — they touch your GCP billing
account, so run them yourself (or ask me to walk through them with you
interactively).

## 0. Prerequisites

- A GCP project with billing enabled (Console → create a project if you
  don't have one → Billing → link a billing account).
- Enable the Compute Engine API for that project: Console → APIs & Services
  → Enable APIs → search "Compute Engine API" → Enable (or it'll prompt you
  automatically the first time you run a `gcloud compute` command).
- Install the `gcloud` CLI locally if you don't have it:
  https://cloud.google.com/sdk/docs/install
- Authenticate and set your project:
  ```bash
  gcloud init
  gcloud auth login
  gcloud config set project YOUR_PROJECT_ID
  ```
- A free [Groq API key](https://console.groq.com/keys) — the whole app runs
  through Groq's API now, so there's no local model to host.

## 1. Create the VM

All inference now happens on Groq's servers, not locally, so this VM only
needs to run two lightweight containers (FastAPI + nginx) — a small,
inexpensive instance is enough even at classroom scale.

```bash
gcloud compute instances create clear-ai \
  --zone=us-central1-a \
  --machine-type=e2-small \
  --boot-disk-size=20GB \
  --boot-disk-type=pd-balanced \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --tags=http-server \
  --metadata=startup-script='#! /bin/bash
    apt-get update
    apt-get install -y ca-certificates curl gnupg
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin'
```

## 2. Open the firewall for HTTP

```bash
gcloud compute firewall-rules create clear-ai-http \
  --allow=tcp:80 \
  --target-tags=http-server \
  --direction=INGRESS
```

## 3. Deploy the app

SSH in once the VM has finished its startup script (give it a minute or two
for Docker to install):

```bash
gcloud compute ssh clear-ai --zone=us-central1-a
```

Then, on the VM:

```bash
git clone https://github.com/MananP00005/CLEAR-AI.git
cd CLEAR-AI
echo "GROQ_API_KEYS=your_groq_key_here" > .env
sudo docker compose up -d --build
```

(If you ever make the repo private, that plain `https` clone stops working
on the VM since it has no credentials of its own — either add a deploy key,
or clone with a GitHub personal access token in the URL. Not needed while
the repo is public.)

Watch progress with:

```bash
sudo docker compose logs -f
```

Once it settles, visit `http://<VM_EXTERNAL_IP>` (get the IP with
`gcloud compute instances describe clear-ai --zone=us-central1-a --format='get(networkInterfaces[0].accessConfigs[0].natIP)'`).

## 4. Updating after code changes

```bash
git pull
sudo docker compose up -d --build
```

The `chat_logs_data` volume persists across this, so participant transcripts
are never lost by a redeploy.

## 5. Pulling transcripts off the VM

```bash
sudo docker cp $(sudo docker compose ps -q backend):/app/server/chat_logs ./chat_logs
```

Copies every participant's `.txt` log from the running container to
`./chat_logs` on the VM, ready to `scp`/`gcloud compute scp` down to your
machine for analysis.

## Notes / follow-ups not covered here

- **HTTPS**: everything above serves plain HTTP. Voice recording via
  `getUserMedia` (the mic button) requires a **secure context** — this works
  fine on `localhost` during development, but most browsers will refuse mic
  access on a plain `http://` production URL. Before a wide classroom
  rollout, put a domain + Caddy or certbot in front of this VM for HTTPS —
  needed for the voice-input feature to work off of `localhost`.
- **Groq needs outbound internet**: all chat/vision/STT/TTS calls go to
  Groq's API over the internet. GCE VMs have open egress by default, so this
  just works, but it's worth knowing if you ever lock down the VM's firewall
  further.
- **Rate limits**: Groq's free tier has daily rate limits per key. `GROQ_API_KEYS`
  supports comma-separated keys for automatic rotation if you're running a
  larger study and expect to exceed a single key's limit.
