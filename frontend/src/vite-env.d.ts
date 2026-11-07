/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Optional legal links for a hosted copy, set at build time (e.g. in .env.production.local). */
  readonly VITE_IMPRINT_URL?: string
  readonly VITE_PRIVACY_URL?: string
  /** Optional link to the map prototype (ui/), e.g. karten/ui/ */
  readonly VITE_MAPS_URL?: string
  /** Optional link to the what-if demo page (whatif/), e.g. whatif/ */
  readonly VITE_WHATIF_URL?: string
}
