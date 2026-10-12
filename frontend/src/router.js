import { createRouter, createWebHistory } from 'vue-router'
import FolderView from './views/FolderView.vue'
import PlayerView from './views/PlayerView.vue'

const routes = [
  { path: '/', redirect: '/folder/root' },
  { path: '/folder/:id', name: 'folder', component: FolderView, props: true },
  { path: '/watch/:id', name: 'player', component: PlayerView, props: true },
  { path: '/:pathMatch(.*)*', redirect: '/folder/root' },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  },
})
