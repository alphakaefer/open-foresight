import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const data = (name: string) => JSON.parse(fs.readFileSync(path.join(process.cwd(), 'src', 'data', name), 'utf8'))
const a05 = data('trace-a05.json').trace
const a13 = data('trace-a13.json').trace
const sensitivity = data('sensitivity.json')
const prediction = data('prediction.json')

test('published outlook opens and year selection changes the data', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Possible worlds, one energy question.' })).toBeVisible()
  await expect(page.getByRole('heading', { name: /No probability change/ })).toBeVisible()
  await expect(page.locator('.regime-card .regime-bar')).toHaveAttribute('aria-label', /Much cheaper 6%/)

  await page.getByRole('group', { name: 'Select future year' }).getByRole('button', { name: '2040' }).click()
  await expect(page.getByRole('heading', { name: 'How the 2040 scenarios distribute' })).toBeVisible()
  await expect(page.locator('.regime-card .regime-bar')).toHaveAttribute('aria-label', /Much cheaper 13%/)
  await expect(page.locator('.scenario-card').filter({ hasText: 'Green Boom on Cost' })).toContainText('13%')
})

test('A05 what-if shows the checked explanation trace', async ({ page }, testInfo) => {
  await page.goto('/')
  await page.getByRole('group', { name: 'Choose a model scenario' }).getByRole('button', { name: /Oil stays high/ }).click()

  const explanation = page.locator('.explanation-card')
  const probability = a05.probabilities['2028']['S01']
  const signal = a05.signals[0]

  await expect(page.locator('.hypo-banner')).toContainText('HYPOTHETICAL / NOT A FORECAST')
  await expect(page.locator('.hypo-banner')).toContainText(a05.changed_indicators[0].text)
  await expect(explanation).toContainText('A05')
  await expect(explanation).toContainText(signal.drivers[0].name)
  await expect(explanation).toContainText(`${signal.boost_per_scenario.S01.toFixed(4)}x`)
  await expect(explanation.locator('.explain-result')).toContainText(`${probability.before}%`)
  await expect(explanation.locator('.explain-result')).toContainText(`${probability.after}%`)
  await expect(explanation).toContainText('checked engine trace at k = 0.15')
  await testInfo.attach('a05-explanation', { body: await explanation.screenshot(), contentType: 'image/png' })
})

test('A13 what-if, reset, and k sensitivity stay separate from published values', async ({ page }) => {
  await page.goto('/')
  const mode = page.getByRole('group', { name: 'Choose a model scenario' })
  await mode.getByRole('button', { name: /Oil eases/ }).click()

  const explanation = page.locator('.explanation-card')
  const probability = a13.probabilities['2028']['S01']
  await expect(page.locator('.hypo-banner')).toContainText('A13')
  await expect(explanation).toContainText(a13.changed_indicators[0].text)
  await expect(explanation.locator('.explain-result')).toContainText(`${probability.after}%`)
  await expect(page.locator('.regime-card .regime-bar')).toHaveAttribute('aria-label', /Much cheaper 6%/)

  await page.locator('.k-control').getByRole('button', { name: '0.30' }).click()
  const movement = sensitivity.summary.C.total_moved_pp_exact['0.3'].toFixed(2)
  await expect(page.locator('.sensitivity-grid .chart-card').first()).toContainText(movement)
  await expect(explanation).toContainText('checked engine trace at k = 0.15')
  await expect(page.locator('.regime-card .regime-bar')).toHaveAttribute('aria-label', /Much cheaper 6%/)

  await page.getByRole('button', { name: /Reset to published/ }).click()
  await expect(page.locator('.hypo-banner')).toHaveCount(0)
  await expect(explanation).toContainText('No new signal in this snapshot')
})

test('mobile view keeps the explanation controls available', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await page.getByRole('group', { name: 'Choose a model scenario' }).getByRole('button', { name: /Oil stays high/ }).click()
  await expect(page.locator('.hypo-banner')).toBeVisible()
  await expect(page.locator('.explanation-card')).toContainText('MODEL BOOST')
  await expect(page.locator('.explanation-card')).toContainText('Hypothetical')
})

test('forecast prototype scores and historical quarter match the new artifact', async ({ page }, testInfo) => {
  await page.goto('/#prediction')
  const section = page.locator('#prediction')
  await expect(section.getByRole('heading', { name: /Can the model anticipate/ })).toBeVisible()
  await expect(section).toContainText('PROTOTYPE / NOT PROOF')
  await expect(section.locator('.prediction-stat-grid')).toContainText(prediction.brier.model.toFixed(4))
  await expect(section.locator('.prediction-stat-grid')).toContainText(prediction.brier.baseline.toFixed(4))
  await expect(section.locator('.prediction-score')).toContainText(prediction.brier.prior_only.toFixed(4))

  const first = prediction.rows[0]
  await section.getByLabel('Forecast quarter').selectOption('0')
  await expect(section.locator('.prediction-detail-values')).toContainText(`${(first.model * 100).toFixed(1)}%`)
  await expect(section.locator('.prediction-outcome')).toContainText(first.outcome ? 'Production fell' : 'Production did not fall')
  await expect(section).toContainText(`through ${first.model_data_up_to}`)
  await testInfo.attach('forecast-check', { body: await section.screenshot(), contentType: 'image/png' })
})
