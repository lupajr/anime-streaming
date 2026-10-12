<template>
  <div class="app-layout">
    <header class="app-header" v-if="!isPlayerRoute">
      <div class="header-left">
        <router-link to="/folder/root" class="logo">
          <svg class="logo-icon" viewBox="0 0 64 64">
            <rect width="64" height="64" rx="14" fill="#181824"/>
            <path d="M24 18v28l22-14z" fill="url(#logo-grad)"/>
            <defs>
              <linearGradient id="logo-grad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stop-color="#a78bfa"/>
                <stop offset="1" stop-color="#f472b6"/>
              </linearGradient>
            </defs>
          </svg>
          <span class="logo-text">Anime<span class="accent-text">Stream</span></span>
        </router-link>
      </div>

      <div class="header-right">
        <button 
          class="btn-icon" 
          @click="showStats = !showStats" 
          title="Consumo da API do Drive / Sistema"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none">
            <path d="M12 20v-6M6 20V10M18 20V4"/>
          </svg>
        </button>

        <button 
          class="btn-sync" 
          :class="{ rotating: syncing }" 
          @click="triggerSync" 
          title="Sincronizar com Google Drive"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" stroke-width="2" fill="none">
            <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.19"/>
          </svg>
          <span class="sync-text">Sincronizar</span>
        </button>
      </div>
    </header>

    <!-- Modal de Estatísticas de Uso da Cota -->
    <div v-if="showStats" class="modal-backdrop" @click="showStats = false">
      <div class="modal-card" @click.stop>
        <div class="modal-header">
          <h3>Cota & Status do Sistema</h3>
          <button class="modal-close" @click="showStats = false">&times;</button>
        </div>
        <div class="modal-body" v-if="stats">
          <div class="stat-group">
            <div class="stat-label">Total de Requisições ao Drive:</div>
            <div class="stat-value highlight">{{ stats.drive_api_total || 0 }}</div>
          </div>
          <div class="stat-details" v-if="stats.drive_api_calls">
            <div v-for="(count, type) in stats.drive_api_calls" :key="type" class="stat-sub">
              <span>{{ type }}:</span>
              <strong>{{ count }}</strong>
            </div>
          </div>
          <hr class="divider"/>
          <div class="stat-group">
            <div class="stat-label">Transcodificações Ativas:</div>
            <div class="stat-value">{{ stats.active_transcodes || 0 }}</div>
          </div>
          <div class="stat-group">
            <div class="stat-label">Extrações de Legendas:</div>
            <div class="stat-value">{{ stats.subtitle_jobs || 0 }}</div>
          </div>
        </div>
        <div v-else class="modal-body loading-text">
          Carregando dados...
        </div>
      </div>
    </div>

    <!-- Conteúdo Principal -->
    <main class="app-main" :class="{ 'no-padding': isPlayerRoute }">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" :key="$route.fullPath" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const isPlayerRoute = computed(() => route.name === 'player')

const syncing = ref(false)
const showStats = ref(false)
const stats = ref(null)

async function fetchStats() {
  try {
    const res = await fetch('/api/stats')
    if (res.ok) {
      stats.value = await res.json()
    }
  } catch (e) {
    console.error('Erro ao buscar stats:', e)
  }
}

async function triggerSync() {
  if (syncing.value) return
  syncing.value = true
  try {
    const res = await fetch('/api/library/refresh', { method: 'POST' })
    if (res.ok) {
      window.location.reload()
    } else {
      const err = await res.json()
      alert(err.detail || 'Erro ao sincronizar')
    }
  } catch (e) {
    alert('Erro de rede ao sincronizar')
  } finally {
    syncing.value = false
  }
}

watch(showStats, (val) => {
  if (val) fetchStats()
})

onMounted(() => {
  fetchStats()
})
</script>

<style scoped>
.app-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-header {
  height: 64px;
  background-color: rgba(18, 18, 28, 0.85);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  position: sticky;
  top: 0;
  z-index: 50;
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 1.25rem;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.logo-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
}

.accent-text {
  color: var(--accent-light);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.btn-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: var(--radius-sm);
  background-color: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-muted);
  transition: all 0.2s;
}

.btn-icon:hover {
  color: var(--text-main);
  border-color: var(--accent);
}

.btn-sync {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background-color: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-main);
  font-size: 0.875rem;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-sync:hover {
  background-color: var(--bg-card-hover);
  border-color: var(--accent);
}

.rotating svg {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.app-main {
  flex: 1;
  padding: 24px;
}

.app-main.no-padding {
  padding: 0;
}

/* Modal */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background-color: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 16px;
}

.modal-card {
  background-color: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  width: 100%;
  max-width: 420px;
  overflow: hidden;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
}

.modal-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.modal-close {
  font-size: 1.5rem;
  color: var(--text-muted);
}

.modal-body {
  padding: 20px;
}

.stat-group {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.stat-label {
  color: var(--text-muted);
  font-size: 0.9rem;
}

.stat-value {
  font-weight: 700;
  font-size: 1.1rem;
}

.stat-value.highlight {
  color: var(--accent-light);
}

.stat-details {
  background: var(--bg-card);
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  margin-bottom: 12px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  font-size: 0.8rem;
}

.divider {
  border: 0;
  border-top: 1px solid var(--border);
  margin: 16px 0;
}

@media (max-width: 640px) {
  .app-header {
    padding: 0 16px;
  }
  .app-main {
    padding: 16px;
  }
  .sync-text {
    display: none;
  }
  .btn-sync {
    padding: 8px;
  }
}
</style>
