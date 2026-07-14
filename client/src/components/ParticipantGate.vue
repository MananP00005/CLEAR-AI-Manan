<script setup>
import { ref } from 'vue'

const emit = defineEmits(['started'])

const participantId = ref('')
const isSubmitting = ref(false)
const error = ref('')

const colors = ["#1b75bc", "#39b54a", "#fbb03b", "#ff1d25", "#4d4d4d", "#754c24", "#ffffff"]
const dots = Array.from({ length: 60 }, () => ({
  top: Math.random() * 100,
  left: Math.random() * 100,
  size: 10 + Math.random() * 6,
  color: colors[Math.floor(Math.random() * colors.length)],
  duration: 8 + Math.random() * 12,
  delay: Math.random() * -20
}))

async function startSession() {
  const trimmed = participantId.value.trim()
  if (!trimmed) {
    error.value = 'Please enter a participant ID.'
    return
  }
  isSubmitting.value = true
  error.value = ''
  try {
    const response = await fetch('/api/session/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ participant_id: trimmed })
    })
    const data = await response.json()
    if (!response.ok) {
      error.value = data.error || 'Something went wrong. Please try again.'
      return
    }
    emit('started', { participantId: data.participant_id, isNew: data.new_participant })
  } catch (err) {
    console.error('Session start failed:', err)
    error.value = 'Could not reach the server. Please try again.'
  } finally {
    isSubmitting.value = false
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
            <div class="glass-card name-card">
              <h1 class="title has-text-centered is-size-1 is-family-monospace" style="color: #1a1a1a;">CLEAR-AI</h1>
              <p class="subtitle" style="color: #444;">Making the World A Cleaner Place</p>
            </div>
          </div>

          <div class="column is-narrow">
            <div class="glass-card gate-card">
              <img src="/mascot.png" class="gate-mascot" alt="Sprout the CLEAR-AI mascot" />
              <h2 class="gate-title">Hi! I'm Sprout 🌱</h2>
              <p class="gate-text">Before we chat, please enter your participant ID.</p>

              <form @submit.prevent="startSession" class="gate-form">
                <input
                  v-model="participantId"
                  type="text"
                  class="input gate-input"
                  placeholder="Participant ID"
                  :disabled="isSubmitting"
                  autocomplete="off"
                />
                <button type="submit" class="button gate-btn" :disabled="isSubmitting">
                  <span v-if="isSubmitting">Starting...</span>
                  <span v-else>Start Chat</span>
                </button>
              </form>

              <p v-if="error" class="gate-error">{{ error }}</p>
              <p class="gate-hint">
                Used the same ID before? Enter it again to keep chatting where you left off.
              </p>
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

.name-card {
  width: 380px;
  height: 560px;
  padding: 40px 32px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.gate-card {
  width: 340px;
  padding: 32px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 8px;
}

.gate-mascot {
  width: 90px;
  height: auto;
  margin-bottom: 4px;
}

.gate-title {
  font-size: 22px;
  font-weight: 700;
  color: #1a1a1a;
  margin: 0;
}

.gate-text {
  color: #444;
  font-size: 14px;
  margin-bottom: 8px;
}

.gate-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.gate-input {
  border-radius: 999px;
  border: 1px solid #9daecc;
  padding: 10px 16px;
  font-size: 14px;
  text-align: center;
}

.gate-btn {
  border-radius: 999px;
  border: 1px solid grey;
  padding: 10px 18px;
  background-color: #39b54a;
  color: white;
  font-weight: 600;
  cursor: pointer;
}

.gate-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

.gate-error {
  color: #c0392b;
  font-size: 13px;
  margin: 0;
}

.gate-hint {
  color: #666;
  font-size: 12px;
  margin-top: 4px;
}
</style>
