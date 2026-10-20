import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  // Backend providers and test artifacts can change while a research session
  // is open. Only frontend changes should trigger a development page reload.
  server: {
    watch: { ignored: ['**/backend/**', '**/docs/**', '**/tests/**', '**/test-results/**', '**/playwright-report/**', '**/.phase*.local/**', '**/.pytest-tmp/**'] },
  },
})
