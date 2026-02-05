import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { tasksApi, labellingApi, commentsApi } from '../services/api'
import Loading from '../components/common/Loading'

interface Task {
  id: string
  name: string
  council: string
  total_locations: number
  completed_locations: number
  failed_locations: number
  status: string
  assignee_name?: string
}

interface LocationItem {
  id: string
  identifier: string
  latitude: number
  longitude: number
  has_label: boolean
  label_status: string | null
  road_name: string | null
  locality: string | null
  town: string | null
  nptg_locality_name: string | null
}

interface CommentSummary {
  total_comments: number
  unresolved_feedback: number
  open_questions: number
  labels_with_comments: number
}

export default function QualityControlPage() {
  const navigate = useNavigate()
  
  const [loading, setLoading] = useState(true)
  const [tasks, setTasks] = useState<Task[]>([])
  const [selectedTask, setSelectedTask] = useState<Task | null>(null)
  const [locations, setLocations] = useState<LocationItem[]>([])
  const [locationsPage, setLocationsPage] = useState(1)
  const [totalLocations, setTotalLocations] = useState(0)
  const [filter, setFilter] = useState<'all' | 'labelled' | 'unlabelled'>('all')
  const [commentSummary, setCommentSummary] = useState<CommentSummary | null>(null)
  const [loadingLocations, setLoadingLocations] = useState(false)
  const pageSize = 40

  useEffect(() => {
    loadTasks()
  }, [])

  useEffect(() => {
    if (selectedTask) {
      loadLocations()
      loadCommentSummary()
    }
  }, [selectedTask, locationsPage])

  const loadTasks = async () => {
    try {
      // Use getAllTasks for managers to see all assigned tasks
      const response = await tasksApi.getAllTasks({ page: 1, page_size: 500 })
      const allTasks = response.data.tasks || []
      // Filter to show only tasks that have been assigned (not pending/unassigned)
      setTasks(allTasks.filter((t: Task) => t.assignee_name && ['assigned', 'in_progress', 'completed'].includes(t.status)))
    } catch (error) {
      console.error('Failed to load tasks:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadLocations = async () => {
    if (!selectedTask) return
    setLoadingLocations(true)
    try {
      const response = await labellingApi.getTaskLocations(selectedTask.id, locationsPage, pageSize)
      setLocations(response.data.locations || [])
      setTotalLocations(response.data.total || 0)
    } catch (error) {
      console.error('Failed to load locations:', error)
    } finally {
      setLoadingLocations(false)
    }
  }

  const loadCommentSummary = async () => {
    if (!selectedTask) return
    try {
      const response = await commentsApi.getTaskCommentsSummary(selectedTask.id)
      setCommentSummary(response.data)
    } catch (error) {
      console.error('Failed to load comment summary:', error)
    }
  }

  const goToLocation = async (locationId: string) => {
    if (!selectedTask) return
    try {
      const response = await labellingApi.getLocationIndexById(selectedTask.id, locationId)
      if (response.data.found) {
        navigate(`/quality-control/${selectedTask.id}/location/${response.data.index}`)
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

  if (loading) return <Loading />

  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
      <h1 className="govuk-heading-xl" style={{ marginBottom: '24px' }}>Quality Control</h1>

      <div style={{ display: 'grid', gridTemplateColumns: '350px 1fr', gap: '24px' }}>
        {/* Task List Sidebar */}
        <div style={{ 
          background: 'white', 
          borderRadius: '16px', 
          padding: '20px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
          height: 'fit-content',
          position: 'sticky',
          top: '20px'
        }}>
          <h2 className="govuk-heading-m" style={{ marginBottom: '16px' }}>Tasks</h2>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {tasks.length === 0 ? (
              <p className="govuk-body" style={{ color: '#6b7280' }}>No tasks available for review.</p>
            ) : (
              tasks.map((task) => (
                <div
                  key={task.id}
                  onClick={() => {
                    setSelectedTask(task)
                    setLocationsPage(1)
                    setFilter('all')
                  }}
                  style={{
                    padding: '12px 16px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    background: selectedTask?.id === task.id ? '#eff6ff' : '#f9fafb',
                    border: selectedTask?.id === task.id ? '2px solid #1d70b8' : '1px solid #e5e7eb',
                    transition: 'all 0.15s ease'
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: '14px', marginBottom: '4px' }}>
                    {task.name}
                  </div>
                  <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '8px' }}>
                    {task.council} • {task.assignee_name || 'Unassigned'}
                  </div>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <div style={{ 
                      flex: 1, 
                      height: '6px', 
                      background: '#e5e7eb', 
                      borderRadius: '3px',
                      overflow: 'hidden'
                    }}>
                      <div style={{ 
                        width: `${(task.completed_locations / task.total_locations) * 100}%`,
                        height: '100%',
                        background: task.status === 'completed' ? '#10b981' : '#3b82f6',
                        borderRadius: '3px'
                      }} />
                    </div>
                    <span style={{ fontSize: '11px', color: '#6b7280' }}>
                      {task.completed_locations}/{task.total_locations}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Main Content */}
        <div>
          {!selectedTask ? (
            <div style={{ 
              background: 'white', 
              borderRadius: '16px', 
              padding: '60px',
              textAlign: 'center',
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
            }}>
              <div style={{ fontSize: '48px', marginBottom: '16px' }}>📋</div>
              <h2 className="govuk-heading-m">Select a Task</h2>
              <p className="govuk-body" style={{ color: '#6b7280' }}>
                Choose a task from the list to review its labels
              </p>
            </div>
          ) : (
            <>
              {/* Task Header */}
              <div style={{ 
                background: 'white', 
                borderRadius: '16px', 
                padding: '24px',
                marginBottom: '24px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <h2 className="govuk-heading-l" style={{ marginBottom: '8px' }}>{selectedTask.name}</h2>
                    <p className="govuk-body-s" style={{ color: '#6b7280', marginBottom: 0 }}>
                      {selectedTask.council} • Assigned to: {selectedTask.assignee_name || 'Unassigned'}
                    </p>
                  </div>
                  <span style={{
                    padding: '6px 12px',
                    borderRadius: '20px',
                    fontSize: '12px',
                    fontWeight: 600,
                    background: selectedTask.status === 'completed' ? '#dcfce7' : selectedTask.status === 'in_progress' ? '#dbeafe' : '#fef3c7',
                    color: selectedTask.status === 'completed' ? '#166534' : selectedTask.status === 'in_progress' ? '#1e40af' : '#92400e'
                  }}>
                    {selectedTask.status.replace('_', ' ')}
                  </span>
                </div>

                {/* Stats Grid */}
                <div style={{ 
                  display: 'grid', 
                  gridTemplateColumns: 'repeat(4, 1fr)', 
                  gap: '16px',
                  marginTop: '20px'
                }}>
                  <div style={{ background: '#f0fdf4', borderRadius: '12px', padding: '16px', textAlign: 'center' }}>
                    <div style={{ fontSize: '28px', fontWeight: 700, color: '#166534' }}>{selectedTask.completed_locations}</div>
                    <div style={{ fontSize: '12px', color: '#6b7280' }}>Labelled</div>
                  </div>
                  <div style={{ background: '#fefce8', borderRadius: '12px', padding: '16px', textAlign: 'center' }}>
                    <div style={{ fontSize: '28px', fontWeight: 700, color: '#92400e' }}>{selectedTask.total_locations - selectedTask.completed_locations}</div>
                    <div style={{ fontSize: '12px', color: '#6b7280' }}>Remaining</div>
                  </div>
                  <div style={{ background: '#fef2f2', borderRadius: '12px', padding: '16px', textAlign: 'center' }}>
                    <div style={{ fontSize: '28px', fontWeight: 700, color: '#991b1b' }}>{selectedTask.failed_locations || 0}</div>
                    <div style={{ fontSize: '12px', color: '#6b7280' }}>Unable to Label</div>
                  </div>
                  {commentSummary && (
                    <div style={{ background: '#eff6ff', borderRadius: '12px', padding: '16px', textAlign: 'center' }}>
                      <div style={{ fontSize: '28px', fontWeight: 700, color: '#1e40af' }}>{commentSummary.open_questions}</div>
                      <div style={{ fontSize: '12px', color: '#6b7280' }}>Open Questions</div>
                    </div>
                  )}
                </div>
              </div>

              {/* Filters */}
              <div style={{ 
                background: 'white', 
                borderRadius: '16px', 
                padding: '16px 24px',
                marginBottom: '24px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}>
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
                <span style={{ fontSize: '13px', color: '#6b7280' }}>
                  Showing {filteredLocations.length} of {locations.length} locations on this page
                </span>
              </div>

              {/* Locations Grid */}
              <div style={{ 
                background: 'white', 
                borderRadius: '16px', 
                padding: '24px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
              }}>
                {loadingLocations ? (
                  <Loading />
                ) : filteredLocations.length === 0 ? (
                  <p className="govuk-body" style={{ textAlign: 'center', color: '#6b7280', padding: '40px' }}>
                    No locations found with the selected filter.
                  </p>
                ) : (
                  <>
                    <div style={{ 
                      display: 'grid', 
                      gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', 
                      gap: '12px' 
                    }}>
                      {filteredLocations.map((loc) => (
                        <div
                          key={loc.id}
                          onClick={() => goToLocation(loc.id)}
                          style={{
                            background: loc.has_label ? '#f0fdf4' : '#fafafa',
                            border: loc.has_label ? '2px solid #10b981' : '1px solid #e5e7eb',
                            borderRadius: '10px',
                            padding: '14px',
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
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                            <span style={{ 
                              fontWeight: 600, 
                              fontSize: '13px',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              maxWidth: '130px'
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
                          {/* Show road name and locality if available */}
                          {(loc.road_name || loc.locality || loc.nptg_locality_name || loc.town) ? (
                            <div style={{ fontSize: '11px', color: '#374151', marginTop: '4px' }}>
                              {loc.road_name && <div style={{ fontWeight: 500 }}>{loc.road_name}</div>}
                              <div style={{ color: '#6b7280' }}>
                                {loc.locality || loc.nptg_locality_name || loc.town || ''}
                              </div>
                            </div>
                          ) : (
                            <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
                              {loc.latitude.toFixed(4)}, {loc.longitude.toFixed(4)}
                            </div>
                          )}
                          <div style={{ 
                            fontSize: '11px', 
                            color: loc.has_label ? '#10b981' : '#f59e0b', 
                            marginTop: '6px',
                            fontWeight: 500
                          }}>
                            {loc.has_label ? 'Review →' : 'Not labelled'}
                          </div>
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
                          onClick={() => setLocationsPage(p => Math.max(1, p - 1))}
                          disabled={locationsPage === 1}
                          style={{
                            padding: '8px 16px',
                            borderRadius: '8px',
                            border: '1px solid #d1d5db',
                            background: 'white',
                            cursor: locationsPage === 1 ? 'not-allowed' : 'pointer',
                            opacity: locationsPage === 1 ? 0.5 : 1
                          }}
                        >
                          ← Previous
                        </button>
                        <span style={{ color: '#6b7280', fontSize: '14px' }}>
                          Page {locationsPage} of {totalPages}
                        </span>
                        <button
                          onClick={() => setLocationsPage(p => Math.min(totalPages, p + 1))}
                          disabled={locationsPage === totalPages}
                          style={{
                            padding: '8px 16px',
                            borderRadius: '8px',
                            border: '1px solid #d1d5db',
                            background: 'white',
                            cursor: locationsPage === totalPages ? 'not-allowed' : 'pointer',
                            opacity: locationsPage === totalPages ? 0.5 : 1
                          }}
                        >
                          Next →
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
