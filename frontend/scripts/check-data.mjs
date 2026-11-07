import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'

const root = path.resolve('src/data')
const read = file => JSON.parse(fs.readFileSync(path.join(root, file), 'utf8'))
const briefing = read('briefing.json')
const sensitivity = read('sensitivity.json')
const prediction = read('prediction.json')
const traces = {
  A: read('trace-real.json'),
  B: read('trace-a05.json'),
  C: read('trace-a13.json'),
}

assert.equal(sensitivity.status, 'ok')
for (const key of ['gate1_case_A_equals_published', 'gate2_k0_equals_base', 'gate3_exact_path_consistent']) {
  assert.equal(sensitivity[key], true, key)
}

for (const [mode, file] of Object.entries(traces)) {
  const { run, trace } = file
  assert.ok(run.gates.every(gate => gate.passed), `${mode} trace gates`)
  assert.deepEqual(run.inputs_sha256, sensitivity.meta.inputs_sha256, `${mode} input hashes`)
  assert.equal(trace.meta.model_version, briefing.inputs.version)
  assert.equal(trace.meta.radar_date, briefing.inputs.radar_date)
  assert.equal(trace.meta.world_state_date, briefing.inputs.world_state_date)
  assert.equal(trace.meta.is_hypothetical, mode !== 'A')
  for (const horizon of briefing.domain.horizons) {
    const rounded = sensitivity.results[mode]['0.15'].rounded[horizon]
    assert.equal(Object.values(rounded).reduce((sum, value) => sum + value, 0), 100)
    for (const [scenarioId, value] of Object.entries(rounded)) {
      assert.equal(trace.probabilities[horizon][scenarioId].after, value, `${mode} ${horizon} ${scenarioId}`)
    }
    assert.equal(Object.values(trace.energy_price_mass[horizon]).reduce((sum, value) => sum + value.after, 0), 100)
  }
}

console.log('Bundled artifacts match: three modes, three horizons, model inputs, and probability totals.')

assert.equal(prediction.mode, 'engine')
assert.equal(prediction.n, prediction.rows.length)
assert.equal(prediction.n, 102)
for (const key of ['model', 'prior_only', 'baseline']) {
  const computed = prediction.rows.reduce((sum, row) => sum + (row[key] - row.outcome) ** 2, 0) / prediction.n
  assert.ok(Math.abs(computed - prediction.brier[key]) < 1e-12, `${key} Brier score`)
}
console.log('Forecast prototype data matches all 102 outcomes and three Brier scores.')
