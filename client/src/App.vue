<script setup>
import { ref } from 'vue'
import ParticipantGate from './components/ParticipantGate.vue'
import ChatWindow from './components/ChatWindow.vue'

const participantId = ref('')
const isNewParticipant = ref(false)
const sessionActive = ref(false)

function handleStarted({ participantId: id, isNew }) {
  participantId.value = id
  isNewParticipant.value = isNew
  sessionActive.value = true
}

function handleReset() {
  participantId.value = ''
  isNewParticipant.value = false
  sessionActive.value = false
}
</script>

<template>
  <ParticipantGate v-if="!sessionActive" @started="handleStarted" />
  <ChatWindow
    v-else
    :key="participantId"
    :participantId="participantId"
    :isNewParticipant="isNewParticipant"
    @reset="handleReset"
  />
</template>
