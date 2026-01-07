import { useEffect, useState } from 'react'
import { adminApi } from '../services/api'
import Loading from '../components/common/Loading'
import RAGStatus from '../components/common/RAGStatus'

interface LabelerPerformance {
  user_id: string
  name: string
  email: string
  total_locations_labelled: number
  total_tasks_completed: number
  average_speed_per_hour: number
  failure_rate: number
  hourly_rate: number | null
  cost_per_location: number | null
  total_time_hours: number
  speed_rag: 'green' | 'amber' | 'red'
  failure_rag: 'green' | 'amber' | 'red'
  overall_rag: 'green' | 'amber' | 'red'
}

interface PerformanceReport {
  labellers: LabelerPerformance[]
  total_locations_labelled: number
  total_tasks_completed: number
  average_speed: number
}

export default function PerformancePage() {
  const [loading, setLoading] = useState(true)
  const [report, setReport] = useState<PerformanceReport | null>(null)
  const [days, setDays] = useState(30)

  useEffect(() => {
    loadReport()
  }, [days])

  const loadReport = async () => {
    try {
      const response = await adminApi.getPerformance(days)
      setReport(response.data)
    } catch (error) {
      console.error('Failed to load performance report:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <Loading />

  return (
    <>
      <h1 className="govuk-heading-xl">Performance Report</h1>

      <div className="govuk-form-group">
        <label className="govuk-label" htmlFor="days">
          Time period
        </label>
        <select
          className="govuk-select"
          id="days"
          value={days}
          onChange={(e) => setDays(parseInt(e.target.value))}
        >
          <option value="7">Last 7 days</option>
          <option value="30">Last 30 days</option>
          <option value="90">Last 90 days</option>
          <option value="365">Last year</option>
        </select>
      </div>

      {report && (
        <>
          {/* Summary Stats */}
          <div className="stats-grid govuk-!-margin-bottom-6">
            <div className="stat-card">
              <span className="stat-card__value">{report.total_locations_labelled.toLocaleString()}</span>
              <span className="stat-card__label">Total Locations Labelled</span>
            </div>
            <div className="stat-card">
              <span className="stat-card__value">{report.total_tasks_completed}</span>
              <span className="stat-card__label">Tasks Completed</span>
            </div>
            <div className="stat-card">
              <span className="stat-card__value">{report.average_speed}</span>
              <span className="stat-card__label">Avg Speed (loc/hr)</span>
            </div>
            <div className="stat-card">
              <span className="stat-card__value">{report.labellers.length}</span>
              <span className="stat-card__label">Active Labellers</span>
            </div>
          </div>

          {/* Labeller Table */}
          <h2 className="govuk-heading-l">Labeller Performance</h2>

          <table className="govuk-table">
            <thead className="govuk-table__head">
              <tr className="govuk-table__row">
                <th className="govuk-table__header">Status</th>
                <th className="govuk-table__header">Labeller</th>
                <th className="govuk-table__header">Locations</th>
                <th className="govuk-table__header">Tasks</th>
                <th className="govuk-table__header">Speed</th>
                <th className="govuk-table__header">Failure Rate</th>
                <th className="govuk-table__header">Hours</th>
                <th className="govuk-table__header">Cost/Loc</th>
              </tr>
            </thead>
            <tbody className="govuk-table__body">
              {report.labellers.map((labeller) => (
                <tr key={labeller.user_id} className="govuk-table__row">
                  <td className="govuk-table__cell">
                    <RAGStatus status={labeller.overall_rag} />
                  </td>
                  <td className="govuk-table__cell">
                    <strong>{labeller.name}</strong>
                    <br />
                    <span className="govuk-body-s">{labeller.email}</span>
                  </td>
                  <td className="govuk-table__cell">
                    {labeller.total_locations_labelled.toLocaleString()}
                  </td>
                  <td className="govuk-table__cell">{labeller.total_tasks_completed}</td>
                  <td className="govuk-table__cell">
                    <RAGStatus status={labeller.speed_rag} label={`${labeller.average_speed_per_hour}/hr`} />
                  </td>
                  <td className="govuk-table__cell">
                    <RAGStatus
                      status={labeller.failure_rag}
                      label={`${(labeller.failure_rate * 100).toFixed(1)}%`}
                    />
                  </td>
                  <td className="govuk-table__cell">{labeller.total_time_hours.toFixed(1)}</td>
                  <td className="govuk-table__cell">
                    {labeller.cost_per_location !== null ? `£${labeller.cost_per_location.toFixed(2)}` : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {report.labellers.length === 0 && (
            <p className="govuk-body">No labelling activity in the selected period.</p>
          )}

          {/* RAG Legend */}
          <details className="govuk-details govuk-!-margin-top-6">
            <summary className="govuk-details__summary">
              <span className="govuk-details__summary-text">RAG Status Thresholds</span>
            </summary>
            <div className="govuk-details__text">
              <table className="govuk-table">
                <thead className="govuk-table__head">
                  <tr className="govuk-table__row">
                    <th className="govuk-table__header">Metric</th>
                    <th className="govuk-table__header">Green</th>
                    <th className="govuk-table__header">Amber</th>
                    <th className="govuk-table__header">Red</th>
                  </tr>
                </thead>
                <tbody className="govuk-table__body">
                  <tr className="govuk-table__row">
                    <td className="govuk-table__cell">Speed</td>
                    <td className="govuk-table__cell">≥20 loc/hr</td>
                    <td className="govuk-table__cell">10-20 loc/hr</td>
                    <td className="govuk-table__cell">&lt;10 loc/hr</td>
                  </tr>
                  <tr className="govuk-table__row">
                    <td className="govuk-table__cell">Failure Rate</td>
                    <td className="govuk-table__cell">≤5%</td>
                    <td className="govuk-table__cell">5-15%</td>
                    <td className="govuk-table__cell">&gt;15%</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </>
  )
}

