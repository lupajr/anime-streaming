<template>
  <div class="folder-view">
    <!-- Estado de Carregamento -->
    <div v-if="loading" class="loading-container">
      <div class="spinner"></div>
      <p>Carregando biblioteca do Drive...</p>
    </div>

    <!-- Estado de Erro -->
    <div v-else-if="error" class="error-container">
      <div class="error-card">
        <svg viewBox="0 0 24 24" width="48" height="48" stroke="#ef4444" stroke-width="2" fill="none">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="8" x2="12" y2="12"/>
          <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        <h3>Atenção: Configuração necessária</h3>
        <p class="error-msg">{{ error }}</p>
        <div class="error-tip" v-if="serviceAccountEmail">
          <strong>Como resolver:</strong>
          <ol>
            <li>Abra o seu Google Drive no navegador.</li>
            <li>Localize a pasta <code>{{ folderName || 'Animes' }}</code>.</li>
            <li>Clique com botão direito &gt; <strong>Compartilhar</strong>.</li>
            <li>Adicione o e-mail da service account com acesso de <strong>Leitor</strong>:</li>
            <div class="sa-box">
              <code>{{ serviceAccountEmail }}</code>
              <button class="btn-copy" @click="copySA">Copiar</button>
            </div>
            <li>Depois volte aqui e clique em <strong>Sincronizar</strong>.</li>
          </ol>
        </div>
        <button class="btn-retry" @click="loadData">Tentar Novamente</button>
      </div>
    </div>

    <!-- Conteúdo da Pasta -->
    <div v-else-if="data" class="content-container">
      <!-- Barra de Navegação / Breadcrumb -->
      <nav class="breadcrumb-bar">
        <div class="crumbs">
          <router-link 
            v-for="(crumb, idx) in data.breadcrumb" 
            :key="crumb.id"
            :to="`/folder/${crumb.id}`"
            class="crumb-link"
            :class="{ active: idx === data.breadcrumb.length - 1 }"
          >
            {{ crumb.name }}
            <span v-if="idx < data.breadcrumb.length - 1" class="crumb-sep">/</span>
          </router-link>
        </div>
      </nav>

      <!-- Seção: Continuar Assistindo (apenas na tela inicial) -->
      <section v-if="isRoot && continueList.length > 0" class="section continue-section">
        <h2 class="section-title">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
            <path d="M8 5v14l11-7z"/>
          </svg>
          Continuar Assistindo
        </h2>

        <div class="continue-grid">
          <div 
            v-for="item in continueList" 
            :key="item.id" 
            class="continue-card"
            @click="openPlayer(item.id)"
          >
            <div class="continue-thumb">
              <img 
                v-if="item.cover" 
                :src="`/api/image/${item.cover}`" 
                :alt="item.folder_name" 
                loading="lazy"
              />
              <div v-else class="thumb-placeholder">
                <svg viewBox="0 0 24 24" width="36" height="36" fill="currentColor">
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/>
                </svg>
              </div>

              <!-- Barra de Progresso no Card -->
              <div class="progress-bar-container" v-if="item.progress && item.progress.duration > 0">
                <div 
                  class="progress-bar-fill" 
                  :style="{ width: `${Math.min(100, (item.progress.position / item.progress.duration) * 100)}%` }"
                ></div>
              </div>
            </div>

            <div class="continue-info">
              <div class="continue-folder">{{ item.folder_name }}</div>
              <div class="continue-episode" :title="item.title">{{ item.title }}</div>
              <div class="continue-meta" v-if="item.progress && item.progress.duration > 0">
                {{ formatRemaining(item.progress.duration - item.progress.position) }} restantes
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Seção: Pastas / Animes / Temporadas -->
      <section v-if="data.folders && data.folders.length > 0" class="section">
        <h2 class="section-title">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
            <path d="M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/>
          </svg>
          {{ isRoot ? 'Animes' : 'Pastas & Temporadas' }}
        </h2>

        <div class="folder-grid">
          <router-link 
            v-for="folder in data.folders" 
            :key="folder.id" 
            :to="`/folder/${folder.id}`"
            class="folder-card"
          >
            <div class="folder-poster">
              <img 
                v-if="folder.cover" 
                :src="`/api/image/${folder.cover}`" 
                :alt="folder.name" 
                loading="lazy"
              />
              <div v-else class="folder-placeholder">
                <svg viewBox="0 0 24 24" width="48" height="48" stroke="currentColor" stroke-width="1.5" fill="none">
                  <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
                </svg>
              </div>

              <div class="folder-badge" v-if="folder.count > 0">
                {{ folder.count }} {{ folder.count === 1 ? 'item' : 'itens' }}
              </div>
            </div>

            <div class="folder-title" :title="folder.name">
              {{ folder.name }}
            </div>
          </router-link>
        </div>
      </section>

      <!-- Seção: Episódios / Vídeos -->
      <section v-if="data.videos && data.videos.length > 0" class="section">
        <h2 class="section-title">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
            <path d="M18 3v2h-2V3H8v2H6V3H4v18h2v-2h2v2h8v-2h2v2h2V3h-2zM8 17H6v-2h2v2zm0-4H6v-2h2v2zm0-4H6V7h2v2zm10 8h-2v-2h2v2zm0-4h-2v-2h2v2zm0-4h-2V7h2v2z"/>
          </svg>
          Episódios ({{ data.videos.length }})
        </h2>

        <div class="video-list">
          <div 
            v-for="(vid, idx) in data.videos" 
            :key="vid.id"
            class="video-row"
            :class="{ watched: vid.progress && vid.progress.watched }"
            @click="openPlayer(vid.id)"
          >
            <div class="video-index">{{ idx + 1 }}</div>

            <div class="video-play-btn">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                <path d="M8 5v14l11-7z"/>
              </svg>
            </div>

            <div class="video-details">
              <div class="video-title">
                {{ vid.title }}
              </div>
              <div class="video-sub">
                <span class="video-size">{{ formatSize(vid.size) }}</span>
                <span v-if="vid.progress && vid.progress.watched" class="badge-watched">✓ Assistido</span>
                <span v-else-if="vid.progress && vid.progress.position > 0" class="badge-progress">
                  Em {{ formatTime(vid.progress.position) }}
                </span>
              </div>

              <!-- Barra de progresso pequena -->
              <div class="video-progress-line" v-if="vid.progress && vid.progress.duration > 0 && !vid.progress.watched">
                <div 
                  class="progress-fill" 
                  :style="{ width: `${(vid.progress.position / vid.progress.duration) * 100}%` }"
                ></div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Pasta Vazia -->
      <div 
        v-if="(!data.folders || data.folders.length === 0) && (!data.videos || data.videos.length === 0)" 
        class="empty-state"
      >
        <svg viewBox="0 0 24 24" width="56" height="56" stroke="currentColor" stroke-width="1.5" fill="none">
          <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
          <line x1="9" y1="13" x2="15" y2="13"/>
        </svg>
        <p>Nenhum vídeo ou subpasta encontrado aqui.</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  id: {
    type: String,
    default: 'root',
  },
})

const router = useRouter()
const loading = ref(true)
const error = ref('')
const data = ref(null)
const continueList = ref([])
const serviceAccountEmail = ref('')
const folderName = ref('')

const isRoot = computed(() => props.id === 'root' || (data.value && data.value.id === 'root'))

async function checkHealth() {
  try {
    const res = await fetch('/api/health')
    if (res.ok) {
      const d = await res.json()
      serviceAccountEmail.value = d.service_account || ''
    }
  } catch (e) {
    // ignorar
  }
}

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const folderRes = await fetch(`/api/folders/${props.id}`)
    if (!folderRes.ok) {
      const err = await folderRes.json()
      throw new Error(err.detail || `Erro ${folderRes.status}`)
    }
    data.value = await folderRes.json()
    folderName.value = data.value.name

    if (isRoot.value) {
      const contRes = await fetch('/api/continue')
      if (contRes.ok) {
        continueList.value = await contRes.json()
      }
    }
  } catch (e) {
    error.value = e.message
    await checkHealth()
  } finally {
    loading.value = false
  }
}

function openPlayer(videoId) {
  router.push(`/watch/${videoId}`)
}

function copySA() {
  if (serviceAccountEmail.value) {
    navigator.clipboard.writeText(serviceAccountEmail.value)
    alert('E-mail copiado! Cole nas permissões da sua pasta no Google Drive.')
  }
}

function formatSize(bytes) {
  if (!bytes) return ''
  const mb = bytes / (1024 * 1024)
  if (mb >= 1000) {
    return `${(mb / 1024).toFixed(1)} GB`
  }
  return `${Math.round(mb)} MB`
}

function formatTime(sec) {
  if (!sec) return '0:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s < 10 ? '0' : ''}${s}`
}

function formatRemaining(sec) {
  if (sec <= 0) return '0m'
  const min = Math.round(sec / 60)
  return `${min}m`
}

watch(() => props.id, () => {
  loadData()
})

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.folder-view {
  max-width: 1400px;
  margin: 0 auto;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  gap: 16px;
  color: var(--text-muted);
}

.spinner {
  width: 44px;
  height: 44px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Erro */
.error-container {
  padding: 40px 16px;
  display: flex;
  justify-content: center;
}

.error-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 32px;
  max-width: 600px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.error-msg {
  color: var(--text-muted);
  line-height: 1.5;
}

.error-tip {
  text-align: left;
  background: var(--bg-card);
  padding: 16px 20px;
  border-radius: var(--radius-sm);
  width: 100%;
  font-size: 0.9rem;
  line-height: 1.6;
}

.error-tip ol {
  margin-top: 8px;
  padding-left: 20px;
}

.sa-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 12px;
  margin: 10px 0;
  word-break: break-all;
}

.sa-box code {
  color: var(--accent-light);
  font-size: 0.85rem;
}

.btn-copy {
  background: var(--accent);
  color: #fff;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  margin-left: 8px;
  white-space: nowrap;
}

.btn-retry {
  background: var(--accent);
  color: #fff;
  padding: 10px 24px;
  border-radius: var(--radius-sm);
  font-weight: 600;
  margin-top: 8px;
}

/* Breadcrumb */
.breadcrumb-bar {
  margin-bottom: 24px;
}

.crumbs {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 1.1rem;
  font-weight: 600;
}

.crumb-link {
  color: var(--text-muted);
  transition: color 0.2s;
}

.crumb-link:hover {
  color: var(--text-main);
}

.crumb-link.active {
  color: var(--accent-light);
}

.crumb-sep {
  margin-left: 8px;
  color: var(--text-dim);
}

.section {
  margin-bottom: 36px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 1.25rem;
  font-weight: 700;
  margin-bottom: 18px;
  color: var(--text-main);
}

/* Continuar assistindo */
.continue-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.continue-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.2s, border-color 0.2s, box-shadow 0.2s;
}

.continue-card:hover {
  transform: translateY(-4px);
  border-color: var(--accent);
  box-shadow: 0 10px 20px -5px var(--accent-glow);
}

.continue-thumb {
  position: relative;
  aspect-ratio: 16 / 9;
  background: var(--bg-secondary);
  overflow: hidden;
}

.continue-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent-light);
  opacity: 0.6;
}

.progress-bar-container {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: rgba(0, 0, 0, 0.6);
}

.progress-bar-fill {
  height: 100%;
  background: var(--accent);
}

.continue-info {
  padding: 12px 14px;
}

.continue-folder {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--accent-light);
  font-weight: 700;
  margin-bottom: 4px;
}

.continue-episode {
  font-size: 0.95rem;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 4px;
}

.continue-meta {
  font-size: 0.8rem;
  color: var(--text-muted);
}

/* Pastas Grid */
.folder-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 20px;
}

.folder-card {
  display: flex;
  flex-direction: column;
  transition: transform 0.2s;
}

.folder-card:hover {
  transform: translateY(-4px);
}

.folder-poster {
  position: relative;
  aspect-ratio: 2 / 3;
  border-radius: var(--radius);
  background: var(--bg-card);
  border: 1px solid var(--border);
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.folder-card:hover .folder-poster {
  border-color: var(--accent);
  box-shadow: 0 8px 20px -4px var(--accent-glow);
}

.folder-poster img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.folder-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-dim);
}

.folder-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(4px);
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-main);
}

.folder-title {
  margin-top: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  line-height: 1.3;
  color: var(--text-main);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Lista de Vídeos / Episódios */
.video-list {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.video-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background-color 0.15s;
}

.video-row:last-child {
  border-bottom: none;
}

.video-row:hover {
  background-color: var(--bg-card-hover);
}

.video-row.watched .video-title {
  color: var(--text-muted);
}

.video-index {
  font-size: 1rem;
  font-weight: 700;
  color: var(--text-dim);
  width: 24px;
  text-align: center;
}

.video-play-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-main);
  transition: all 0.2s;
  flex-shrink: 0;
}

.video-row:hover .video-play-btn {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
  transform: scale(1.08);
}

.video-details {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.video-title {
  font-size: 1rem;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.video-sub {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 0.8rem;
  color: var(--text-muted);
}

.badge-watched {
  color: var(--success);
  font-weight: 600;
}

.badge-progress {
  color: var(--accent-light);
  font-weight: 600;
}

.video-progress-line {
  height: 3px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
  width: 120px;
  margin-top: 4px;
}

.progress-fill {
  height: 100%;
  background: var(--accent);
}

.empty-state {
  padding: 80px 20px;
  text-align: center;
  color: var(--text-dim);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

@media (max-width: 640px) {
  .folder-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
  }
  .video-row {
    padding: 12px 14px;
    gap: 12px;
  }
}
</style>
