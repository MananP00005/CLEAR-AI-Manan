<script setup>
import { ref, nextTick, onMounted } from 'vue'

const props = defineProps({
  participantId: String,
  isNewParticipant: Boolean
})

const emit = defineEmits(['reset'])

const colors = ["#1b75bc", "#39b54a", "#fbb03b", "#ff1d25", "#4d4d4d", "#754c24", "#ffffff"]
const dots = Array.from({ length: 40 }, () => ({
  top: Math.random() * 100,
  left: Math.random() * 100,
  size: 10 + Math.random() * 6,
  color: colors[Math.floor(Math.random() * colors.length)],
  duration: 8 + Math.random() * 12,
  delay: Math.random() * -20
}))

let nextId = 1
const messages = ref([])
const composerText = ref('')
const attachedImage = ref(null) // { file, previewUrl }
const isSending = ref(false)
const isRecording = ref(false)
const isTranscribing = ref(false)
const voiceEnabled = ref(localStorage.getItem('clearai-voice') !== 'off')
const isSpeaking = ref(false)

const fileInput = ref(null)
const cameraInput = ref(null)
const chatBody = ref(null)

let mediaRecorder = null
let audioChunks = []

onMounted(() => {
  const greeting = props.isNewParticipant
    ? "Hi there! I'm Sprout 🌱 I love talking about keeping our planet clean! You can ask me questions, send me a picture of some trash or recycling, or even talk to me with your voice. What's on your mind?"
    : "Welcome back! 🌱 Ready to keep learning about keeping our planet clean? What would you like to talk about?"
  messages.value.push({
    id: nextId++,
    role: 'assistant',
    text: greeting,
    clientOnly: true
  })
  scrollToBottom()
  if (voiceEnabled.value) speak(greeting)
})

function scrollToBottom() {
  nextTick(() => {
    if (chatBody.value) chatBody.value.scrollTop = chatBody.value.scrollHeight
  })
}

function toggleVoice() {
  voiceEnabled.value = !voiceEnabled.value
  localStorage.setItem('clearai-voice', voiceEnabled.value ? 'on' : 'off')
}

const EMOJI_RE = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}]+/gu

function speak(text) {
  if (!text || isSpeaking.value) return
  if (!('speechSynthesis' in window)) return
  const clean = text.replace(EMOJI_RE, '').trim()
  if (!clean) return
  isSpeaking.value = true
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(clean)
  utterance.onend = () => { isSpeaking.value = false }
  utterance.onerror = () => { isSpeaking.value = false }
  window.speechSynthesis.speak(utterance)
}

function triggerFileInput() {
  fileInput.value.click()
}

function triggerCamera() {
  cameraInput.value.click()
}

function handleImageSelected(event) {
  const file = event.target.files[0]
  event.target.value = ''
  if (!file) return
  if (attachedImage.value) URL.revokeObjectURL(attachedImage.value.previewUrl)
  attachedImage.value = { file, previewUrl: URL.createObjectURL(file) }
}

function removeAttachedImage() {
  if (attachedImage.value) URL.revokeObjectURL(attachedImage.value.previewUrl)
  attachedImage.value = null
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

function buildHistoryPayload() {
  return messages.value
    .filter((m) => !m.clientOnly)
    .map((m) => {
      if (m.role === 'user' && m.imageDataUrl) {
        return {
          role: 'user',
          content: [
            { type: 'text', text: m.text || 'What is in this picture?' },
            { type: 'image_url', image_url: { url: m.imageDataUrl } }
          ]
        }
      }
      return { role: m.role, content: m.text }
    })
}

async function sendMessage() {
  const text = composerText.value.trim()
  if (!text && !attachedImage.value) return
  if (isSending.value) return

  isSending.value = true
  try {
    let imageDataUrl = null
    if (attachedImage.value) {
      imageDataUrl = await fileToDataUrl(attachedImage.value.file)
    }

    const historyPayload = buildHistoryPayload()

    const userMsg = {
      id: nextId++,
      role: 'user',
      text,
      imageDataUrl
    }
    messages.value.push(userMsg)
    scrollToBottom()

    const formData = new FormData()
    formData.append('message', text)
    formData.append('participant_id', props.participantId)
    formData.append('history', JSON.stringify(historyPayload))
    if (attachedImage.value) formData.append('image', attachedImage.value.file)

    composerText.value = ''
    removeAttachedImage()

    const response = await fetch('/api/chat', { method: 'POST', body: formData })
    const data = await response.json()

    if (!response.ok) {
      messages.value.push({
        id: nextId++,
        role: 'assistant',
        text: data.error || "Sprout couldn't reply right now. Please try again.",
        isError: true
      })
    } else {
      messages.value.push({ id: nextId++, role: 'assistant', text: data.reply })
      if (voiceEnabled.value) speak(data.reply)
    }
  } catch (err) {
    console.error('Send failed:', err)
    messages.value.push({
      id: nextId++,
      role: 'assistant',
      text: "Sprout couldn't reach the server. Please check your connection and try again.",
      isError: true
    })
  } finally {
    isSending.value = false
    scrollToBottom()
  }
}

async function toggleRecording() {
  if (isRecording.value) {
    mediaRecorder?.stop()
    return
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    audioChunks = []
    mediaRecorder = new MediaRecorder(stream)
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data)
    }
    mediaRecorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop())
      isRecording.value = false
      const blob = new Blob(audioChunks, { type: 'audio/webm' })
      transcribeAndSend(blob)
    }
    mediaRecorder.start()
    isRecording.value = true
  } catch (err) {
    console.error('Microphone access failed:', err)
    messages.value.push({
      id: nextId++,
      role: 'assistant',
      text: "Sprout couldn't hear your microphone. Please check your browser's mic permission and try again.",
      isError: true
    })
    scrollToBottom()
  }
}

async function transcribeAndSend(blob) {
  isTranscribing.value = true
  try {
    const formData = new FormData()
    formData.append('audio', blob, 'recording.webm')
    const response = await fetch('/api/transcribe', { method: 'POST', body: formData })
    const data = await response.json()
    if (!response.ok || !data.text) {
      messages.value.push({
        id: nextId++,
        role: 'assistant',
        text: data.error || "Sprout couldn't quite hear that. Please try again.",
        isError: true
      })
      scrollToBottom()
      return
    }
    composerText.value = data.text
    await nextTick()
    await sendMessage()
  } catch (err) {
    console.error('Transcribe failed:', err)
    messages.value.push({
      id: nextId++,
      role: 'assistant',
      text: "Sprout couldn't reach the server to listen to that. Please try again.",
      isError: true
    })
    scrollToBottom()
  } finally {
    isTranscribing.value = false
  }
}
</script>

<template>
  <section class="hero is-fullheight particle-bg">
    <div
      v-for="(dot, i) in dots"
      :key="i"
      class="dot"
      :style="{
        top: dot.top + '%',
        left: dot.left + '%',
        width: dot.size + 'px',
        height: dot.size + 'px',
        backgroundColor: dot.color,
        animationDuration: dot.duration + 's',
        animationDelay: dot.delay + 's'
      }"
    ></div>

    <div class="hero-body">
      <div class="container">
        <div class="columns is-vcentered is-centered cards-row">
          <div class="column is-narrow">
            <div class="glass-card chat-box">
              <div class="top-bar">
                <span class="chat-title">Talking with Sprout 🌱</span>
                <div class="top-bar-actions">
                  <button
                    class="voice-toggle-btn"
                    :class="{ 'voice-off': !voiceEnabled }"
                    @click="toggleVoice"
                    :title="voiceEnabled ? 'Voice is on' : 'Voice is off'"
                  >
                    <i class="fa-solid" :class="voiceEnabled ? 'fa-volume-high' : 'fa-volume-xmark'"></i>
                  </button>
                  <button class="new-participant-btn" @click="emit('reset')" title="Switch participant">
                    New participant
                  </button>
                </div>
              </div>

              <div class="chat-body" ref="chatBody">
                <div
                  v-for="m in messages"
                  :key="m.id"
                  class="message-row"
                  :class="m.role === 'user' ? 'row-user' : 'row-assistant'"
                >
                  <img v-if="m.role === 'assistant'" src="/mascot.png" class="avatar" alt="Sprout" />
                  <div class="bubble" :class="{ 'bubble-user': m.role === 'user', 'bubble-error': m.isError }">
                    <img v-if="m.imageDataUrl" :src="m.imageDataUrl" class="bubble-image" />
                    <p v-if="m.text">{{ m.text }}</p>
                    <button
                      v-if="m.role === 'assistant' && m.text"
                      class="replay-btn"
                      @click="speak(m.text)"
                      :disabled="isSpeaking"
                    >
                      <i class="fa-solid fa-volume-high"></i>
                    </button>
                  </div>
                </div>

                <div v-if="isSending" class="message-row row-assistant">
                  <img src="/mascot.png" class="avatar" alt="Sprout" />
                  <div class="bubble typing-bubble">
                    <span class="typing-dot"></span>
                    <span class="typing-dot"></span>
                    <span class="typing-dot"></span>
                  </div>
                </div>
              </div>

              <div class="composer">
                <div v-if="attachedImage" class="attached-preview">
                  <img :src="attachedImage.previewUrl" />
                  <button class="remove-attachment" @click="removeAttachedImage">
                    <i class="fa-solid fa-xmark"></i>
                  </button>
                </div>

                <input type="file" ref="fileInput" accept="image/*" @change="handleImageSelected" hidden />
                <input
                  type="file"
                  ref="cameraInput"
                  accept="image/*"
                  capture="environment"
                  @change="handleImageSelected"
                  hidden
                />

                <div class="composer-row">
                  <button class="icon-btn" @click="triggerFileInput" title="Attach a photo">
                    <i class="fa-solid fa-image"></i>
                  </button>
                  <button class="icon-btn" @click="triggerCamera" title="Take a photo">
                    <i class="fa-solid fa-camera"></i>
                  </button>
                  <button
                    class="icon-btn mic-btn"
                    :class="{ recording: isRecording }"
                    @click="toggleRecording"
                    :disabled="isTranscribing"
                    :title="isRecording ? 'Stop recording' : 'Send a voice message'"
                  >
                    <i class="fa-solid fa-microphone"></i>
                  </button>
                  <input
                    v-model="composerText"
                    type="text"
                    class="composer-input"
                    :placeholder="isTranscribing ? 'Listening...' : 'Ask Sprout something...'"
                    :disabled="isTranscribing"
                    @keyup.enter="sendMessage"
                  />
                  <button class="send-btn" @click="sendMessage" :disabled="isSending || isTranscribing">
                    <i class="fa-solid fa-paper-plane"></i>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.particle-bg {
  background-color: #ffffff;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

.dot {
  position: absolute;
  border-radius: 50%;
  opacity: 0.7;
  pointer-events: none;
  animation-name: float;
  animation-timing-function: ease-in-out;
  animation-iteration-count: infinite;
}

@keyframes float {
  0%   { transform: translate(0, 0); }
  25%  { transform: translate(15px, -20px); }
  50%  { transform: translate(-10px, -35px); }
  75%  { transform: translate(-20px, -10px); }
  100% { transform: translate(0, 0); }
}

.cards-row {
  position: relative;
  z-index: 1;
}

.glass-card {
  backdrop-filter: blur(20px);
  background: rgba(255, 255, 255, 0.35);
  border: 2px solid #9daecc;
  border-radius: 24px;
  box-shadow: 0 4px 12px #01050b;
}

.chat-box {
  width: 910px;
  max-width: 95vw;
  box-sizing: border-box;
  padding: 0;
  height: 90vh;
  max-height: 900px;
  display: flex;
  flex-direction: column;
}

.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #9daecc;
  padding: 16px 24px;
  flex-shrink: 0;
}

.chat-title {
  font-weight: 600;
  color: #1a1a1a;
}

.top-bar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.voice-toggle-btn {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 1px solid grey;
  background-color: #39b54a;
  color: white;
  cursor: pointer;
  font-size: 16px;
}

.voice-toggle-btn.voice-off {
  background-color: lightgray;
  color: #555;
}

.new-participant-btn {
  border-radius: 999px;
  border: 1px solid grey;
  padding: 8px 14px;
  font-size: 12px;
  background-color: lightgray;
  color: #1a1a1a;
  cursor: pointer;
  white-space: nowrap;
}

.chat-body {
  padding: 20px 24px;
  overflow-y: auto;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.message-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}

.row-user {
  justify-content: flex-end;
}

.row-assistant {
  justify-content: flex-start;
}

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  flex-shrink: 0;
  object-fit: cover;
}

.bubble {
  max-width: 65%;
  background-color: rgba(255, 255, 255, 0.85);
  border: 1px solid #ddd;
  border-radius: 16px;
  padding: 10px 14px;
  color: #333;
  position: relative;
}

.bubble p {
  margin: 0;
  line-height: 1.5;
  white-space: pre-line;
}

.bubble-user {
  background-color: #39b54a;
  color: white;
  border: none;
}

.bubble-error {
  background-color: #fdecea;
  border-color: #f5c6c0;
  color: #7a2e25;
}

.bubble-image {
  max-width: 200px;
  border-radius: 12px;
  display: block;
  margin-bottom: 6px;
}

.replay-btn {
  border: none;
  background: transparent;
  color: #39b54a;
  cursor: pointer;
  padding: 4px 0 0;
  font-size: 12px;
}

.replay-btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.typing-bubble {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 14px 16px;
}

.typing-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: #999;
  animation: bounce 1.2s infinite ease-in-out;
}

.typing-dot:nth-child(2) { animation-delay: 0.15s; }
.typing-dot:nth-child(3) { animation-delay: 0.3s; }

@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
  30% { transform: translateY(-4px); opacity: 1; }
}

.composer {
  border-top: 1px solid #9daecc;
  padding: 14px 20px;
  flex-shrink: 0;
}

.attached-preview {
  position: relative;
  width: fit-content;
  margin-bottom: 10px;
}

.attached-preview img {
  max-height: 80px;
  border-radius: 10px;
  display: block;
}

.remove-attachment {
  position: absolute;
  top: -8px;
  right: -8px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: none;
  background-color: #ff1d25;
  color: white;
  cursor: pointer;
  font-size: 11px;
}

.composer-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.icon-btn {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 1px solid grey;
  background-color: lightgray;
  color: #1a1a1a;
  cursor: pointer;
}

.mic-btn.recording {
  background-color: #ff1d25;
  color: white;
  animation: pulse 1.2s infinite;
}

@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(255, 29, 37, 0.5); }
  70% { box-shadow: 0 0 0 8px rgba(255, 29, 37, 0); }
  100% { box-shadow: 0 0 0 0 rgba(255, 29, 37, 0); }
}

.composer-input {
  flex: 1;
  border-radius: 999px;
  border: 1px solid #9daecc;
  padding: 10px 16px;
  font-size: 14px;
}

.composer-input:disabled {
  opacity: 0.7;
}

.send-btn {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: none;
  background-color: #39b54a;
  color: white;
  cursor: pointer;
}

.send-btn:disabled {
  opacity: 0.6;
  cursor: default;
}
</style>
