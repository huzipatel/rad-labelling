import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { labellingApi, tasksApi } from '../services/api'
import Loading from '../components/common/Loading'

interface LocationItem {
  id: string
  identifier: string
  latitude: number
  longitude: number
  has_label: boolean
  label_status: string | null
}

interface TaskInfo {
  id: string
  name: string
  council: string
  total_locations: number
  completed_locations: number
}

export default function LabellingGridPage() {
  const { taskId } = useParams<{ taskId: string }>()
  const navigate = useNavigate()
  
  const [loading, setLoading] = useState(true)
  const [locations, setLocations] = useState<LocationItem[]>([])
  const [task, setTask] = useState<TaskInfo | null>(null)
  const [page, setPage] = useState(1)
  const [totalLocations, setTotalLocations] = useState(0)
  const [filter, setFilter] = useState<'all' | 'labelled' | 'unlabelled'>('all')
  const pageSize = 50

  useEffect(() => {
    if (taskId) {
      loadTask()
      loadLocations()
    }
  }, [taskId, page])

  const loadTask = async () => {
    try {
      const response = await tasksApi.getTasks()
      const taskData = response.data.tasks?.find((t: any) => t.id === taskId)
      if (taskData) {
        setTask({
          id: taskData.id,
          name: taskData.name,
          council: taskData.council,
          total_locations: taskData.total_locations,
          completed_locations: taskData.completed_locations
        })
      }
    } catch (error) {
      console.error('Failed to load task:', error)
    }
  }

  const loadLocations = async () => {
    setLoading(true)
    try {
      const response = await labellingApi.getTaskLocations(taskId!, page, pageSize)
      setLocations(response.data.locations || [])
      setTotalLocations(response.data.total || 0)
    } catch (error) {
      console.error('Failed to load locations:', error)
    } finally {
      setLoading(false)
    }
  }

  const goToLocation = async (locationId: string) => {
    try {
      const response = await labellingApi.getLocationIndexById(taskId!, locationId)
      if (response.data.found) {
        navigate(`/labelling/${taskId}?index=${response.data.index}`)
      }
    } catch (error) {
      console.error('Failed to find location:', error)
    }
  }

  const filteredLocations = locations.filter(loc => {
    if (filter === 'labelled') return loc.has_label
    if (filter === 'unlabelled') return !loc.has_label
    return true
  })

  const totalPages = Math.ceil(totalLocations / pageSize)

  if (loading && page === 1) return <Loading />

  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ 
        background: 'white', 
        borderRadius: '16px', 
        padding: '24px', 
        marginBottom: '24px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h1 className="govuk-heading-l" style={{ marginBottom: '8px' }}>
              All Locations
            </h1>
            <p className="govuk-body-s" style={{ marginBottom: 0, color: '#6b7280' }}>
              {task?.name || 'Task'} • {task?.council || ''} • {totalLocations} locations
            </p>
          </div>
          <button
            onClick={() => navigate(`/labelling/${taskId}`)}
            className="govuk-button govuk-button--secondary"
            style={{ marginBottom: 0 }}
          >
            ← Back to Labelling
          </button>
        </div>

        {/* Stats */}
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: 'repeat(3, 1fr)', 
          gap: '16px',
          marginBottom: '16px'
        }}>
          <div style={{ 
            background: '#f0fdf4', 
            borderRadius: '12px', 
            padding: '16px', 
            textAlign: 'center',
            border: '1px solid #bbf7d0'
          }}>
            <div style={{ fontSize: '28px', fontWeight: 700, color: '#166534' }}>
              {task?.completed_locations || 0}
            </div>
            <div style={{ fontSize: '12px', color: '#6b7280', textTransform: 'uppercase' }}>Labelled</div>
          </div>
          <div style={{ 
            background: '#fefce8', 
            borderRadius: '12px', 
            padding: '16px', 
            textAlign: 'center',
            border: '1px solid #fde68a'
          }}>
            <div style={{ fontSize: '28px', fontWeight: 700, color: '#92400e' }}>
              {(task?.total_locations || 0) - (task?.completed_locations || 0)}
            </div>
            <div style={{ fontSize: '12px', color: '#6b7280', textTransform: 'uppercase' }}>Remaining</div>
          </div>
          <div style={{ 
            background: '#f8fafc', 
            borderRadius: '12px', 
            padding: '16px', 
            textAlign: 'center',
            border: '1px solid #e2e8f0'
          }}>
            <div style={{ fontSize: '28px', fontWeight: 700, color: '#475569' }}>
              {task?.total_locations || 0}
            </div>
            <div style={{ fontSize: '12px', color: '#6b7280', textTransform: 'uppercase' }}>Total</div>
          </div>
        </div>

        {/* Filter */}
        <div style={{ display: 'flex', gap: '8px' }}>
          {(['all', 'labelled', 'unlabelled'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              style={{
                padding: '8px 16px',
                borderRadius: '8px',
                border: filter === f ? '2px solid #1d70b8' : '1px solid #d1d5db',
                background: filter === f ? '#eff6ff' : 'white',
                color: filter === f ? '#1d70b8' : '#6b7280',
                fontWeight: 500,
                fontSize: '13px',
                cursor: 'pointer'
              }}
            >
              {f === 'all' ? 'All' : f === 'labelled' ? '✅ Labelled' : '⏳ Unlabelled'}
            </button>
          ))}
        </div>
      </div>

      {/* Grid */}
      <div style={{ 
        background: 'white', 
        borderRadius: '16px', 
        padding: '24px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
      }}>
        {loading ? (
          <Loading />
        ) : filteredLocations.length === 0 ? (
          <p className="govuk-body" style={{ textAlign: 'center', color: '#6b7280', padding: '40px' }}>
            No locations found with the selected filter.
          </p>
        ) : (
          <>
            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', 
              gap: '16px' 
            }}>
              {filteredLocations.map((loc) => (
                <div
                  key={loc.id}
                  onClick={() => goToLocation(loc.id)}
                  style={{
                    background: loc.has_label ? '#f0fdf4' : '#fafafa',
                    border: loc.has_label ? '2px solid #10b981' : '1px solid #e5e7eb',
                    borderRadius: '12px',
                    padding: '16px',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease'
                  }}
                  onMouseOver={(e) => {
                    e.currentTarget.style.transform = 'translateY(-2px)'
                    e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)'
                  }}
                  onMouseOut={(e) => {
                    e.currentTarget.style.transform = 'none'
                    e.currentTarget.style.boxShadow = 'none'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                    <span style={{ 
                      fontWeight: 600, 
                      fontSize: '14px',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      maxWidth: '150px'
                    }}>
                      {loc.identifier}
                    </span>
                    {loc.has_label && (
                      <span style={{
                        background: '#dcfce7',
                        color: '#166534',
                        fontSize: '10px',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        fontWeight: 600
                      }}>
                        ✓
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: '11px', color: '#6b7280' }}>
                    {loc.latitude.toFixed(4)}, {loc.longitude.toFixed(4)}
                  </div>
                  {loc.has_label && (
                    <div style={{ 
                      fontSize: '11px', 
                      color: '#10b981', 
                      marginTop: '8px',
                      fontWeight: 500
                    }}>
                      Click to review →
                    </div>
                  )}
                  {!loc.has_label && (
                    <div style={{ 
                      fontSize: '11px', 
                      color: '#f59e0b', 
                      marginTop: '8px',
                      fontWeight: 500
                    }}>
                      Click to label →
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div style={{ 
                display: 'flex', 
                justifyContent: 'center', 
                alignItems: 'center', 
                gap: '8px',
                marginTop: '24px',
                paddingTop: '24px',
                borderTop: '1px solid #e5e7eb'
              }}>
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  style={{
                    padding: '8px 16px',
                    borderRadius: '8px',
                    border: '1px solid #d1d5db',
                    background: 'white',
                    cursor: page === 1 ? 'not-allowed' : 'pointer',
                    opacity: page === 1 ? 0.5 : 1
                  }}
                >
                  ← Previous
                </button>
                <span style={{ color: '#6b7280', fontSize: '14px' }}>
                  Page {page} of {totalPages}
                </span>
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  style={{
                    padding: '8px 16px',
                    borderRadius: '8px',
                    border: '1px solid #d1d5db',
                    background: 'white',
                    cursor: page === totalPages ? 'not-allowed' : 'pointer',
                    opacity: page === totalPages ? 0.5 : 1
                  }}
                >
                  Next →
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
