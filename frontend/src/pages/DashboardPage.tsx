import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import { tasksApi } from '../services/api'
import Loading from '../components/common/Loading'
import ProgressBar from '../components/common/ProgressBar'

interface Task {
  id: string
  location_type_name: string
  council: string
  status: string
  total_locations: number
  completed_locations: number
  completion_percentage: number
}

export default function DashboardPage() {
  const { user } = useAuthStore()
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState({
    assigned: 0,
    inProgress: 0,
    completed: 0,
    totalLocations: 0,
  })

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      const response = await tasksApi.getMyTasks()
      const taskList = response.data

      setTasks(taskList)
      
      // Calculate stats
      const assigned = taskList.filter((t: Task) => t.status === 'ready').length
      const inProgress = taskList.filter((t: Task) => t.status === 'in_progress').length
      const completed = taskList.filter((t: Task) => t.status === 'completed').length
      const totalLocations = taskList.reduce((sum: number, t: Task) => sum + t.completed_locations, 0)

      setStats({ assigned, inProgress, completed, totalLocations })
    } catch (error) {
      console.error('Failed to load tasks:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <Loading />

  return (
    <>
      <h1 className="govuk-heading-xl">Welcome, {user?.name}</h1>

      <div className="stats-grid">
        <div className="stat-card">
          <span className="stat-card__value">{stats.assigned}</span>
          <span className="stat-card__label">Tasks Assigned</span>
        </div>
        <div className="stat-card">
          <span className="stat-card__value">{stats.inProgress}</span>
          <span className="stat-card__label">In Progress</span>
        </div>
        <div className="stat-card">
          <span className="stat-card__value">{stats.completed}</span>
          <span className="stat-card__label">Completed</span>
        </div>
        <div className="stat-card">
          <span className="stat-card__value">{stats.totalLocations}</span>
          <span className="stat-card__label">Locations Labelled</span>
        </div>
      </div>

      <h2 className="govuk-heading-l">Your Tasks</h2>

      {tasks.length === 0 ? (
        <p className="govuk-body">No tasks have been assigned to you yet.</p>
      ) : (
        <div>
          {tasks
            .filter((task) => task.status !== 'completed')
            .map((task) => (
              <div key={task.id} className={`task-card task-card--${task.status}`}>
                <div className="govuk-grid-row">
                  <div className="govuk-grid-column-two-thirds">
                    <h3 className="govuk-heading-m govuk-!-margin-bottom-1">
                      {task.location_type_name}
                    </h3>
                    <p className="govuk-body govuk-!-margin-bottom-2">{task.council}</p>
                    <ProgressBar
                      value={task.completed_locations}
                      max={task.total_locations}
                    />
                  </div>
                  <div className="govuk-grid-column-one-third" style={{ textAlign: 'right' }}>
                    <p className="govuk-body-s govuk-!-margin-bottom-2">
                      Status: <strong>{task.status.replace('_', ' ')}</strong>
                    </p>
                    {task.status === 'ready' || task.status === 'in_progress' ? (
                      <Link
                        to={`/labelling/${task.id}`}
                        className="govuk-button"
                        data-module="govuk-button"
                      >
                        {task.status === 'in_progress' ? 'Continue' : 'Start'} Labelling
                      </Link>
                    ) : (
                      <span className="govuk-tag govuk-tag--yellow">
                        {task.status === 'downloading' ? 'Downloading images...' : 'Pending'}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
        </div>
      )}

      {tasks.filter((t) => t.status === 'completed').length > 0 && (
        <>
          <h2 className="govuk-heading-l govuk-!-margin-top-8">Completed Tasks</h2>
          <table className="govuk-table">
            <thead className="govuk-table__head">
              <tr className="govuk-table__row">
                <th className="govuk-table__header">Type</th>
                <th className="govuk-table__header">Council</th>
                <th className="govuk-table__header">Locations</th>
                <th className="govuk-table__header">Status</th>
              </tr>
            </thead>
            <tbody className="govuk-table__body">
              {tasks
                .filter((t) => t.status === 'completed')
                .map((task) => (
                  <tr key={task.id} className="govuk-table__row">
                    <td className="govuk-table__cell">{task.location_type_name}</td>
                    <td className="govuk-table__cell">{task.council}</td>
                    <td className="govuk-table__cell">{task.total_locations}</td>
                    <td className="govuk-table__cell">
                      <span className="govuk-tag govuk-tag--green">Completed</span>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </>
      )}
    </>
  )
}

