import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { spreadsheetsApi, dataApi } from '../services/api'
import Loading from '../components/common/Loading'
import Modal from '../components/common/Modal'

interface LocationType {
  id: string
  name: string
  display_name: string
  description: string | null
  location_count: number
  label_fields: any
}

interface Shapefile {
  id: string
  name: string
  display_name: string
  description: string | null
  shapefile_type: string
  target_column: string | null
  feature_count: number
  geometry_type: string | null
  attribute_columns: Record<string, { type: string; length?: number }>
  name_column: string | null
  attribute_mappings: { source_column: string; target_column: string }[]
  value_columns: string[]
  is_loaded: boolean
  created_at: string
  loaded_at: string | null
}

interface ShapefileAnalysis {
  filename: string
  file_type?: 'shapefile' | 'geopackage'
  shapefiles_found: {
    name: string
    file: string
    identifier?: string
    description?: string
    has_required_files: boolean
    feature_count: number
    geometry_type: string
    attributes: Record<string, { type: string; length?: number }>
    sample_values: Record<string, string[]>
  }[]
  layers_found?: {
    name: string
    file: string
    identifier?: string
    description?: string
    has_required_files: boolean
    feature_count: number
    geometry_type: string
    attributes: Record<string, { type: string; length?: number }>
    sample_values: Record<string, string[]>
  }[]
  message: string
}

interface EnhancementPreview {
  location_type_id: string
  location_type_name: string
  total_locations: number
  unenhanced_count: number
  columns_to_add: {
    name: string
    description: string
    shapefile_required: string
    shapefile_loaded: boolean
  }[]
  available_shapefiles: {
    id: string
    name: string
    type: string
    feature_count: number
    adds_column: string
  }[]
  sample_locations: any[]
}

interface EnhancementJob {
  id: string
  location_type_id: string
  status: string
  total_locations: number
  processed_locations: number
  enhanced_locations: number
  progress_percent: number
  enhance_council: boolean
  enhance_road: boolean
  enhance_authority: boolean
  councils_found: string[]
  error_message: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

interface UploadJobStatus {
  job_id: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  stage: string
  progress_percent: number
  error_message: string | null
  locations_created: number | null
  total_rows: number | null
}

const defaultBusStopFields = {
  fields: [
    { id: 'advertising_present', type: 'boolean', label: 'Advertising present' },
    { id: 'bus_shelter_present', type: 'boolean', label: 'Bus shelter present' },
    { id: 'number_of_panels', type: 'number', label: 'Number of panels' },
    { id: 'pole_stop', type: 'boolean', label: 'Pole stop' },
    { id: 'unmarked_stop', type: 'boolean', label: 'Unmarked stop' },
  ],
}

// Icons
const UploadIcon = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" width="24" height="24">
    <path d="M9 16h6v-6h4l-7-7-7 7h4zm-4 2h14v2H5z"/>
  </svg>
)

const MapIcon = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" width="24" height="24">
    <path d="M20.5 3l-.16.03L15 5.1 9 3 3.36 4.9c-.21.07-.36.25-.36.48V20.5c0 .28.22.5.5.5l.16-.03L9 18.9l6 2.1 5.64-1.9c.21-.07.36-.25.36-.48V3.5c0-.28-.22-.5-.5-.5zM15 19l-6-2.11V5l6 2.11V19z"/>
  </svg>
)

const EnhanceIcon = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" width="24" height="24">
    <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/>
  </svg>
)

export default function UploadPage() {
  const [activeTab, setActiveTab] = useState<'upload' | 'shapefiles' | 'enhance'>('upload')
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [locationTypes, setLocationTypes] = useState<LocationType[]>([])
  const [shapefiles, setShapefiles] = useState<Shapefile[]>([])
  
  // Upload form state
  const [selectedType, setSelectedType] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [latColumn, setLatColumn] = useState('Latitude')
  const [lngColumn, setLngColumn] = useState('Longitude')
  const [identifierColumn, setIdentifierColumn] = useState('ATCOCode')
  const [uploadResult, setUploadResult] = useState<any>(null)
  const [uploadJobIdForSpreadsheet, setUploadJobIdForSpreadsheet] = useState<string | null>(null)
  const [uploadJobStatus, setUploadJobStatus] = useState<UploadJobStatus | null>(null)
  
  // Create type modal
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [newTypeName, setNewTypeName] = useState('')
  const [newTypeDisplayName, setNewTypeDisplayName] = useState('')
  const [newTypeDescription, setNewTypeDescription] = useState('')
  
  // Shapefile upload
  const [shapefileModalOpen, setShapefileModalOpen] = useState(false)
  const [shapefileName, setShapefileName] = useState('')
  const [shapefileDisplayName, setShapefileDisplayName] = useState('')
  const [shapefileDescription, setShapefileDescription] = useState('')
  const [shapefileType, setShapefileType] = useState('custom')  // Default to custom for multi-attribute
  const [shapefileFile, setShapefileFile] = useState<File | null>(null)
  const [uploadingShapefile, setUploadingShapefile] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)  // 0-100 for file upload progress
  const [uploadStage, setUploadStage] = useState('')  // Current stage description
  const [uploadJobId, setUploadJobId] = useState<string | null>(null)  // For chunked uploads
  const [analyzingShapefile, setAnalyzingShapefile] = useState(false)
  const [shapefileAnalysis, setShapefileAnalysis] = useState<ShapefileAnalysis | null>(null)
  const [selectedShapefileIndex, setSelectedShapefileIndex] = useState(0)
  // Multiple attribute mappings: [{source_column, target_column}]
  const [attributeMappings, setAttributeMappings] = useState<{source_column: string, target_column: string}[]>([])
  const [loadingShapefileId, setLoadingShapefileId] = useState<string | null>(null)
  
  // Chunk size for large file uploads (5MB)
  const CHUNK_SIZE = 5 * 1024 * 1024
  
  // Enhancement
  const [enhancementPreview, setEnhancementPreview] = useState<EnhancementPreview | null>(null)
  const [enhancementJobs, setEnhancementJobs] = useState<EnhancementJob[]>([])
  const [enhanceCouncil, setEnhanceCouncil] = useState(true)
  const [enhanceRoad, setEnhanceRoad] = useState(true)
  const [enhanceAuthority, setEnhanceAuthority] = useState(true)
  const [startingEnhancement, setStartingEnhancement] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    // Load each resource independently so one failure doesn't block others
    try {
      const typesRes = await spreadsheetsApi.getLocationTypes()
      setLocationTypes(typesRes.data)
    } catch (error) {
      console.error('Failed to load location types:', error)
    }
    
    try {
      const shapesRes = await dataApi.getShapefiles()
      setShapefiles(shapesRes.data)
    } catch (error) {
      console.error('Failed to load shapefiles:', error)
    }
    
    try {
      const jobsRes = await dataApi.getEnhancementJobs()
      setEnhancementJobs(jobsRes.data)
    } catch (error) {
      console.error('Failed to load enhancement jobs:', error)
    }
    
    setLoading(false)
  }

  // Poll for active enhancement jobs
  useEffect(() => {
    const activeJobs = enhancementJobs.filter(j => j.status === 'running' || j.status === 'pending')
    if (activeJobs.length === 0) return
    
    const interval = setInterval(async () => {
      try {
        const response = await dataApi.getEnhancementJobs()
        setEnhancementJobs(response.data)
        
        // Check if any running jobs completed
        const stillRunning = response.data.filter((j: EnhancementJob) => 
          j.status === 'running' || j.status === 'pending'
        )
        if (stillRunning.length === 0) {
          loadData() // Refresh all data
        }
      } catch (error) {
        console.error('Failed to poll jobs:', error)
      }
    }, 2000)
    
    return () => clearInterval(interval)
  }, [enhancementJobs])

  const handleCreateType = async () => {
    if (!newTypeName || !newTypeDisplayName) return

    try {
      await spreadsheetsApi.createLocationType({
        name: newTypeName.toLowerCase().replace(/\s+/g, '_'),
        display_name: newTypeDisplayName,
        description: newTypeDescription,
        identifier_field: 'atco_code',
        label_fields: defaultBusStopFields,
      })

      setCreateModalOpen(false)
      setNewTypeName('')
      setNewTypeDisplayName('')
      setNewTypeDescription('')
      loadData()
    } catch (error) {
      console.error('Failed to create location type:', error)
      alert('Failed to create location type')
    }
  }

  const handleDeleteLocationType = async (typeId: string, typeName: string, locationCount: number) => {
    const confirmMessage = locationCount > 0 
      ? `Are you sure you want to delete "${typeName}"?\n\nThis will permanently delete ${locationCount.toLocaleString()} locations and cannot be undone.`
      : `Are you sure you want to delete "${typeName}"?`
    
    if (!confirm(confirmMessage)) return
    
    try {
      await spreadsheetsApi.deleteLocationType(typeId)
      // Clear selection if we deleted the selected type
      if (selectedType === typeId) {
        setSelectedType('')
      }
      loadData()
    } catch (error: any) {
      console.error('Failed to delete location type:', error)
      const detail = error.response?.data?.detail
      const errorMsg = Array.isArray(detail) ? detail.map((e: any) => e.msg || JSON.stringify(e)).join(', ') : (detail || 'Failed to delete location type')
      alert(errorMsg)
    }
  }

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!file || !selectedType) return

    setUploading(true)
    setUploadResult(null)
    setUploadJobIdForSpreadsheet(null)
    setUploadJobStatus(null)

    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('location_type_id', selectedType)
      formData.append('lat_column', latColumn)
      formData.append('lng_column', lngColumn)
      formData.append('identifier_column', identifierColumn)

      const response = await spreadsheetsApi.uploadSpreadsheet(formData)
      
      // Handle async upload response
      if (response.data.job_id) {
        setUploadJobIdForSpreadsheet(response.data.job_id)
        setUploadJobStatus({
          job_id: response.data.job_id,
          status: response.data.status || 'pending',
          stage: 'File uploaded, processing started...',
          progress_percent: 0,
          error_message: null,
          locations_created: null,
          total_rows: null
        })
        // Polling will be handled by useEffect
      } else {
        // Legacy sync response (shouldn't happen anymore)
        setUploadResult(response.data)
        setFile(null)
        loadData()
      }
    } catch (error: any) {
      console.error('Failed to upload:', error)
      const detail = error.response?.data?.detail
      const errorMsg = Array.isArray(detail) ? detail.map((e: any) => e.msg || JSON.stringify(e)).join(', ') : (detail || 'Upload failed')
      alert(errorMsg)
      setUploading(false)
    }
  }
  
  // Poll for upload job status
  useEffect(() => {
    if (!uploadJobIdForSpreadsheet) return
    
    const pollStatus = async () => {
      try {
        const response = await spreadsheetsApi.getUploadJobStatus(uploadJobIdForSpreadsheet)
        setUploadJobStatus(response.data)
        
        if (response.data.status === 'completed') {
          setUploadResult({
            locations_created: response.data.locations_created || 0,
            message: 'Upload completed successfully'
          })
          setFile(null)
          setUploading(false)
          setUploadJobIdForSpreadsheet(null)
          loadData()
        } else if (response.data.status === 'failed') {
          alert(response.data.error_message || 'Upload processing failed')
          setUploading(false)
          setUploadJobIdForSpreadsheet(null)
        }
      } catch (error) {
        console.error('Failed to poll job status:', error)
      }
    }
    
    const interval = setInterval(pollStatus, 2000)
    pollStatus() // Initial poll
    
    return () => clearInterval(interval)
  }, [uploadJobIdForSpreadsheet])

  const handleAnalyzeShapefile = async (file: File) => {
    setAnalyzingShapefile(true)
    setShapefileAnalysis(null)
    setAttributeMappings([])  // Reset mappings
    
    try {
      const formData = new FormData()
      formData.append('file', file)
      
      const response = await dataApi.analyzeShapefile(formData)
      setShapefileAnalysis(response.data)
      setSelectedShapefileIndex(0)
    } catch (error: any) {
      console.error('Failed to analyze shapefile:', error)
      const detail = error.response?.data?.detail
      const errorMsg = Array.isArray(detail) ? detail.map((e: any) => e.msg || JSON.stringify(e)).join(', ') : (detail || 'Failed to analyze shapefile')
      alert(errorMsg)
    } finally {
      setAnalyzingShapefile(false)
    }
  }

  const addAttributeMapping = () => {
    setAttributeMappings([...attributeMappings, { source_column: '', target_column: '' }])
  }

  const updateAttributeMapping = (index: number, field: 'source_column' | 'target_column', value: string) => {
    const updated = [...attributeMappings]
    updated[index][field] = value
    setAttributeMappings(updated)
  }

  const removeAttributeMapping = (index: number) => {
    setAttributeMappings(attributeMappings.filter((_, i) => i !== index))
  }

  const handleShapefileUpload = async () => {
    if (!shapefileFile || !shapefileName || !shapefileDisplayName || attributeMappings.length === 0) return
    
    // Validate all mappings have both columns filled
    const validMappings = attributeMappings.filter(m => m.source_column && m.target_column)
    if (validMappings.length === 0) {
      alert('Please add at least one complete attribute mapping')
      return
    }

    setUploadingShapefile(true)
    setUploadProgress(0)
    setUploadStage('Preparing upload...')
    
    const fileSize = shapefileFile.size
    const fileSizeMB = fileSize / (1024 * 1024)
    
    // Use chunked upload for files > 100MB
    const useChunkedUpload = fileSize > 100 * 1024 * 1024
    
    try {
      if (useChunkedUpload) {
        // === CHUNKED UPLOAD FOR LARGE FILES ===
        setUploadStage(`Starting chunked upload (${fileSizeMB.toFixed(1)} MB)...`)
        
        // 1. Initialize upload job
        const initResponse = await dataApi.startChunkedUpload({
          filename: shapefileFile.name,
          file_size: fileSize,
          name: shapefileName,
          display_name: shapefileDisplayName,
          description: shapefileDescription,
          shapefile_type: shapefileType,
          attribute_mappings: JSON.stringify(validMappings),
          layer_name: shapefileAnalysis?.shapefiles_found && shapefileAnalysis.shapefiles_found.length > 1 
            ? shapefileAnalysis.shapefiles_found[selectedShapefileIndex].name 
            : undefined
        })
        
        const jobId = initResponse.data.id
        setUploadJobId(jobId)
        
        // 2. Upload file in chunks
        let uploadedBytes = 0
        const totalChunks = Math.ceil(fileSize / CHUNK_SIZE)
        
        for (let i = 0; i < totalChunks; i++) {
          const start = i * CHUNK_SIZE
          const end = Math.min(start + CHUNK_SIZE, fileSize)
          const chunk = shapefileFile.slice(start, end)
          const chunkBuffer = await chunk.arrayBuffer()
          
          await dataApi.uploadChunk(jobId, chunkBuffer)
          
          uploadedBytes += (end - start)
          const progress = Math.round((uploadedBytes / fileSize) * 100)
          setUploadProgress(progress)
          setUploadStage(`Uploading... ${(uploadedBytes / (1024*1024)).toFixed(1)} MB / ${fileSizeMB.toFixed(1)} MB (chunk ${i + 1}/${totalChunks})`)
        }
        
        // 3. Signal upload complete
        setUploadStage('Processing file...')
        await dataApi.completeUpload(jobId)
        
        // 4. Poll for completion
        setUploadStage('Analyzing file structure...')
        let status = 'analyzing'
        let attempts = 0
        const maxAttempts = 1800 // 30 minutes max for large files
        
        while (status !== 'completed' && status !== 'failed' && attempts < maxAttempts) {
          await new Promise(resolve => setTimeout(resolve, 1000))
          try {
            const statusResponse = await dataApi.getUploadStatus(jobId)
            status = statusResponse.data.status
            const stage = statusResponse.data.stage
            const elapsed = Math.floor(attempts / 60)
            setUploadStage(`${stage} (${elapsed}m elapsed)`)
          } catch (e) {
            // Keep polling even if one request fails
            console.warn('Status poll failed, retrying...', e)
          }
          attempts++
        }
        
        if (status === 'failed') {
          throw new Error('File processing failed')
        }
        
        if (status !== 'completed') {
          throw new Error('Processing timed out after 30 minutes')
        }
        
      } else {
        // === STANDARD UPLOAD FOR SMALLER FILES ===
        setUploadStage('Uploading file...')
        
        const formData = new FormData()
        formData.append('file', shapefileFile)
        formData.append('name', shapefileName)
        formData.append('display_name', shapefileDisplayName)
        formData.append('description', shapefileDescription)
        formData.append('shapefile_type', shapefileType)
        formData.append('attribute_mappings', JSON.stringify(validMappings))
        
        if (shapefileAnalysis?.shapefiles_found && shapefileAnalysis.shapefiles_found.length > 1) {
          formData.append('layer_name', shapefileAnalysis.shapefiles_found[selectedShapefileIndex].name)
        }

        await dataApi.uploadShapefile(formData, (percent) => {
          setUploadProgress(percent)
          setUploadStage(`Uploading... ${percent}%`)
        })
        
        setUploadStage('Processing complete!')
      }
      
      // Reset form
      setShapefileModalOpen(false)
      setShapefileName('')
      setShapefileDisplayName('')
      setShapefileDescription('')
      setShapefileFile(null)
      setShapefileAnalysis(null)
      setShapefileType('custom')
      setAttributeMappings([])
      setUploadProgress(0)
      setUploadStage('')
      setUploadJobId(null)
      
      loadData()
    } catch (error: any) {
      console.error('Failed to upload shapefile:', error)
      let errorMsg = 'Shapefile upload failed'
      if (error.response?.data?.detail) {
        const detail = error.response.data.detail
        if (Array.isArray(detail)) {
          // FastAPI validation errors are arrays of objects
          errorMsg = detail.map((e: any) => e.msg || JSON.stringify(e)).join(', ')
        } else if (typeof detail === 'string') {
          errorMsg = detail
        } else {
          errorMsg = JSON.stringify(detail)
        }
      } else if (error.message) {
        errorMsg = error.message
      }
      alert(errorMsg)
    } finally {
      setUploadingShapefile(false)
      setUploadProgress(0)
      setUploadStage('')
      setUploadJobId(null)
    }
  }

  const handleLoadShapefile = async (shapefileId: string) => {
    setLoadingShapefileId(shapefileId)
    try {
      await dataApi.loadShapefile(shapefileId)
      alert('Shapefile loaded successfully! Geometries are now in the database.')
      loadData()
    } catch (error: any) {
      const detail = error.response?.data?.detail
      const errorMsg = Array.isArray(detail) ? detail.map((e: any) => e.msg || JSON.stringify(e)).join(', ') : (detail || 'Failed to load shapefile')
      alert(errorMsg)
    } finally {
      setLoadingShapefileId(null)
    }
  }

  const handleDeleteShapefile = async (shapefileId: string) => {
    if (!confirm('Are you sure you want to delete this shapefile?')) return
    
    try {
      await dataApi.deleteShapefile(shapefileId)
      loadData()
    } catch (error: any) {
      const detail = error.response?.data?.detail
      const errorMsg = Array.isArray(detail) ? detail.map((e: any) => e.msg || JSON.stringify(e)).join(', ') : (detail || 'Failed to delete shapefile')
      alert(errorMsg)
    }
  }

  const loadEnhancementPreview = async (locationTypeId: string) => {
    try {
      const response = await dataApi.getEnhancementPreview(locationTypeId)
      setEnhancementPreview(response.data)
    } catch (error) {
      console.error('Failed to load enhancement preview:', error)
    }
  }

  const handleStartEnhancement = async () => {
    if (!enhancementPreview) return
    
    setStartingEnhancement(true)
    try {
      await dataApi.startEnhancement({
        location_type_id: enhancementPreview.location_type_id,
        enhance_council: enhanceCouncil,
        enhance_road: enhanceRoad,
        enhance_authority: enhanceAuthority
      })
      
      loadData()
      setEnhancementPreview(null)
    } catch (error: any) {
      const detail = error.response?.data?.detail
      const errorMsg = Array.isArray(detail) ? detail.map((e: any) => e.msg || JSON.stringify(e)).join(', ') : (detail || 'Failed to start enhancement')
      alert(errorMsg)
    } finally {
      setStartingEnhancement(false)
    }
  }

  if (loading) return <Loading />

  return (
    <>
      <h1 className="govuk-heading-xl" style={{ marginBottom: '8px' }}>Data Management</h1>
      <p className="govuk-body-l" style={{ color: '#6b7280', marginBottom: '32px' }}>
        Upload location data, manage shapefiles, and enhance your datasets
      </p>

      {/* Improved Tab Navigation */}
      <div className="data-management-tabs">
        <nav className="data-management-tabs__nav">
          <button
            className={`data-management-tabs__button ${activeTab === 'upload' ? 'data-management-tabs__button--active' : ''}`}
            onClick={() => setActiveTab('upload')}
          >
            <UploadIcon />
            <span>Upload Data</span>
            {locationTypes.length > 0 && (
              <span className="data-management-tabs__badge">{locationTypes.length}</span>
            )}
          </button>
          <button
            className={`data-management-tabs__button ${activeTab === 'shapefiles' ? 'data-management-tabs__button--active' : ''}`}
            onClick={() => setActiveTab('shapefiles')}
          >
            <MapIcon />
            <span>Shapefiles</span>
            {shapefiles.length > 0 && (
              <span className="data-management-tabs__badge">{shapefiles.length}</span>
            )}
          </button>
          <button
            className={`data-management-tabs__button ${activeTab === 'enhance' ? 'data-management-tabs__button--active' : ''}`}
            onClick={() => setActiveTab('enhance')}
          >
            <EnhanceIcon />
            <span>Enhance Data</span>
            {enhancementJobs.filter(j => j.status === 'running').length > 0 && (
              <span className="data-management-tabs__badge" style={{ background: '#f59e0b' }}>
                {enhancementJobs.filter(j => j.status === 'running').length} active
              </span>
            )}
          </button>
        </nav>

        <div className="data-management-tabs__content">
          {/* Upload Tab */}
          {activeTab === 'upload' && (
            <div>
              <div className="govuk-grid-row">
                {/* Location Types */}
                <div className="govuk-grid-column-one-third">
                  <h2 className="govuk-heading-m">Location Types</h2>
                  <p className="govuk-body" style={{ color: '#6b7280' }}>
                    Select or create a location type before uploading data.
                  </p>
                  
                  {locationTypes.length === 0 ? (
                    <div className="govuk-inset-text">
                      No location types created yet. Create one to get started.
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      {locationTypes.map((type) => (
                        <div 
                          key={type.id} 
                          className={`task-card ${selectedType === type.id ? 'task-card--in-progress' : ''}`}
                          style={{ cursor: 'pointer' }}
                          onClick={() => setSelectedType(type.id)}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                            <div>
                              <h3 className="govuk-heading-s" style={{ marginBottom: '4px' }}>{type.display_name}</h3>
                              <p className="govuk-body" style={{ marginBottom: '8px', color: '#6b7280' }}>
                                {type.location_count.toLocaleString()} locations
                              </p>
                            </div>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation()
                                handleDeleteLocationType(type.id, type.display_name, type.location_count)
                              }}
                              style={{
                                background: 'none',
                                border: 'none',
                                color: '#dc2626',
                                cursor: 'pointer',
                                padding: '4px 8px',
                                fontSize: '14px',
                                borderRadius: '4px',
                                transition: 'background-color 0.15s'
                              }}
                              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#fef2f2'}
                              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                              title="Delete location type"
                            >
                              🗑️
                            </button>
                          </div>
                          <Link 
                            to={`/data?type=${type.id}`}
                            className="govuk-link"
                            onClick={(e) => e.stopPropagation()}
                            style={{ fontSize: '14px' }}
                          >
                            View data →
                          </Link>
                        </div>
                      ))}
                    </div>
                  )}
                  
                  <button
                    className="govuk-button govuk-button--secondary"
                    onClick={() => setCreateModalOpen(true)}
                    style={{ marginTop: '20px', width: '100%' }}
                  >
                    + Create New Type
                  </button>
                </div>

                {/* Upload Form */}
                <div className="govuk-grid-column-two-thirds">
                  <h2 className="govuk-heading-m">Upload Spreadsheet</h2>
                  <p className="govuk-body" style={{ color: '#6b7280', marginBottom: '24px' }}>
                    Upload Excel (.xlsx, .xls) or CSV files containing location data with latitude and longitude columns.
                  </p>

                  <form onSubmit={handleUpload}>
                    <div className="govuk-form-group">
                      <label className="govuk-label" htmlFor="locationType">
                        Location Type
                      </label>
                      <p className="govuk-hint">Select the type of locations you're uploading</p>
                      <select
                        className="govuk-select"
                        id="locationType"
                        value={selectedType}
                        onChange={(e) => setSelectedType(e.target.value)}
                        required
                        style={{ maxWidth: '100%' }}
                      >
                        <option value="">-- Select a location type --</option>
                        {locationTypes.map((type) => (
                          <option key={type.id} value={type.id}>
                            {type.display_name} ({type.location_count.toLocaleString()} existing)
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="govuk-form-group">
                      <label className="govuk-label" htmlFor="file">
                        Spreadsheet File
                      </label>
                      <p className="govuk-hint">Excel or CSV file with location data</p>
                      <input
                        className="govuk-file-upload"
                        id="file"
                        type="file"
                        accept=".xlsx,.xls,.csv"
                        onChange={(e) => setFile(e.target.files?.[0] || null)}
                        required
                      />
                      {file && (
                        <p className="govuk-body" style={{ marginTop: '8px', color: '#10b981' }}>
                          ✓ Selected: {file.name}
                        </p>
                      )}
                    </div>

                    <details className="govuk-details">
                      <summary className="govuk-details__summary">
                        <span className="govuk-details__summary-text">Column mapping options</span>
                      </summary>
                      <div className="govuk-details__text">
                        <p className="govuk-body" style={{ marginBottom: '16px' }}>
                          Specify the column names in your spreadsheet that contain the required data.
                        </p>
                        <div className="govuk-form-group">
                          <label className="govuk-label" htmlFor="latColumn">Latitude column name</label>
                          <input className="govuk-input" id="latColumn" value={latColumn} onChange={(e) => setLatColumn(e.target.value)} style={{ maxWidth: '300px' }} />
                        </div>
                        <div className="govuk-form-group">
                          <label className="govuk-label" htmlFor="lngColumn">Longitude column name</label>
                          <input className="govuk-input" id="lngColumn" value={lngColumn} onChange={(e) => setLngColumn(e.target.value)} style={{ maxWidth: '300px' }} />
                        </div>
                        <div className="govuk-form-group">
                          <label className="govuk-label" htmlFor="identifierColumn">Identifier column name</label>
                          <p className="govuk-hint">e.g., ATCOCode for bus stops</p>
                          <input className="govuk-input" id="identifierColumn" value={identifierColumn} onChange={(e) => setIdentifierColumn(e.target.value)} style={{ maxWidth: '300px' }} />
                        </div>
                      </div>
                    </details>

                    <button type="submit" className="govuk-button" disabled={uploading || !file || !selectedType}>
                      {uploading ? 'Uploading...' : 'Upload Spreadsheet'}
                    </button>
                  </form>

                  {/* Upload Progress */}
                  {uploadJobStatus && uploadJobStatus.status !== 'completed' && (
                    <div style={{ 
                      marginTop: '24px', 
                      background: '#f0f9ff', 
                      border: '1px solid #3b82f6',
                      borderRadius: '8px',
                      padding: '20px'
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', marginBottom: '12px' }}>
                        <div className="loading-spinner__icon" style={{ 
                          width: '24px', 
                          height: '24px', 
                          marginRight: '12px',
                          borderWidth: '3px'
                        }} />
                        <p className="govuk-body" style={{ margin: 0, fontWeight: 600 }}>
                          {uploadJobStatus.stage || 'Processing...'}
                        </p>
                      </div>
                      <div className="progress-bar" style={{ height: '12px', marginBottom: '8px' }}>
                        <div 
                          className="progress-bar__fill" 
                          style={{ width: `${uploadJobStatus.progress_percent}%` }}
                        />
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span className="govuk-body-s" style={{ color: '#6b7280' }}>
                          {uploadJobStatus.progress_percent}% complete
                        </span>
                        {uploadJobStatus.total_rows && (
                          <span className="govuk-body-s" style={{ color: '#6b7280' }}>
                            {uploadJobStatus.locations_created?.toLocaleString() || 0} / {uploadJobStatus.total_rows.toLocaleString()} rows
                          </span>
                        )}
                      </div>
                      {uploadJobStatus.status === 'failed' && uploadJobStatus.error_message && (
                        <div style={{ marginTop: '12px', color: '#dc2626' }}>
                          Error: {uploadJobStatus.error_message}
                        </div>
                      )}
                    </div>
                  )}

                  {uploadResult && (
                    <div className="govuk-panel govuk-panel--confirmation" style={{ marginTop: '24px' }}>
                      <h2 className="govuk-panel__title">Upload Complete</h2>
                      <div className="govuk-panel__body">
                        {(uploadResult.locations_created || 0).toLocaleString()} locations created
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Shapefiles Tab */}
          {activeTab === 'shapefiles' && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
                <div>
                  <h2 className="govuk-heading-m" style={{ marginBottom: '8px' }}>Spatial Data Files</h2>
                  <p className="govuk-body" style={{ color: '#6b7280', maxWidth: '700px' }}>
                    Upload Ordnance Survey or other spatial data to enable location enhancement.
                    Supported formats: <strong>Shapefile ZIP</strong> (.shp, .shx, .dbf, .prj in a ZIP) or <strong>GeoPackage</strong> (.gpkg).
                  </p>
                </div>
                <button className="govuk-button" onClick={() => setShapefileModalOpen(true)}>
                  + Upload Shapefile
                </button>
              </div>

              {shapefiles.length === 0 ? (
                <div className="govuk-inset-text">
                  <strong>No shapefiles uploaded yet.</strong><br/>
                  Upload shapefiles to enable data enhancement with council boundaries, road classifications, and combined authorities.
                </div>
              ) : (
              <table className="govuk-table">
                <thead className="govuk-table__head">
                  <tr className="govuk-table__row">
                    <th className="govuk-table__header" style={{ width: '22%' }}>Name</th>
                    <th className="govuk-table__header" style={{ width: '12%' }}>Type</th>
                    <th className="govuk-table__header" style={{ width: '10%' }}>Features</th>
                    <th className="govuk-table__header" style={{ width: '28%' }}>Columns Added</th>
                    <th className="govuk-table__header" style={{ width: '10%' }}>Status</th>
                    <th className="govuk-table__header" style={{ width: '18%' }}>Actions</th>
                  </tr>
                </thead>
                <tbody className="govuk-table__body">
                  {shapefiles.map((sf) => {
                    // Get columns from attribute_mappings or fall back to type-based
                    const columns = sf.attribute_mappings && sf.attribute_mappings.length > 0
                      ? sf.attribute_mappings.map((m: any) => m.target_column)
                      : sf.shapefile_type === 'council_boundaries' ? ['council']
                      : sf.shapefile_type === 'combined_authorities' ? ['combined_authority']
                      : sf.shapefile_type === 'road_classifications' ? ['road_classification']
                      : [sf.shapefile_type]
                    
                    return (
                      <tr key={sf.id} className="govuk-table__row">
                        <td className="govuk-table__cell">
                          <strong style={{ fontSize: '16px' }}>{sf.display_name}</strong>
                          {sf.description && <p className="govuk-body" style={{ margin: '4px 0 0', color: '#6b7280', fontSize: '14px' }}>{sf.description}</p>}
                        </td>
                        <td className="govuk-table__cell" style={{ textTransform: 'capitalize' }}>
                          {sf.shapefile_type.replace(/_/g, ' ')}
                        </td>
                        <td className="govuk-table__cell">
                          {sf.feature_count.toLocaleString()}
                        </td>
                        <td className="govuk-table__cell">
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                            {columns.map((col: string, i: number) => (
                              <code key={i} style={{ 
                                background: '#dbeafe', 
                                color: '#1e40af',
                                padding: '2px 8px',
                                borderRadius: '4px',
                                fontSize: '13px'
                              }}>
                                {col}
                              </code>
                            ))}
                          </div>
                          {sf.attribute_mappings && sf.attribute_mappings.length > 0 && (
                            <p className="govuk-body-s" style={{ margin: '4px 0 0', color: '#6b7280' }}>
                              From: {sf.attribute_mappings.map((m: any) => m.source_column).join(', ')}
                            </p>
                          )}
                        </td>
                        <td className="govuk-table__cell">
                          {sf.is_loaded ? (
                            <strong className="govuk-tag govuk-tag--green">Loaded</strong>
                          ) : (
                            <strong className="govuk-tag govuk-tag--grey">Not Loaded</strong>
                          )}
                        </td>
                        <td className="govuk-table__cell">
                          <div style={{ display: 'flex', gap: '16px' }}>
                            {!sf.is_loaded && (
                              <button 
                                className="govuk-link" 
                                style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '16px' }} 
                                onClick={() => handleLoadShapefile(sf.id)}
                                disabled={loadingShapefileId !== null}
                              >
                                {loadingShapefileId === sf.id ? 'Loading...' : 'Load'}
                              </button>
                            )}
                            <button 
                              className="govuk-link" 
                              style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', fontSize: '16px' }} 
                              onClick={() => handleDeleteShapefile(sf.id)}
                            >
                              Delete
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              )}

              <div className="govuk-inset-text" style={{ marginTop: '32px' }}>
                <h3 className="govuk-heading-s">Shapefile Types & Their Uses</h3>
                <ul className="govuk-list govuk-list--bullet">
                  <li><strong>Council Boundaries</strong> — Adds <code>council</code> column with local authority name based on location coordinates</li>
                  <li><strong>Combined Authorities</strong> — Adds <code>combined_authority</code> column (e.g., Greater Manchester, West Midlands)</li>
                  <li><strong>Road Classifications</strong> — Adds <code>road_classification</code> column (A/B/C roads) based on nearest road</li>
                </ul>
              </div>
            </div>
          )}

          {/* Enhance Tab */}
          {activeTab === 'enhance' && (
            <div>
              <h2 className="govuk-heading-m" style={{ marginBottom: '8px' }}>Enhance Location Data</h2>
              <p className="govuk-body" style={{ color: '#6b7280', marginBottom: '24px' }}>
                Add council boundaries, road classifications, and combined authority information to your location data using uploaded shapefiles.
              </p>

              {/* Running Jobs */}
              {enhancementJobs.filter(j => j.status === 'running' || j.status === 'pending').length > 0 && (
                <div style={{ marginBottom: '32px' }}>
                  <h3 className="govuk-heading-s" style={{ color: '#f59e0b' }}>⚡ Active Enhancement Jobs</h3>
                  {enhancementJobs.filter(j => j.status === 'running' || j.status === 'pending').map((job) => (
                    <div key={job.id} className="task-card task-card--in-progress">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                        <div>
                          <strong style={{ fontSize: '18px' }}>{locationTypes.find(lt => lt.id === job.location_type_id)?.display_name || 'Dataset'}</strong>
                          <span className="govuk-body" style={{ marginLeft: '12px', color: '#6b7280' }}>
                            {job.processed_locations.toLocaleString()} / {job.total_locations.toLocaleString()} locations
                          </span>
                        </div>
                        <strong className="govuk-tag govuk-tag--blue">{job.status.toUpperCase()}</strong>
                      </div>
                      <div className="progress-bar">
                        <div className="progress-bar__fill" style={{ width: `${job.progress_percent}%` }} />
                      </div>
                      <p className="govuk-body" style={{ marginTop: '8px', marginBottom: '0', color: '#6b7280' }}>
                        <strong>{job.progress_percent.toFixed(1)}%</strong> complete • {job.enhanced_locations.toLocaleString()} enhanced
                        {job.councils_found.length > 0 && (
                          <> • Found <strong>{job.councils_found.length}</strong> councils</>
                        )}
                      </p>
                    </div>
                  ))}
                </div>
              )}

              {/* Dataset Selection */}
              <div className="govuk-form-group" style={{ maxWidth: '500px' }}>
                <label className="govuk-label" htmlFor="enhanceDataset">Select dataset to enhance</label>
                <p className="govuk-hint">Choose a dataset to preview and start enhancement</p>
                <select
                  className="govuk-select"
                  id="enhanceDataset"
                  value={enhancementPreview?.location_type_id || ''}
                  onChange={(e) => e.target.value && loadEnhancementPreview(e.target.value)}
                  style={{ maxWidth: '100%' }}
                >
                  <option value="">-- Choose a dataset --</option>
                  {locationTypes.map((type) => (
                    <option key={type.id} value={type.id}>
                      {type.display_name} — {type.location_count.toLocaleString()} locations
                    </option>
                  ))}
                </select>
              </div>

              {/* Enhancement Preview */}
              {enhancementPreview && (
                <div style={{ marginTop: '32px' }}>
                  <h3 className="govuk-heading-m">Enhancement Preview: {enhancementPreview.location_type_name}</h3>
                  
                  <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', maxWidth: '500px', marginBottom: '32px' }}>
                    <div className="stat-card">
                      <span className="stat-card__value">{enhancementPreview.total_locations.toLocaleString()}</span>
                      <span className="stat-card__label">Total Locations</span>
                    </div>
                    <div className="stat-card">
                      <span className="stat-card__value" style={{ color: '#f59e0b' }}>{enhancementPreview.unenhanced_count.toLocaleString()}</span>
                      <span className="stat-card__label">To Be Enhanced</span>
                    </div>
                  </div>

                  {/* Columns to Add */}
                  <h4 className="govuk-heading-s">Columns that will be added:</h4>
                  <table className="govuk-table" style={{ marginBottom: '32px' }}>
                    <thead className="govuk-table__head">
                      <tr className="govuk-table__row">
                        <th className="govuk-table__header" style={{ width: '60px' }}>Add</th>
                        <th className="govuk-table__header">Column</th>
                        <th className="govuk-table__header">Description</th>
                        <th className="govuk-table__header">Shapefile Status</th>
                      </tr>
                    </thead>
                    <tbody className="govuk-table__body">
                      {enhancementPreview.columns_to_add.map((col) => (
                        <tr key={col.name} className="govuk-table__row">
                          <td className="govuk-table__cell">
                            <input
                              type="checkbox"
                              style={{ width: '22px', height: '22px', cursor: 'pointer' }}
                              checked={
                                col.name === 'council' ? enhanceCouncil :
                                col.name === 'road_classification' ? enhanceRoad :
                                enhanceAuthority
                              }
                              onChange={(e) => {
                                if (col.name === 'council') setEnhanceCouncil(e.target.checked)
                                else if (col.name === 'road_classification') setEnhanceRoad(e.target.checked)
                                else setEnhanceAuthority(e.target.checked)
                              }}
                              disabled={!col.shapefile_loaded}
                            />
                          </td>
                          <td className="govuk-table__cell"><code>{col.name}</code></td>
                          <td className="govuk-table__cell">{col.description}</td>
                          <td className="govuk-table__cell">
                            {col.shapefile_loaded ? (
                              <strong className="govuk-tag govuk-tag--green">Ready</strong>
                            ) : (
                              <strong className="govuk-tag govuk-tag--red">Missing Shapefile</strong>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  {/* Sample Data Preview */}
                  {enhancementPreview.sample_locations.length > 0 && (
                    <>
                      <h4 className="govuk-heading-s">Sample locations (before enhancement):</h4>
                      <div style={{ overflowX: 'auto' }}>
                        <table className="govuk-table" style={{ marginBottom: '32px' }}>
                          <thead className="govuk-table__head">
                            <tr className="govuk-table__row">
                              <th className="govuk-table__header">Identifier</th>
                              <th className="govuk-table__header">Latitude</th>
                              <th className="govuk-table__header">Longitude</th>
                              <th className="govuk-table__header">Council</th>
                              <th className="govuk-table__header">Authority</th>
                              <th className="govuk-table__header">Road</th>
                            </tr>
                          </thead>
                          <tbody className="govuk-table__body">
                            {enhancementPreview.sample_locations.map((loc, i) => (
                              <tr key={i} className="govuk-table__row">
                                <td className="govuk-table__cell"><code>{loc.identifier}</code></td>
                                <td className="govuk-table__cell">{loc.latitude.toFixed(4)}</td>
                                <td className="govuk-table__cell">{loc.longitude.toFixed(4)}</td>
                                <td className="govuk-table__cell">{loc.council || <span style={{ color: '#9ca3af' }}>—</span>}</td>
                                <td className="govuk-table__cell">{loc.combined_authority || <span style={{ color: '#9ca3af' }}>—</span>}</td>
                                <td className="govuk-table__cell">{loc.road_classification || <span style={{ color: '#9ca3af' }}>—</span>}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </>
                  )}

                  {/* Warning if no shapefiles */}
                  {!enhancementPreview.columns_to_add.some(c => c.shapefile_loaded) && (
                    <div className="govuk-warning-text">
                      <span className="govuk-warning-text__icon" aria-hidden="true">!</span>
                      <strong className="govuk-warning-text__text">
                        No shapefiles are loaded. Upload and load shapefiles in the Shapefiles tab first.
                      </strong>
                    </div>
                  )}

                  <button
                    className="govuk-button"
                    onClick={handleStartEnhancement}
                    disabled={startingEnhancement || enhancementPreview.unenhanced_count === 0 || !enhancementPreview.columns_to_add.some(c => c.shapefile_loaded)}
                    style={{ marginTop: '16px' }}
                  >
                    {startingEnhancement ? 'Starting Enhancement...' : `Start Enhancement (${enhancementPreview.unenhanced_count.toLocaleString()} locations)`}
                  </button>
                </div>
              )}

              {/* Past Jobs */}
              {enhancementJobs.filter(j => j.status === 'completed' || j.status === 'failed').length > 0 && (
                <div style={{ marginTop: '48px' }}>
                  <h3 className="govuk-heading-s">Recent Enhancement Jobs</h3>
                  <table className="govuk-table">
                    <thead className="govuk-table__head">
                      <tr className="govuk-table__row">
                        <th className="govuk-table__header">Dataset</th>
                        <th className="govuk-table__header">Locations</th>
                        <th className="govuk-table__header">Enhanced</th>
                        <th className="govuk-table__header">Status</th>
                        <th className="govuk-table__header">Completed</th>
                      </tr>
                    </thead>
                    <tbody className="govuk-table__body">
                      {enhancementJobs.filter(j => j.status === 'completed' || j.status === 'failed').slice(0, 5).map((job) => (
                        <tr key={job.id} className="govuk-table__row">
                          <td className="govuk-table__cell">{locationTypes.find(lt => lt.id === job.location_type_id)?.display_name || '—'}</td>
                          <td className="govuk-table__cell">{job.total_locations.toLocaleString()}</td>
                          <td className="govuk-table__cell">{job.enhanced_locations.toLocaleString()}</td>
                          <td className="govuk-table__cell">
                            {job.status === 'completed' ? (
                              <strong className="govuk-tag govuk-tag--green">Completed</strong>
                            ) : (
                              <strong className="govuk-tag govuk-tag--red">Failed</strong>
                            )}
                          </td>
                          <td className="govuk-table__cell">
                            {job.completed_at && new Date(job.completed_at).toLocaleString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Create Type Modal */}
      <Modal isOpen={createModalOpen} onClose={() => setCreateModalOpen(false)} title="Create Location Type">
        <div className="govuk-form-group">
          <label className="govuk-label" htmlFor="newTypeName">Internal name</label>
          <p className="govuk-hint">Lowercase with underscores, e.g., bus_stops</p>
          <input className="govuk-input" id="newTypeName" value={newTypeName} onChange={(e) => setNewTypeName(e.target.value)} placeholder="e.g. bus_stops" />
        </div>
        <div className="govuk-form-group">
          <label className="govuk-label" htmlFor="newTypeDisplayName">Display name</label>
          <p className="govuk-hint">Human-readable name shown in the interface</p>
          <input className="govuk-input" id="newTypeDisplayName" value={newTypeDisplayName} onChange={(e) => setNewTypeDisplayName(e.target.value)} placeholder="e.g. Bus Stops" />
        </div>
        <div className="govuk-form-group">
          <label className="govuk-label" htmlFor="newTypeDescription">Description (optional)</label>
          <textarea className="govuk-textarea" id="newTypeDescription" rows={3} value={newTypeDescription} onChange={(e) => setNewTypeDescription(e.target.value)} placeholder="Brief description of this location type" />
        </div>
        <div className="govuk-button-group">
          <button className="govuk-button" onClick={handleCreateType} disabled={!newTypeName || !newTypeDisplayName}>
            Create Type
          </button>
          <button className="govuk-button govuk-button--secondary" onClick={() => setCreateModalOpen(false)}>
            Cancel
          </button>
        </div>
      </Modal>

      {/* Shapefile Upload Modal */}
      <Modal isOpen={shapefileModalOpen} onClose={() => {
        setShapefileModalOpen(false)
        setShapefileAnalysis(null)
        setShapefileFile(null)
      }} title="Upload Shapefile">
        {/* Step 1: Upload and Analyze */}
        <div className="govuk-form-group">
          <label className="govuk-label" htmlFor="shapefileFile">
            <strong>Step 1:</strong> Select Spatial Data File
          </label>
          <p className="govuk-hint">
            Supported formats:<br/>
            • <strong>Shapefile ZIP</strong> (.zip) - containing .shp, .shx, .dbf, .prj files<br/>
            • <strong>GeoPackage</strong> (.gpkg) - SQLite-based geospatial format
          </p>
          <input 
            className="govuk-file-upload" 
            id="shapefileFile" 
            type="file" 
            accept=".zip,.gpkg" 
            onChange={(e) => {
              const file = e.target.files?.[0] || null
              setShapefileFile(file)
              if (file) {
                handleAnalyzeShapefile(file)
              } else {
                setShapefileAnalysis(null)
              }
            }} 
          />
          {analyzingShapefile && (
            <p className="govuk-body" style={{ marginTop: '8px', color: '#2563eb' }}>
              ⏳ Analyzing file...
            </p>
          )}
        </div>

        {/* Step 2: Analysis Results */}
        {shapefileAnalysis && shapefileAnalysis.shapefiles_found.length > 0 && (
          <>
            <div style={{ 
              background: '#f0fdf4', 
              border: '1px solid #10b981', 
              borderRadius: '8px', 
              padding: '16px', 
              marginBottom: '20px' 
            }}>
              <p className="govuk-body" style={{ margin: 0, color: '#166534' }}>
                ✓ <strong>{shapefileAnalysis.file_type === 'geopackage' ? 'GeoPackage' : 'Shapefile'}</strong>: Found{' '}
                <strong>{shapefileAnalysis.shapefiles_found.length}</strong>{' '}
                {shapefileAnalysis.file_type === 'geopackage' ? 'layer(s)' : 'shapefile(s)'} with{' '}
                <strong>{shapefileAnalysis.shapefiles_found[selectedShapefileIndex]?.feature_count.toLocaleString()}</strong> features
                {shapefileAnalysis.shapefiles_found[selectedShapefileIndex]?.geometry_type && (
                  <> • Geometry: <strong>{shapefileAnalysis.shapefiles_found[selectedShapefileIndex].geometry_type}</strong></>
                )}
              </p>
            </div>

            {/* Layer/Shapefile selector (if multiple) */}
            {shapefileAnalysis.shapefiles_found.length > 1 && (
              <div className="govuk-form-group">
                <label className="govuk-label">
                  Select {shapefileAnalysis.file_type === 'geopackage' ? 'layer' : 'shapefile'} to import
                </label>
                <select 
                  className="govuk-select" 
                  value={selectedShapefileIndex}
                  onChange={(e) => {
                    const idx = parseInt(e.target.value)
                    setSelectedShapefileIndex(idx)
                    // Reset attribute selection
                    const attrs = Object.keys(shapefileAnalysis.shapefiles_found[idx]?.attributes || {})
                    setShapefileNameColumn(attrs[0] || '')
                  }}
                >
                  {shapefileAnalysis.shapefiles_found.map((shp, idx) => (
                    <option key={idx} value={idx}>
                      {shp.name} ({shp.feature_count.toLocaleString()} features, {shp.geometry_type})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Step 2: Configure */}
            <h3 className="govuk-heading-s" style={{ marginTop: '24px' }}>
              <strong>Step 2:</strong> Configure Shapefile
            </h3>

            <div className="govuk-form-group">
              <label className="govuk-label" htmlFor="shapefileName">Internal name</label>
              <p className="govuk-hint">Unique identifier, lowercase with underscores</p>
              <input 
                className="govuk-input" 
                id="shapefileName" 
                value={shapefileName} 
                onChange={(e) => setShapefileName(e.target.value)} 
                placeholder="e.g. uk_councils_2024" 
              />
            </div>

            <div className="govuk-form-group">
              <label className="govuk-label" htmlFor="shapefileDisplayName">Display name</label>
              <input 
                className="govuk-input" 
                id="shapefileDisplayName" 
                value={shapefileDisplayName} 
                onChange={(e) => setShapefileDisplayName(e.target.value)} 
                placeholder="e.g. UK Council Boundaries 2024" 
              />
            </div>

            <div className="govuk-form-group">
              <label className="govuk-label" htmlFor="shapefileType">Category</label>
              <p className="govuk-hint">Categorize this spatial data file</p>
              <select 
                className="govuk-select" 
                id="shapefileType" 
                value={shapefileType} 
                onChange={(e) => setShapefileType(e.target.value)}
              >
                <option value="custom">Custom / Multi-attribute</option>
                <option value="council_boundaries">Council Boundaries</option>
                <option value="combined_authorities">Combined Authorities</option>
                <option value="road_classifications">Road Classifications</option>
              </select>
            </div>

            {/* Multiple Attribute Mappings */}
            <div className="govuk-form-group">
              <label className="govuk-label">
                <strong>Step 3:</strong> Select Attributes to Extract
              </label>
              <p className="govuk-hint">
                Add one or more attributes from this file. Each attribute will become a new column in your location data.
              </p>
              
              {attributeMappings.length === 0 ? (
                <div style={{ 
                  background: '#f9fafb', 
                  border: '2px dashed #d1d5db', 
                  borderRadius: '8px', 
                  padding: '24px',
                  textAlign: 'center',
                  marginBottom: '16px'
                }}>
                  <p className="govuk-body" style={{ margin: 0, color: '#6b7280' }}>
                    No attributes selected. Click the button below to add attributes.
                  </p>
                </div>
              ) : (
                <div style={{ marginBottom: '16px' }}>
                  {attributeMappings.map((mapping, idx) => (
                    <div 
                      key={idx} 
                      style={{ 
                        display: 'grid',
                        gridTemplateColumns: '1fr auto 1fr auto',
                        gap: '12px',
                        alignItems: 'end',
                        marginBottom: '12px',
                        padding: '16px',
                        background: '#f9fafb',
                        borderRadius: '8px',
                        border: '1px solid #e5e7eb'
                      }}
                    >
                      <div>
                        <label className="govuk-label" style={{ fontSize: '14px', marginBottom: '4px' }}>
                          Source Attribute
                        </label>
                        <select
                          className="govuk-select"
                          value={mapping.source_column}
                          onChange={(e) => updateAttributeMapping(idx, 'source_column', e.target.value)}
                          style={{ width: '100%' }}
                        >
                          <option value="">-- Select --</option>
                          {Object.entries(shapefileAnalysis.shapefiles_found[selectedShapefileIndex]?.attributes || {}).map(([attrName, attrInfo]) => (
                            <option key={attrName} value={attrName}>
                              {attrName} ({(attrInfo as any).type})
                            </option>
                          ))}
                        </select>
                        {mapping.source_column && shapefileAnalysis.shapefiles_found[selectedShapefileIndex]?.sample_values?.[mapping.source_column] && (
                          <p className="govuk-hint" style={{ fontSize: '12px', margin: '4px 0 0' }}>
                            e.g. {shapefileAnalysis.shapefiles_found[selectedShapefileIndex].sample_values[mapping.source_column].slice(0, 2).join(', ')}
                          </p>
                        )}
                      </div>
                      
                      <span style={{ paddingBottom: '12px', color: '#6b7280', fontSize: '20px' }}>→</span>
                      
                      <div>
                        <label className="govuk-label" style={{ fontSize: '14px', marginBottom: '4px' }}>
                          Target Column Name
                        </label>
                        <input
                          className="govuk-input"
                          type="text"
                          value={mapping.target_column}
                          onChange={(e) => updateAttributeMapping(idx, 'target_column', e.target.value.toLowerCase().replace(/\s+/g, '_'))}
                          placeholder="e.g. council"
                          style={{ width: '100%' }}
                        />
                      </div>
                      
                      <button
                        type="button"
                        onClick={() => removeAttributeMapping(idx)}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: '#ef4444',
                          cursor: 'pointer',
                          padding: '8px',
                          fontSize: '20px',
                          lineHeight: 1
                        }}
                        title="Remove"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              )}
              
              <button
                type="button"
                className="govuk-button govuk-button--secondary"
                onClick={addAttributeMapping}
                style={{ marginBottom: 0 }}
              >
                + Add Attribute
              </button>
            </div>

            {/* Summary of what will be added */}
            {attributeMappings.filter(m => m.source_column && m.target_column).length > 0 && (
              <div style={{ 
                background: '#f0fdf4', 
                border: '1px solid #10b981', 
                borderRadius: '8px', 
                padding: '16px',
                marginBottom: '20px'
              }}>
                <p className="govuk-body-s" style={{ margin: 0, fontWeight: 600, color: '#166534' }}>
                  Columns to be added to your location data:
                </p>
                <ul style={{ margin: '8px 0 0', paddingLeft: '20px' }}>
                  {attributeMappings.filter(m => m.source_column && m.target_column).map((m, i) => (
                    <li key={i} className="govuk-body" style={{ margin: '4px 0', color: '#166534' }}>
                      <code style={{ background: '#dcfce7' }}>{m.target_column}</code> ← {m.source_column}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="govuk-form-group">
              <label className="govuk-label" htmlFor="shapefileDescription">Description (optional)</label>
              <textarea 
                className="govuk-textarea" 
                id="shapefileDescription" 
                rows={2} 
                value={shapefileDescription} 
                onChange={(e) => setShapefileDescription(e.target.value)} 
                placeholder="Brief description of this shapefile" 
              />
            </div>

            {/* Progress bar during upload */}
            {uploadingShapefile && (
              <div style={{ 
                marginBottom: '20px', 
                background: '#f0f9ff', 
                border: '1px solid #3b82f6',
                borderRadius: '8px',
                padding: '20px'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', marginBottom: '12px' }}>
                  <div className="loading-spinner__icon" style={{ 
                    width: '24px', 
                    height: '24px', 
                    marginRight: '12px',
                    borderWidth: '3px'
                  }} />
                  <p className="govuk-body" style={{ margin: 0, fontWeight: 600 }}>
                    {uploadStage || 'Processing...'}
                  </p>
                </div>
                <div className="progress-bar" style={{ height: '12px', marginBottom: '8px' }}>
                  <div 
                    className="progress-bar__fill" 
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span className="govuk-body-s" style={{ color: '#6b7280' }}>
                    {uploadProgress}% complete
                  </span>
                  {shapefileFile && (
                    <span className="govuk-body-s" style={{ color: '#6b7280' }}>
                      {(shapefileFile.size / (1024*1024)).toFixed(1)} MB total
                    </span>
                  )}
                </div>
                <p className="govuk-body-s" style={{ color: '#6b7280', marginTop: '12px', marginBottom: 0 }}>
                  {shapefileFile && shapefileFile.size > 100 * 1024 * 1024 
                    ? '⚡ Large file detected - using chunked upload for reliability'
                    : 'After upload, you\'ll need to "Load" the shapefile to import geometries into the database.'
                  }
                </p>
              </div>
            )}

            <div className="govuk-button-group">
              <button 
                className="govuk-button" 
                onClick={handleShapefileUpload} 
                disabled={
                  uploadingShapefile || 
                  !shapefileFile || 
                  !shapefileName || 
                  !shapefileDisplayName ||
                  attributeMappings.filter(m => m.source_column && m.target_column).length === 0
                }
              >
                {uploadingShapefile ? (uploadStage || `Uploading... ${uploadProgress}%`) : `Upload with ${attributeMappings.filter(m => m.source_column && m.target_column).length} Attribute(s)`}
              </button>
              <button 
                className="govuk-button govuk-button--secondary" 
                onClick={() => {
                  setShapefileModalOpen(false)
                  setShapefileAnalysis(null)
                  setShapefileFile(null)
                  setAttributeMappings([])
                }}
                disabled={uploadingShapefile}
              >
                Cancel
              </button>
            </div>
          </>
        )}

        {/* No shapefile selected yet */}
        {!shapefileFile && !analyzingShapefile && (
          <div className="govuk-inset-text">
            Select a ZIP file containing your shapefile to see available attributes.
          </div>
        )}
      </Modal>
    </>
  )
}
