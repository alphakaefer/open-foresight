/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Optional legal links for a hosted copy, set at build time (e.g. in .env.production.local). */
  readonly VITE_IMPRINT_URL?: string
  readonly VITE_PRIVACY_URL?: string
}
