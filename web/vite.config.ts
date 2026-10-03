import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // GitHub Pages project site lives at /research-bot/
  base: process.env.GITHUB_ACTIONS ? '/research-bot/' : '/',
  server: {
    port: 5173,
  },
})
