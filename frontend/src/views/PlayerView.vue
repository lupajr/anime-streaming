<template>
  <div 
    class="player-wrapper" 
    :class="{ 'controls-hidden': !showControls && isPlaying }"
    @mousemove="onUserActivity"
    @touchstart="onUserActivity"
    ref="wrapperRef"
  >
    <!-- Vídeo Principal -->
    <video
      ref="videoRef"
      class="video-element"
      playsinline
      crossorigin="anonymous"
      @play="onPlay"
      @pause="onPause"
      @timeupdate="onTimeUpdate"
      @durationchange="onDurationChange"
      @ended="onEnded"
      @waiting="isBuffering = true"
      @playing="isBuffering = false"
      @error="onVideoError"
      @click="togglePlay"
    ></video>

    <!-- Indicador de Buffer / Carregando -->
    <div v-if="isBuffering || loadingInfo" class="buffer-indicator">
      <div class="spinner"></div>
      <span v-if="loadingInfo">Carregando episódio...</span>
    </div>

    <!-- Overlay de Controles -->
    <div class="player-overlay" :class="{ visible: showControls || !isPlaying }">
      <!-- Topo: Voltar, Título, Modo de Streaming, Configurações -->
      <div class="overlay-top">
        <button class="btn-back" @click="goBack" title="Voltar para a pasta">
          <svg viewBox="0 0 24 24" width="24" height="24" stroke="currentColor" stroke-width="2.5" fill="none">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
        </button>

        <div class="top-title" v-if="fileData">
          <span class="folder-name">{{ fileData.parent_name }}</span>
          <h1 class="ep-name">{{ fileData.title }}</h1>
        </div>

        <div class="top-actions">
          <!-- Seletor de Modo: Direto vs Compatível -->
          <button 
            class="badge-mode" 
            :class="{ active: streamMode === 'transcode' }"
            @click="toggleMode"
            :title="streamMode === 'direct' ? 'Modo Direto: clique para alternar para Compatível (FFmpeg)' : 'Modo Compatível: clique para alternar para Direto'"
          >
            {{ streamMode === 'direct' ? '⚡ Direto' : '🔄 Compatível' }}
          </button>

          <!-- Botão de Configurações (Áudio/Legendas) -->
          <button 
            class="btn-top-icon" 
            @click.stop="showTrackMenu = !showTrackMenu"
            title="Áudio e Legendas"
          >
            <svg viewBox="0 0 24 24" width="22" height="22" stroke="currentColor" stroke-width="2" fill="none">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- Centro: Play/Pause e Seek rápido (toque duplo ou botões) -->
      <div class="overlay-center" @click.self="togglePlay">
        <button 
          v-if="fileData && fileData.prev" 
          class="center-btn skip-btn" 
          @click.stop="goToEpisode(fileData.prev.id)"
          title="Episódio Anterior"
        >
          <svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor">
            <path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/>
          </svg>
        </button>

        <button 
          class="center-btn seek-jump" 
          @click.stop="seekRelative(-10)"
          title="Voltar 10s"
        >
          <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M1 4v6h6M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>
            <text x="12" y="15" font-size="7" font-weight="bold" fill="currentColor" text-anchor="middle" stroke="none">10</text>
          </svg>
        </button>

        <button 
          class="center-btn play-main" 
          @click.stop="togglePlay"
        >
          <svg v-if="!isPlaying" viewBox="0 0 24 24" width="44" height="44" fill="currentColor">
            <path d="M8 5v14l11-7z"/>
          </svg>
          <svg v-else viewBox="0 0 24 24" width="44" height="44" fill="currentColor">
            <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>
          </svg>
        </button>

        <button 
          class="center-btn seek-jump" 
          @click.stop="seekRelative(10)"
          title="Avançar 10s"
        >
          <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M23 4v6h-6M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
            <text x="12" y="15" font-size="7" font-weight="bold" fill="currentColor" text-anchor="middle" stroke="none">10</text>
          </svg>
        </button>

        <button 
          v-if="fileData && fileData.next" 
          class="center-btn skip-btn" 
          @click.stop="goToEpisode(fileData.next.id)"
          title="Próximo Episódio"
        >
          <svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor">
            <path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/>
          </svg>
        </button>
      </div>

      <!-- Fundo: Barra de Progresso e Controles -->
      <div class="overlay-bottom">
        <!-- Linha do Tempo / Scrubbing -->
        <div 
          class="timeline-container" 
          @mousedown="startScrub"
          @touchstart="startScrub"
          ref="timelineRef"
        >
          <div class="timeline-rail">
            <div 
              class="timeline-progress" 
              :style="{ width: `${progressPercent}%` }"
            ></div>
            <div 
              class="timeline-handle" 
              :style="{ left: `${progressPercent}%` }"
            ></div>
          </div>
        </div>

        <div class="bottom-bar">
          <div class="bottom-left">
            <button class="btn-control" @click="togglePlay">
              <svg v-if="!isPlaying" viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
                <path d="M8 5v14l11-7z"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
                <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>
              </svg>
            </button>

            <!-- Próximo Episódio Rápido -->
            <button 
              v-if="fileData && fileData.next" 
              class="btn-control" 
              @click="goToEpisode(fileData.next.id)"
              title="Próximo Episódio"
            >
              <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                <path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/>
              </svg>
            </button>

            <!-- Tempo -->
            <div class="time-display">
              <span>{{ formatTime(currentTime) }}</span>
              <span class="time-sep">/</span>
              <span>{{ formatTime(duration) }}</span>
            </div>
          </div>

          <div class="bottom-right">
            <!-- Autoplay Toggle -->
            <button 
              class="btn-control auto-btn" 
              :class="{ active: autoplayNext }"
              @click="autoplayNext = !autoplayNext"
              title="Autoplay: Próximo episódio automático"
            >
              <span class="auto-label">Auto</span>
            </button>

            <!-- PiP (Picture in Picture) -->
            <button 
              class="btn-control" 
              @click="togglePiP" 
              v-if="supportsPiP"
              title="Picture in Picture"
            >
              <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                <path d="M19 11h-8v6h8v-6zm4 8V4.98C23 3.88 22.1 3 21 3H3c-1.1 0-2 .88-2 1.98V19c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2zm-2 .02H3V4.97h18v14.05z"/>
              </svg>
            </button>

            <!-- Tela Cheia -->
            <button class="btn-control" @click="toggleFullscreen" title="Tela Cheia (F)">
              <svg v-if="!isFullscreen" viewBox="0 0 24 24" width="22" height="22" stroke="currentColor" stroke-width="2" fill="none">
                <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" width="22" height="22" stroke="currentColor" stroke-width="2" fill="none">
                <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Menu Lateral / Popup: Faixas de Áudio e Legendas -->
    <div v-if="showTrackMenu" class="track-menu" @click.stop>
      <div class="track-menu-header">
        <h3>Áudio & Legendas</h3>
        <button class="track-close" @click="showTrackMenu = false">&times;</button>
      </div>

      <div class="track-menu-body" v-if="mediaInfo">
        <!-- Áudio -->
        <div class="track-section">
          <h4>Áudio</h4>
          <div class="track-options">
            <button 
              v-for="a in mediaInfo.audio" 
              :key="a.index"
              class="track-option"
              :class="{ selected: selectedAudio === a.index }"
              @click="changeAudio(a.index)"
            >
              <span>{{ a.title || a.language || `Faixa ${a.index + 1}` }} ({{ a.codec }})</span>
              <span v-if="selectedAudio === a.index" class="check">✓</span>
            </button>
          </div>
        </div>

        <!-- Legendas -->
        <div class="track-section">
          <h4>Legendas</h4>
          <div class="track-options">
            <button 
              class="track-option"
              :class="{ selected: selectedSubtitle === -1 }"
              @click="changeSubtitle(-1)"
            >
              <span>Desativadas</span>
              <span v-if="selectedSubtitle === -1" class="check">✓</span>
            </button>

            <button 
              v-for="s in mediaInfo.subtitles" 
              :key="s.index"
              class="track-option"
              :class="{ selected: selectedSubtitle === s.index }"
              @click="changeSubtitle(s.index)"
            >
              <span>{{ s.title || s.language || `Legenda ${s.index + 1}` }} {{ s.forced ? '(Forçada)' : '' }}</span>
              <span v-if="selectedSubtitle === s.index" class="check">✓</span>
            </button>
          </div>
        </div>
      </div>
      <div v-else class="track-menu-body">
        Carregando faixas...
      </div>
    </div>

    <!-- Modal de Fim de Episódio (Up Next) -->
    <div v-if="showEndCard && fileData && fileData.next" class="end-card">
      <div class="end-card-box">
        <span class="end-tag">Próximo Episódio em {{ nextCountdown }}s</span>
        <h3 class="end-title">{{ fileData.next.title }}</h3>
        <div class="end-actions">
          <button class="btn-end-play" @click="goToEpisode(fileData.next.id)">Assistir Agora</button>
          <button class="btn-end-cancel" @click="cancelAutoplay">Cancelar</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  id: {
    type: String,
    required: true,
  },
})

const router = useRouter()
const wrapperRef = ref(null)
const videoRef = ref(null)
const timelineRef = ref(null)

const isPlaying = ref(false)
const isBuffering = ref(false)
const showControls = ref(true)
const currentTime = ref(0)
const duration = ref(0)
const isFullscreen = ref(false)
const supportsPiP = ref(false)

const fileData = ref(null)
const mediaInfo = ref(null)
const loadingInfo = ref(true)

const streamMode = ref('direct') // 'direct' ou 'transcode'
const showTrackMenu = ref(false)
const selectedAudio = ref(0)
const selectedSubtitle = ref(-1)

const autoplayNext = ref(true)
const showEndCard = ref(false)
const nextCountdown = ref(5)

let hideTimer = null
let saveProgressTimer = null
let countdownInterval = null
let isScrubbing = false

const progressPercent = computed(() => {
  if (!duration.value || duration.value <= 0) return 0
  return Math.min(100, (currentTime.value / duration.value) * 100)
})

// ---------------------------------------------------------------- Ciclo de Vida
onMounted(async () => {
  supportsPiP.value = 'pictureInPictureEnabled' in document
  document.addEventListener('keydown', onKeyDown)
  document.addEventListener('fullscreenchange', onFullscreenChange)

  await loadEpisode()

  saveProgressTimer = setInterval(() => {
    saveCurrentProgress()
  }, 5000)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeyDown)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  clearTimeout(hideTimer)
  clearInterval(saveProgressTimer)
  clearInterval(countdownInterval)
  saveCurrentProgress()
})

// ---------------------------------------------------------------- Carregamento
async function loadEpisode() {
  loadingInfo.value = true
  showEndCard.value = false
  clearInterval(countdownInterval)

  try {
    const fileRes = await fetch(`/api/files/${props.id}`)
    if (!fileRes.ok) throw new Error('Falha ao obter metadados do vídeo')
    fileData.value = await fileRes.json()

    // Busca detalhes do ffmpeg (áudios, legendas, duração)
    fetchMediaInfo()

    // Configura src do vídeo
    setupVideoSource(fileData.value.progress ? fileData.value.progress.position : 0)
  } catch (e) {
    alert(e.message)
    goBack()
  } finally {
    loadingInfo.value = false
  }
}

async function fetchMediaInfo() {
  try {
    const res = await fetch(`/api/media/${props.id}/info`)
    if (res.ok) {
      mediaInfo.value = await res.json()
      if (mediaInfo.value.duration) {
        duration.value = mediaInfo.value.duration
      }
      if (mediaInfo.value.default_audio !== undefined) {
        selectedAudio.value = mediaInfo.value.default_audio
      }
      // Se houver legenda default, ativa
      const defSub = mediaInfo.value.subtitles?.find(s => s.default)
      if (defSub) {
        applySubtitle(defSub.index)
      }
    }
  } catch (e) {
    console.warn('Erro ao carregar probe media:', e)
  }
}

function setupVideoSource(startPos = 0) {
  const vid = videoRef.value
  if (!vid) return

  if (streamMode.value === 'direct') {
    vid.src = `/api/stream/${props.id}`
  } else {
    // Modo compatível via transcode FFmpeg
    let url = `/api/transcode/${props.id}?start=${startPos}&audio=${selectedAudio.value}`
    if (selectedSubtitle.value >= 0 && mediaInfo.value?.subtitles?.[selectedSubtitle.value]?.text === false) {
      // Legenda de imagem (burn-in)
      url += `&burn=${selectedSubtitle.value}`
    }
    vid.src = url
  }

  vid.load()

  // Se estiver no modo direto e tiver posição salva anterior
  if (streamMode.value === 'direct' && startPos > 5) {
    vid.currentTime = startPos
  }

  vid.play().catch(() => {
    isPlaying.value = false
  })
}

// ---------------------------------------------------------------- Legendas
function applySubtitle(index) {
  selectedSubtitle.value = index
  const vid = videoRef.value
  if (!vid) return

  // Remove tracks antigos
  while (vid.firstChild) {
    vid.removeChild(vid.firstChild)
  }

  if (index >= 0) {
    const sub = mediaInfo.value?.subtitles?.[index]
    if (sub && sub.text) {
      // Legenda de texto: insere track nativo WebVTT
      const track = document.createElement('track')
      track.kind = 'subtitles'
      track.label = sub.title || sub.language || 'Legenda'
      track.srclang = sub.language || 'pt'
      track.src = `/api/media/${props.id}/subtitles/${index}`
      track.default = true
      vid.appendChild(track)
      if (vid.textTracks && vid.textTracks[0]) {
        vid.textTracks[0].mode = 'showing'
      }
    } else if (sub && !sub.text) {
      // Legenda bitmap: precisa de transcode com burn
      streamMode.value = 'transcode'
      setupVideoSource(currentTime.value)
    }
  }
}

function changeSubtitle(index) {
  applySubtitle(index)
  showTrackMenu.value = false
}

function changeAudio(index) {
  selectedAudio.value = index
  showTrackMenu.value = false
  if (streamMode.value === 'transcode') {
    setupVideoSource(currentTime.value)
  } else {
    // Para trocar áudio em MKV no browser, transcode é necessário
    streamMode.value = 'transcode'
    setupVideoSource(currentTime.value)
  }
}

function toggleMode() {
  const newMode = streamMode.value === 'direct' ? 'transcode' : 'direct'
  streamMode.value = newMode
  setupVideoSource(currentTime.value)
}

// ---------------------------------------------------------------- Progresso
async function saveCurrentProgress() {
  if (!currentTime.value || !duration.value) return
  try {
    await fetch(`/api/progress/${props.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        position: currentTime.value,
        duration: duration.value,
      }),
    })
  } catch (e) {
    // silencioso
  }
}

// ---------------------------------------------------------------- Controles & Ações
function togglePlay() {
  const vid = videoRef.value
  if (!vid) return
  if (vid.paused) {
    vid.play()
  } else {
    vid.pause()
  }
}

function onPlay() {
  isPlaying.value = true
  resetHideTimer()
}

function onPause() {
  isPlaying.value = false
  showControls.value = true
  saveCurrentProgress()
}

function onTimeUpdate() {
  if (isScrubbing) return
  const vid = videoRef.value
  if (vid) {
    currentTime.value = vid.currentTime
  }
}

function onDurationChange() {
  const vid = videoRef.value
  if (vid && vid.duration && !isNaN(vid.duration)) {
    duration.value = vid.duration
  }
}

function onEnded() {
  isPlaying.value = false
  saveCurrentProgress()
  if (autoplayNext.value && fileData.value?.next) {
    showEndCard.value = true
    nextCountdown.value = 5
    countdownInterval = setInterval(() => {
      nextCountdown.value--
      if (nextCountdown.value <= 0) {
        clearInterval(countdownInterval)
        goToEpisode(fileData.value.next.id)
      }
    }, 1000)
  }
}

function onVideoError() {
  // Se falhar no modo direto, tenta alternar automaticamente para compatível
  if (streamMode.value === 'direct') {
    console.warn('Falha no modo direto. Alternando automaticamente para Compatível (FFmpeg)...')
    streamMode.value = 'transcode'
    setupVideoSource(currentTime.value)
  }
}

function seekRelative(seconds) {
  const vid = videoRef.value
  if (!vid) return
  const target = Math.max(0, Math.min(duration.value, vid.currentTime + seconds))
  vid.currentTime = target
  currentTime.value = target
  resetHideTimer()
}

function startScrub(e) {
  isScrubbing = true
  updateScrub(e)

  const moveHandler = (ev) => updateScrub(ev)
  const upHandler = () => {
    isScrubbing = false
    window.removeEventListener('mousemove', moveHandler)
    window.removeEventListener('mouseup', upHandler)
    window.removeEventListener('touchmove', moveHandler)
    window.removeEventListener('touchend', upHandler)
  }

  window.addEventListener('mousemove', moveHandler)
  window.addEventListener('mouseup', upHandler)
  window.addEventListener('touchmove', moveHandler)
  window.addEventListener('touchend', upHandler)
}

function updateScrub(e) {
  const rect = timelineRef.value?.getBoundingClientRect()
  if (!rect || !duration.value) return
  const clientX = e.touches ? e.touches[0].clientX : e.clientX
  const pos = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
  const target = pos * duration.value
  currentTime.value = target
  if (videoRef.value) {
    videoRef.value.currentTime = target
  }
}

function toggleFullscreen() {
  const wrap = wrapperRef.value
  if (!wrap) return
  if (!document.fullscreenElement) {
    wrap.requestFullscreen().catch(() => {})
  } else {
    document.exitFullscreen().catch(() => {})
  }
}

function onFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement
}

async function togglePiP() {
  const vid = videoRef.value
  if (!vid) return
  try {
    if (document.pictureInPictureElement) {
      await document.exitPictureInPicture()
    } else {
      await vid.requestPictureInPicture()
    }
  } catch (e) {
    console.error('Erro PiP:', e)
  }
}

function goToEpisode(nextId) {
  router.push(`/watch/${nextId}`)
}

function cancelAutoplay() {
  showEndCard.value = false
  clearInterval(countdownInterval)
}

function goBack() {
  if (fileData.value && fileData.value.parent) {
    router.push(`/folder/${fileData.value.parent}`)
  } else {
    router.push('/folder/root')
  }
}

function onUserActivity() {
  showControls.value = true
  resetHideTimer()
}

function resetHideTimer() {
  clearTimeout(hideTimer)
  if (isPlaying.value) {
    hideTimer = setTimeout(() => {
      if (!showTrackMenu.value) {
        showControls.value = false
      }
    }, 3500)
  }
}

function onKeyDown(e) {
  if (e.target.tagName === 'INPUT') return
  switch (e.key) {
    case ' ':
    case 'k':
      e.preventDefault()
      togglePlay()
      break
    case 'ArrowLeft':
      e.preventDefault()
      seekRelative(-10)
      break
    case 'ArrowRight':
      e.preventDefault()
      seekRelative(10)
      break
    case 'f':
      e.preventDefault()
      toggleFullscreen()
      break
    case 'n':
      if (fileData.value?.next) {
        goToEpisode(fileData.value.next.id)
      }
      break
  }
}

function formatTime(sec) {
  if (!sec || isNaN(sec)) return '00:00'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = Math.floor(sec % 60)
  const pad = (n) => (n < 10 ? `0${n}` : `${n}`)
  if (h > 0) {
    return `${h}:${pad(m)}:${pad(s)}`
  }
  return `${pad(m)}:${pad(s)}`
}

watch(() => props.id, () => {
  loadEpisode()
})
</script>

<style scoped>
.player-wrapper {
  position: fixed;
  inset: 0;
  background-color: #000;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.player-wrapper.controls-hidden {
  cursor: none;
}

.video-element {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background-color: #000;
}

/* Indicador de Buffer */
.buffer-indicator {
  position: absolute;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: var(--text-main);
  pointer-events: none;
}

.spinner {
  width: 50px;
  height: 50px;
  border: 4px solid rgba(255, 255, 255, 0.2);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Overlay Geral */
.player-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  background: linear-gradient(
    to bottom,
    rgba(0, 0, 0, 0.75) 0%,
    rgba(0, 0, 0, 0) 25%,
    rgba(0, 0, 0, 0) 70%,
    rgba(0, 0, 0, 0.85) 100%
  );
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.3s ease;
}

.player-overlay.visible {
  opacity: 1;
  pointer-events: auto;
}

/* Topo */
.overlay-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 28px;
  gap: 16px;
}

.btn-back {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(8px);
  color: #fff;
  transition: background 0.2s;
}

.btn-back:hover {
  background: rgba(255, 255, 255, 0.25);
}

.top-title {
  flex: 1;
  min-width: 0;
}

.folder-name {
  font-size: 0.8rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.ep-name {
  font-size: 1.15rem;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #fff;
}

.top-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.badge-mode {
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 700;
  background: rgba(255, 255, 255, 0.15);
  backdrop-filter: blur(8px);
  color: #fff;
  transition: all 0.2s;
}

.badge-mode.active {
  background: var(--accent);
  box-shadow: 0 0 12px var(--accent-glow);
}

.btn-top-icon {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(8px);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s;
}

.btn-top-icon:hover {
  background: rgba(255, 255, 255, 0.25);
}

/* Centro */
.overlay-center {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 32px;
}

.center-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(6px);
  color: #fff;
  transition: transform 0.15s, background 0.2s;
}

.center-btn:hover {
  background: rgba(255, 255, 255, 0.2);
  transform: scale(1.1);
}

.play-main {
  width: 76px;
  height: 76px;
  background: var(--accent);
}

.play-main:hover {
  background: var(--accent-hover);
}

.seek-jump {
  width: 56px;
  height: 56px;
}

.skip-btn {
  width: 48px;
  height: 48px;
}

/* Fundo */
.overlay-bottom {
  padding: 0 28px 24px 28px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Timeline */
.timeline-container {
  padding: 10px 0;
  cursor: pointer;
}

.timeline-rail {
  position: relative;
  height: 5px;
  background: rgba(255, 255, 255, 0.3);
  border-radius: 3px;
  transition: height 0.15s;
}

.timeline-container:hover .timeline-rail {
  height: 8px;
}

.timeline-progress {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  background: var(--accent);
  border-radius: 3px;
}

.timeline-handle {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 0 8px rgba(0, 0, 0, 0.5);
  opacity: 0;
  transition: opacity 0.15s;
}

.timeline-container:hover .timeline-handle {
  opacity: 1;
}

/* Barra inferior */
.bottom-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.bottom-left, .bottom-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.btn-control {
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 6px;
  border-radius: 6px;
  transition: color 0.2s;
}

.btn-control:hover {
  color: var(--accent-light);
}

.auto-btn {
  border: 1px solid rgba(255, 255, 255, 0.25);
  padding: 3px 8px;
  font-size: 0.75rem;
  font-weight: 700;
  border-radius: 12px;
}

.auto-btn.active {
  background: var(--accent);
  border-color: var(--accent);
}

.time-display {
  font-size: 0.85rem;
  font-weight: 600;
  color: #ddd;
  display: flex;
  gap: 6px;
}

.time-sep {
  color: rgba(255, 255, 255, 0.4);
}

/* Menu de Áudio e Legendas */
.track-menu {
  position: absolute;
  top: 80px;
  right: 28px;
  width: 320px;
  max-height: calc(100vh - 160px);
  background: rgba(18, 18, 28, 0.95);
  backdrop-filter: blur(16px);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow-y: auto;
  box-shadow: 0 20px 30px rgba(0, 0, 0, 0.7);
  z-index: 50;
}

.track-menu-header {
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.track-menu-header h3 {
  font-size: 1rem;
}

.track-close {
  font-size: 1.4rem;
  color: var(--text-muted);
}

.track-menu-body {
  padding: 16px;
}

.track-section {
  margin-bottom: 16px;
}

.track-section h4 {
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--accent-light);
  margin-bottom: 8px;
}

.track-options {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.track-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-radius: 6px;
  background: var(--bg-card);
  font-size: 0.85rem;
  text-align: left;
  transition: background 0.15s;
}

.track-option:hover {
  background: var(--bg-card-hover);
}

.track-option.selected {
  background: var(--accent);
  color: #fff;
}

.check {
  font-weight: 700;
}

/* End Card */
.end-card {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 60;
  padding: 20px;
}

.end-card-box {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 32px;
  max-width: 480px;
  width: 100%;
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.end-tag {
  color: var(--accent-light);
  font-size: 0.85rem;
  font-weight: 700;
  text-transform: uppercase;
}

.end-title {
  font-size: 1.25rem;
  font-weight: 700;
}

.end-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.btn-end-play {
  background: var(--accent);
  color: #fff;
  padding: 10px 20px;
  border-radius: var(--radius-sm);
  font-weight: 700;
}

.btn-end-cancel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-muted);
  padding: 10px 20px;
  border-radius: var(--radius-sm);
}

@media (max-width: 640px) {
  .overlay-top, .overlay-bottom {
    padding-left: 16px;
    padding-right: 16px;
  }
  .overlay-center {
    gap: 16px;
  }
  .play-main {
    width: 60px;
    height: 60px;
  }
  .seek-jump, .skip-btn {
    width: 44px;
    height: 44px;
  }
  .track-menu {
    top: auto;
    bottom: 0;
    left: 0;
    right: 0;
    width: 100%;
    border-radius: 18px 18px 0 0;
  }
}
</style>
