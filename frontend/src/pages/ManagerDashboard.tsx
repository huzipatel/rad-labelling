import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { tasksApi, spreadsheetsApi, usersApi, exportsApi } from '../services/api'
import Loading from '../components/common/Loading'
import ProgressBar from '../components/common/ProgressBar'
import Modal from '../components/common/Modal'

interface Task {
  id: string
  location_type_id: string
  location_type_name: string
  council: string
  group_field?: string
  group_value?: string
  name?: string
  status: string
  assigned_to: string | null
  assignee_name: string | null
  total_locations: number
  completed_locations: number
  failed_locations: number
  completion_percentage: number
  images_downloaded: number
  total_images: number
  download_progress: number
  created_at: string
  assigned_at: string | null
  started_at: string | null
  completed_at: string | null
}

interface Labeller {
  id: string
  name: string
  email: string
}

interface GroupableField {
  key: string
  label: string
  source: string
  distinct_values: number
  sample_values: string[]
}

interface TaskPreviewItem {
  group_value: string
  location_count: number
  already_exists: boolean
}

interface TaskCreationPreview {
  location_type_id: string
  location_type_name: string
  group_field: string
  group_field_label: string
  tasks_to_create: TaskPreviewItem[]
  total_tasks: number
  total_locations: number
  existing_tasks: number
  new_tasks: number
}

interface FilterField {
  key: string
  values: { value: string; count: number }[]
  distinct_count: number
}

interface FilterPreviewTask {
  task_id: string
  task_name: string
  total_locations: number
  locations_affected: number
  new_total: number
}

export default function ManagerDashboard() {
  const [loading, setLoading] = useState(true)
  const [tasks, setTasks] = useState<Task[]>([])
  const [labellers, setLabellers] = useState<Labeller[]>([])
  const [locationTypes, setLocationTypes] = useState<any[]>([])
  const [stats, setStats] = useState<any>(null)
  
  // Main dashboard tab
  const [mainTab, setMainTab] = useState<'tasks' | 'results'>('tasks')
  
  // Results tab state
  const [selectedExportTasks, setSelectedExportTasks] = useState<string[]>([])
  const [exportingBulk, setExportingBulk] = useState(false)
  const [exportProgress, setExportProgress] = useState<string>('')
  const [resultsPage, setResultsPage] = useState(1)
  const [resultsStatusFilter, setResultsStatusFilter] = useState('')
  const resultsPageSize = 20
  const [allTasks, setAllTasks] = useState<Task[]>([])
  const [loadingAllTasks, setLoadingAllTasks] = useState(false)
  
  const [selectedTasks, setSelectedTasks] = useState<string[]>([])
  const [assignModalOpen, setAssignModalOpen] = useState(false)
  const [selectedLabeller, setSelectedLabeller] = useState('')
  
  const [filterType, setFilterType] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterCouncil, setFilterCouncil] = useState('')
  const [filterAssignee, setFilterAssignee] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  
  // Task creation state
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [createStep, setCreateStep] = useState<'select' | 'preview'>('select')
  const [selectedLocationType, setSelectedLocationType] = useState('')
  const [groupableFields, setGroupableFields] = useState<GroupableField[]>([])
  const [selectedGroupField, setSelectedGroupField] = useState('')
  const [taskPreview, setTaskPreview] = useState<TaskCreationPreview | null>(null)
  const [selectedTaskValues, setSelectedTaskValues] = useState<string[]>([])
  const [loadingFields, setLoadingFields] = useState(false)
  const [loadingPreview, setLoadingPreview] = useState(false)
  const [creatingTasks, setCreatingTasks] = useState(false)
  
  // Download all images state
  const [downloadingAllImages, setDownloadingAllImages] = useState(false)
  
  // Task detail modal
  const [selectedTask, setSelectedTask] = useState<Task | null>(null)
  const [taskDetailOpen, setTaskDetailOpen] = useState(false)
  const [downloadingImages, setDownloadingImages] = useState(false)
  const [taskImages, setTaskImages] = useState<any>(null)
  const [imagesPage, setImagesPage] = useState(1)
  const [showImages, setShowImages] = useState(false)
  const [downloadLogs, setDownloadLogs] = useState<any[]>([])
  const [showLogs, setShowLogs] = useState(false)
  const [logsRefreshInterval, setLogsRefreshInterval] = useState<NodeJS.Timeout | null>(null)
  const [taskSummary, setTaskSummary] = useState<any>(null)
  const [loadingSummary, setLoadingSummary] = useState(false)
  const [taskDetailTab, setTaskDetailTab] = useState<'overview' | 'progress' | 'downloads' | 'export'>('overview')
  
  // Location filter state
  const [filterModalOpen, setFilterModalOpen] = useState(false)
  const [filterStep, setFilterStep] = useState<'select' | 'preview'>('select')
  const [filterLocationType, setFilterLocationType] = useState('')
  const [filterFields, setFilterFields] = useState<FilterField[]>([])
  const [selectedFilterField, setSelectedFilterField] = useState('')
  const [selectedFilterValue, setSelectedFilterValue] = useState('')
  const [filterPreview, setFilterPreview] = useState<{
    total_matching: number
    tasks_affected: FilterPreviewTask[]
    total_tasks_affected: number
  } | null>(null)
  const [loadingFilterFields, setLoadingFilterFields] = useState(false)
  const [loadingFilterPreview, setLoadingFilterPreview] = useState(false)
  const [applyingFilter, setApplyingFilter] = useState(false)
  
  // Sample task state
  const [sampleModalOpen, setSampleModalOpen] = useState(false)
  const [tasksWithImages, setTasksWithImages] = useState<Task[]>([])
  const [selectedSourceTask, setSelectedSourceTask] = useState('')
  const [sampleSize, setSampleSize] = useState(10)
  const [sampleName, setSampleName] = useState('')
  const [loadingTasksWithImages, setLoadingTasksWithImages] = useState(false)
  const [creatingSample, setCreatingSample] = useState(false)

  useEffect(() => {
    loadData()
  }, [filterType, filterStatus, filterCouncil, filterAssignee, page])

  // Load all tasks when switching to Results tab
  useEffect(() => {
    if (mainTab === 'results' && allTasks.length === 0) {
      loadAllTasks()
    }
  }, [mainTab])

  const loadAllTasks = async () => {
    setLoadingAllTasks(true)
    try {
      // Fetch all tasks with a large page size to get everything
      const response = await tasksApi.getAllTasks({
        page: 1,
        page_size: 1000, // Max allowed by backend
      })
      setAllTasks(response.data.tasks)
    } catch (error) {
      console.error('Failed to load all tasks:', error)
    } finally {
      setLoadingAllTasks(false)
    }
  }

  const loadData = async () => {
    // Load each API call separately to prevent one failure from blocking others
    try {
      const typesRes = await spreadsheetsApi.getLocationTypes()
      setLocationTypes(typesRes.data)
    } catch (error) {
      console.error('Failed to load location types:', error)
    }

    try {
      const labellersRes = await usersApi.getLabellers()
      setLabellers(labellersRes.data)
    } catch (error) {
      console.error('Failed to load labellers:', error)
    }

    try {
      const statsRes = await tasksApi.getStats(filterType || undefined)
      setStats(statsRes.data)
    } catch (error) {
      console.error('Failed to load stats:', error)
    }

    try {
      const tasksRes = await tasksApi.getAllTasks({
        page,
        page_size: 20,
        location_type_id: filterType || undefined,
        status: filterStatus || undefined,
        council: filterCouncil || undefined,
        assigned_to: filterAssignee || undefined,
      })
      // Sort tasks: downloading first, then by status priority, then by download progress
      const statusPriority: Record<string, number> = {
        'downloading': 0,
        'pending': 1,
        'ready': 2,
        'in_progress': 3,
        'completed': 4,
        'failed': 5,
      }
      const sortedTasks = [...tasksRes.data.tasks].sort((a, b) => {
        // First, sort by status priority
        const aPriority = statusPriority[a.status] ?? 99
        const bPriority = statusPriority[b.status] ?? 99
        if (aPriority !== bPriority) return aPriority - bPriority
        
        // Then by download progress (less downloaded first for pending/downloading)
        if (a.status === 'downloading' || a.status === 'pending') {
          return (a.download_progress || 0) - (b.download_progress || 0)
        }
        
        // For ready/in_progress, sort by completion percentage
        return (a.completion_percentage || 0) - (b.completion_percentage || 0)
      })
      setTasks(sortedTasks)
      setTotal(tasksRes.data.total)
    } catch (error) {
      console.error('Failed to load tasks:', error)
    }

    setLoading(false)
  }

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedTasks(tasks.map((t) => t.id))
    } else {
      setSelectedTasks([])
    }
  }

  const handleSelectTask = (taskId: string, checked: boolean) => {
    if (checked) {
      setSelectedTasks([...selectedTasks, taskId])
    } else {
      setSelectedTasks(selectedTasks.filter((id) => id !== taskId))
    }
  }

  const handleBulkAssign = async () => {
    if (!selectedLabeller || selectedTasks.length === 0) return

    try {
      await tasksApi.bulkAssign(selectedTasks, selectedLabeller)
      setAssignModalOpen(false)
      setSelectedTasks([])
      setSelectedLabeller('')
      loadData()
    } catch (error) {
      console.error('Failed to assign tasks:', error)
      alert('Failed to assign tasks')
    }
  }

  const handleDownloadAllImages = async () => {
    if (!confirm('This will start downloading images for all pending tasks. Continue?')) return
    
    setDownloadingAllImages(true)
    try {
      const response = await tasksApi.downloadAllImages()
      alert(`Started downloading images for ${response.data.tasks_queued} tasks`)
      loadData()
    } catch (error) {
      console.error('Failed to start downloads:', error)
      alert('Failed to start image downloads')
    } finally {
      setDownloadingAllImages(false)
    }
  }

  // Task creation handlers
  const handleOpenCreateModal = () => {
    setCreateModalOpen(true)
    setCreateStep('select')
    setSelectedLocationType('')
    setSelectedGroupField('')
    setGroupableFields([])
    setTaskPreview(null)
    setSelectedTaskValues([])
  }

  const handleLocationTypeChange = async (typeId: string) => {
    setSelectedLocationType(typeId)
    setSelectedGroupField('')
    setGroupableFields([])
    setTaskPreview(null)
    
    if (!typeId) return
    
    setLoadingFields(true)
    try {
      const response = await tasksApi.getGroupableFields(typeId)
      setGroupableFields(response.data)
    } catch (error) {
      console.error('Failed to load groupable fields:', error)
      alert('Failed to load groupable fields')
    } finally {
      setLoadingFields(false)
    }
  }

  const handlePreviewTasks = async () => {
    if (!selectedLocationType || !selectedGroupField) return
    
    setLoadingPreview(true)
    try {
      const response = await tasksApi.previewTaskCreation({
        location_type_id: selectedLocationType,
        group_field: selectedGroupField,
      })
      setTaskPreview(response.data)
      setSelectedTaskValues(
        response.data.tasks_to_create
          .filter((t: TaskPreviewItem) => !t.already_exists)
          .map((t: TaskPreviewItem) => t.group_value)
      )
      setCreateStep('preview')
    } catch (error) {
      console.error('Failed to preview tasks:', error)
      alert('Failed to preview task creation')
    } finally {
      setLoadingPreview(false)
    }
  }

  const handleToggleTaskValue = (value: string) => {
    setSelectedTaskValues(prev => 
      prev.includes(value)
        ? prev.filter(v => v !== value)
        : [...prev, value]
    )
  }

  const handleSelectAllNew = () => {
    if (!taskPreview) return
    setSelectedTaskValues(
      taskPreview.tasks_to_create
        .filter(t => !t.already_exists)
        .map(t => t.group_value)
    )
  }

  const handleDeselectAll = () => {
    setSelectedTaskValues([])
  }

  const handleCreateTasks = async () => {
    if (!selectedLocationType || !selectedGroupField || selectedTaskValues.length === 0) return
    
    setCreatingTasks(true)
    try {
      const response = await tasksApi.createTasksFromField({
        location_type_id: selectedLocationType,
        group_field: selectedGroupField,
        selected_values: selectedTaskValues,
      })
      alert(response.data.message)
      setCreateModalOpen(false)
      loadData()
    } catch (error) {
      console.error('Failed to create tasks:', error)
      alert('Failed to create tasks')
    } finally {
      setCreatingTasks(false)
    }
  }

  const handleDeleteSelectedTasks = async () => {
    if (selectedTasks.length === 0) return
    
    if (!confirm(`Are you sure you want to delete ${selectedTasks.length} task(s)?`)) return
    
    try {
      const response = await tasksApi.bulkDeleteTasks(selectedTasks)
      alert(response.data.message)
      setSelectedTasks([])
      loadData()
    } catch (error: any) {
      console.error('Failed to delete tasks:', error)
      alert(error.response?.data?.detail || 'Failed to delete tasks')
    }
  }

  // Location filter handlers
  const handleOpenFilterModal = () => {
    setFilterModalOpen(true)
    setFilterStep('select')
    setFilterLocationType('')
    setFilterFields([])
    setSelectedFilterField('')
    setSelectedFilterValue('')
    setFilterPreview(null)
  }

  const handleFilterLocationTypeChange = async (typeId: string) => {
    setFilterLocationType(typeId)
    setSelectedFilterField('')
    setSelectedFilterValue('')
    setFilterFields([])
    setFilterPreview(null)
    
    if (!typeId) return
    
    setLoadingFilterFields(true)
    try {
      const response = await tasksApi.getLocationFilterFields(typeId)
      setFilterFields(response.data.fields)
    } catch (error) {
      console.error('Failed to load filter fields:', error)
      alert('Failed to load filter fields')
    } finally {
      setLoadingFilterFields(false)
    }
  }

  const handlePreviewFilter = async () => {
    if (!filterLocationType || !selectedFilterField || !selectedFilterValue) return
    
    setLoadingFilterPreview(true)
    try {
      const response = await tasksApi.previewLocationFilter({
        location_type_id: filterLocationType,
        filter_field: selectedFilterField,
        filter_value: selectedFilterValue,
        action: 'preview'
      })
      setFilterPreview(response.data)
      setFilterStep('preview')
    } catch (error) {
      console.error('Failed to preview filter:', error)
      alert('Failed to preview filter')
    } finally {
      setLoadingFilterPreview(false)
    }
  }

  const handleApplyFilter = async () => {
    if (!filterLocationType || !selectedFilterField || !selectedFilterValue) return
    
    const confirmMsg = `Are you sure you want to PERMANENTLY REMOVE ${filterPreview?.total_matching || 0} locations where "${selectedFilterField}" = "${selectedFilterValue}"? This cannot be undone.`
    if (!confirm(confirmMsg)) return
    
    setApplyingFilter(true)
    try {
      const response = await tasksApi.applyLocationFilter({
        location_type_id: filterLocationType,
        filter_field: selectedFilterField,
        filter_value: selectedFilterValue,
        action: 'apply'
      })
      alert(response.data.message)
      setFilterModalOpen(false)
      loadData()
    } catch (error: any) {
      console.error('Failed to apply filter:', error)
      alert(error.response?.data?.detail || 'Failed to apply filter')
    } finally {
      setApplyingFilter(false)
    }
  }

  // Sample task handlers
  const handleOpenSampleModal = async () => {
    setSampleModalOpen(true)
    setSelectedSourceTask('')
    setSampleSize(10)
    setSampleName('')
    setLoadingTasksWithImages(true)
    
    try {
      const response = await tasksApi.getTasksWithImages()
      setTasksWithImages(response.data)
    } catch (error) {
      console.error('Failed to load tasks with images:', error)
      alert('Failed to load tasks with images')
    } finally {
      setLoadingTasksWithImages(false)
    }
  }

  const handleCreateSampleTask = async () => {
    if (!selectedSourceTask || sampleSize <= 0) return
    
    setCreatingSample(true)
    try {
      const response = await tasksApi.createSampleTask({
        source_task_id: selectedSourceTask,
        sample_size: sampleSize,
        sample_name: sampleName || undefined
      })
      alert(response.data.message)
      setSampleModalOpen(false)
      loadData()
    } catch (error: any) {
      console.error('Failed to create sample task:', error)
      const detail = error.response?.data?.detail
      const errorMsg = Array.isArray(detail) 
        ? detail.map((e: any) => e.msg || JSON.stringify(e)).join(', ') 
        : (detail || 'Failed to create sample task')
      alert(errorMsg)
    } finally {
      setCreatingSample(false)
    }
  }

  const getStatusTag = (status: string) => {
    const colors: Record<string, string> = {
      pending: 'grey',
      downloading: 'yellow',
      paused: 'orange',
      ready: 'blue',
      in_progress: 'purple',
      completed: 'green',
    }
    const labels: Record<string, string> = {
      pending: '⏳ Pending',
      downloading: '📥 Downloading',
      paused: '⏸️ Paused',
      ready: '✅ Ready',
      in_progress: '🏃 In Progress',
      completed: '✓ Completed',
    }
    return (
      <span className={`govuk-tag govuk-tag--${colors[status] || 'grey'}`}>
        {labels[status] || status.replace('_', ' ')}
      </span>
    )
  }

  const handleViewTaskDetails = async (task: Task) => {
    setSelectedTask(task)
    setTaskDetailOpen(true)
    setTaskDetailTab('overview')
    setShowImages(false)
    setTaskImages(null)
    setShowLogs(false)
    setDownloadLogs([])
    setTaskSummary(null)
    setShowSnapshots(false)
    setTaskSnapshots(null)
    
    // Clear any existing interval
    if (logsRefreshInterval) {
      clearInterval(logsRefreshInterval)
      setLogsRefreshInterval(null)
    }
    
    // Load task summary
    setLoadingSummary(true)
    try {
      const response = await exportsApi.getTaskSummary(task.id)
      setTaskSummary(response.data)
    } catch (error) {
      console.error('Failed to load task summary:', error)
    } finally {
      setLoadingSummary(false)
    }
  }

  const handleTriggerDownload = async () => {
    if (!selectedTask) return
    
    setDownloadingImages(true)
    try {
      await tasksApi.triggerImageDownload(selectedTask.id)
      alert('Image download started! Click "View Logs" to monitor progress.')
      loadData()
      // Auto-show logs after triggering
      handleViewLogs()
    } catch (error: any) {
      console.error('Failed to trigger download:', error)
      alert(error.response?.data?.detail || 'Failed to start image download')
    } finally {
      setDownloadingImages(false)
    }
  }

  const handleCancelDownload = async () => {
    if (!selectedTask) return
    
    if (!confirm('Are you sure you want to cancel the download? This will stop all ongoing downloads for this task.')) {
      return
    }
    
    try {
      await tasksApi.cancelDownload(selectedTask.id)
      alert('Download cancelled.')
      loadData()
      loadDownloadLogs()
    } catch (error: any) {
      console.error('Failed to cancel download:', error)
      alert(error.response?.data?.detail || 'Failed to cancel download')
    }
  }

  const handlePauseDownload = async () => {
    if (!selectedTask) return
    
    try {
      await tasksApi.pauseDownload(selectedTask.id)
      alert('Download paused. You can resume it later.')
      loadData()
      loadDownloadLogs()
    } catch (error: any) {
      console.error('Failed to pause download:', error)
      alert(error.response?.data?.detail || 'Failed to pause download')
    }
  }

  const handleResumeDownload = async () => {
    if (!selectedTask) return
    
    try {
      await tasksApi.resumeDownload(selectedTask.id)
      alert('Download resumed!')
      loadData()
      loadDownloadLogs()
    } catch (error: any) {
      console.error('Failed to resume download:', error)
      alert(error.response?.data?.detail || 'Failed to resume download')
    }
  }

  const handleRestartDownload = async (force: boolean = false) => {
    if (!selectedTask) return
    
    const message = force 
      ? 'This will DELETE all existing images and re-download everything. Are you sure?'
      : 'This will download any missing images. Continue?'
    
    if (!confirm(message)) return
    
    try {
      const response = await tasksApi.restartDownload(selectedTask.id, force)
      alert(force 
        ? `Download restarted. Deleted ${response.data.deleted_images} existing images.`
        : 'Download restarted for missing images.')
      loadData()
      loadDownloadLogs()
    } catch (error: any) {
      console.error('Failed to restart download:', error)
      alert(error.response?.data?.detail || 'Failed to restart download')
    }
  }

  const handleExportCsv = async (includeUnlabelled: boolean = true) => {
    if (!selectedTask) return
    
    try {
      const response = await exportsApi.exportTaskCsv(selectedTask.id, includeUnlabelled)
      
      // Create download link
      const blob = new Blob([response.data], { type: 'text/csv' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${selectedTask.name || selectedTask.group_value || 'task'}_${new Date().toISOString().split('T')[0]}.csv`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (error: any) {
      console.error('Failed to export CSV:', error)
      alert(error.response?.data?.detail || 'Failed to export CSV')
    }
  }

  const [taskSnapshots, setTaskSnapshots] = useState<any>(null)
  const [showSnapshots, setShowSnapshots] = useState(false)

  const handleViewSnapshots = async () => {
    if (!selectedTask) return
    
    try {
      const response = await exportsApi.getTaskSnapshots(selectedTask.id)
      setTaskSnapshots(response.data)
      setShowSnapshots(true)
      setShowImages(false)
      setShowLogs(false)
    } catch (error: any) {
      console.error('Failed to load snapshots:', error)
      alert(error.response?.data?.detail || 'Failed to load snapshots')
    }
  }

  const handleViewImages = async (page: number = 1) => {
    if (!selectedTask) return
    
    setShowImages(true)
    setShowLogs(false)
    setImagesPage(page)
    try {
      const response = await tasksApi.getTaskImages(selectedTask.id, page, 10)
      setTaskImages(response.data)
    } catch (error) {
      console.error('Failed to load images:', error)
      alert('Failed to load images')
    }
  }

  const handleViewLogs = async () => {
    if (!selectedTask) return
    
    setShowLogs(true)
    setShowImages(false)
    
    // Load logs initially
    await loadDownloadLogs()
    
    // Set up auto-refresh every 3 seconds
    const interval = setInterval(loadDownloadLogs, 3000)
    setLogsRefreshInterval(interval)
  }

  const loadDownloadLogs = async () => {
    if (!selectedTask) return
    
    try {
      const response = await tasksApi.getDownloadLogs(selectedTask.id)
      setDownloadLogs(response.data.logs || [])
    } catch (error) {
      console.error('Failed to load download logs:', error)
    }
  }

  const handleCloseLogs = () => {
    setShowLogs(false)
    if (logsRefreshInterval) {
      clearInterval(logsRefreshInterval)
      setLogsRefreshInterval(null)
    }
  }

  // Cleanup interval on unmount
  useEffect(() => {
    return () => {
      if (logsRefreshInterval) {
        clearInterval(logsRefreshInterval)
      }
    }
  }, [logsRefreshInterval])

  // Calculate aggregate image stats
  const totalImagesAcrossTasks = tasks.reduce((sum, t) => sum + (t.total_images || 0), 0)
  const downloadedImagesAcrossTasks = tasks.reduce((sum, t) => sum + (t.images_downloaded || 0), 0)
  const overallDownloadProgress = totalImagesAcrossTasks > 0 
    ? Math.round((downloadedImagesAcrossTasks / totalImagesAcrossTasks) * 100) 
    : 0

  if (loading) return <Loading />

  return (
    <>
      <h1 className="govuk-heading-xl">Manager Dashboard</h1>

      {/* Stats */}
      {stats && (
        <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(6, 1fr)' }}>
          <div className="stat-card">
            <span className="stat-card__value">{stats.total_tasks}</span>
            <span className="stat-card__label">Total Tasks</span>
          </div>
          <div className="stat-card">
            <span className="stat-card__value" style={{ color: '#f59e0b' }}>{stats.downloading || 0}</span>
            <span className="stat-card__label">Downloading</span>
          </div>
          <div className="stat-card">
            <span className="stat-card__value" style={{ color: '#3b82f6' }}>{stats.ready}</span>
            <span className="stat-card__label">Ready</span>
          </div>
          <div className="stat-card">
            <span className="stat-card__value" style={{ color: '#8b5cf6' }}>{stats.in_progress}</span>
            <span className="stat-card__label">In Progress</span>
          </div>
          <div className="stat-card">
            <span className="stat-card__value" style={{ color: '#10b981' }}>{stats.completed}</span>
            <span className="stat-card__label">Completed</span>
          </div>
          <div className="stat-card">
            <span className="stat-card__value" style={{ color: overallDownloadProgress === 100 ? '#10b981' : '#6b7280' }}>
              {overallDownloadProgress}%
            </span>
            <span className="stat-card__label">Images Downloaded</span>
            <div style={{ marginTop: '8px' }}>
              <ProgressBar 
                value={downloadedImagesAcrossTasks} 
                max={totalImagesAcrossTasks || 1} 
                showLabel={false}
                variant={overallDownloadProgress === 100 ? 'success' : 'default'}
              />
              <span style={{ fontSize: '11px', color: '#6b7280' }}>
                {downloadedImagesAcrossTasks.toLocaleString()} / {totalImagesAcrossTasks.toLocaleString()}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Main Tab Navigation */}
      <div style={{ 
        display: 'flex', 
        gap: '0', 
        marginBottom: '24px',
        borderBottom: '3px solid #e5e7eb'
      }}>
        <button
          onClick={() => setMainTab('tasks')}
          style={{
            padding: '16px 32px',
            background: mainTab === 'tasks' ? '#1d4ed8' : 'transparent',
            color: mainTab === 'tasks' ? 'white' : '#4b5563',
            border: 'none',
            borderRadius: '12px 12px 0 0',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: '16px',
            transition: 'all 0.15s ease',
            marginBottom: '-3px',
            borderBottom: mainTab === 'tasks' ? '3px solid #1d4ed8' : '3px solid transparent'
          }}
        >
          📋 Tasks Management
        </button>
        <button
          onClick={() => setMainTab('results')}
          style={{
            padding: '16px 32px',
            background: mainTab === 'results' ? '#059669' : 'transparent',
            color: mainTab === 'results' ? 'white' : '#4b5563',
            border: 'none',
            borderRadius: '12px 12px 0 0',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: '16px',
            transition: 'all 0.15s ease',
            marginBottom: '-3px',
            borderBottom: mainTab === 'results' ? '3px solid #059669' : '3px solid transparent'
          }}
        >
          📊 Results & Export
        </button>
      </div>

      {mainTab === 'tasks' && (
        <>
          {/* Quick Actions */}
          <div className="govuk-!-margin-bottom-6">
            <button 
              className="govuk-button govuk-!-margin-right-2"
              onClick={handleOpenCreateModal}
            >
              + Create Tasks
            </button>
            <button 
              className="govuk-button govuk-button--secondary govuk-!-margin-right-2"
              onClick={handleDownloadAllImages}
              disabled={downloadingAllImages}
            >
              {downloadingAllImages ? 'Starting Downloads...' : '⬇️ Download All Images'}
            </button>
            <button 
              className="govuk-button govuk-button--secondary govuk-!-margin-right-2"
              onClick={handleOpenSampleModal}
            >
              🎲 Create Sample Task
            </button>
            <button 
              className="govuk-button govuk-button--secondary govuk-!-margin-right-2"
              onClick={handleOpenFilterModal}
            >
              🔍 Filter Locations
            </button>
            <Link to="/upload" className="govuk-button govuk-button--secondary govuk-!-margin-right-2">
              Upload Data
            </Link>
            <Link to="/performance" className="govuk-button govuk-button--secondary govuk-!-margin-right-2">
              Performance Report
            </Link>
            <Link to="/exports" className="govuk-button govuk-button--secondary">
              Export Data
            </Link>
          </div>

      {/* Filters */}
      <div style={{ 
        background: 'white', 
        borderRadius: '12px', 
        padding: '20px',
        border: '1px solid #e5e7eb',
        marginBottom: '24px'
      }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
          <div className="govuk-form-group" style={{ marginBottom: 0 }}>
            <label className="govuk-label" htmlFor="filterType">
              Location Type
            </label>
            <select
              className="govuk-select"
              id="filterType"
              value={filterType}
              onChange={(e) => { setFilterType(e.target.value); setPage(1); }}
              style={{ width: '100%' }}
            >
              <option value="">All types</option>
              {locationTypes.map((type) => (
                <option key={type.id} value={type.id}>
                  {type.display_name}
                </option>
              ))}
            </select>
          </div>
          <div className="govuk-form-group" style={{ marginBottom: 0 }}>
            <label className="govuk-label" htmlFor="filterStatus">
              Status
            </label>
            <select
              className="govuk-select"
              id="filterStatus"
              value={filterStatus}
              onChange={(e) => { setFilterStatus(e.target.value); setPage(1); }}
              style={{ width: '100%' }}
            >
              <option value="">All statuses</option>
              <option value="pending">Pending</option>
              <option value="downloading">Downloading</option>
              <option value="ready">Ready</option>
              <option value="in_progress">In Progress</option>
              <option value="completed">Completed</option>
            </select>
          </div>
          <div className="govuk-form-group" style={{ marginBottom: 0 }}>
            <label className="govuk-label" htmlFor="filterAssignee">
              Assigned To
            </label>
            <select
              className="govuk-select"
              id="filterAssignee"
              value={filterAssignee}
              onChange={(e) => { setFilterAssignee(e.target.value); setPage(1); }}
              style={{ width: '100%' }}
            >
              <option value="">All assignees</option>
              <option value="unassigned">Unassigned</option>
              {labellers.map((labeller) => (
                <option key={labeller.id} value={labeller.id}>
                  {labeller.name}
                </option>
              ))}
            </select>
          </div>
          <div className="govuk-form-group" style={{ marginBottom: 0 }}>
            <label className="govuk-label" htmlFor="filterCouncil">
              Search
            </label>
            <input
              className="govuk-input"
              id="filterCouncil"
              type="text"
              value={filterCouncil}
              onChange={(e) => setFilterCouncil(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') setPage(1); }}
              placeholder="Search task name..."
              style={{ width: '100%' }}
            />
          </div>
        </div>
      </div>

      {/* Bulk Actions */}
      {selectedTasks.length > 0 && (
        <div className="govuk-inset-text" style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <span><strong>{selectedTasks.length}</strong> tasks selected.</span>
          <button
            className="govuk-button govuk-button--secondary"
            style={{ marginBottom: 0 }}
            onClick={() => setAssignModalOpen(true)}
          >
            Assign to labeller
          </button>
          <button
            className="govuk-button govuk-button--warning"
            style={{ marginBottom: 0 }}
            onClick={handleDeleteSelectedTasks}
          >
            Delete selected
          </button>
        </div>
      )}

      {/* Tasks Table */}
      <div style={{ background: 'white', borderRadius: '12px', border: '1px solid #e5e7eb', overflow: 'hidden' }}>
        <table className="govuk-table" style={{ marginBottom: 0 }}>
          <thead className="govuk-table__head">
            <tr className="govuk-table__row">
              <th className="govuk-table__header" style={{ width: '40px' }}>
                <input
                  type="checkbox"
                  checked={selectedTasks.length === tasks.length && tasks.length > 0}
                  onChange={(e) => handleSelectAll(e.target.checked)}
                />
              </th>
              <th className="govuk-table__header">Type</th>
              <th className="govuk-table__header">Task Name</th>
              <th className="govuk-table__header">Assigned To</th>
              <th className="govuk-table__header">Images</th>
              <th className="govuk-table__header">Labelling</th>
              <th className="govuk-table__header">Status</th>
            </tr>
          </thead>
          <tbody className="govuk-table__body">
            {tasks.length === 0 ? (
              <tr className="govuk-table__row">
                <td className="govuk-table__cell" colSpan={7} style={{ textAlign: 'center', padding: '32px', color: '#6b7280' }}>
                  No tasks found. Click "Create Tasks" to get started.
                </td>
              </tr>
            ) : (
              tasks.map((task) => (
                <tr 
                  key={task.id} 
                  className="govuk-table__row"
                  style={{ cursor: 'pointer' }}
                  onClick={() => handleViewTaskDetails(task)}
                >
                  <td className="govuk-table__cell" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selectedTasks.includes(task.id)}
                      onChange={(e) => handleSelectTask(task.id, e.target.checked)}
                    />
                  </td>
                  <td className="govuk-table__cell">{task.location_type_name}</td>
                  <td className="govuk-table__cell">
                    <strong>{task.name || task.group_value || task.council}</strong>
                    <br />
                    <span className="govuk-body-s" style={{ color: '#6b7280' }}>
                      {task.total_locations.toLocaleString()} locations
                    </span>
                  </td>
                  <td className="govuk-table__cell">
                    {task.assignee_name || (
                      <span style={{ color: '#9ca3af' }}>Unassigned</span>
                    )}
                  </td>
                  <td className="govuk-table__cell" style={{ width: '160px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <div style={{ flex: 1 }}>
                        <ProgressBar
                          value={task.images_downloaded || 0}
                          max={task.total_images || 1}
                          showLabel={false}
                          variant={task.status === 'downloading' ? 'warning' : (task.download_progress >= 100 ? 'success' : 'default')}
                        />
                      </div>
                      <span className="govuk-body-s" style={{ whiteSpace: 'nowrap', minWidth: '40px', textAlign: 'right' }}>
                        {Math.round(task.download_progress || 0)}%
                      </span>
                    </div>
                    <span className="govuk-body-s" style={{ color: '#6b7280', fontSize: '11px' }}>
                      {(task.images_downloaded || 0).toLocaleString()} / {(task.total_images || 0).toLocaleString()}
                    </span>
                    {task.status === 'downloading' && (
                      <span style={{ fontSize: '10px', color: '#f59e0b', display: 'block' }}>⏳ Downloading...</span>
                    )}
                  </td>
                  <td className="govuk-table__cell" style={{ width: '140px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <div style={{ flex: 1 }}>
                        <ProgressBar
                          value={task.completed_locations}
                          max={task.total_locations}
                          showLabel={false}
                          variant={task.completion_percentage >= 100 ? 'success' : 'default'}
                        />
                      </div>
                      <span className="govuk-body-s" style={{ whiteSpace: 'nowrap', minWidth: '35px', textAlign: 'right' }}>
                        {Math.round(task.completion_percentage || 0)}%
                      </span>
                    </div>
                    <span className="govuk-body-s" style={{ color: '#6b7280', fontSize: '11px' }}>
                      {task.completed_locations.toLocaleString()} / {task.total_locations.toLocaleString()} labelled
                    </span>
                  </td>
                  <td className="govuk-table__cell">{getStatusTag(task.status)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <nav className="govuk-pagination" aria-label="Pagination">
        <p className="govuk-body">
          Showing {(page - 1) * 20 + 1} to {Math.min(page * 20, total)} of {total} tasks
        </p>
        <div>
          <button
            className="govuk-button govuk-button--secondary govuk-!-margin-right-2"
            disabled={page === 1}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </button>
          <button
            className="govuk-button govuk-button--secondary"
            disabled={page * 20 >= total}
            onClick={() => setPage(page + 1)}
          >
            Next
          </button>
        </div>
      </nav>
        </>
      )}

      {/* Results Tab Content */}
      {mainTab === 'results' && (() => {
        // Filter tasks for results view - use allTasks instead of tasks
        const filteredResultsTasks = allTasks.filter(t => 
          !resultsStatusFilter || t.status === resultsStatusFilter
        )
        const totalResultsTasks = filteredResultsTasks.length
        const totalResultsPages = Math.ceil(totalResultsTasks / resultsPageSize)
        const paginatedResultsTasks = filteredResultsTasks.slice(
          (resultsPage - 1) * resultsPageSize,
          resultsPage * resultsPageSize
        )
        
        // Get all active tasks (for select all) - use allTasks
        const allActiveTasks = allTasks.filter(t => 
          t.status === 'in_progress' || t.status === 'ready' || t.status === 'completed' || t.status === 'downloading'
        )
        
        // Check if all visible tasks are selected
        const allVisibleSelected = paginatedResultsTasks.length > 0 && 
          paginatedResultsTasks.every(t => selectedExportTasks.includes(t.id))
        
        return (
        <div>
          {/* Results Header */}
          <div style={{ 
            background: 'linear-gradient(135deg, #059669 0%, #047857 100%)', 
            borderRadius: '16px', 
            padding: '24px',
            marginBottom: '24px',
            color: 'white'
          }}>
            <h2 className="govuk-heading-l" style={{ color: 'white', marginBottom: '8px' }}>
              📊 Labelling Results Dashboard
            </h2>
            <p className="govuk-body" style={{ color: 'rgba(255,255,255,0.9)', marginBottom: 0 }}>
              View progress of all labelling tasks and export results in bulk. Total tasks: <strong>{allTasks.length}</strong>
              {loadingAllTasks && <span> (Loading...)</span>}
            </p>
          </div>

          {/* Filters and Actions Bar */}
          <div style={{ 
            background: 'white', 
            borderRadius: '12px', 
            padding: '16px 20px',
            marginBottom: '16px',
            border: '1px solid #e5e7eb',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '12px'
          }}>
            <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
              <select 
                className="govuk-select"
                value={resultsStatusFilter}
                onChange={(e) => { setResultsStatusFilter(e.target.value); setResultsPage(1); }}
                style={{ marginBottom: 0, minWidth: '150px' }}
              >
                <option value="">All Statuses</option>
                <option value="pending">Pending</option>
                <option value="downloading">Downloading</option>
                <option value="paused">Paused</option>
                <option value="ready">Ready</option>
                <option value="in_progress">In Progress</option>
                <option value="completed">Completed</option>
              </select>
              <span className="govuk-body-s" style={{ color: '#6b7280' }}>
                Showing {totalResultsTasks} task{totalResultsTasks !== 1 ? 's' : ''}
              </span>
            </div>
            
            <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
              <span style={{ 
                background: selectedExportTasks.length > 0 ? '#ecfdf5' : '#f3f4f6',
                padding: '6px 12px',
                borderRadius: '6px',
                fontSize: '14px',
                fontWeight: 600,
                color: selectedExportTasks.length > 0 ? '#059669' : '#6b7280'
              }}>
                {selectedExportTasks.length} selected
              </span>
              <button
                className="govuk-button govuk-button--secondary"
                style={{ marginBottom: 0 }}
                onClick={() => {
                  // Toggle select all visible
                  if (allVisibleSelected) {
                    setSelectedExportTasks(selectedExportTasks.filter(id => 
                      !paginatedResultsTasks.find(t => t.id === id)
                    ))
                  } else {
                    const newSelection = [...new Set([...selectedExportTasks, ...paginatedResultsTasks.map(t => t.id)])]
                    setSelectedExportTasks(newSelection)
                  }
                }}
              >
                {allVisibleSelected ? 'Deselect Page' : 'Select Page'}
              </button>
              <button
                className="govuk-button"
                style={{ marginBottom: 0, background: '#059669' }}
                onClick={() => {
                  setSelectedExportTasks(allActiveTasks.map(t => t.id))
                }}
              >
                Select All Active ({allActiveTasks.length})
              </button>
              <button
                className="govuk-button govuk-button--secondary"
                style={{ marginBottom: 0 }}
                onClick={() => setSelectedExportTasks([])}
                disabled={selectedExportTasks.length === 0}
              >
                Clear
              </button>
              <button
                className="govuk-button govuk-button--secondary"
                style={{ marginBottom: 0 }}
                onClick={() => loadAllTasks()}
                disabled={loadingAllTasks}
              >
                {loadingAllTasks ? '⏳ Loading...' : '🔄 Refresh'}
              </button>
            </div>
          </div>

          {/* Tasks Table */}
          <div style={{ 
            background: 'white', 
            borderRadius: '16px', 
            padding: '0',
            marginBottom: '24px',
            border: '1px solid #e5e7eb',
            overflow: 'hidden'
          }}>
            <table className="govuk-table" style={{ marginBottom: 0 }}>
              <thead className="govuk-table__head" style={{ background: '#f8fafc' }}>
                <tr className="govuk-table__row">
                  <th className="govuk-table__header" style={{ width: '40px', padding: '12px' }}>
                    <input
                      type="checkbox"
                      checked={allVisibleSelected && paginatedResultsTasks.length > 0}
                      onChange={() => {
                        if (allVisibleSelected) {
                          setSelectedExportTasks(selectedExportTasks.filter(id => 
                            !paginatedResultsTasks.find(t => t.id === id)
                          ))
                        } else {
                          const newSelection = [...new Set([...selectedExportTasks, ...paginatedResultsTasks.map(t => t.id)])]
                          setSelectedExportTasks(newSelection)
                        }
                      }}
                      style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                    />
                  </th>
                  <th className="govuk-table__header">Task Name</th>
                  <th className="govuk-table__header">Type</th>
                  <th className="govuk-table__header">Status</th>
                  <th className="govuk-table__header">Labelling Progress</th>
                  <th className="govuk-table__header">Images</th>
                  <th className="govuk-table__header">Assignee</th>
                </tr>
              </thead>
              <tbody className="govuk-table__body">
                {loadingAllTasks ? (
                  <tr className="govuk-table__row">
                    <td className="govuk-table__cell" colSpan={7} style={{ textAlign: 'center', padding: '40px', color: '#6b7280' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '12px' }}>
                        <span style={{ fontSize: '24px' }}>⏳</span>
                        <span>Loading all tasks...</span>
                      </div>
                    </td>
                  </tr>
                ) : paginatedResultsTasks.length === 0 ? (
                  <tr className="govuk-table__row">
                    <td className="govuk-table__cell" colSpan={7} style={{ textAlign: 'center', padding: '40px', color: '#6b7280' }}>
                      No tasks found
                    </td>
                  </tr>
                ) : (
                  paginatedResultsTasks.map((task) => {
                    const isSelected = selectedExportTasks.includes(task.id)
                    return (
                      <tr 
                        key={task.id} 
                        className="govuk-table__row"
                        onClick={() => {
                          if (isSelected) {
                            setSelectedExportTasks(selectedExportTasks.filter(id => id !== task.id))
                          } else {
                            setSelectedExportTasks([...selectedExportTasks, task.id])
                          }
                        }}
                        style={{ 
                          cursor: 'pointer',
                          background: isSelected ? '#ecfdf5' : 'transparent',
                          transition: 'background 0.15s ease'
                        }}
                      >
                        <td className="govuk-table__cell" style={{ padding: '12px' }} onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => {
                              if (isSelected) {
                                setSelectedExportTasks(selectedExportTasks.filter(id => id !== task.id))
                              } else {
                                setSelectedExportTasks([...selectedExportTasks, task.id])
                              }
                            }}
                            style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                          />
                        </td>
                        <td className="govuk-table__cell">
                          <div>
                            <strong>{task.name || task.group_value || task.council}</strong>
                            {task.group_field && (
                              <div style={{ fontSize: '12px', color: '#6b7280' }}>
                                {task.group_field}: {task.group_value}
                              </div>
                            )}
                          </div>
                        </td>
                        <td className="govuk-table__cell" style={{ fontSize: '13px' }}>
                          {task.location_type_name}
                        </td>
                        <td className="govuk-table__cell">
                          {getStatusTag(task.status)}
                        </td>
                        <td className="govuk-table__cell">
                          <div style={{ minWidth: '150px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                              <span style={{ fontWeight: 600, color: task.completion_percentage >= 100 ? '#10b981' : '#4b5563' }}>
                                {task.completed_locations} / {task.total_locations}
                              </span>
                              <span style={{ color: '#6b7280' }}>
                                {Math.round(task.completion_percentage || 0)}%
                              </span>
                            </div>
                            <ProgressBar
                              value={task.completed_locations || 0}
                              max={task.total_locations || 1}
                              showLabel={false}
                              variant={task.completion_percentage >= 100 ? 'success' : 'default'}
                            />
                          </div>
                        </td>
                        <td className="govuk-table__cell">
                          <div style={{ minWidth: '120px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                              <span style={{ fontWeight: 600, color: task.download_progress >= 100 ? '#10b981' : '#3b82f6' }}>
                                {task.images_downloaded || 0} / {task.total_images || 0}
                              </span>
                            </div>
                            <ProgressBar
                              value={task.images_downloaded || 0}
                              max={task.total_images || 1}
                              showLabel={false}
                              variant={task.download_progress >= 100 ? 'success' : 'warning'}
                            />
                          </div>
                        </td>
                        <td className="govuk-table__cell" style={{ fontSize: '13px' }}>
                          {task.assignee_name || <span style={{ color: '#9ca3af' }}>Unassigned</span>}
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <nav className="govuk-pagination" aria-label="Results pagination" style={{ marginBottom: '100px' }}>
            <p className="govuk-body">
              Showing {((resultsPage - 1) * resultsPageSize) + 1} to {Math.min(resultsPage * resultsPageSize, totalResultsTasks)} of {totalResultsTasks} tasks
            </p>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                className="govuk-button govuk-button--secondary"
                onClick={() => setResultsPage(p => Math.max(1, p - 1))}
                disabled={resultsPage <= 1}
                style={{ marginBottom: 0 }}
              >
                Previous
              </button>
              <span style={{ 
                padding: '8px 16px', 
                background: '#f3f4f6', 
                borderRadius: '6px',
                display: 'flex',
                alignItems: 'center'
              }}>
                Page {resultsPage} of {totalResultsPages || 1}
              </span>
              <button
                className="govuk-button govuk-button--secondary"
                onClick={() => setResultsPage(p => Math.min(totalResultsPages, p + 1))}
                disabled={resultsPage >= totalResultsPages}
                style={{ marginBottom: 0 }}
              >
                Next
              </button>
            </div>
          </nav>

          {/* Export Actions - Sticky Footer */}
          {selectedExportTasks.length > 0 && (
            <div style={{ 
              position: 'fixed',
              bottom: '0',
              left: '0',
              right: '0',
              background: 'white', 
              padding: '20px 40px',
              boxShadow: '0 -4px 20px rgba(0,0,0,0.15)',
              borderTop: '3px solid #10b981',
              zIndex: 1000
            }}>
              <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <h3 className="govuk-heading-s" style={{ marginBottom: '4px' }}>
                    📦 Export {selectedExportTasks.length} Task{selectedExportTasks.length > 1 ? 's' : ''}
                  </h3>
                  <p className="govuk-body-s" style={{ marginBottom: 0, color: '#6b7280' }}>
                    {exportProgress || 'Choose an export option below'}
                  </p>
                </div>
                <div style={{ display: 'flex', gap: '12px' }}>
                  <button
                    className="govuk-button govuk-button--secondary"
                    style={{ marginBottom: 0 }}
                    onClick={async () => {
                      setExportingBulk(true)
                      setExportProgress('Generating CSV files...')
                      try {
                        const response = await exportsApi.bulkExportCsv(selectedExportTasks)
                        const blob = new Blob([response.data], { type: 'application/zip' })
                        const url = window.URL.createObjectURL(blob)
                        const a = document.createElement('a')
                        a.href = url
                        a.download = `labelling_results_${new Date().toISOString().split('T')[0]}.zip`
                        document.body.appendChild(a)
                        a.click()
                        window.URL.revokeObjectURL(url)
                        document.body.removeChild(a)
                        setExportProgress('CSV export complete!')
                      } catch (error) {
                        console.error('Export failed:', error)
                        setExportProgress('Export failed. Please try again.')
                      } finally {
                        setExportingBulk(false)
                      }
                    }}
                    disabled={exportingBulk}
                  >
                    📊 Export Labels (CSV)
                  </button>
                  <button
                    className="govuk-button"
                    style={{ marginBottom: 0, background: '#059669' }}
                    onClick={async () => {
                      setExportingBulk(true)
                      setExportProgress('Preparing images and snapshots... This may take a while.')
                      try {
                        const response = await exportsApi.bulkExportAll(selectedExportTasks)
                        const blob = new Blob([response.data], { type: 'application/zip' })
                        const url = window.URL.createObjectURL(blob)
                        const a = document.createElement('a')
                        a.href = url
                        a.download = `labelling_complete_export_${new Date().toISOString().split('T')[0]}.zip`
                        document.body.appendChild(a)
                        a.click()
                        window.URL.revokeObjectURL(url)
                        document.body.removeChild(a)
                        setExportProgress('Full export complete!')
                      } catch (error) {
                        console.error('Export failed:', error)
                        setExportProgress('Export failed. Please try again.')
                      } finally {
                        setExportingBulk(false)
                      }
                    }}
                    disabled={exportingBulk}
                  >
                    {exportingBulk ? '⏳ Exporting...' : '📦 Export All (CSV + Images + Snapshots)'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
        )
      })()}

      {/* Assign Modal */}
      <Modal
        isOpen={assignModalOpen}
        onClose={() => setAssignModalOpen(false)}
        title="Assign Tasks"
      >
        <p className="govuk-body">
          Assign {selectedTasks.length} task(s) to a labeller:
        </p>
        <div className="govuk-form-group">
          <label className="govuk-label" htmlFor="labeller">
            Select labeller
          </label>
          <select
            className="govuk-select"
            id="labeller"
            value={selectedLabeller}
            onChange={(e) => setSelectedLabeller(e.target.value)}
          >
            <option value="">Choose a labeller</option>
            {labellers.map((labeller) => (
              <option key={labeller.id} value={labeller.id}>
                {labeller.name} ({labeller.email})
              </option>
            ))}
          </select>
        </div>
        <div className="govuk-button-group">
          <button className="govuk-button" onClick={handleBulkAssign} disabled={!selectedLabeller}>
            Assign Tasks
          </button>
          <button
            className="govuk-button govuk-button--secondary"
            onClick={() => setAssignModalOpen(false)}
          >
            Cancel
          </button>
        </div>
      </Modal>

      {/* Create Tasks Modal */}
      <Modal
        isOpen={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        title={createStep === 'select' ? 'Create Tasks' : 'Preview & Confirm'}
      >
        {createStep === 'select' ? (
          <>
            <p className="govuk-body">
              Create tasks by grouping locations based on a field. This is typically done by council.
            </p>
            
            <div className="govuk-form-group">
              <label className="govuk-label" htmlFor="locationType">
                1. Select Location Type
              </label>
              <select
                className="govuk-select"
                id="locationType"
                value={selectedLocationType}
                onChange={(e) => handleLocationTypeChange(e.target.value)}
              >
                <option value="">Choose a location type</option>
                {locationTypes.map((type) => (
                  <option key={type.id} value={type.id}>
                    {type.display_name} ({(type.location_count || type.total_locations || 0).toLocaleString()} locations)
                  </option>
                ))}
              </select>
            </div>

            {loadingFields && (
              <div className="govuk-inset-text">Loading available fields...</div>
            )}

            {selectedLocationType && groupableFields.length > 0 && (
              <div className="govuk-form-group">
                <label className="govuk-label" htmlFor="groupField">
                  2. Group tasks by
                </label>
                <select
                  className="govuk-select"
                  id="groupField"
                  value={selectedGroupField}
                  onChange={(e) => setSelectedGroupField(e.target.value)}
                >
                  <option value="">Choose a field to group by</option>
                  <optgroup label="Enhanced Fields">
                    {groupableFields.filter(f => f.source === 'enhanced').map((field) => (
                      <option key={field.key} value={field.key}>
                        {field.label} ({field.distinct_values} unique values)
                      </option>
                    ))}
                  </optgroup>
                  <optgroup label="Original CSV Fields">
                    {groupableFields.filter(f => f.source === 'original').map((field) => (
                      <option key={field.key} value={field.key}>
                        {field.label} ({field.distinct_values} unique values)
                      </option>
                    ))}
                  </optgroup>
                </select>
                {selectedGroupField && (
                  <div className="govuk-hint" style={{ marginTop: '8px' }}>
                    Sample values:{' '}
                    {groupableFields.find(f => f.key === selectedGroupField)?.sample_values.slice(0, 5).join(', ')}
                    {(groupableFields.find(f => f.key === selectedGroupField)?.sample_values.length || 0) > 5 && '...'}
                  </div>
                )}
              </div>
            )}

            {selectedLocationType && groupableFields.length === 0 && !loadingFields && (
              <div className="govuk-warning-text">
                <span className="govuk-warning-text__icon" aria-hidden="true">!</span>
                <strong className="govuk-warning-text__text">
                  No groupable fields found. Please enhance your data first to add council or other fields.
                </strong>
              </div>
            )}

            <div className="govuk-button-group" style={{ marginTop: '24px' }}>
              <button
                className="govuk-button"
                onClick={handlePreviewTasks}
                disabled={!selectedLocationType || !selectedGroupField || loadingPreview}
              >
                {loadingPreview ? 'Loading preview...' : 'Preview Tasks →'}
              </button>
              <button
                className="govuk-button govuk-button--secondary"
                onClick={() => setCreateModalOpen(false)}
              >
                Cancel
              </button>
            </div>
          </>
        ) : (
          <>
            {taskPreview && (
              <>
                <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)', marginBottom: '24px' }}>
                  <div className="stat-card">
                    <span className="stat-card__value">{taskPreview.total_tasks}</span>
                    <span className="stat-card__label">Total Groups</span>
                  </div>
                  <div className="stat-card">
                    <span className="stat-card__value" style={{ color: '#10b981' }}>{taskPreview.new_tasks}</span>
                    <span className="stat-card__label">New Tasks</span>
                  </div>
                  <div className="stat-card">
                    <span className="stat-card__value" style={{ color: '#f59e0b' }}>{taskPreview.existing_tasks}</span>
                    <span className="stat-card__label">Already Exist</span>
                  </div>
                </div>

                <p className="govuk-body">
                  Creating tasks for <strong>{taskPreview.location_type_name}</strong> grouped by <strong>{taskPreview.group_field_label}</strong>.
                </p>

                <div style={{ display: 'flex', gap: '12px', marginBottom: '16px' }}>
                  <button
                    className="govuk-link"
                    style={{ background: 'none', border: 'none', cursor: 'pointer' }}
                    onClick={handleSelectAllNew}
                  >
                    Select all new ({taskPreview.new_tasks})
                  </button>
                  <span style={{ color: '#d1d5db' }}>|</span>
                  <button
                    className="govuk-link"
                    style={{ background: 'none', border: 'none', cursor: 'pointer' }}
                    onClick={handleDeselectAll}
                  >
                    Deselect all
                  </button>
                </div>

                <div style={{ 
                  maxHeight: '300px', 
                  overflowY: 'auto', 
                  border: '1px solid #e5e7eb', 
                  borderRadius: '8px',
                  marginBottom: '24px'
                }}>
                  <table className="govuk-table" style={{ marginBottom: 0 }}>
                    <thead className="govuk-table__head" style={{ position: 'sticky', top: 0, background: 'white' }}>
                      <tr className="govuk-table__row">
                        <th className="govuk-table__header" style={{ width: '40px' }}></th>
                        <th className="govuk-table__header">{taskPreview.group_field_label}</th>
                        <th className="govuk-table__header" style={{ textAlign: 'right' }}>Locations</th>
                        <th className="govuk-table__header">Status</th>
                      </tr>
                    </thead>
                    <tbody className="govuk-table__body">
                      {taskPreview.tasks_to_create.map((task) => (
                        <tr 
                          key={task.group_value} 
                          className="govuk-table__row"
                          style={{ opacity: task.already_exists ? 0.5 : 1 }}
                        >
                          <td className="govuk-table__cell">
                            <input
                              type="checkbox"
                              checked={selectedTaskValues.includes(task.group_value)}
                              onChange={() => handleToggleTaskValue(task.group_value)}
                              disabled={task.already_exists}
                            />
                          </td>
                          <td className="govuk-table__cell">{task.group_value}</td>
                          <td className="govuk-table__cell" style={{ textAlign: 'right' }}>
                            {task.location_count.toLocaleString()}
                          </td>
                          <td className="govuk-table__cell">
                            {task.already_exists ? (
                              <span className="govuk-tag govuk-tag--yellow">Already exists</span>
                            ) : selectedTaskValues.includes(task.group_value) ? (
                              <span className="govuk-tag govuk-tag--green">Will create</span>
                            ) : (
                              <span className="govuk-tag govuk-tag--grey">Not selected</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <p className="govuk-body" style={{ fontWeight: 600 }}>
                  {selectedTaskValues.length} task(s) will be created covering{' '}
                  {taskPreview.tasks_to_create
                    .filter(t => selectedTaskValues.includes(t.group_value))
                    .reduce((sum, t) => sum + t.location_count, 0)
                    .toLocaleString()}{' '}
                  locations.
                </p>

                <div className="govuk-button-group">
                  <button
                    className="govuk-button"
                    onClick={handleCreateTasks}
                    disabled={selectedTaskValues.length === 0 || creatingTasks}
                  >
                    {creatingTasks ? 'Creating...' : `Create ${selectedTaskValues.length} Task(s)`}
                  </button>
                  <button
                    className="govuk-button govuk-button--secondary"
                    onClick={() => setCreateStep('select')}
                  >
                    ← Back
                  </button>
                  <button
                    className="govuk-button govuk-button--secondary"
                    onClick={() => setCreateModalOpen(false)}
                  >
                    Cancel
                  </button>
                </div>
              </>
            )}
          </>
        )}
      </Modal>

      {/* Filter Locations Modal */}
      <Modal
        isOpen={filterModalOpen}
        onClose={() => setFilterModalOpen(false)}
        title={filterStep === 'select' ? 'Filter Locations' : 'Confirm Removal'}
      >
        {filterStep === 'select' ? (
          <>
            <p className="govuk-body">
              Remove locations from your dataset based on a field value. For example, remove all locations where Status = "Deleted".
            </p>
            
            <div className="govuk-warning-text">
              <span className="govuk-warning-text__icon" aria-hidden="true">!</span>
              <strong className="govuk-warning-text__text">
                This will permanently delete matching locations from the database. Task counts will be updated automatically.
              </strong>
            </div>

            <div className="govuk-form-group">
              <label className="govuk-label" htmlFor="filterLocationType">
                1. Select Location Type
              </label>
              <select
                className="govuk-select"
                id="filterLocationType"
                value={filterLocationType}
                onChange={(e) => handleFilterLocationTypeChange(e.target.value)}
              >
                <option value="">Choose a location type</option>
                {locationTypes.map((type) => (
                  <option key={type.id} value={type.id}>
                    {type.display_name}
                  </option>
                ))}
              </select>
            </div>

            {loadingFilterFields && (
              <div className="govuk-inset-text">Loading available fields...</div>
            )}

            {filterLocationType && filterFields.length > 0 && (
              <>
                <div className="govuk-form-group">
                  <label className="govuk-label" htmlFor="filterField">
                    2. Select Field to Filter
                  </label>
                  <select
                    className="govuk-select"
                    id="filterField"
                    value={selectedFilterField}
                    onChange={(e) => {
                      setSelectedFilterField(e.target.value)
                      setSelectedFilterValue('')
                    }}
                  >
                    <option value="">Choose a field</option>
                    {filterFields.map((field) => (
                      <option key={field.key} value={field.key}>
                        {field.key} ({field.distinct_count} values)
                      </option>
                    ))}
                  </select>
                </div>

                {selectedFilterField && (
                  <div className="govuk-form-group">
                    <label className="govuk-label" htmlFor="filterValue">
                      3. Select Value to Remove
                    </label>
                    <select
                      className="govuk-select"
                      id="filterValue"
                      value={selectedFilterValue}
                      onChange={(e) => setSelectedFilterValue(e.target.value)}
                    >
                      <option value="">Choose a value</option>
                      {filterFields
                        .find(f => f.key === selectedFilterField)
                        ?.values.map((v) => (
                          <option key={v.value} value={v.value}>
                            {v.value} ({v.count.toLocaleString()} locations)
                          </option>
                        ))}
                    </select>
                  </div>
                )}
              </>
            )}

            <div className="govuk-button-group" style={{ marginTop: '24px' }}>
              <button
                className="govuk-button govuk-button--warning"
                onClick={handlePreviewFilter}
                disabled={!filterLocationType || !selectedFilterField || !selectedFilterValue || loadingFilterPreview}
              >
                {loadingFilterPreview ? 'Loading preview...' : 'Preview Removal →'}
              </button>
              <button
                className="govuk-button govuk-button--secondary"
                onClick={() => setFilterModalOpen(false)}
              >
                Cancel
              </button>
            </div>
          </>
        ) : (
          <>
            {filterPreview && (
              <>
                <div className="govuk-warning-text">
                  <span className="govuk-warning-text__icon" aria-hidden="true">!</span>
                  <strong className="govuk-warning-text__text">
                    You are about to permanently remove <strong>{filterPreview.total_matching.toLocaleString()}</strong> locations where <strong>{selectedFilterField}</strong> = "<strong>{selectedFilterValue}</strong>"
                  </strong>
                </div>

                <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', marginBottom: '24px' }}>
                  <div className="stat-card">
                    <span className="stat-card__value" style={{ color: '#dc2626' }}>{filterPreview.total_matching.toLocaleString()}</span>
                    <span className="stat-card__label">Locations to Remove</span>
                  </div>
                  <div className="stat-card">
                    <span className="stat-card__value" style={{ color: '#f59e0b' }}>{filterPreview.total_tasks_affected}</span>
                    <span className="stat-card__label">Tasks Affected</span>
                  </div>
                </div>

                {filterPreview.tasks_affected.length > 0 && (
                  <>
                    <h3 className="govuk-heading-s">Tasks that will be updated:</h3>
                    <div style={{ 
                      maxHeight: '250px', 
                      overflowY: 'auto', 
                      border: '1px solid #e5e7eb', 
                      borderRadius: '8px',
                      marginBottom: '24px'
                    }}>
                      <table className="govuk-table" style={{ marginBottom: 0 }}>
                        <thead className="govuk-table__head" style={{ position: 'sticky', top: 0, background: 'white' }}>
                          <tr className="govuk-table__row">
                            <th className="govuk-table__header">Task</th>
                            <th className="govuk-table__header" style={{ textAlign: 'right' }}>Current</th>
                            <th className="govuk-table__header" style={{ textAlign: 'right' }}>Removing</th>
                            <th className="govuk-table__header" style={{ textAlign: 'right' }}>New Total</th>
                          </tr>
                        </thead>
                        <tbody className="govuk-table__body">
                          {filterPreview.tasks_affected.map((task) => (
                            <tr key={task.task_id} className="govuk-table__row">
                              <td className="govuk-table__cell">{task.task_name}</td>
                              <td className="govuk-table__cell" style={{ textAlign: 'right' }}>{task.total_locations.toLocaleString()}</td>
                              <td className="govuk-table__cell" style={{ textAlign: 'right', color: '#dc2626' }}>-{task.locations_affected.toLocaleString()}</td>
                              <td className="govuk-table__cell" style={{ textAlign: 'right' }}>{task.new_total.toLocaleString()}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}

                <div className="govuk-button-group">
                  <button
                    className="govuk-button govuk-button--warning"
                    onClick={handleApplyFilter}
                    disabled={applyingFilter}
                  >
                    {applyingFilter ? 'Removing...' : `Remove ${filterPreview.total_matching.toLocaleString()} Locations`}
                  </button>
                  <button
                    className="govuk-button govuk-button--secondary"
                    onClick={() => setFilterStep('select')}
                  >
                    ← Back
                  </button>
                  <button
                    className="govuk-button govuk-button--secondary"
                    onClick={() => setFilterModalOpen(false)}
                  >
                    Cancel
                  </button>
                </div>
              </>
            )}
          </>
        )}
      </Modal>

      {/* Sample Task Modal */}
      <Modal
        isOpen={sampleModalOpen}
        onClose={() => setSampleModalOpen(false)}
        title="Create Sample Task"
      >
        <p className="govuk-body">
          Create a smaller sample task from an existing task that has downloaded images.
          This is useful for creating training or demo datasets.
        </p>

        {loadingTasksWithImages ? (
          <Loading />
        ) : tasksWithImages.length === 0 ? (
          <div className="govuk-inset-text">
            No tasks with downloaded images found. Please download images for a task first.
          </div>
        ) : (
          <>
            <div className="govuk-form-group">
              <label className="govuk-label" htmlFor="sourceTask">
                Source Task
              </label>
              <p className="govuk-hint">Select the task to create a sample from</p>
              <select
                className="govuk-select"
                id="sourceTask"
                value={selectedSourceTask}
                onChange={(e) => setSelectedSourceTask(e.target.value)}
                style={{ width: '100%' }}
              >
                <option value="">-- Select a task --</option>
                {tasksWithImages.map((task) => (
                  <option key={task.id} value={task.id}>
                    {task.name || task.group_value || task.council} ({task.images_downloaded} images)
                  </option>
                ))}
              </select>
            </div>

            <div className="govuk-form-group">
              <label className="govuk-label" htmlFor="sampleSize">
                Sample Size
              </label>
              <p className="govuk-hint">Number of locations to include in the sample</p>
              <input
                className="govuk-input"
                id="sampleSize"
                type="number"
                min="1"
                value={sampleSize}
                onChange={(e) => setSampleSize(parseInt(e.target.value) || 0)}
                style={{ maxWidth: '150px' }}
              />
            </div>

            <div className="govuk-form-group">
              <label className="govuk-label" htmlFor="sampleName">
                Sample Name (optional)
              </label>
              <p className="govuk-hint">A custom name for the sample task</p>
              <input
                className="govuk-input"
                id="sampleName"
                type="text"
                value={sampleName}
                onChange={(e) => setSampleName(e.target.value)}
                placeholder="e.g., Training Sample - Manchester"
              />
            </div>

            <div className="govuk-button-group">
              <button
                className="govuk-button"
                onClick={handleCreateSampleTask}
                disabled={creatingSample || !selectedSourceTask || sampleSize <= 0}
              >
                {creatingSample ? 'Creating...' : 'Create Sample Task'}
              </button>
              <button
                className="govuk-button govuk-button--secondary"
                onClick={() => setSampleModalOpen(false)}
              >
                Cancel
              </button>
            </div>
          </>
        )}
      </Modal>

      {/* Task Detail Modal */}
      <Modal
        isOpen={taskDetailOpen}
        onClose={() => setTaskDetailOpen(false)}
        title="Task Details"
      >
        {selectedTask && (
          <>
            {/* Header */}
            <div style={{ marginBottom: '16px' }}>
              <h2 className="govuk-heading-m" style={{ marginBottom: '4px' }}>
                {selectedTask.name || selectedTask.group_value || selectedTask.council}
              </h2>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span className="govuk-body" style={{ color: '#6b7280', margin: 0 }}>
                  {selectedTask.location_type_name}
                </span>
                {getStatusTag(selectedTask.status)}
              </div>
            </div>

            {/* Quick Stats Bar */}
            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(4, 1fr)', 
              gap: '12px', 
              marginBottom: '20px',
              padding: '16px',
              background: '#f8fafc',
              borderRadius: '12px'
            }}>
              <div style={{ textAlign: 'center' }}>
                <span style={{ fontSize: '20px', fontWeight: 700, display: 'block' }}>
                  {selectedTask.total_locations.toLocaleString()}
                </span>
                <span style={{ fontSize: '11px', color: '#6b7280' }}>Locations</span>
              </div>
              <div style={{ textAlign: 'center' }}>
                <span style={{ fontSize: '20px', fontWeight: 700, color: '#10b981', display: 'block' }}>
                  {Math.round(selectedTask.completion_percentage || 0)}%
                </span>
                <span style={{ fontSize: '11px', color: '#6b7280' }}>Labelled</span>
              </div>
              <div style={{ textAlign: 'center' }}>
                <span style={{ fontSize: '20px', fontWeight: 700, color: '#3b82f6', display: 'block' }}>
                  {Math.round(selectedTask.download_progress || 0)}%
                </span>
                <span style={{ fontSize: '11px', color: '#6b7280' }}>Downloaded</span>
              </div>
              <div style={{ textAlign: 'center' }}>
                <span style={{ fontSize: '20px', fontWeight: 700, color: taskSummary?.with_advertising > 0 ? '#059669' : '#6b7280', display: 'block' }}>
                  {taskSummary?.with_advertising || 0}
                </span>
                <span style={{ fontSize: '11px', color: '#6b7280' }}>With Ads</span>
              </div>
            </div>

            {/* Tab Navigation */}
            <div style={{ 
              display: 'flex', 
              gap: '4px', 
              marginBottom: '20px',
              borderBottom: '2px solid #e5e7eb',
              paddingBottom: '0'
            }}>
              {[
                { id: 'overview', label: '📋 Overview', icon: '📋' },
                { id: 'progress', label: '📊 Progress & Results', icon: '📊' },
                { id: 'downloads', label: '📥 Downloads', icon: '📥' },
                { id: 'export', label: '📤 Export', icon: '📤' },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setTaskDetailTab(tab.id as any)}
                  style={{
                    padding: '12px 16px',
                    background: taskDetailTab === tab.id ? '#1d4ed8' : 'transparent',
                    color: taskDetailTab === tab.id ? 'white' : '#4b5563',
                    border: 'none',
                    borderRadius: '8px 8px 0 0',
                    cursor: 'pointer',
                    fontWeight: taskDetailTab === tab.id ? 600 : 400,
                    fontSize: '14px',
                    transition: 'all 0.15s ease',
                    marginBottom: '-2px',
                    borderBottom: taskDetailTab === tab.id ? '2px solid #1d4ed8' : '2px solid transparent'
                  }}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Tab Content */}
            {taskDetailTab === 'overview' && (
              <>
                {/* Assignment Info */}
                <div style={{ 
                  background: '#f9fafb', 
                  borderRadius: '12px', 
                  padding: '20px',
                  marginBottom: '24px'
                }}>
                  <h3 className="govuk-heading-s" style={{ marginBottom: '16px' }}>
                    👤 Assignment
                  </h3>
                  <dl className="govuk-summary-list govuk-summary-list--no-border" style={{ marginBottom: 0 }}>
                    <div className="govuk-summary-list__row">
                      <dt className="govuk-summary-list__key">Assigned To</dt>
                      <dd className="govuk-summary-list__value">
                        {selectedTask.assignee_name || <em style={{ color: '#9ca3af' }}>Unassigned</em>}
                      </dd>
                    </div>
                    <div className="govuk-summary-list__row">
                      <dt className="govuk-summary-list__key">Created</dt>
                      <dd className="govuk-summary-list__value">
                        {selectedTask.created_at ? new Date(selectedTask.created_at).toLocaleString() : '—'}
                      </dd>
                    </div>
                    <div className="govuk-summary-list__row">
                      <dt className="govuk-summary-list__key">Assigned</dt>
                      <dd className="govuk-summary-list__value">
                        {selectedTask.assigned_at ? new Date(selectedTask.assigned_at).toLocaleString() : '—'}
                      </dd>
                    </div>
                    <div className="govuk-summary-list__row">
                      <dt className="govuk-summary-list__key">Started</dt>
                      <dd className="govuk-summary-list__value">
                        {selectedTask.started_at ? new Date(selectedTask.started_at).toLocaleString() : '—'}
                      </dd>
                    </div>
                    <div className="govuk-summary-list__row">
                      <dt className="govuk-summary-list__key">Completed</dt>
                      <dd className="govuk-summary-list__value">
                        {selectedTask.completed_at ? new Date(selectedTask.completed_at).toLocaleString() : '—'}
                      </dd>
                    </div>
                  </dl>
                </div>

                {/* Task Info */}
                <div style={{ 
                  background: '#f9fafb', 
                  borderRadius: '12px', 
                  padding: '20px'
                }}>
                  <h3 className="govuk-heading-s" style={{ marginBottom: '16px' }}>
                    📍 Task Details
                  </h3>
                  <dl className="govuk-summary-list govuk-summary-list--no-border" style={{ marginBottom: 0 }}>
                    <div className="govuk-summary-list__row">
                      <dt className="govuk-summary-list__key">Location Type</dt>
                      <dd className="govuk-summary-list__value">{selectedTask.location_type_name}</dd>
                    </div>
                    <div className="govuk-summary-list__row">
                      <dt className="govuk-summary-list__key">Council/Group</dt>
                      <dd className="govuk-summary-list__value">{selectedTask.group_value || selectedTask.council || '—'}</dd>
                    </div>
                    <div className="govuk-summary-list__row">
                      <dt className="govuk-summary-list__key">Total Locations</dt>
                      <dd className="govuk-summary-list__value">{selectedTask.total_locations.toLocaleString()}</dd>
                    </div>
                  </dl>
                </div>
              </>
            )}

            {taskDetailTab === 'progress' && (
              <>
                {/* Labelling Progress */}
                <div style={{ 
                  background: '#f9fafb', 
                  borderRadius: '12px', 
                  padding: '20px',
                  marginBottom: '24px'
                }}>
                  <h3 className="govuk-heading-s" style={{ marginBottom: '16px' }}>
                    🏷️ Labelling Progress
                  </h3>
                  <div style={{ marginBottom: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <span className="govuk-body-s">Progress</span>
                      <span className="govuk-body-s" style={{ fontWeight: 600 }}>
                        {Math.round(selectedTask.completion_percentage || 0)}%
                      </span>
                    </div>
                    <ProgressBar
                      value={selectedTask.completed_locations || 0}
                      max={selectedTask.total_locations || 1}
                      showLabel={false}
                      variant={selectedTask.completion_percentage >= 100 ? 'success' : 'default'}
                    />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', textAlign: 'center' }}>
                    <div>
                      <span style={{ fontSize: '24px', fontWeight: 700, color: '#10b981', display: 'block' }}>
                        {(selectedTask.completed_locations || 0).toLocaleString()}
                      </span>
                      <span className="govuk-body-s" style={{ color: '#6b7280' }}>Completed</span>
                    </div>
                    <div>
                      <span style={{ fontSize: '24px', fontWeight: 700, color: '#dc2626', display: 'block' }}>
                        {(selectedTask.failed_locations || 0).toLocaleString()}
                      </span>
                      <span className="govuk-body-s" style={{ color: '#6b7280' }}>Failed</span>
                    </div>
                    <div>
                      <span style={{ fontSize: '24px', fontWeight: 700, color: '#6b7280', display: 'block' }}>
                        {((selectedTask.total_locations || 0) - (selectedTask.completed_locations || 0) - (selectedTask.failed_locations || 0)).toLocaleString()}
                      </span>
                      <span className="govuk-body-s" style={{ color: '#6b7280' }}>Remaining</span>
                    </div>
                  </div>
                </div>

                {/* Labelling Results Summary */}
                <div style={{ 
                  background: '#ecfdf5', 
                  borderRadius: '12px', 
                  padding: '20px',
                  border: '1px solid #a7f3d0'
                }}>
                  <h3 className="govuk-heading-s" style={{ marginBottom: '16px', color: '#065f46' }}>
                    📈 Labelling Results Summary
                  </h3>
                  {loadingSummary ? (
                    <div style={{ textAlign: 'center', padding: '20px', color: '#6b7280' }}>
                      Loading results...
                    </div>
                  ) : taskSummary ? (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', textAlign: 'center' }}>
                      <div style={{ background: 'white', padding: '16px', borderRadius: '8px' }}>
                        <span style={{ fontSize: '28px', fontWeight: 700, color: '#059669', display: 'block' }}>
                          {taskSummary.with_advertising || 0}
                        </span>
                        <span style={{ fontSize: '12px', color: '#6b7280' }}>With Advertising</span>
                      </div>
                      <div style={{ background: 'white', padding: '16px', borderRadius: '8px' }}>
                        <span style={{ fontSize: '28px', fontWeight: 700, color: '#2563eb', display: 'block' }}>
                          {taskSummary.with_shelter || 0}
                        </span>
                        <span style={{ fontSize: '12px', color: '#6b7280' }}>With Shelter</span>
                      </div>
                      <div style={{ background: 'white', padding: '16px', borderRadius: '8px' }}>
                        <span style={{ fontSize: '28px', fontWeight: 700, color: '#7c3aed', display: 'block' }}>
                          {taskSummary.advertising_rate || 0}%
                        </span>
                        <span style={{ fontSize: '12px', color: '#6b7280' }}>Advertising Rate</span>
                      </div>
                      <div style={{ background: 'white', padding: '16px', borderRadius: '8px' }}>
                        <span style={{ fontSize: '28px', fontWeight: 700, color: '#dc2626', display: 'block' }}>
                          {taskSummary.unable_to_label || 0}
                        </span>
                        <span style={{ fontSize: '12px', color: '#6b7280' }}>Unable to Label</span>
                      </div>
                    </div>
                  ) : (
                    <div style={{ textAlign: 'center', padding: '20px', color: '#6b7280' }}>
                      No labelling results yet
                    </div>
                  )}
                </div>
              </>
            )}

            {taskDetailTab === 'downloads' && (
              <>
                {/* Image Download Progress */}
            <div style={{ 
              background: '#f9fafb', 
              borderRadius: '12px', 
              padding: '20px',
              marginBottom: '24px'
            }}>
              <h3 className="govuk-heading-s" style={{ marginBottom: '16px' }}>
                📷 Image Download Progress
              </h3>
              <div style={{ marginBottom: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span className="govuk-body-s">Progress</span>
                  <span className="govuk-body-s" style={{ fontWeight: 600 }}>
                    {Math.round(selectedTask.download_progress || 0)}%
                  </span>
                </div>
                <ProgressBar
                  value={selectedTask.images_downloaded || 0}
                  max={selectedTask.total_images || 1}
                  showLabel={false}
                  variant={selectedTask.download_progress >= 100 ? 'success' : (selectedTask.status === 'downloading' ? 'warning' : 'default')}
                />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', textAlign: 'center' }}>
                <div>
                  <span style={{ fontSize: '24px', fontWeight: 700, color: '#10b981', display: 'block' }}>
                    {(selectedTask.images_downloaded || 0).toLocaleString()}
                  </span>
                  <span className="govuk-body-s" style={{ color: '#6b7280' }}>Downloaded</span>
                </div>
                <div>
                  <span style={{ fontSize: '24px', fontWeight: 700, color: '#6b7280', display: 'block' }}>
                    {((selectedTask.total_images || 0) - (selectedTask.images_downloaded || 0)).toLocaleString()}
                  </span>
                  <span className="govuk-body-s" style={{ color: '#6b7280' }}>Remaining</span>
                </div>
                <div>
                  <span style={{ fontSize: '24px', fontWeight: 700, display: 'block' }}>
                    {(selectedTask.total_images || 0).toLocaleString()}
                  </span>
                  <span className="govuk-body-s" style={{ color: '#6b7280' }}>Total Images</span>
                </div>
              </div>
              {selectedTask.status === 'downloading' && (
                <div style={{ 
                  marginTop: '16px', 
                  padding: '12px', 
                  background: '#fef3c7', 
                  borderRadius: '8px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px'
                }}>
                  <span style={{ fontSize: '18px' }}>⏳</span>
                  <span className="govuk-body-s" style={{ color: '#92400e', margin: 0 }}>
                    Images are currently being downloaded from Google Street View...
                  </span>
                </div>
              )}
              {selectedTask.download_progress >= 100 && (
                <div style={{ 
                  marginTop: '16px', 
                  padding: '12px', 
                  background: '#d1fae5', 
                  borderRadius: '8px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px'
                }}>
                  <span style={{ fontSize: '18px' }}>✅</span>
                  <span className="govuk-body-s" style={{ color: '#065f46', margin: 0 }}>
                    All images downloaded successfully!
                  </span>
                </div>
              )}
            </div>

            {/* Download Control Buttons */}
            <div style={{ 
              background: '#f0f9ff',
              border: '1px solid #0ea5e9',
              borderRadius: '12px',
              padding: '16px',
              marginBottom: '24px'
            }}>
              <h3 className="govuk-heading-s" style={{ marginBottom: '12px', color: '#0369a1' }}>
                📥 Image Download Controls
              </h3>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '12px' }}>
                {/* Start/Resume button */}
                {selectedTask.status === 'paused' ? (
                  <button
                    className="govuk-button"
                    onClick={handleResumeDownload}
                    style={{ marginBottom: 0 }}
                  >
                    ▶️ Resume Download
                  </button>
                ) : (
                  <button
                    className="govuk-button"
                    onClick={handleTriggerDownload}
                    disabled={downloadingImages || selectedTask.status === 'downloading'}
                    style={{ marginBottom: 0 }}
                  >
                    {downloadingImages ? '⏳ Starting...' : '▶️ Start Download'}
                  </button>
                )}
                
                {/* Pause button - only when downloading */}
                {selectedTask.status === 'downloading' && (
                  <button
                    className="govuk-button govuk-button--secondary"
                    onClick={handlePauseDownload}
                    style={{ marginBottom: 0 }}
                  >
                    ⏸️ Pause
                  </button>
                )}
                
                {/* Cancel button */}
                <button
                  className="govuk-button"
                  onClick={handleCancelDownload}
                  disabled={selectedTask.status !== 'downloading' && selectedTask.status !== 'paused'}
                  style={{ marginBottom: 0, background: '#ef4444' }}
                >
                  ⏹️ Stop
                </button>
              </div>
              
              {/* Restart options */}
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                <button
                  className="govuk-button govuk-button--secondary"
                  onClick={() => handleRestartDownload(false)}
                  disabled={selectedTask.status === 'downloading'}
                  style={{ marginBottom: 0 }}
                >
                  🔄 Download Missing
                </button>
                <button
                  className="govuk-button govuk-button--warning"
                  onClick={() => handleRestartDownload(true)}
                  disabled={selectedTask.status === 'downloading'}
                  style={{ marginBottom: 0, background: '#f59e0b' }}
                >
                  🔄 Re-download All
                </button>
                <button
                  className="govuk-button govuk-button--secondary"
                  onClick={handleViewLogs}
                  style={{ marginBottom: 0 }}
                >
                  📋 View Logs
                </button>
              </div>
              
              {/* Status message */}
              <p className="govuk-body-s" style={{ marginTop: '12px', marginBottom: 0, color: '#6b7280' }}>
                {selectedTask.status === 'downloading' 
                  ? '⏳ Download is currently in progress... You can pause or stop it anytime.' 
                  : selectedTask.status === 'paused'
                  ? '⏸️ Download is paused. Click Resume to continue.'
                  : selectedTask.status === 'ready'
                  ? '✅ Images downloaded. Use "Download Missing" to fill gaps or "Re-download All" to start fresh.'
                  : '📥 Click Start to begin downloading images from Google Street View.'}
              </p>
            </div>

            {/* Download Logs */}
            {showLogs && (
              <div style={{ 
                background: '#f1f5f9', 
                borderRadius: '12px', 
                padding: '20px',
                marginBottom: '24px'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <h3 className="govuk-heading-s" style={{ marginBottom: 0 }}>
                    📋 Download Logs
                  </h3>
                  <button
                    className="govuk-button govuk-button--secondary"
                    style={{ marginBottom: 0 }}
                    onClick={() => setShowLogs(false)}
                  >
                    Hide
                  </button>
                </div>
                <div style={{ 
                  maxHeight: '300px', 
                  overflow: 'auto', 
                  background: '#1e293b', 
                  borderRadius: '8px', 
                  padding: '12px',
                  fontFamily: 'monospace',
                  fontSize: '12px'
                }}>
                  {downloadLogs.length === 0 ? (
                    <p style={{ color: '#94a3b8', margin: 0 }}>No logs available yet.</p>
                  ) : (
                    downloadLogs.map((log, idx) => (
                      <div key={idx} style={{ 
                        color: log.level === 'error' ? '#f87171' : log.level === 'warning' ? '#fbbf24' : '#4ade80',
                        marginBottom: '4px'
                      }}>
                        [{log.timestamp}] {log.message}
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
              </>
            )}

            {taskDetailTab === 'export' && (
              <>
                {/* Results & Export Section */}
                <div style={{ 
                  background: '#eff6ff', 
                  borderRadius: '12px', 
                  padding: '20px',
                  marginBottom: '24px',
                  border: '1px solid #bfdbfe'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                    <h3 className="govuk-heading-s" style={{ marginBottom: 0, color: '#1e40af' }}>
                      📊 Results & Export
                    </h3>
                    {selectedTask.status !== 'completed' && (
                      <span className="govuk-tag govuk-tag--blue" style={{ fontSize: '11px' }}>
                        Available for in-progress tasks
                      </span>
                    )}
                  </div>
                  
                  <p className="govuk-body-s" style={{ color: '#1e40af', marginBottom: '16px' }}>
                    View and export labelling results at any time, even while the task is still in progress.
                  </p>
                  
                  <div style={{ 
                    display: 'grid', 
                    gridTemplateColumns: 'repeat(2, 1fr)', 
                    gap: '12px',
                    marginBottom: '16px'
                  }}>
                    <button
                      className="govuk-button"
                      onClick={() => handleViewImages(1)}
                      style={{ marginBottom: 0, width: '100%' }}
                    >
                      🖼️ View Downloaded Images
                    </button>
                    <button
                      className="govuk-button"
                      onClick={handleViewSnapshots}
                      style={{ marginBottom: 0, width: '100%' }}
                    >
                      📷 View User Snapshots
                    </button>
                    <button
                      className="govuk-button govuk-button--secondary"
                      onClick={() => handleExportCsv(true)}
                      style={{ marginBottom: 0, width: '100%' }}
                    >
                      📥 Export CSV (All Locations)
                    </button>
                    <button
                      className="govuk-button govuk-button--secondary"
                      onClick={() => handleExportCsv(false)}
                      style={{ marginBottom: 0, width: '100%' }}
                    >
                      📥 Export CSV (Labelled Only)
                    </button>
                  </div>
                  
                  <p className="govuk-body-s" style={{ margin: 0, color: '#6b7280' }}>
                    💡 Tip: "Labelled Only" exports just locations that have been completed. "All Locations" includes pending locations with empty label fields.
                  </p>
                </div>

                {/* Image Gallery */}
            {showImages && taskImages && (
              <div style={{ 
                background: '#f9fafb', 
                borderRadius: '12px', 
                padding: '20px',
                marginBottom: '24px'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <h3 className="govuk-heading-s" style={{ marginBottom: 0 }}>
                    🖼️ Downloaded Images ({taskImages.total_locations} locations)
                  </h3>
                  <button
                    className="govuk-button govuk-button--secondary"
                    style={{ marginBottom: 0 }}
                    onClick={() => setShowImages(false)}
                  >
                    Hide
                  </button>
                </div>
                
                {taskImages.locations.length === 0 ? (
                  <p className="govuk-body" style={{ color: '#6b7280', textAlign: 'center', padding: '20px' }}>
                    No images downloaded yet.
                  </p>
                ) : (
                  <>
                    {taskImages.locations.map((loc: any) => (
                      <div key={loc.id} style={{ 
                        marginBottom: '16px', 
                        padding: '16px', 
                        background: 'white', 
                        borderRadius: '8px',
                        border: '1px solid #e5e7eb'
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                          <span className="govuk-body" style={{ fontWeight: 600, margin: 0 }}>
                            {loc.identifier}
                          </span>
                          <span className={`govuk-tag ${loc.has_images ? 'govuk-tag--green' : 'govuk-tag--grey'}`}>
                            {loc.images.length > 0 ? `${loc.images.length} images` : 'No images'}
                          </span>
                        </div>
                        {loc.images.length > 0 ? (
                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '8px' }}>
                            {loc.images.map((img: any) => {
                              // Normalize URL - handle various formats
                              let imgUrl = img.gcs_url || ''
                              if (imgUrl.startsWith('http://localhost:8000')) {
                                imgUrl = imgUrl.replace('http://localhost:8000', '')
                              }
                              if (!imgUrl.startsWith('/') && !imgUrl.startsWith('http')) {
                                imgUrl = `/api/v1/images/${imgUrl}`
                              }
                              
                              return (
                                <div key={img.id} style={{ position: 'relative' }}>
                                  <img
                                    src={imgUrl}
                                    alt={`${loc.identifier} - ${img.heading}°`}
                                    style={{ 
                                      width: '100%', 
                                      height: '80px', 
                                      objectFit: 'cover', 
                                      borderRadius: '4px',
                                      cursor: 'pointer',
                                      background: '#f3f4f6'
                                    }}
                                    onClick={() => window.open(imgUrl, '_blank')}
                                    onError={(e) => {
                                      const target = e.target as HTMLImageElement
                                      console.error('Image failed to load:', imgUrl)
                                      target.style.display = 'none'
                                      target.parentElement!.innerHTML = `<div style="width:100%;height:80px;background:#fee2e2;border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:10px;color:#991b1b;text-align:center;padding:4px" title="${imgUrl}">⚠️ Failed<br/><small>${img.heading}°</small></div>`
                                    }}
                                  />
                                  <div style={{ 
                                    position: 'absolute', 
                                    bottom: '4px', 
                                    left: '4px', 
                                    background: 'rgba(0,0,0,0.7)', 
                                    color: 'white',
                                    padding: '2px 6px',
                                    borderRadius: '4px',
                                    fontSize: '11px'
                                  }}>
                                    {img.heading}°
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                        ) : (
                          <p className="govuk-body-s" style={{ color: '#9ca3af', margin: 0 }}>
                            📍 {loc.latitude.toFixed(6)}, {loc.longitude.toFixed(6)}
                          </p>
                        )}
                      </div>
                    ))}
                    
                    {/* Pagination */}
                    {taskImages.total_pages > 1 && (
                      <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', marginTop: '16px' }}>
                        <button
                          className="govuk-button govuk-button--secondary"
                          style={{ marginBottom: 0 }}
                          disabled={imagesPage <= 1}
                          onClick={() => handleViewImages(imagesPage - 1)}
                        >
                          Previous
                        </button>
                        <span className="govuk-body" style={{ display: 'flex', alignItems: 'center', margin: '0 12px' }}>
                          Page {imagesPage} of {taskImages.total_pages}
                        </span>
                        <button
                          className="govuk-button govuk-button--secondary"
                          style={{ marginBottom: 0 }}
                          disabled={imagesPage >= taskImages.total_pages}
                          onClick={() => handleViewImages(imagesPage + 1)}
                        >
                          Next
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>
            )}

                {/* Snapshots Panel */}
                {showSnapshots && taskSnapshots && (
              <div style={{ 
                background: '#f9fafb', 
                borderRadius: '12px', 
                padding: '20px',
                marginBottom: '24px'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <h3 className="govuk-heading-s" style={{ marginBottom: 0 }}>
                    📷 User Snapshots ({taskSnapshots.total_snapshots})
                  </h3>
                  <button
                    className="govuk-button govuk-button--secondary"
                    style={{ marginBottom: 0 }}
                    onClick={() => setShowSnapshots(false)}
                  >
                    Hide
                  </button>
                </div>
                
                {taskSnapshots.snapshots.length === 0 ? (
                  <p className="govuk-body" style={{ color: '#6b7280', textAlign: 'center', padding: '40px' }}>
                    No snapshots taken yet for this task.
                  </p>
                ) : (
                  <div style={{ 
                    display: 'grid', 
                    gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', 
                    gap: '16px' 
                  }}>
                    {taskSnapshots.snapshots.map((snapshot: any) => (
                      <div 
                        key={snapshot.id} 
                        style={{ 
                          background: 'white',
                          borderRadius: '12px',
                          overflow: 'hidden',
                          border: '1px solid #e5e7eb'
                        }}
                      >
                        <div style={{ position: 'relative', aspectRatio: '4/3' }}>
                          <img
                            src={snapshot.gcs_url}
                            alt={`Snapshot for ${snapshot.location_identifier}`}
                            style={{ 
                              width: '100%', 
                              height: '100%', 
                              objectFit: 'cover',
                              cursor: 'pointer'
                            }}
                            onClick={() => window.open(snapshot.gcs_url, '_blank')}
                            onError={(e) => {
                              const target = e.target as HTMLImageElement
                              target.style.opacity = '0.3'
                            }}
                          />
                        </div>
                        <div style={{ padding: '12px' }}>
                          <p style={{ fontWeight: 600, marginBottom: '4px', fontSize: '14px' }}>
                            {snapshot.location_identifier}
                          </p>
                          <p style={{ color: '#6b7280', fontSize: '12px', marginBottom: 0 }}>
                            Heading: {snapshot.heading}° • {snapshot.created_at ? new Date(snapshot.created_at).toLocaleDateString() : 'Unknown date'}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                </div>
              )}
              </>
            )}

            {/* Download Logs Panel - shown in any tab */}
            {showLogs && (
              <div style={{ 
                background: '#1e1e1e', 
                borderRadius: '12px', 
                padding: '20px',
                marginBottom: '24px',
                color: '#d4d4d4'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <h3 className="govuk-heading-s" style={{ marginBottom: 0, color: '#fff' }}>
                    📋 Download Logs {downloadLogs.length > 0 && downloadLogs[0]?.status === 'in_progress' && '(Live)'}
                  </h3>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      className="govuk-button govuk-button--secondary"
                      style={{ marginBottom: 0, padding: '4px 12px', fontSize: '14px' }}
                      onClick={loadDownloadLogs}
                    >
                      🔄 Refresh
                    </button>
                    <button
                      className="govuk-button govuk-button--secondary"
                      style={{ marginBottom: 0, padding: '4px 12px', fontSize: '14px' }}
                      onClick={handleCloseLogs}
                    >
                      ✕ Close
                    </button>
                  </div>
                </div>
                
                {downloadLogs.length === 0 ? (
                  <p style={{ color: '#9ca3af', textAlign: 'center', padding: '20px' }}>
                    No download logs yet. Click "Start Image Download" to begin.
                  </p>
                ) : (
                  <>
                    {downloadLogs.map((log: any) => (
                      <div key={log.id} style={{ 
                        marginBottom: '16px', 
                        padding: '16px', 
                        background: '#2d2d2d', 
                        borderRadius: '8px',
                        border: log.status === 'in_progress' ? '2px solid #10b981' : '1px solid #404040'
                      }}>
                        {/* Status header */}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                          <span style={{ 
                            padding: '4px 12px', 
                            borderRadius: '12px', 
                            fontSize: '12px',
                            fontWeight: 600,
                            background: log.status === 'completed' ? '#065f46' : 
                                       log.status === 'in_progress' ? '#1e40af' : 
                                       log.status === 'failed' ? '#7f1d1d' : '#374151',
                            color: 'white'
                          }}>
                            {log.status === 'in_progress' && '⏳ '}{log.status.toUpperCase()}
                          </span>
                          <span style={{ color: '#9ca3af', fontSize: '12px' }}>
                            Started: {log.started_at ? new Date(log.started_at).toLocaleString() : 'Not started'}
                          </span>
                        </div>

                        {/* Progress bar */}
                        <div style={{ marginBottom: '12px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                            <span style={{ fontSize: '13px' }}>Progress</span>
                            <span style={{ fontSize: '13px', fontWeight: 600, color: '#10b981' }}>
                              {log.progress_percent}%
                            </span>
                          </div>
                          <div style={{ 
                            height: '8px', 
                            background: '#404040', 
                            borderRadius: '4px', 
                            overflow: 'hidden' 
                          }}>
                            <div style={{ 
                              height: '100%', 
                              width: `${log.progress_percent}%`, 
                              background: log.status === 'failed' ? '#dc2626' : '#10b981',
                              transition: 'width 0.3s ease'
                            }} />
                          </div>
                        </div>

                        {/* Stats */}
                        <div style={{ 
                          display: 'grid', 
                          gridTemplateColumns: 'repeat(5, 1fr)', 
                          gap: '8px', 
                          marginBottom: '12px',
                          textAlign: 'center'
                        }}>
                          <div>
                            <span style={{ display: 'block', fontSize: '18px', fontWeight: 700, color: '#60a5fa' }}>
                              {log.processed_locations}
                            </span>
                            <span style={{ fontSize: '11px', color: '#9ca3af' }}>Processed</span>
                          </div>
                          <div>
                            <span style={{ display: 'block', fontSize: '18px', fontWeight: 700, color: '#6b7280' }}>
                              {log.total_locations}
                            </span>
                            <span style={{ fontSize: '11px', color: '#9ca3af' }}>Total</span>
                          </div>
                          <div>
                            <span style={{ display: 'block', fontSize: '18px', fontWeight: 700, color: '#10b981' }}>
                              {log.successful_downloads}
                            </span>
                            <span style={{ fontSize: '11px', color: '#9ca3af' }}>Downloaded</span>
                          </div>
                          <div>
                            <span style={{ display: 'block', fontSize: '18px', fontWeight: 700, color: '#f59e0b' }}>
                              {log.skipped_existing}
                            </span>
                            <span style={{ fontSize: '11px', color: '#9ca3af' }}>Skipped</span>
                          </div>
                          <div>
                            <span style={{ display: 'block', fontSize: '18px', fontWeight: 700, color: '#dc2626' }}>
                              {log.failed_downloads}
                            </span>
                            <span style={{ fontSize: '11px', color: '#9ca3af' }}>Failed</span>
                          </div>
                        </div>

                        {/* Current location */}
                        {log.current_location && (
                          <div style={{ 
                            padding: '8px 12px', 
                            background: '#1e1e1e', 
                            borderRadius: '4px', 
                            marginBottom: '12px',
                            fontSize: '13px'
                          }}>
                            <span style={{ color: '#9ca3af' }}>Processing: </span>
                            <span style={{ color: '#60a5fa', fontFamily: 'monospace' }}>{log.current_location}</span>
                          </div>
                        )}

                        {/* Last error */}
                        {log.last_error && (
                          <div style={{ 
                            padding: '12px', 
                            background: '#450a0a', 
                            borderRadius: '4px', 
                            marginBottom: '12px',
                            border: '1px solid #7f1d1d'
                          }}>
                            <span style={{ color: '#fca5a5', fontSize: '13px', fontWeight: 600 }}>⚠️ Last Error:</span>
                            <pre style={{ 
                              color: '#fecaca', 
                              margin: '8px 0 0 0', 
                              fontSize: '12px', 
                              whiteSpace: 'pre-wrap',
                              wordBreak: 'break-all'
                            }}>
                              {log.last_error}
                            </pre>
                          </div>
                        )}

                        {/* Log messages */}
                        {log.log_messages && log.log_messages.length > 0 && (
                          <div style={{ 
                            maxHeight: '200px', 
                            overflowY: 'auto', 
                            background: '#1e1e1e', 
                            borderRadius: '4px',
                            padding: '8px',
                            fontFamily: 'monospace',
                            fontSize: '11px'
                          }}>
                            {log.log_messages.slice(-20).map((msg: any, idx: number) => (
                              <div key={idx} style={{ 
                                padding: '2px 0',
                                color: msg.level === 'error' ? '#fca5a5' : 
                                       msg.level === 'warning' ? '#fcd34d' : '#d4d4d4'
                              }}>
                                <span style={{ color: '#6b7280' }}>
                                  [{new Date(msg.time).toLocaleTimeString()}]
                                </span>{' '}
                                <span style={{ 
                                  color: msg.level === 'error' ? '#f87171' : 
                                         msg.level === 'warning' ? '#fbbf24' : '#60a5fa',
                                  fontWeight: 600
                                }}>
                                  [{msg.level.toUpperCase()}]
                                </span>{' '}
                                {msg.message}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}

            <div className="govuk-button-group">
              <button
                className="govuk-button govuk-button--secondary"
                onClick={() => setTaskDetailOpen(false)}
              >
                Close
              </button>
            </div>
          </>
        )}
      </Modal>
    </>
  )
}

