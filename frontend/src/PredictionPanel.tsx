import { useState } from 'react'
import predictionJson from './data/prediction.json'
import './prediction.css'

type ForecastRow = {
  date: string
  outcome: 0 | 1
  model: number
  prior_only: number
  baseline: number
  baseline_n_known: number
  model_data_up_to: string
}
type Prediction = {
  mode: string
  limits: string[]
  brier: { model: number; prior_only: number; baseline: number }
  skill_vs_baseline: { model: number; prior_only: number }
  n: number
  repo_head: string
  rows: ForecastRow[]
}

const prediction = predictionJson as Prediction
const percent = (value: number) => `${(value * 100).toFixed(1)}%`
const score = (value: number) => value.toFixed(4)

function HistoryChart({ rows, selected }: { rows: ForecastRow[]; selected: number }) {
  const left = 44, top = 12, right = 740, bottom = 172
  const min = 0.25, max = 0.45
  const x = (index: number) => left + index * (right - left) / (rows.length - 1)
  const y = (value: number) => bottom - (value - min) * (bottom - top) / (max - min)
  const points = (key: 'model' | 'baseline') => rows.map((row, index) => `${x(index).toFixed(1)},${y(row[key]).toFixed(1)}`).join(' ')
  const chosen = rows[selected]
  return <div className="prediction-chart-wrap">
    <svg className="prediction-chart" viewBox="0 0 780 220" role="img" aria-label={`Historical quarterly forecast probabilities from ${rows[0].date} to ${rows[rows.length - 1].date}. Selected ${chosen.date}: model ${percent(chosen.model)}, historical baseline ${percent(chosen.baseline)}. The observed outcome was ${chosen.outcome ? 'a decline' : 'no decline'}.`}>
      {[0.25, 0.35, 0.45].map(value => <g key={value}><line x1={left} x2={right} y1={y(value)} y2={y(value)} stroke="#dfe9e0" /><text x="2" y={y(value) + 4} fill="#708579" fontSize="11">{Math.round(value * 100)}%</text></g>)}
      <polyline points={points('baseline')} fill="none" stroke="#9cb4a4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <polyline points={points('model')} fill="none" stroke="#bc6847" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      {rows.map((row, index) => row.outcome ? <line key={row.date} x1={x(index)} x2={x(index)} y1="190" y2="199" stroke="#c78461" strokeWidth="2" /> : null)}
      <line x1={x(selected)} x2={x(selected)} y1={top} y2="199" stroke="#294d42" strokeDasharray="4 4" />
      <circle cx={x(selected)} cy={y(chosen.model)} r="6" fill="#bc6847" stroke="white" strokeWidth="2" />
      <text x={left} y="217" fill="#708579" fontSize="11">2000</text>
      <text x={right - 29} y="217" fill="#708579" fontSize="11">2025</text>
    </svg>
    <div className="prediction-chart-legend"><span><i className="model-line" />Model forecast</span><span><i className="baseline-line" />Historical baseline</span><span><i className="outcome-mark" />Observed decline</span></div>
  </div>
}

export default function PredictionPanel() {
  const rows = prediction.rows
  const [selected, setSelected] = useState(rows.length - 1)
  const row = rows[selected]
  const declines = rows.reduce((total, item) => total + item.outcome, 0)
  const valid = prediction.mode === 'engine' && prediction.n === rows.length && rows.length > 1
  if (!valid) return <section id="prediction" className="section prediction-section"><h2>Forecast check unavailable</h2><p>The historical result did not pass its data checks.</p></section>

  return <section id="prediction" className="section prediction-section">
    <div className="section-top"><div><div className="section-number">04 / HISTORICAL FORECAST CHECK</div><h2>Can the model anticipate<br /><em>a measurable outcome?</em></h2><p>A prototype tests whether German manufacturing production fell 12 months after each quarterly forecast.</p></div><span className="prediction-warning">PROTOTYPE / NOT PROOF</span></div>

    <div className="prediction-stat-grid">
      <div className="prediction-stat"><span className="label">QUARTERLY FORECASTS</span><strong>{prediction.n}</strong><small>{rows[0].date} to {rows[rows.length - 1].date}</small></div>
      <div className="prediction-stat"><span className="label">ACTUAL DECLINES</span><strong>{declines}</strong><small>of {prediction.n} observed outcomes</small></div>
      <div className="prediction-stat highlight"><span className="label">MODEL BRIER SCORE</span><strong>{score(prediction.brier.model)}</strong><small>lower is better</small></div>
      <div className="prediction-stat"><span className="label">HISTORICAL BASELINE</span><strong>{score(prediction.brier.baseline)}</strong><small>Brier score for comparison</small></div>
    </div>

    <div className="prediction-grid">
      <div className="card prediction-history"><div className="card-head"><span className="label">FORECAST PROBABILITY OF A DECLINE</span><span className="badge">2000-2025</span></div><h3>How forecasts changed over time</h3><HistoryChart rows={rows} selected={selected} /><p className="small-note">The small marks below the chart show quarters whose manufacturing output was lower 12 months later. Historical results use data revised after those dates.</p></div>
      <div className="card prediction-detail"><span className="label">INSPECT A HISTORICAL FORECAST</span><label htmlFor="prediction-date">Forecast quarter</label><select id="prediction-date" value={selected} onChange={event => setSelected(Number(event.target.value))}>{rows.map((item, index) => <option key={item.date} value={index}>{item.date}</option>)}</select><div className="prediction-detail-values"><div><span>Model forecast</span><strong>{percent(row.model)}</strong></div><div><span>Prior only</span><strong>{percent(row.prior_only)}</strong></div><div><span>Historical baseline</span><strong>{percent(row.baseline)}</strong></div></div><div className={`prediction-outcome ${row.outcome ? 'decline' : ''}`}><span>12 months later</span><strong>{row.outcome ? 'Production fell' : 'Production did not fall'}</strong></div><p className="small-note">The model used indicator data through {row.model_data_up_to}, two months before the forecast quarter.</p></div>
    </div>

    <div className="prediction-bottom"><div className="prediction-score"><span className="label">BRIER SCORE COMPARISON</span><table><thead><tr><th scope="col">Forecaster</th><th scope="col">Brier</th><th scope="col">Vs. baseline</th></tr></thead><tbody><tr><th scope="row">Model with updates</th><td>{score(prediction.brier.model)}</td><td>+{prediction.skill_vs_baseline.model.toFixed(3)}</td></tr><tr><th scope="row">Prior only (38%)</th><td>{score(prediction.brier.prior_only)}</td><td>+{prediction.skill_vs_baseline.prior_only.toFixed(3)}</td></tr><tr><th scope="row">Historical baseline</th><td>{score(prediction.brier.baseline)}</td><td>0</td></tr></tbody></table><p>The model scored slightly better here. The update itself improved the Brier score by only {(prediction.brier.prior_only - prediction.brier.model).toFixed(4)} compared with the fixed prior.</p></div><div className="prediction-limits"><span className="label">WHY THIS IS NOT PROOF</span><ul><li>The model's starting probabilities were set in 2026 with knowledge of past crises.</li><li>World-scenario growth was mapped to German manufacturing decline as a judgment.</li><li>Overlapping 12-month windows and revised historical data limit what the small score difference can tell us.</li></ul><a href="https://github.com/alphakaefer/open-foresight/blob/develop/docs/analysis-tools.md" target="_blank" rel="noreferrer">Read the full method and limits</a></div></div>
  </section>
}
