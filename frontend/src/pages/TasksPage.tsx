import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { tasksApi } from '../services/api'
import Loading from '../components/common/Loading'
import ProgressBar from '../components/common/ProgressBar'

interface Task {
  id: string
  location_type_name: string
  council: string
  name: string | null
  group_field: string | null
  group_value: string | null
  status: string
  total_locations: number
  completed_locations: number
  failed_locations: number
  completion_percentage: number
  download_progress: number
  images_downloaded: number
  total_images: number
  assigned_at: string | null
  started_at: string | null
}

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    loadTasks()
  }, [])

  const loadTasks = async () => {
    try {
      const response = await tasksApi.getMyTasks()
      setTasks(response.data)
    } catch (error) {
      console.error('Failed to load tasks:', error)
    } finally {
      setLoading(false)
    }
  }

  const filteredTasks = tasks.filter((task) => {
    if (filter === 'all') return true
    return task.status === filter
  })

  const getStatusTag = (status: string) => {
    const colors: Record<string, string> = {
      pending: 'grey',
      downloading: 'yellow',
      ready: 'blue',
      in_progress: 'purple',
      completed: 'green',
    }
    return (
      <span className={`govuk-tag govuk-tag--${colors[status] || 'grey'}`}>
        {status.replace('_', ' ')}
      </span>
    )
  }

  const readyTasks = tasks.filter(t => t.status === 'ready' || t.status === 'in_progress').length
  const completedTasks = tasks.filter(t => t.status === 'completed').length

  if (loading) return <Loading />

  return (
    <>
      <div style={{ marginBottom: '32px' }}>
        <h1 className="govuk-heading-xl" style={{ marginBottom: '8px' }}>My Tasks</h1>
        <p className="govuk-body-l" style={{ color: '#6b7280', margin: 0 }}>
          Tasks assigned to you for labelling
        </p>
      </div>

      {/* Summary stats */}
      <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)', marginBottom: '32px' }}>
        <div className="stat-card">
          <span className="stat-card__value">{tasks.length}</span>
          <span className="stat-card__label">Total Tasks</span>
        </div>
        <div className="stat-card">
          <span className="stat-card__value" style={{ color: '#10b981' }}>{readyTasks}</span>
          <span className="stat-card__label">Ready to Label</span>
        </div>
        <div className="stat-card">
          <span className="stat-card__value" style={{ color: '#6366f1' }}>{completedTasks}</span>
          <span className="stat-card__label">Completed</span>
        </div>
        <div className="stat-card">
          <span className="stat-card__value">{tasks.reduce((sum, t) => sum + t.total_locations, 0).toLocaleString()}</span>
          <span className="stat-card__label">Total Locations</span>
        </div>
      </div>

      <div className="govuk-form-group" style={{ marginBottom: '24px' }}>
        <label className="govuk-label" htmlFor="filter">
          Filter by status
        </label>
        <select
          className="govuk-select"
          id="filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          style={{ minWidth: '200px' }}
        >
          <option value="all">All tasks ({tasks.length})</option>
          <option value="pending">Pending ({tasks.filter(t => t.status === 'pending').length})</option>
          <option value="downloading">Downloading ({tasks.filter(t => t.status === 'downloading').length})</option>
          <option value="ready">Ready ({tasks.filter(t => t.status === 'ready').length})</option>
          <option value="in_progress">In Progress ({tasks.filter(t => t.status === 'in_progress').length})</option>
          <option value="completed">Completed ({tasks.filter(t => t.status === 'completed').length})</option>
        </select>
      </div>

      {filteredTasks.length === 0 ? (
        <div style={{ 
          textAlign: 'center', 
          padding: '48px 24px', 
          background: '#f9fafb', 
          borderRadius: '12px' 
        }}>
          <span style={{ fontSize: '48px', display: 'block', marginBottom: '16px' }}>📋</span>
          <p className="govuk-body-l" style={{ marginBottom: '8px' }}>No tasks found</p>
          <p className="govuk-body" style={{ color: '#6b7280' }}>
            {filter === 'all' 
              ? "You don't have any tasks assigned yet." 
              : `No ${filter.replace('_', ' ')} tasks.`}
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {filteredTasks.map((task) => (
            <div 
              key={task.id}
              style={{
                background: 'white',
                border: '1px solid #e5e7eb',
                borderRadius: '12px',
                padding: '20px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
                <div>
                  <h2 className="govuk-heading-m" style={{ marginBottom: '4px' }}>
                    {task.name || task.group_value || task.council}
                  </h2>
                  <p className="govuk-body-s" style={{ color: '#6b7280', margin: 0 }}>
                    {task.location_type_name}
                  </p>
                </div>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  {getStatusTag(task.status)}
                </div>
              </div>

              {/* Progress bars */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px', marginBottom: '16px' }}>
                {/* Image download progress */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <span className="govuk-body-s" style={{ fontWeight: 500 }}>📷 Images</span>
                    <span className="govuk-body-s">{task.images_downloaded || 0} / {task.total_images || 0}</span>
                  </div>
                  <ProgressBar
                    value={task.images_downloaded || 0}
                    max={task.total_images || 1}
                    showLabel={false}
                    variant={task.download_progress >= 100 ? 'success' : (task.status === 'downloading' ? 'warning' : 'default')}
                  />
                </div>

                {/* Labelling progress */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <span className="govuk-body-s" style={{ fontWeight: 500 }}>🏷️ Labelling</span>
                    <span className="govuk-body-s">{task.completed_locations} / {task.total_locations}</span>
                  </div>
                  <ProgressBar
                    value={task.completed_locations}
                    max={task.total_locations}
                    showLabel={false}
                    variant={task.status === 'completed' ? 'success' : 'default'}
                  />
                </div>
              </div>

              {/* Status messages and action button */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  {task.status === 'pending' && (
                    <span className="govuk-body-s" style={{ color: '#9ca3af' }}>
                      ⏳ Waiting for image download to complete
                    </span>
                  )}
                  {task.status === 'downloading' && (
                    <span className="govuk-body-s" style={{ color: '#f59e0b' }}>
                      ⬇️ Downloading images from Google Street View...
                    </span>
                  )}
                  {task.status === 'ready' && (
                    <span className="govuk-body-s" style={{ color: '#10b981' }}>
                      ✅ Ready to start labelling!
                    </span>
                  )}
                  {task.status === 'in_progress' && task.started_at && (
                    <span className="govuk-body-s" style={{ color: '#6366f1' }}>
                      🏃 Started {new Date(task.started_at).toLocaleDateString()}
                    </span>
                  )}
                  {task.status === 'completed' && (
                    <span className="govuk-body-s" style={{ color: '#10b981' }}>
                      🎉 Task completed!
                    </span>
                  )}
                </div>

                <div>
                  {(task.status === 'ready' || task.status === 'in_progress') && (
                    <Link
                      to={`/labelling/${task.id}`}
                      className="govuk-button"
                      style={{ marginBottom: 0 }}
                    >
                      {task.status === 'in_progress' ? '▶️ Continue Labelling' : '🏁 Start Labelling'}
                    </Link>
                  )}
                  {task.status === 'downloading' && (
                    <button className="govuk-button govuk-button--disabled" disabled style={{ marginBottom: 0 }}>
                      ⏳ Downloading...
                    </button>
                  )}
                  {task.status === 'completed' && (
                    <Link
                      to={`/labelling/${task.id}`}
                      className="govuk-button govuk-button--secondary"
                      style={{ marginBottom: 0 }}
                    >
                      👀 Review Labels
                    </Link>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  )
}

