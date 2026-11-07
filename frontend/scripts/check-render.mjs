import assert from 'node:assert/strict'
import React from 'react'
import { renderToString } from 'react-dom/server'
import { createServer } from 'vite'

const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
try {
  const { default: App } = await vite.ssrLoadModule('/src/App.tsx')
  const modes = ['A', 'B', 'C']
  const horizons = ['2028', '2032', '2040']
  const kValues = [0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5]
  for (const initialMode of modes) {
    for (const initialHorizon of horizons) {
      for (const initialK of kValues) {
        const html = renderToString(React.createElement(App, { initialMode, initialHorizon, initialK }))
        assert.match(html, /Possible worlds, one energy question/)
        assert.match(html, /What does the/)
        assert.match(html, /FORESIGHT/)
        assert.doesNotMatch(html, /STUDIO|DEMO|â|Â/)
        if (initialMode === 'A') assert.match(html, /No probability change/)
        else assert.match(html, /HYPOTHETICAL/)
      }
    }
  }
  console.log('Dashboard renders in all 63 mode, horizon, and k combinations.')
} finally {
  await vite.close()
}
