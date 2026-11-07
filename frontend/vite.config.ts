import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base './': the build also works in a subfolder (for example https://example.org/energiewende/)
export default defineConfig({ base: './', plugins: [react()] })
