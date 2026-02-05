import { useEffect, useState, useRef, useCallback } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { labellingApi, tasksApi, commentsApi } from '../services/api'
import Loading from '../components/common/Loading'
import ProgressBar from '../components/common/ProgressBar'
import { Loader } from '@googlemaps/js-api-loader'
import { useAuthStore } from '../store/authStore'

interface Comment {
  id: string
  author_name: string
  content: string
  comment_type: string
  is_read: boolean
  is_resolved: boolean
  created_at: string
  replies: Comment[]
}

interface LocationData {
  id: string
  identifier: string
  latitude: number
  longitude: number
  council: string | null
  road_name: string | null
  locality: string | null
  road_classification: string | null
  combined_authority: string | null
  original_data: Record<string, any> | null
  index: number
  total: number
  images: {
    id: string
    heading: number
    gcs_url: string
    capture_date: string | null
    is_user_snapshot: boolean
  }[]
  label: {
    advertising_present: boolean | null
    bus_shelter_present: boolean | null
    number_of_panels: number | null
    pole_stop: boolean | null
    unmarked_stop: boolean | null
    selected_image: number | null
    notes: string | null
    unable_to_label: boolean
    unable_reason: string | null
  } | null
  label_fields: any
}

interface LabelFormData {
  advertising_present: boolean | null
  bus_shelter_present: boolean | null
  number_of_panels: number | null
  pole_stop: boolean | null
  shelter_stop: boolean | null
  unmarked_stop: boolean | null
  selected_image: number | null
  notes: string
  unable_to_label: boolean
  unable_reason: string
}

const defaultLabelData: LabelFormData = {
  advertising_present: null,
  bus_shelter_present: null,
  number_of_panels: null,
  pole_stop: null,
  shelter_stop: null,
  unmarked_stop: null,
  selected_image: null,
  notes: '',
  unable_to_label: false,
  unable_reason: '',
}

interface LabellingPageProps {
  isQualityControl?: boolean
}

export default function LabellingPage({ isQualityControl = false }: LabellingPageProps) {
  const { taskId, locationIndex: urlLocationIndex } = useParams<{ taskId: string; locationIndex?: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { user } = useAuthStore()
  
  const isManager = user?.role === 'manager' || user?.role === 'admin'
  
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [location, setLocation] = useState<LocationData | null>(null)
  const [formData, setFormData] = useState<LabelFormData>(defaultLabelData)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [streetViewDate, setStreetViewDate] = useState<string | null>(null)
  const [gsvError, setGsvError] = useState<string | null>(null)
  const [mapsLoaded, setMapsLoaded] = useState(false)
  const [showSnapshotsModal, setShowSnapshotsModal] = useState(false)
  const [sidebarHidden, setSidebarHidden] = useState(false)
  const [expandedImage, setExpandedImage] = useState<{ url: string; title: string; zoom: number } | null>(null)
  const [labelledLocations, setLabelledLocations] = useState<any[]>([])
  const [showLabelledDropdown, setShowLabelledDropdown] = useState(false)
  
  // Comments state (for QC mode)
  const [comments, setComments] = useState<Comment[]>([])
  const [newComment, setNewComment] = useState('')
  const [showComments, setShowComments] = useState(false)
  const [labelId, setLabelId] = useState<string | null>(null)
  
  // Drag-to-zoom state
  const [zoomBoxes, setZoomBoxes] = useState<{ [key: string]: { x: number; y: number; width: number; height: number } }>({})
  const [dragState, setDragState] = useState<{
    imageKey: string;
    startX: number;
    startY: number;
    currentX: number;
    currentY: number;
    isDragging: boolean;
  } | null>(null)
  
  // Handle drag-to-zoom
  const handleZoomDragStart = (e: React.MouseEvent<HTMLDivElement>, imageKey: string) => {
    e.preventDefault()
    const rect = e.currentTarget.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * 100
    const y = ((e.clientY - rect.top) / rect.height) * 100
    setDragState({
      imageKey,
      startX: x,
      startY: y,
      currentX: x,
      currentY: y,
      isDragging: true
    })
  }
  
  const handleZoomDragMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!dragState || !dragState.isDragging) return
    const rect = e.currentTarget.getBoundingClientRect()
    const x = Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100))
    const y = Math.max(0, Math.min(100, ((e.clientY - rect.top) / rect.height) * 100))
    setDragState({ ...dragState, currentX: x, currentY: y })
  }
  
  const handleZoomDragEnd = () => {
    if (!dragState || !dragState.isDragging) return
    const { imageKey, startX, startY, currentX, currentY } = dragState
    const minX = Math.min(startX, currentX)
    const minY = Math.min(startY, currentY)
    const width = Math.abs(currentX - startX)
    const height = Math.abs(currentY - startY)
    
    // Only apply zoom if the box is large enough (at least 10% in both dimensions)
    if (width > 10 && height > 10) {
      setZoomBoxes({ ...zoomBoxes, [imageKey]: { x: minX, y: minY, width, height } })
    }
    setDragState(null)
  }
  
  const resetZoom = (imageKey: string, e: React.MouseEvent) => {
    e.stopPropagation()
    const newZoomBoxes = { ...zoomBoxes }
    delete newZoomBoxes[imageKey]
    setZoomBoxes(newZoomBoxes)
  }
  
  // Handle sidebar visibility by adding/removing class on body
  useEffect(() => {
    if (sidebarHidden) {
      document.body.classList.add('sidebar-hidden')
    } else {
      document.body.classList.remove('sidebar-hidden')
    }
    return () => {
      document.body.classList.remove('sidebar-hidden')
    }
  }, [sidebarHidden])
  
  const streetViewRef = useRef<HTMLDivElement>(null)
  const panoramaRef = useRef<google.maps.StreetViewPanorama | null>(null)
  
  // Load Google Maps API
  useEffect(() => {
    const apiKey = import.meta.env.VITE_GSV_API_KEY as string | undefined
    
    // If no API key, show a message to the user
    if (!apiKey) {
      console.warn('Google Maps API key not configured (VITE_GSV_API_KEY)')
      setGsvError('Google Maps API key not configured. Please contact your administrator to enable interactive Street View.')
      return
    }
    
    try {
      const loader = new Loader({
        apiKey,
        version: 'weekly',
      })
      
      loader.load().then(() => {
        console.log('Google Maps API loaded successfully')
        setMapsLoaded(true)
      }).catch((err: Error) => {
        console.error('Failed to load Google Maps API:', err)
        setGsvError('Failed to load Google Maps API. Please check the API key.')
      })
    } catch (err) {
      console.error('Error initializing Google Maps loader:', err)
      setGsvError('Failed to initialize Google Maps. Please try refreshing the page.')
    }
  }, [])

  // Set initial index from URL params (QC mode or query string)
  useEffect(() => {
    const indexFromUrl = urlLocationIndex ? parseInt(urlLocationIndex, 10) : null
    const indexFromQuery = searchParams.get('index') ? parseInt(searchParams.get('index')!, 10) : null
    const initialIndex = indexFromUrl ?? indexFromQuery ?? 0
    setCurrentIndex(initialIndex)
  }, [urlLocationIndex, searchParams])
  
  useEffect(() => {
    if (taskId) {
      if (!isQualityControl) {
        startTask()
      }
      loadLabelledLocations()
    }
  }, [taskId, isQualityControl])

  useEffect(() => {
    if (taskId) {
      loadLocation(currentIndex)
    }
  }, [currentIndex, taskId])
  
  const loadLabelledLocations = async () => {
    try {
      const response = await labellingApi.getLabelledLocations(taskId!)
      setLabelledLocations(response.data.labelled_locations || [])
    } catch (error) {
      console.error('Failed to load labelled locations:', error)
    }
  }

  const startTask = async () => {
    try {
      await tasksApi.startTask(taskId!)
    } catch (error) {
      console.error('Failed to start task:', error)
    }
  }

  const loadLocation = async (index: number) => {
    setLoading(true)
    setGsvError(null)
    try {
      const response = await labellingApi.getLocationForLabelling(taskId!, index)
      setLocation(response.data)
      
      // Populate form with existing label data
      if (response.data.label) {
        setFormData({
          advertising_present: response.data.label.advertising_present,
          bus_shelter_present: response.data.label.bus_shelter_present,
          number_of_panels: response.data.label.number_of_panels,
          pole_stop: response.data.label.pole_stop,
          unmarked_stop: response.data.label.unmarked_stop,
          selected_image: response.data.label.selected_image,
          notes: response.data.label.notes || '',
          unable_to_label: response.data.label.unable_to_label,
          unable_reason: response.data.label.unable_reason || '',
        })
        
        // Store label ID for comments - load for all users, not just QC
        if (response.data.label.id) {
          setLabelId(response.data.label.id)
          loadComments(response.data.label.id)
        }
      } else {
        setFormData(defaultLabelData)
        setLabelId(null)
        setComments([])
      }
      
      // Street View will be initialized by the useEffect when mapsLoaded and location are ready
    } catch (error) {
      console.error('Failed to load location:', error)
    } finally {
      setLoading(false)
    }
  }
  
  const loadComments = async (labelIdToLoad: string) => {
    try {
      const response = await commentsApi.getLabelComments(labelIdToLoad)
      setComments(response.data.comments || [])
    } catch (error) {
      console.error('Failed to load comments:', error)
    }
  }
  
  const submitComment = async () => {
    if (!labelId || !newComment.trim()) return
    
    try {
      // Managers leave feedback, labellers ask questions
      const commentType = isManager ? 'feedback' : 'question'
      await commentsApi.createComment(labelId, newComment.trim(), commentType)
      setNewComment('')
      loadComments(labelId)
    } catch (error) {
      console.error('Failed to submit comment:', error)
      alert('Failed to submit comment')
    }
  }

  const initStreetView = useCallback((lat: number, lng: number) => {
    if (!streetViewRef.current || !mapsLoaded) return
    
    // Check if Google Maps is available
    if (typeof google === 'undefined' || !google.maps) {
      setGsvError('Google Maps API not loaded. Please refresh the page or check API key configuration.')
      return
    }
    
    try {
      // Clear any previous error
      setGsvError(null)
      
      const panorama = new google.maps.StreetViewPanorama(streetViewRef.current, {
        position: { lat, lng },
        pov: { heading: 0, pitch: 0 },
        zoom: 1,
        addressControl: false,
        showRoadLabels: false,
      })
      
      panoramaRef.current = panorama
      
      // Get capture date when panorama changes
      panorama.addListener('pano_changed', () => {
        const panoId = panorama.getPano()
        if (panoId) {
          const service = new google.maps.StreetViewService()
          service.getPanorama({ pano: panoId }, (data, status) => {
            if (status === 'OK' && data?.imageDate) {
              setStreetViewDate(data.imageDate)
            }
          })
        }
      })
      
      // Handle errors
      panorama.addListener('status_changed', () => {
        const status = panorama.getStatus()
        if (status === 'ZERO_RESULTS') {
          setGsvError('No Street View imagery available for this location.')
        }
      })
    } catch (error) {
      console.error('Failed to initialize Street View:', error)
      setGsvError('Failed to load Street View. Please try refreshing the page.')
    }
  }, [mapsLoaded])

  // Initialize street view when maps API is loaded and we have location data
  useEffect(() => {
    if (mapsLoaded && location && streetViewRef.current) {
      initStreetView(location.latitude, location.longitude)
    }
  }, [mapsLoaded, location, initStreetView])

  const handleSave = async (goNext: boolean = true) => {
    if (!location || !taskId) return
    
    setSaving(true)
    try {
      const result = await labellingApi.saveLabel(taskId, location.id, formData)
      
      // Refresh labelled locations list
      loadLabelledLocations()
      
      if (result.data.is_task_complete) {
        alert('Task completed! Great work.')
        navigate('/tasks')
        return
      }
      
      if (goNext && currentIndex < location.total - 1) {
        setCurrentIndex(currentIndex + 1)
      }
    } catch (error) {
      console.error('Failed to save label:', error)
      alert('Failed to save. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  const [snapshotLoading, setSnapshotLoading] = useState(false)
  
  const handleSnapshot = async () => {
    if (!location || !taskId) {
      alert('Location or task not loaded')
      return
    }
    
    if (!panoramaRef.current) {
      // Fallback: use location coordinates with default heading
      alert('Street View not loaded. Taking snapshot at default angle.')
    }
    
    setSnapshotLoading(true)
    
    try {
      const pov = panoramaRef.current?.getPov()
      const heading = Math.round(pov?.heading || 0)
      const pitch = Math.round(pov?.pitch || 0)
      const panoId = panoramaRef.current?.getPano() || undefined
      
      console.log('Taking snapshot:', { heading, pitch, panoId, locationId: location.id })
      
      // Use backend to fetch from Street View Static API
      await labellingApi.saveSnapshot(
        taskId,
        location.id,
        heading,
        pitch,
        panoId
      )
      
      // Reload location to get the new snapshot
      await loadLocation(currentIndex)
      
      // Auto-select the new snapshot (snapshots start at index 5)
      // Get the count of existing snapshots from the reloaded location
      const snapshots = location.images.filter((img: any) => img.is_user_snapshot)
      const newSnapshotIndex = 5 + snapshots.length // The new snapshot will be at this index
      setFormData(prev => ({ ...prev, selected_image: newSnapshotIndex }))
      
      alert('Snapshot saved and selected!')
    } catch (error: any) {
      console.error('Failed to save snapshot:', error)
      const message = error?.response?.data?.detail || error?.message || 'Unknown error'
      alert(`Failed to save snapshot: ${message}`)
    } finally {
      setSnapshotLoading(false)
    }
  }

  const handleSearch = async () => {
    if (!searchQuery || !taskId) return
    
    try {
      const response = await labellingApi.searchLocation(taskId, searchQuery)
      setSearchResults(response.data.results)
    } catch (error) {
      console.error('Search failed:', error)
    }
  }

  const goToLocation = (index: number) => {
    setCurrentIndex(index)
    setSearchResults([])
    setSearchQuery('')
  }
  
  const goToLabelledLocation = async (locationId: string) => {
    try {
      const response = await labellingApi.getLocationIndexById(taskId!, locationId)
      if (response.data.found) {
        setCurrentIndex(response.data.index)
        setShowLabelledDropdown(false)
      }
    } catch (error) {
      console.error('Failed to find location:', error)
    }
  }

  if (loading) return <Loading />
  if (!location) return <p className="govuk-body">Location not found</p>

  // Extract road function from original_data - check many possible field names
  const roadFunction = location.road_classification ||
                       location.original_data?.['RoadClassification'] ||
                       location.original_data?.['road_classification'] ||
                       location.original_data?.['RoadType'] ||
                       location.original_data?.['road_type'] ||
                       location.original_data?.['BusStopType'] ||
                       location.original_data?.['StopType'] ||
                       location.original_data?.['stop_type'] ||
                       location.original_data?.['Type'] ||
                       location.original_data?.['type'] ||
                       location.original_data?.['function'] || 
                       location.original_data?.['Function'] || 
                       location.original_data?.['roadFunction'] ||
                       location.original_data?.['Bearing'] ||
                       location.original_data?.['TimingStatus']

  return (
    <div className="labelling-page-content" style={{ maxWidth: sidebarHidden ? '100%' : '1400px', margin: '0 auto', transition: 'max-width 0.3s ease' }}>
      {/* Header with Location Info */}
      <div style={{ 
        background: 'white', 
        borderRadius: '16px', 
        padding: '24px', 
        marginBottom: '24px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
          <div>
            <h1 className="govuk-heading-l" style={{ marginBottom: '8px' }}>
              {location.identifier}
            </h1>
            <p className="govuk-body-s" style={{ marginBottom: 0, color: '#6b7280' }}>
              Location {location.index + 1} of {location.total}
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '16px' }}>
            {/* Review Previously Labelled Dropdown */}
            <div style={{ position: 'relative' }}>
              <button
                onClick={() => setShowLabelledDropdown(!showLabelledDropdown)}
                style={{
                  background: labelledLocations.length > 0 ? '#f0fdf4' : '#f3f4f6',
                  border: labelledLocations.length > 0 ? '1px solid #10b981' : '1px solid #d1d5db',
                  borderRadius: '8px',
                  padding: '8px 12px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  fontSize: '13px',
                  fontWeight: 500
                }}
              >
                📋 Review ({labelledLocations.length})
                <span style={{ fontSize: '10px' }}>{showLabelledDropdown ? '▲' : '▼'}</span>
              </button>
              {showLabelledDropdown && labelledLocations.length > 0 && (
                <div style={{
                  position: 'absolute',
                  top: '100%',
                  right: 0,
                  marginTop: '4px',
                  background: 'white',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                  zIndex: 100,
                  maxHeight: '300px',
                  overflowY: 'auto',
                  minWidth: '280px'
                }}>
                  <div style={{ padding: '8px 12px', borderBottom: '1px solid #e5e7eb', background: '#f9fafb' }}>
                    <span style={{ fontSize: '12px', fontWeight: 600, color: '#6b7280' }}>Previously Labelled</span>
                  </div>
                  {labelledLocations.map((loc) => (
                    <div
                      key={loc.id}
                      onClick={() => goToLabelledLocation(loc.id)}
                      style={{
                        padding: '10px 12px',
                        cursor: 'pointer',
                        borderBottom: '1px solid #f3f4f6',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center'
                      }}
                      onMouseOver={(e) => e.currentTarget.style.background = '#f9fafb'}
                      onMouseOut={(e) => e.currentTarget.style.background = 'white'}
                    >
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 500, fontSize: '13px' }}>{loc.identifier}</div>
                        {/* Show road name and locality if available */}
                        {(loc.road_name || loc.locality || loc.nptg_locality_name || loc.town) && (
                          <div style={{ fontSize: '11px', color: '#374151', marginTop: '2px' }}>
                            {loc.road_name && <span style={{ fontWeight: 500 }}>{loc.road_name}</span>}
                            {loc.road_name && (loc.locality || loc.nptg_locality_name || loc.town) && ' • '}
                            {loc.locality || loc.nptg_locality_name || loc.town}
                          </div>
                        )}
                        <div style={{ fontSize: '11px', color: '#6b7280' }}>
                          {loc.advertising_present ? '✅ Has advertising' : '❌ No advertising'}
                        </div>
                      </div>
                      <span style={{ 
                        fontSize: '10px', 
                        background: loc.status === 'completed' ? '#dcfce7' : '#fef3c7',
                        color: loc.status === 'completed' ? '#166534' : '#92400e',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        flexShrink: 0,
                        marginLeft: '8px'
                      }}>
                        {loc.status}
                      </span>
                    </div>
                  ))}
                  <div style={{ padding: '8px 12px', borderTop: '1px solid #e5e7eb' }}>
                    <button
                      onClick={() => navigate(`/labelling/${taskId}/grid`)}
                      style={{
                        width: '100%',
                        background: '#1d70b8',
                        color: 'white',
                        border: 'none',
                        borderRadius: '6px',
                        padding: '8px',
                        fontSize: '12px',
                        fontWeight: 500,
                        cursor: 'pointer'
                      }}
                    >
                      View All Locations Grid →
                    </button>
                  </div>
                </div>
              )}
            </div>
            <div style={{ width: '180px' }}>
              <ProgressBar
                value={location.index + 1}
                max={location.total}
                variant="success"
              />
              <p className="govuk-body-s" style={{ textAlign: 'right', margin: 0 }}>
                {Math.round(((location.index + 1) / location.total) * 100)}% Complete
              </p>
            </div>
          </div>
        </div>
        
        {/* Location Metadata Grid */}
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '16px',
          padding: '16px',
          background: '#f8fafc',
          borderRadius: '12px'
        }}>
          <div>
            <span style={{ fontSize: '12px', color: '#6b7280', textTransform: 'uppercase', fontWeight: 600 }}>Council</span>
            <p style={{ margin: '4px 0 0', fontWeight: 500 }}>{location.council || location.original_data?.['LocalAuthority'] || location.original_data?.['Council'] || 'N/A'}</p>
          </div>
          <div>
            <span style={{ fontSize: '12px', color: '#6b7280', textTransform: 'uppercase', fontWeight: 600 }}>Locality</span>
            <p style={{ margin: '4px 0 0', fontWeight: 500 }}>{location.locality || location.original_data?.['LocalityName'] || 'N/A'}</p>
          </div>
          <div>
            <span style={{ fontSize: '12px', color: '#6b7280', textTransform: 'uppercase', fontWeight: 600 }}>Road Name</span>
            <p style={{ margin: '4px 0 0', fontWeight: 500 }}>{location.road_name || location.original_data?.['CommonName'] || 'N/A'}</p>
          </div>
          <div>
            <span style={{ fontSize: '12px', color: '#6b7280', textTransform: 'uppercase', fontWeight: 600 }}>Road Type</span>
            <p style={{ margin: '4px 0 0', fontWeight: 500 }}>{roadFunction || 'N/A'}</p>
          </div>
          <div>
            <span style={{ fontSize: '12px', color: '#6b7280', textTransform: 'uppercase', fontWeight: 600 }}>Latitude</span>
            <p style={{ margin: '4px 0 0', fontWeight: 500, fontFamily: 'monospace' }}>{location.latitude.toFixed(6)}</p>
          </div>
          <div>
            <span style={{ fontSize: '12px', color: '#6b7280', textTransform: 'uppercase', fontWeight: 600 }}>Longitude</span>
            <p style={{ margin: '4px 0 0', fontWeight: 500, fontFamily: 'monospace' }}>{location.longitude.toFixed(6)}</p>
          </div>
        </div>
      </div>

      {/* Search */}
      <div style={{ 
        background: 'white', 
        borderRadius: '16px', 
        padding: '24px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
        marginBottom: '24px'
      }}>
        <details className="govuk-details" style={{ marginBottom: 0 }}>
          <summary className="govuk-details__summary">
            <span className="govuk-details__summary-text">🔍 Search for a location</span>
          </summary>
          <div className="govuk-details__text" style={{ marginTop: '16px' }}>
            <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
              <input
                className="govuk-input"
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Enter identifier/shelter code..."
                onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
                style={{ flex: 1 }}
              />
              <button 
                className="govuk-button govuk-button--secondary" 
                onClick={handleSearch}
                style={{ marginBottom: 0 }}
              >
                Search
              </button>
            </div>
            {searchResults.length > 0 && (
              <ul className="govuk-list" style={{ marginTop: '16px', marginBottom: 0 }}>
                {searchResults.map((result) => (
                  <li key={result.id}>
                    <button
                      className="govuk-link"
                      style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '4px 0' }}
                      onClick={() => goToLocation(result.index)}
                    >
                      {result.identifier} (#{result.index + 1})
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </details>
      </div>

      {/* Single Column Layout */}
      <div>
        {/* Label Form - MOVED TO TOP */}
        <div style={{ 
          background: 'white', 
          borderRadius: '16px', 
          padding: '24px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
          marginBottom: '24px'
        }}>
          <h2 className="govuk-heading-m" style={{ marginBottom: '20px' }}>🏷️ Labels</h2>
          
          <div className="label-form">
            {/* Unable to label */}
            <div style={{ marginBottom: '20px', padding: '16px', background: '#fef3c7', borderRadius: '12px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={formData.unable_to_label}
                  onChange={(e) => setFormData({ ...formData, unable_to_label: e.target.checked })}
                  style={{ width: '20px', height: '20px', cursor: 'pointer' }}
                />
                <span style={{ fontWeight: 600, color: '#92400e' }}>⚠️ Unable to label this location</span>
              </label>
            </div>

            {formData.unable_to_label ? (
              <div style={{ marginBottom: '20px' }}>
                <label className="govuk-label" htmlFor="unable_reason">
                  Reason for being unable to label
                </label>
                <input
                  className="govuk-input"
                  id="unable_reason"
                  type="text"
                  value={formData.unable_reason}
                  onChange={(e) => setFormData({ ...formData, unable_reason: e.target.value })}
                  placeholder="E.g., No Street View coverage, obscured view..."
                />
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '24px' }}>
                {/* Advertising present */}
                <div>
                  <label className="govuk-label" style={{ marginBottom: '12px' }}>Advertising present?</label>
                  <div style={{ display: 'flex', gap: '12px' }}>
                    <label style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      gap: '8px', 
                      padding: '10px 16px',
                      background: formData.advertising_present === true ? '#dcfce7' : '#f3f4f6',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      border: formData.advertising_present === true ? '2px solid #10b981' : '2px solid transparent',
                      transition: 'all 0.15s ease'
                    }}>
                      <input
                        type="radio"
                        name="advertising"
                        checked={formData.advertising_present === true}
                        onChange={() => setFormData({ ...formData, advertising_present: true })}
                        style={{ width: '18px', height: '18px' }}
                      />
                      <span style={{ fontWeight: 500 }}>✅ Yes</span>
                    </label>
                    <label style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      gap: '8px', 
                      padding: '10px 16px',
                      background: formData.advertising_present === false ? '#fee2e2' : '#f3f4f6',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      border: formData.advertising_present === false ? '2px solid #ef4444' : '2px solid transparent',
                      transition: 'all 0.15s ease'
                    }}>
                      <input
                        type="radio"
                        name="advertising"
                        checked={formData.advertising_present === false}
                        onChange={() => setFormData({ ...formData, advertising_present: false })}
                        style={{ width: '18px', height: '18px' }}
                      />
                      <span style={{ fontWeight: 500 }}>❌ No</span>
                    </label>
                  </div>
                </div>

                {/* Bus shelter present */}
                <div>
                  <label className="govuk-label" style={{ marginBottom: '12px' }}>Bus shelter present?</label>
                  <div style={{ display: 'flex', gap: '12px' }}>
                    <label style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      gap: '8px', 
                      padding: '10px 16px',
                      background: formData.bus_shelter_present === true ? '#dcfce7' : '#f3f4f6',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      border: formData.bus_shelter_present === true ? '2px solid #10b981' : '2px solid transparent',
                      transition: 'all 0.15s ease'
                    }}>
                      <input
                        type="radio"
                        name="shelter"
                        checked={formData.bus_shelter_present === true}
                        onChange={() => setFormData({ ...formData, bus_shelter_present: true })}
                        style={{ width: '18px', height: '18px' }}
                      />
                      <span style={{ fontWeight: 500 }}>✅ Yes</span>
                    </label>
                    <label style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      gap: '8px', 
                      padding: '10px 16px',
                      background: formData.bus_shelter_present === false ? '#fee2e2' : '#f3f4f6',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      border: formData.bus_shelter_present === false ? '2px solid #ef4444' : '2px solid transparent',
                      transition: 'all 0.15s ease'
                    }}>
                      <input
                        type="radio"
                        name="shelter"
                        checked={formData.bus_shelter_present === false}
                        onChange={() => setFormData({ ...formData, bus_shelter_present: false })}
                        style={{ width: '18px', height: '18px' }}
                      />
                      <span style={{ fontWeight: 500 }}>❌ No</span>
                    </label>
                  </div>
                </div>

                {/* Number of panels */}
                <div>
                  <label className="govuk-label" htmlFor="panels">
                    Panels
                  </label>
                  <input
                    className="govuk-input"
                    id="panels"
                    type="number"
                    min="0"
                    style={{ width: '80px' }}
                    value={formData.number_of_panels ?? ''}
                    onChange={(e) => setFormData({ ...formData, number_of_panels: e.target.value ? parseInt(e.target.value) : null })}
                  />
                </div>

                {/* Stop type checkboxes */}
                <div>
                  <label className="govuk-label" style={{ marginBottom: '12px' }}>Stop type</label>
                  <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                    <label style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      gap: '8px', 
                      padding: '10px 16px',
                      background: formData.pole_stop ? '#dbeafe' : '#f3f4f6',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      border: formData.pole_stop ? '2px solid #3b82f6' : '2px solid transparent',
                      transition: 'all 0.15s ease'
                    }}>
                      <input
                        type="checkbox"
                        checked={formData.pole_stop === true}
                        onChange={(e) => setFormData({ ...formData, pole_stop: e.target.checked })}
                        style={{ width: '18px', height: '18px' }}
                      />
                      <span style={{ fontWeight: 500 }}>🪧 Pole</span>
                    </label>
                    <label style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      gap: '8px', 
                      padding: '10px 16px',
                      background: formData.shelter_stop ? '#dbeafe' : '#f3f4f6',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      border: formData.shelter_stop ? '2px solid #3b82f6' : '2px solid transparent',
                      transition: 'all 0.15s ease'
                    }}>
                      <input
                        type="checkbox"
                        checked={formData.shelter_stop === true}
                        onChange={(e) => setFormData({ ...formData, shelter_stop: e.target.checked })}
                        style={{ width: '18px', height: '18px' }}
                      />
                      <span style={{ fontWeight: 500 }}>🏠 Shelter</span>
                    </label>
                    <label style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      gap: '8px', 
                      padding: '10px 16px',
                      background: formData.unmarked_stop ? '#dbeafe' : '#f3f4f6',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      border: formData.unmarked_stop ? '2px solid #3b82f6' : '2px solid transparent',
                      transition: 'all 0.15s ease'
                    }}>
                      <input
                        type="checkbox"
                        checked={formData.unmarked_stop === true}
                        onChange={(e) => setFormData({ ...formData, unmarked_stop: e.target.checked })}
                        style={{ width: '18px', height: '18px' }}
                      />
                      <span style={{ fontWeight: 500 }}>❓ Unmarked</span>
                    </label>
                  </div>
                </div>

                {/* Notes */}
                <div style={{ gridColumn: 'span 2' }}>
                  <label className="govuk-label" htmlFor="notes">
                    Notes (optional)
                  </label>
                  <textarea
                    className="govuk-textarea"
                    id="notes"
                    rows={2}
                    value={formData.notes}
                    onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                    placeholder="Any additional observations..."
                    style={{ marginBottom: 0 }}
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Street View Images - 2x2 Grid */}
        <div style={{ 
          background: 'white', 
          borderRadius: '16px', 
          padding: '24px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
          marginBottom: '24px'
        }}>
          <h2 className="govuk-heading-m" style={{ marginBottom: '16px' }}>📸 Street View Images (click to select)</h2>
          
          {/* Downloaded images in 2x2 grid */}
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: 'repeat(2, 1fr)', 
            gap: '16px'
          }}>
              {[0, 90, 180, 270].map((heading, idx) => {
                const image = location.images.find((img) => img.heading === heading && !img.is_user_snapshot)
                const isSelected = formData.selected_image === idx + 1
                const imageKey = `main-${heading}`
                const zoomBox = zoomBoxes[imageKey]
                const isCurrentlyDragging = dragState?.imageKey === imageKey && dragState.isDragging
                const imageUrl = image ? (() => {
                  let url = image.gcs_url || ''
                  if (url.startsWith('http://localhost:8000')) url = url.replace('http://localhost:8000', '')
                  if (!url.startsWith('/') && !url.startsWith('http')) url = `/api/v1/images/${url}`
                  return url
                })() : ''
                return (
                  <div
                    key={heading}
                    onClick={() => !dragState && setFormData({ ...formData, selected_image: isSelected ? 0 : idx + 1 })}
                    onMouseDown={(e) => image && !zoomBox && handleZoomDragStart(e, imageKey)}
                    onMouseMove={(e) => image && handleZoomDragMove(e)}
                    onMouseUp={handleZoomDragEnd}
                    onMouseLeave={handleZoomDragEnd}
                    style={{
                      position: 'relative',
                      aspectRatio: '4/3',
                      borderRadius: '12px',
                      overflow: 'hidden',
                      cursor: zoomBox ? 'default' : 'crosshair',
                      border: isSelected ? '3px solid #10b981' : '2px solid #e5e7eb',
                      boxShadow: isSelected ? '0 0 0 4px rgba(16, 185, 129, 0.2)' : 'none',
                      transition: 'border 0.2s ease, box-shadow 0.2s ease',
                      background: '#f3f4f6',
                      userSelect: 'none'
                    }}
                  >
                    {image ? (
                      <>
                        <img 
                          src={imageUrl}
                          alt={`View ${heading}°`}
                          draggable={false}
                          style={{ 
                            width: '100%', 
                            height: '100%', 
                            objectFit: 'cover',
                            objectPosition: zoomBox 
                              ? `${zoomBox.x + zoomBox.width / 2}% ${zoomBox.y + zoomBox.height / 2}%` 
                              : 'center',
                            transform: zoomBox 
                              ? `scale(${100 / Math.max(zoomBox.width, zoomBox.height)})` 
                              : 'none',
                            transformOrigin: zoomBox 
                              ? `${zoomBox.x + zoomBox.width / 2}% ${zoomBox.y + zoomBox.height / 2}%` 
                              : 'center',
                            transition: 'transform 0.3s ease, object-position 0.3s ease'
                          }}
                          onError={(e) => {
                            const target = e.target as HTMLImageElement
                            target.style.opacity = '0.3'
                          }}
                        />
                        {/* Selection box while dragging */}
                        {isCurrentlyDragging && dragState && (
                          <div style={{
                            position: 'absolute',
                            left: `${Math.min(dragState.startX, dragState.currentX)}%`,
                            top: `${Math.min(dragState.startY, dragState.currentY)}%`,
                            width: `${Math.abs(dragState.currentX - dragState.startX)}%`,
                            height: `${Math.abs(dragState.currentY - dragState.startY)}%`,
                            border: '2px dashed #1d70b8',
                            background: 'rgba(29, 112, 184, 0.2)',
                            pointerEvents: 'none',
                            zIndex: 10
                          }} />
                        )}
                        {/* Reset zoom button */}
                        {zoomBox && (
                          <button
                            onClick={(e) => resetZoom(imageKey, e)}
                            style={{
                              position: 'absolute',
                              top: '8px',
                              left: '8px',
                              background: 'rgba(0,0,0,0.7)',
                              color: 'white',
                              border: 'none',
                              borderRadius: '6px',
                              padding: '6px 12px',
                              fontSize: '12px',
                              cursor: 'pointer',
                              zIndex: 15,
                              display: 'flex',
                              alignItems: 'center',
                              gap: '4px'
                            }}
                          >
                            ↩ Reset
                          </button>
                        )}
                        {/* Expand button */}
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setExpandedImage({ url: imageUrl, title: `${heading}° View`, zoom: 1 })
                          }}
                          style={{
                            position: 'absolute',
                            top: '8px',
                            left: zoomBox ? '80px' : '8px',
                            background: 'rgba(0,0,0,0.6)',
                            color: 'white',
                            border: 'none',
                            borderRadius: '6px',
                            padding: '6px 10px',
                            fontSize: '12px',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px',
                            zIndex: 5
                          }}
                        >
                          ⛶ Expand
                        </button>
                        <div style={{
                          position: 'absolute',
                          bottom: 0,
                          left: 0,
                          right: 0,
                          background: 'linear-gradient(transparent, rgba(0,0,0,0.8))',
                          color: 'white',
                          padding: '20px 12px 10px',
                          fontSize: '13px',
                          fontWeight: 500
                        }}>
                          {heading}° | {image.capture_date || 'Unknown date'} {!zoomBox && <span style={{ opacity: 0.7, fontSize: '11px' }}>• Drag to zoom</span>}
                        </div>
                        {isSelected && (
                          <div style={{
                            position: 'absolute',
                            top: '8px',
                            right: '8px',
                            background: '#10b981',
                            color: 'white',
                            borderRadius: '50%',
                            width: '28px',
                            height: '28px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: '16px'
                          }}>✓</div>
                        )}
                      </>
                    ) : (
                      <div style={{ 
                        display: 'flex', 
                        alignItems: 'center', 
                        justifyContent: 'center', 
                        height: '100%', 
                        flexDirection: 'column', 
                        gap: '8px' 
                      }}>
                        <span style={{ fontSize: '40px' }}>🖼️</span>
                        <span style={{ color: '#9ca3af', fontSize: '14px' }}>No image ({heading}°)</span>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

          {/* User snapshots - inline */}
          {location.images.filter((img) => img.is_user_snapshot).length > 0 && (
            <div style={{ 
              marginTop: '24px', 
              paddingTop: '24px', 
              borderTop: '1px solid #e5e7eb' 
            }}>
              <h3 className="govuk-heading-s" style={{ marginBottom: '16px' }}>📷 Your Snapshots ({location.images.filter((img) => img.is_user_snapshot).length})</h3>
              <div style={{ 
                display: 'grid', 
                gridTemplateColumns: 'repeat(2, 1fr)', 
                gap: '20px' 
              }}>
                  {location.images
                    .filter((img) => img.is_user_snapshot)
                    .map((image, idx) => {
                      const isSelected = formData.selected_image === 5 + idx
                      const imageKey = `snapshot-${image.id}`
                      const zoomBox = zoomBoxes[imageKey]
                      const isCurrentlyDragging = dragState?.imageKey === imageKey && dragState.isDragging
                      const snapshotUrl = (() => {
                        let url = image.gcs_url || ''
                        if (url.startsWith('http://localhost:8000')) url = url.replace('http://localhost:8000', '')
                        if (!url.startsWith('/') && !url.startsWith('http')) url = `/api/v1/images/${url}`
                        return url
                      })()
                      return (
                        <div
                          key={image.id}
                          onClick={() => !dragState && setFormData({ ...formData, selected_image: isSelected ? 0 : 5 + idx })}
                          onMouseDown={(e) => !zoomBox && handleZoomDragStart(e, imageKey)}
                          onMouseMove={handleZoomDragMove}
                          onMouseUp={handleZoomDragEnd}
                          onMouseLeave={handleZoomDragEnd}
                          style={{
                            position: 'relative',
                            aspectRatio: '4/3',
                            borderRadius: '8px',
                            overflow: 'hidden',
                            cursor: zoomBox ? 'default' : 'crosshair',
                            border: isSelected ? '3px solid #10b981' : '2px solid #e5e7eb',
                            boxShadow: isSelected ? '0 0 0 3px rgba(16, 185, 129, 0.2)' : 'none',
                            userSelect: 'none'
                          }}
                        >
                          <img 
                            src={snapshotUrl}
                            alt={`Snapshot ${idx + 1}`}
                            draggable={false}
                            style={{ 
                              width: '100%', 
                              height: '100%', 
                              objectFit: 'cover',
                              objectPosition: zoomBox 
                                ? `${zoomBox.x + zoomBox.width / 2}% ${zoomBox.y + zoomBox.height / 2}%` 
                                : 'center',
                              transform: zoomBox 
                                ? `scale(${100 / Math.max(zoomBox.width, zoomBox.height)})` 
                                : 'none',
                              transformOrigin: zoomBox 
                                ? `${zoomBox.x + zoomBox.width / 2}% ${zoomBox.y + zoomBox.height / 2}%` 
                                : 'center',
                              transition: 'transform 0.3s ease, object-position 0.3s ease'
                            }}
                            onError={(e) => {
                              const target = e.target as HTMLImageElement
                              target.style.opacity = '0.3'
                            }}
                          />
                          {/* Selection box while dragging */}
                          {isCurrentlyDragging && dragState && (
                            <div style={{
                              position: 'absolute',
                              left: `${Math.min(dragState.startX, dragState.currentX)}%`,
                              top: `${Math.min(dragState.startY, dragState.currentY)}%`,
                              width: `${Math.abs(dragState.currentX - dragState.startX)}%`,
                              height: `${Math.abs(dragState.currentY - dragState.startY)}%`,
                              border: '2px dashed #1d70b8',
                              background: 'rgba(29, 112, 184, 0.2)',
                              pointerEvents: 'none',
                              zIndex: 10
                            }} />
                          )}
                          {/* Reset zoom button */}
                          {zoomBox && (
                            <button
                              onClick={(e) => resetZoom(imageKey, e)}
                              style={{
                                position: 'absolute',
                                top: '4px',
                                left: '4px',
                                background: 'rgba(0,0,0,0.7)',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                padding: '4px 8px',
                                fontSize: '11px',
                                cursor: 'pointer',
                                zIndex: 15
                              }}
                            >
                              ↩ Reset
                            </button>
                          )}
                          {/* Expand button */}
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              setExpandedImage({ url: snapshotUrl, title: `Snapshot #${idx + 1}`, zoom: 1 })
                            }}
                            style={{
                              position: 'absolute',
                              top: '4px',
                              left: zoomBox ? '60px' : '4px',
                              background: 'rgba(0,0,0,0.6)',
                              color: 'white',
                              border: 'none',
                              borderRadius: '4px',
                              padding: '4px 8px',
                              fontSize: '11px',
                              cursor: 'pointer',
                              zIndex: 5
                            }}
                          >
                            ⛶
                          </button>
                          <div style={{
                            position: 'absolute',
                            bottom: 0,
                            left: 0,
                            right: 0,
                            background: 'rgba(0,0,0,0.7)',
                            color: 'white',
                            padding: '6px 8px',
                            fontSize: '11px'
                          }}>
                            Snapshot #{idx + 1} {!zoomBox && <span style={{ opacity: 0.7 }}>• Drag to zoom</span>}
                          </div>
                          {isSelected && (
                            <div style={{
                              position: 'absolute',
                              top: '4px',
                              right: '4px',
                              background: '#10b981',
                              color: 'white',
                              borderRadius: '50%',
                              width: '22px',
                              height: '22px',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: '12px'
                            }}>✓</div>
                          )}
                        </div>
                      )
                    })}
              </div>
            </div>
          )}
        </div>

        {/* Embedded Street View - Full Width */}
        <div style={{ 
          background: 'white', 
          borderRadius: '16px', 
          padding: '24px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
          marginBottom: '24px'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h2 className="govuk-heading-m" style={{ marginBottom: 0 }}>🗺️ Interactive Street View</h2>
            <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
              {streetViewDate && (
                <span style={{ fontSize: '14px', color: '#6b7280', marginRight: '8px' }}>
                  📅 {streetViewDate}
                </span>
              )}
              <button
                className="govuk-button"
                onClick={handleSnapshot}
                disabled={snapshotLoading}
                style={{ marginBottom: 0 }}
              >
                {snapshotLoading ? '⏳ Saving...' : '📸 Take Snapshot'}
              </button>
              <button
                className="govuk-button govuk-button--secondary"
                onClick={() => setShowSnapshotsModal(true)}
                style={{ marginBottom: 0 }}
              >
                🖼️ View Snapshots ({location.images.filter((img) => img.is_user_snapshot).length})
              </button>
              <a 
                href={`https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${location.latitude},${location.longitude}`}
                target="_blank"
                rel="noopener noreferrer"
                className="govuk-button govuk-button--secondary"
                style={{ marginBottom: 0 }}
              >
                🔗 Google Maps
              </a>
            </div>
          </div>
          <div className="street-view-container street-view-container--large">
            {gsvError ? (
                <div style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'center', 
                  height: '100%',
                  flexDirection: 'column',
                  gap: '16px',
                  padding: '40px'
                }}>
                  <span style={{ fontSize: '48px' }}>🗺️</span>
                  <p style={{ color: '#6b7280', textAlign: 'center', maxWidth: '400px' }}>{gsvError}</p>
                  <a 
                    href={`https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${location.latitude},${location.longitude}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="govuk-button govuk-button--secondary"
                  >
                    Open in Google Maps
                  </a>
                </div>
            ) : !mapsLoaded ? (
                <div style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'center', 
                  height: '100%',
                  flexDirection: 'column',
                  gap: '16px',
                  padding: '40px'
                }}>
                  <span style={{ fontSize: '32px' }}>⏳</span>
                  <p style={{ color: '#6b7280', textAlign: 'center' }}>Loading Street View...</p>
                </div>
            ) : (
              <div ref={streetViewRef} className="street-view-container__embed" />
            )}
          </div>
        </div>
      </div>

      {/* Comments Section - Available for all users when a label exists */}
      {labelId && (
        <div style={{ 
          background: 'white', 
          borderRadius: '16px', 
          padding: '24px',
          marginBottom: '24px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h2 className="govuk-heading-m" style={{ marginBottom: 0 }}>
              💬 {isManager ? 'Feedback & Comments' : 'Questions & Feedback'} ({comments.length})
            </h2>
            <button
              onClick={() => setShowComments(!showComments)}
              style={{
                background: 'transparent',
                border: 'none',
                color: '#1d70b8',
                cursor: 'pointer',
                fontWeight: 500,
                fontSize: '14px'
              }}
            >
              {showComments ? 'Hide' : 'Show'}
            </button>
          </div>
          
          {showComments && (
            <>
              {/* Add New Comment */}
              <div style={{ marginBottom: '16px' }}>
                <textarea
                  value={newComment}
                  onChange={(e) => setNewComment(e.target.value)}
                  placeholder={isManager 
                    ? "Add feedback or suggestion for this label..." 
                    : "Ask a question or leave a note for the manager..."
                  }
                  style={{
                    width: '100%',
                    padding: '12px',
                    borderRadius: '8px',
                    border: '1px solid #d1d5db',
                    minHeight: '80px',
                    fontSize: '14px',
                    resize: 'vertical'
                  }}
                />
                <button
                  onClick={submitComment}
                  disabled={!newComment.trim()}
                  className="govuk-button"
                  style={{ marginTop: '8px', marginBottom: 0 }}
                >
                  {isManager ? 'Add Feedback' : 'Ask Question'}
                </button>
              </div>
              
              {/* Comment List */}
              {comments.length === 0 ? (
                <p style={{ color: '#6b7280', textAlign: 'center', padding: '20px' }}>
                  {isManager 
                    ? "No comments yet. Add feedback to help the labeller."
                    : "No comments yet. Ask a question if you're unsure about this location."
                  }
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {comments.map((comment) => (
                    <div 
                      key={comment.id}
                      style={{
                        background: comment.comment_type === 'question' ? '#fef3c7' : '#f0f9ff',
                        borderRadius: '8px',
                        padding: '12px 16px',
                        border: comment.comment_type === 'question' ? '1px solid #fcd34d' : '1px solid #bae6fd'
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '4px' }}>
                        <span style={{ fontWeight: 600, fontSize: '13px' }}>
                          {comment.author_name}
                          <span style={{ 
                            marginLeft: '8px',
                            fontSize: '11px',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            background: comment.comment_type === 'question' ? '#fef3c7' : '#dbeafe',
                            color: comment.comment_type === 'question' ? '#92400e' : '#1e40af'
                          }}>
                            {comment.comment_type === 'question' ? '❓ Question' : '💡 Feedback'}
                          </span>
                        </span>
                        <span style={{ fontSize: '11px', color: '#6b7280' }}>
                          {new Date(comment.created_at).toLocaleDateString()}
                        </span>
                      </div>
                      <p style={{ margin: 0, fontSize: '14px' }}>{comment.content}</p>
                      {comment.is_resolved && (
                        <span style={{ 
                          display: 'inline-block',
                          marginTop: '8px',
                          fontSize: '11px',
                          color: '#10b981',
                          fontWeight: 500
                        }}>
                          ✓ Resolved
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Sidebar Toggle Button */}
      <button
        onClick={() => setSidebarHidden(!sidebarHidden)}
        style={{
          position: 'fixed',
          top: '16px',
          left: sidebarHidden ? '16px' : '276px',
          background: '#2563eb',
          color: 'white',
          border: 'none',
          borderRadius: '8px',
          padding: '8px 12px',
          cursor: 'pointer',
          zIndex: 100,
          fontSize: '12px',
          boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
          transition: 'left 0.3s ease',
          display: 'flex',
          alignItems: 'center',
          gap: '6px'
        }}
      >
        {sidebarHidden ? '→' : '←'} {sidebarHidden ? 'Show Menu' : 'Hide Menu'}
      </button>

      {/* Navigation Bar */}
      <div style={{ 
        position: 'fixed',
        bottom: 0,
        left: sidebarHidden ? '0' : '260px',
        right: 0,
        background: 'white',
        borderTop: '1px solid #e5e7eb',
        padding: '16px 32px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        boxShadow: '0 -4px 6px -1px rgba(0,0,0,0.1)',
        zIndex: 50,
        transition: 'left 0.3s ease'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {isQualityControl && (
            <button
              className="govuk-button govuk-button--secondary"
              onClick={() => navigate('/quality-control')}
              style={{ marginBottom: 0 }}
            >
              ← Back to QC
            </button>
          )}
          <span style={{ fontWeight: 500, color: '#6b7280' }}>
            📍 {location.index + 1} of {location.total} locations
          </span>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
          <button
            className="govuk-button govuk-button--secondary"
            disabled={currentIndex === 0 || saving}
            onClick={() => setCurrentIndex(currentIndex - 1)}
            style={{ marginBottom: 0 }}
          >
            ← Previous
          </button>
          <button
            className="govuk-button govuk-button--secondary"
            disabled={currentIndex === location.total - 1 || saving}
            onClick={() => setCurrentIndex(currentIndex + 1)}
            style={{ marginBottom: 0 }}
          >
            Next →
          </button>
          <button
            className="govuk-button"
            disabled={saving}
            onClick={() => handleSave(true)}
            style={{ marginBottom: 0 }}
          >
            {saving ? '⏳ Saving...' : isQualityControl ? '💾 Save Changes' : (currentIndex === location.total - 1 ? '✅ Save & Finish' : '💾 Save & Next →')}
          </button>
        </div>
      </div>
      
      {/* Spacer for fixed nav */}
      <div style={{ height: '80px' }} />

      {/* Snapshots Modal */}
      {showSnapshotsModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.7)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 100
        }} onClick={() => setShowSnapshotsModal(false)}>
          <div style={{
            background: 'white',
            borderRadius: '16px',
            padding: '24px',
            maxWidth: '900px',
            maxHeight: '90vh',
            overflow: 'auto',
            width: '90%'
          }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h2 className="govuk-heading-m" style={{ marginBottom: 0 }}>📷 All Snapshots for {location.identifier}</h2>
              <button
                onClick={() => setShowSnapshotsModal(false)}
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: '24px',
                  cursor: 'pointer',
                  padding: '8px'
                }}
              >
                ✕
              </button>
            </div>
            
            {location.images.filter((img) => img.is_user_snapshot).length === 0 ? (
              <p className="govuk-body" style={{ textAlign: 'center', color: '#6b7280', padding: '40px' }}>
                No snapshots taken yet. Use the "Take Snapshot" button to capture the current Street View.
              </p>
            ) : (
              <div style={{ 
                display: 'grid', 
                gridTemplateColumns: 'repeat(2, 1fr)', 
                gap: '20px' 
              }}>
                {location.images
                  .filter((img) => img.is_user_snapshot)
                  .map((image, idx) => {
                    const isSelected = formData.selected_image === 5 + idx
                    return (
                      <div
                        key={image.id}
                        onClick={() => {
                          setFormData({ ...formData, selected_image: 5 + idx })
                          setShowSnapshotsModal(false)
                        }}
                        style={{
                          position: 'relative',
                          aspectRatio: '16/9',
                          borderRadius: '12px',
                          overflow: 'hidden',
                          cursor: 'pointer',
                          border: isSelected ? '3px solid #10b981' : '2px solid #e5e7eb',
                          boxShadow: isSelected ? '0 0 0 4px rgba(16, 185, 129, 0.2)' : '0 2px 4px rgba(0,0,0,0.1)',
                          transition: 'all 0.2s ease'
                        }}
                      >
                        <img 
                          src={(() => {
                            let url = image.gcs_url || ''
                            if (url.startsWith('http://localhost:8000')) url = url.replace('http://localhost:8000', '')
                            if (!url.startsWith('/') && !url.startsWith('http')) url = `/api/v1/images/${url}`
                            return url
                          })()}
                          alt={`Snapshot ${idx + 1}`}
                          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                          onError={(e) => {
                            const target = e.target as HTMLImageElement
                            target.style.opacity = '0.3'
                          }}
                        />
                        <div style={{
                          position: 'absolute',
                          bottom: 0,
                          left: 0,
                          right: 0,
                          background: 'linear-gradient(transparent, rgba(0,0,0,0.8))',
                          color: 'white',
                          padding: '24px 12px 12px',
                          fontSize: '14px',
                          fontWeight: 500
                        }}>
                          Snapshot #{idx + 1}
                          {image.capture_date && <span style={{ opacity: 0.8, marginLeft: '8px' }}>• {image.capture_date}</span>}
                        </div>
                        {isSelected && (
                          <div style={{
                            position: 'absolute',
                            top: '12px',
                            right: '12px',
                            background: '#10b981',
                            color: 'white',
                            borderRadius: '50%',
                            width: '32px',
                            height: '32px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: '18px'
                          }}>✓</div>
                        )}
                      </div>
                    )
                  })}
              </div>
            )}
            
            <p className="govuk-body-s" style={{ marginTop: '16px', color: '#6b7280', textAlign: 'center' }}>
              Click a snapshot to select it as the representative image
            </p>
          </div>
        </div>
      )}

      {/* Expanded Image Modal */}
      {expandedImage && (
        <div 
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.9)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 200
          }}
          onClick={() => setExpandedImage(null)}
        >
          {/* Header */}
          <div style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            padding: '16px 24px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            background: 'linear-gradient(rgba(0,0,0,0.8), transparent)'
          }}>
            <span style={{ color: 'white', fontSize: '16px', fontWeight: 500 }}>{expandedImage.title}</span>
            <button
              onClick={() => setExpandedImage(null)}
              style={{
                background: 'rgba(255,255,255,0.2)',
                border: 'none',
                color: 'white',
                fontSize: '20px',
                width: '40px',
                height: '40px',
                borderRadius: '50%',
                cursor: 'pointer'
              }}
            >
              ✕
            </button>
          </div>

          {/* Zoom controls */}
          <div style={{
            position: 'absolute',
            bottom: '24px',
            left: '50%',
            transform: 'translateX(-50%)',
            display: 'flex',
            gap: '12px',
            alignItems: 'center',
            background: 'rgba(0,0,0,0.7)',
            padding: '12px 20px',
            borderRadius: '24px'
          }} onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => setExpandedImage(prev => prev ? { ...prev, zoom: Math.max(0.5, prev.zoom - 0.25) } : null)}
              style={{
                background: 'rgba(255,255,255,0.2)',
                border: 'none',
                color: 'white',
                fontSize: '20px',
                width: '36px',
                height: '36px',
                borderRadius: '50%',
                cursor: 'pointer'
              }}
            >
              −
            </button>
            <span style={{ color: 'white', minWidth: '60px', textAlign: 'center', fontSize: '14px' }}>
              {Math.round(expandedImage.zoom * 100)}%
            </span>
            <button
              onClick={() => setExpandedImage(prev => prev ? { ...prev, zoom: Math.min(3, prev.zoom + 0.25) } : null)}
              style={{
                background: 'rgba(255,255,255,0.2)',
                border: 'none',
                color: 'white',
                fontSize: '20px',
                width: '36px',
                height: '36px',
                borderRadius: '50%',
                cursor: 'pointer'
              }}
            >
              +
            </button>
            <button
              onClick={() => setExpandedImage(prev => prev ? { ...prev, zoom: 1 } : null)}
              style={{
                background: 'rgba(255,255,255,0.2)',
                border: 'none',
                color: 'white',
                fontSize: '12px',
                padding: '8px 12px',
                borderRadius: '16px',
                cursor: 'pointer',
                marginLeft: '8px'
              }}
            >
              Reset
            </button>
          </div>

          {/* Image container */}
          <div 
            style={{
              maxWidth: '90vw',
              maxHeight: '80vh',
              overflow: 'auto',
              borderRadius: '8px'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <img
              src={expandedImage.url}
              alt={expandedImage.title}
              style={{
                display: 'block',
                transform: `scale(${expandedImage.zoom})`,
                transformOrigin: 'center center',
                transition: 'transform 0.2s ease',
                maxWidth: expandedImage.zoom === 1 ? '90vw' : 'none',
                maxHeight: expandedImage.zoom === 1 ? '80vh' : 'none'
              }}
            />
          </div>
        </div>
      )}

    </div>
  )
}
