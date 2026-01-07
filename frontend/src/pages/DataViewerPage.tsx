import { useEffect, useState, useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { dataApi } from '../services/api'
import Loading from '../components/common/Loading'

interface Location {
  id: string
  identifier: string
  latitude: number
  longitude: number
  council: string | null
  combined_authority: string | null
  road_classification: string | null
  is_enhanced: boolean
  original_data: Record<string, any>
  created_at: string
  common_name: string | null
  locality_name: string | null
  labelling_status: string | null
  labeller_name: string | null
  advertising_present: boolean | null
}

interface ColumnInfo {
  key: string
  label: string
  type: string
  source: string  // 'system', 'enhanced', 'computed', 'original'
  original_key?: string
  filterable?: boolean
}

interface LocationsResponse {
  locations: Location[]
  total: number
  page: number
  page_size: int
  total_pages: number
  enhanced_count: number
  unenhanced_count: number
  labelled_count: number
  unlabelled_count: number
  all_columns: ColumnInfo[]
}

interface Dataset {
  location_type_id: string
  location_type_name: string
  display_name: string
  total_locations: number
  enhanced_count: number
  unenhanced_count: number
  councils: { name: string; count: number }[]
  columns: ColumnInfo[]
  filter_values: Record<string, string[]>
}

export default function DataViewerPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  
  const [loading, setLoading] = useState(true)
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [selectedDataset, setSelectedDataset] = useState<Dataset | null>(null)
  const [locationsData, setLocationsData] = useState<LocationsResponse | null>(null)
  const [selectedLocation, setSelectedLocation] = useState<Location | null>(null)
  
  // Column visibility - will be populated from dataset columns
  const [visibleColumns, setVisibleColumns] = useState<string[]>([])
  const [showColumnSelector, setShowColumnSelector] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  
  // Filters
  const [searchTerm, setSearchTerm] = useState(searchParams.get('search') || '')
  const [columnFilters, setColumnFilters] = useState<Record<string, string>>({})
  const [page, setPage] = useState(parseInt(searchParams.get('page') || '1'))
  const pageSize = 25

  // Load datasets
  useEffect(() => {
    loadDatasets()
  }, [])

  const loadDatasets = async () => {
    try {
      const response = await dataApi.getDatasets()
      setDatasets(response.data)
      
      // Auto-select first dataset
      if (response.data.length > 0) {
        const target = response.data[0]
        setSelectedDataset(target)
        // Set default visible columns
        const defaultCols = target.columns
          .filter((c: ColumnInfo) => 
            ['identifier', 'council', 'labelling_status', 'advertising_present'].includes(c.key) ||
            c.label.toLowerCase().includes('name') ||
            c.label.toLowerCase().includes('locality')
          )
          .map((c: ColumnInfo) => c.key)
          .slice(0, 8)
        setVisibleColumns(defaultCols.length > 0 ? defaultCols : target.columns.slice(0, 6).map((c: ColumnInfo) => c.key))
      }
    } catch (error) {
      console.error('Failed to load datasets:', error)
    } finally {
      setLoading(false)
    }
  }

  // Load locations when dataset or filters change
  const loadLocations = useCallback(async () => {
    if (!selectedDataset) return
    
    try {
      const params: any = {
        page,
        page_size: pageSize,
      }
      if (searchTerm) params.search = searchTerm
      
      // Add column filters
      const activeFilters: Record<string, string> = {}
      for (const [key, value] of Object.entries(columnFilters)) {
        if (value && value !== '') {
          if (key === 'council') {
            params.council = value
          } else if (key === 'is_enhanced') {
            params.enhanced_only = value === 'true'
          } else if (key === 'labelling_status') {
            params.labelled_only = value === 'Labelled'
          } else if (key.startsWith('original_')) {
            activeFilters[key.replace('original_', '')] = value
          }
        }
      }
      
      if (Object.keys(activeFilters).length > 0) {
        params.filters = JSON.stringify(activeFilters)
      }
      
      const response = await dataApi.getLocations(selectedDataset.location_type_id, params)
      setLocationsData(response.data)
    } catch (error) {
      console.error('Failed to load locations:', error)
    }
  }, [selectedDataset, page, searchTerm, columnFilters])

  useEffect(() => {
    if (selectedDataset) {
      loadLocations()
    }
  }, [selectedDataset, loadLocations])

  // Handle dataset change
  const handleDatasetChange = (dataset: Dataset) => {
    setSelectedDataset(dataset)
    setPage(1)
    setSearchTerm('')
    setColumnFilters({})
    // Reset visible columns to defaults for new dataset
    const defaultCols = dataset.columns
      .filter((c: ColumnInfo) => 
        ['identifier', 'council', 'labelling_status', 'advertising_present'].includes(c.key) ||
        c.label.toLowerCase().includes('name') ||
        c.label.toLowerCase().includes('locality')
      )
      .map((c: ColumnInfo) => c.key)
      .slice(0, 8)
    setVisibleColumns(defaultCols.length > 0 ? defaultCols : dataset.columns.slice(0, 6).map((c: ColumnInfo) => c.key))
  }

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setPage(1)
    loadLocations()
  }

  const handlePageChange = (newPage: number) => {
    setPage(newPage)
  }

  const toggleColumn = (columnKey: string) => {
    setVisibleColumns(prev => 
      prev.includes(columnKey) 
        ? prev.filter(k => k !== columnKey)
        : [...prev, columnKey]
    )
  }

  const updateFilter = (columnKey: string, value: string) => {
    setColumnFilters(prev => ({
      ...prev,
      [columnKey]: value
    }))
    setPage(1)
  }

  const clearFilters = () => {
    setColumnFilters({})
    setSearchTerm('')
    setPage(1)
  }

  // Get cell value for any column type
  const getCellValue = (location: Location, column: ColumnInfo) => {
    const { key, type, source, original_key } = column
    let value: any
    
    // Get the value based on source
    if (source === 'original' && original_key) {
      value = location.original_data?.[original_key]
    } else {
      value = (location as any)[key]
    }
    
    // Format based on type
    if (value === null || value === undefined || value === '') {
      return <span style={{ color: '#9ca3af' }}>—</span>
    }
    
    if (type === 'boolean') {
      if (key === 'advertising_present') {
        return value ? (
          <strong className="govuk-tag govuk-tag--blue">Yes</strong>
        ) : (
          <strong className="govuk-tag govuk-tag--grey">No</strong>
        )
      }
      return value ? (
        <strong className="govuk-tag govuk-tag--green">Yes</strong>
      ) : (
        <strong className="govuk-tag govuk-tag--grey">No</strong>
      )
    }
    
    if (key === 'labelling_status') {
      return value === 'Labelled' ? (
        <strong className="govuk-tag govuk-tag--green">Labelled</strong>
      ) : (
        <strong className="govuk-tag govuk-tag--grey">Not Labelled</strong>
      )
    }
    
    if (key === 'identifier') {
      return <strong>{value}</strong>
    }
    
    if (type === 'number') {
      const num = parseFloat(value)
      if (!isNaN(num)) {
        // Check if it's a coordinate
        if (key === 'latitude' || key === 'longitude') {
          return num.toFixed(6)
        }
        return num.toLocaleString()
      }
    }
    
    return String(value)
  }

  // Get filterable columns
  const filterableColumns = useMemo(() => {
    if (!selectedDataset) return []
    return selectedDataset.columns.filter(c => c.filterable !== false)
  }, [selectedDataset])

  // Count active filters
  const activeFilterCount = Object.values(columnFilters).filter(v => v && v !== '').length + (searchTerm ? 1 : 0)

  if (loading) return <Loading />

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
        <div>
          <h1 className="govuk-heading-xl" style={{ marginBottom: '8px' }}>Data Viewer</h1>
          <p className="govuk-body-l" style={{ color: '#6b7280' }}>
            Browse and filter your location datasets
          </p>
        </div>
      </div>

      {datasets.length === 0 ? (
        <div className="govuk-inset-text">
          No datasets found. Upload a spreadsheet first to view data.
        </div>
      ) : (
        <div className="govuk-grid-row">
          {/* Dataset Selection Sidebar */}
          <div className="govuk-grid-column-one-quarter">
            <div style={{ 
              background: 'white', 
              borderRadius: '12px', 
              padding: '20px',
              border: '1px solid #e5e7eb',
              position: 'sticky',
              top: '100px'
            }}>
              <h2 className="govuk-heading-s" style={{ marginBottom: '16px' }}>Datasets</h2>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {datasets.map((dataset) => (
                  <button
                    key={dataset.location_type_id}
                    style={{ 
                      background: selectedDataset?.location_type_id === dataset.location_type_id ? '#2563eb' : 'white',
                      color: selectedDataset?.location_type_id === dataset.location_type_id ? 'white' : '#374151',
                      border: `1px solid ${selectedDataset?.location_type_id === dataset.location_type_id ? '#2563eb' : '#e5e7eb'}`,
                      borderRadius: '8px',
                      padding: '14px 16px',
                      cursor: 'pointer',
                      textAlign: 'left',
                      transition: 'all 0.15s ease'
                    }}
                    onClick={() => handleDatasetChange(dataset)}
                  >
                    <strong style={{ display: 'block', fontSize: '15px' }}>{dataset.display_name}</strong>
                    <span style={{ 
                      fontSize: '13px', 
                      opacity: selectedDataset?.location_type_id === dataset.location_type_id ? 0.9 : 0.7 
                    }}>
                      {dataset.total_locations.toLocaleString()} locations
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Data Table */}
          <div className="govuk-grid-column-three-quarters">
            {selectedDataset && (
              <>
                {/* Dataset Stats */}
                <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)', marginBottom: '24px' }}>
                  <div className="stat-card">
                    <span className="stat-card__value">{selectedDataset.total_locations.toLocaleString()}</span>
                    <span className="stat-card__label">Total</span>
                  </div>
                  <div className="stat-card">
                    <span className="stat-card__value" style={{ color: '#10b981' }}>{selectedDataset.enhanced_count.toLocaleString()}</span>
                    <span className="stat-card__label">Enhanced</span>
                  </div>
                  {locationsData && (
                    <>
                      <div className="stat-card">
                        <span className="stat-card__value" style={{ color: '#2563eb' }}>{locationsData.labelled_count.toLocaleString()}</span>
                        <span className="stat-card__label">Labelled</span>
                      </div>
                      <div className="stat-card">
                        <span className="stat-card__value" style={{ color: '#f59e0b' }}>{locationsData.unlabelled_count.toLocaleString()}</span>
                        <span className="stat-card__label">Not Labelled</span>
                      </div>
                    </>
                  )}
                </div>

                {/* Search and Controls */}
                <div style={{ 
                  background: 'white', 
                  borderRadius: '12px', 
                  padding: '20px',
                  border: '1px solid #e5e7eb',
                  marginBottom: '20px'
                }}>
                  <form onSubmit={handleSearch} style={{ display: 'flex', gap: '12px', marginBottom: '16px' }}>
                    <input
                      className="govuk-input"
                      type="text"
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      placeholder="Search by identifier..."
                      style={{ flex: 1 }}
                    />
                    <button type="submit" className="govuk-button govuk-button--secondary" style={{ marginBottom: 0 }}>
                      Search
                    </button>
                  </form>
                  
                  <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                    <button 
                      type="button" 
                      className={`govuk-button govuk-button--secondary`}
                      onClick={() => setShowColumnSelector(!showColumnSelector)}
                      style={{ marginBottom: 0 }}
                    >
                      📊 Columns ({visibleColumns.length}/{selectedDataset.columns.length})
                    </button>
                    <button 
                      type="button" 
                      className={`govuk-button ${showFilters ? '' : 'govuk-button--secondary'}`}
                      onClick={() => setShowFilters(!showFilters)}
                      style={{ marginBottom: 0 }}
                    >
                      🔍 Filters {activeFilterCount > 0 && `(${activeFilterCount})`}
                    </button>
                    {activeFilterCount > 0 && (
                      <button 
                        type="button" 
                        className="govuk-button govuk-button--warning"
                        onClick={clearFilters}
                        style={{ marginBottom: 0 }}
                      >
                        Clear filters
                      </button>
                    )}
                  </div>
                </div>

                {/* Column Selector */}
                {showColumnSelector && (
                  <div style={{ 
                    background: '#f9fafb', 
                    borderRadius: '12px',
                    padding: '20px',
                    marginBottom: '20px',
                    border: '1px solid #e5e7eb'
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                      <h3 className="govuk-heading-s" style={{ margin: 0 }}>Select Columns to Display</h3>
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <button
                          className="govuk-link"
                          style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '14px' }}
                          onClick={() => setVisibleColumns(selectedDataset.columns.map(c => c.key))}
                        >
                          Select all
                        </button>
                        <span style={{ color: '#d1d5db' }}>|</span>
                        <button
                          className="govuk-link"
                          style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '14px' }}
                          onClick={() => setVisibleColumns(['identifier'])}
                        >
                          Clear
                        </button>
                      </div>
                    </div>
                    
                    {/* Group columns by source */}
                    {['system', 'enhanced', 'computed', 'original'].map(source => {
                      const sourceCols = selectedDataset.columns.filter(c => c.source === source)
                      if (sourceCols.length === 0) return null
                      
                      const sourceLabels: Record<string, string> = {
                        system: 'System Fields',
                        enhanced: 'Enhanced Fields',
                        computed: 'Labelling Fields',
                        original: 'Original CSV Columns'
                      }
                      
                      return (
                        <div key={source} style={{ marginBottom: '16px' }}>
                          <p className="govuk-body-s" style={{ fontWeight: 600, color: '#6b7280', marginBottom: '8px' }}>
                            {sourceLabels[source]}
                          </p>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                            {sourceCols.map(col => (
                              <label
                                key={col.key}
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '6px',
                                  padding: '8px 12px',
                                  background: visibleColumns.includes(col.key) ? '#dbeafe' : 'white',
                                  border: `1px solid ${visibleColumns.includes(col.key) ? '#2563eb' : '#e5e7eb'}`,
                                  borderRadius: '6px',
                                  cursor: 'pointer',
                                  fontSize: '14px',
                                  transition: 'all 0.15s ease'
                                }}
                              >
                                <input
                                  type="checkbox"
                                  checked={visibleColumns.includes(col.key)}
                                  onChange={() => toggleColumn(col.key)}
                                  style={{ width: '16px', height: '16px' }}
                                />
                                {col.label}
                              </label>
                            ))}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}

                {/* Column Filters */}
                {showFilters && (
                  <div style={{ 
                    background: '#f9fafb', 
                    borderRadius: '12px',
                    padding: '20px',
                    marginBottom: '20px',
                    border: '1px solid #e5e7eb'
                  }}>
                    <h3 className="govuk-heading-s" style={{ marginBottom: '16px' }}>Filter by Column</h3>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '16px' }}>
                      {filterableColumns.slice(0, 12).map(col => {
                        const filterOptions = selectedDataset.filter_values[col.key] || []
                        
                        return (
                          <div key={col.key} className="govuk-form-group" style={{ marginBottom: 0 }}>
                            <label className="govuk-label" style={{ fontSize: '14px', marginBottom: '6px' }}>
                              {col.label}
                            </label>
                            {filterOptions.length > 0 ? (
                              <select
                                className="govuk-select"
                                value={columnFilters[col.key] || ''}
                                onChange={(e) => updateFilter(col.key, e.target.value)}
                                style={{ width: '100%' }}
                              >
                                <option value="">All</option>
                                {filterOptions.map(opt => (
                                  <option key={opt} value={opt}>{opt}</option>
                                ))}
                              </select>
                            ) : col.type === 'boolean' ? (
                              <select
                                className="govuk-select"
                                value={columnFilters[col.key] || ''}
                                onChange={(e) => updateFilter(col.key, e.target.value)}
                                style={{ width: '100%' }}
                              >
                                <option value="">All</option>
                                <option value="true">Yes</option>
                                <option value="false">No</option>
                              </select>
                            ) : (
                              <input
                                className="govuk-input"
                                type="text"
                                value={columnFilters[col.key] || ''}
                                onChange={(e) => updateFilter(col.key, e.target.value)}
                                placeholder={`Filter ${col.label}...`}
                                style={{ width: '100%' }}
                              />
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* Results */}
                {locationsData && (
                  <>
                    <p className="govuk-body" style={{ color: '#6b7280', marginBottom: '16px' }}>
                      Showing {((locationsData.page - 1) * locationsData.page_size) + 1} to{' '}
                      {Math.min(locationsData.page * locationsData.page_size, locationsData.total)} of{' '}
                      <strong>{locationsData.total.toLocaleString()}</strong> locations
                    </p>

                    <div style={{ 
                      background: 'white', 
                      borderRadius: '12px',
                      border: '1px solid #e5e7eb',
                      overflow: 'hidden'
                    }}>
                      <div style={{ overflowX: 'auto' }}>
                        <table className="govuk-table govuk-table--clickable" style={{ marginBottom: 0 }}>
                          <thead className="govuk-table__head">
                            <tr className="govuk-table__row">
                              {selectedDataset.columns
                                .filter(col => visibleColumns.includes(col.key))
                                .map(col => (
                                  <th key={col.key} className="govuk-table__header" style={{ whiteSpace: 'nowrap' }}>
                                    {col.label}
                                  </th>
                                ))}
                            </tr>
                          </thead>
                          <tbody className="govuk-table__body">
                            {locationsData.locations.map((location) => (
                              <tr 
                                key={location.id} 
                                className="govuk-table__row"
                                onClick={() => setSelectedLocation(location)}
                              >
                                {selectedDataset.columns
                                  .filter(col => visibleColumns.includes(col.key))
                                  .map(col => (
                                    <td key={col.key} className="govuk-table__cell" style={{ whiteSpace: 'nowrap' }}>
                                      {getCellValue(location, col)}
                                    </td>
                                  ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    {/* Pagination */}
                    {locationsData.total_pages > 1 && (
                      <div style={{ 
                        display: 'flex', 
                        justifyContent: 'center', 
                        alignItems: 'center',
                        gap: '12px',
                        marginTop: '24px'
                      }}>
                        <button
                          className="govuk-button govuk-button--secondary"
                          onClick={() => handlePageChange(page - 1)}
                          disabled={page <= 1}
                          style={{ marginBottom: 0 }}
                        >
                          ← Previous
                        </button>
                        
                        <span className="govuk-body" style={{ padding: '0 16px' }}>
                          Page <strong>{page}</strong> of <strong>{locationsData.total_pages}</strong>
                        </span>
                        
                        <button
                          className="govuk-button govuk-button--secondary"
                          onClick={() => handlePageChange(page + 1)}
                          disabled={page >= locationsData.total_pages}
                          style={{ marginBottom: 0 }}
                        >
                          Next →
                        </button>
                      </div>
                    )}
                  </>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* Location Detail Modal */}
      {selectedLocation && (
        <div className="modal-overlay" onClick={() => setSelectedLocation(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '1000px' }}>
            <div className="modal__header">
              <div>
                <h2 className="govuk-heading-m" style={{ marginBottom: '4px' }}>
                  {selectedLocation.identifier}
                </h2>
                {selectedLocation.common_name && (
                  <p className="govuk-body" style={{ color: '#6b7280', margin: 0 }}>{selectedLocation.common_name}</p>
                )}
              </div>
              <button className="modal__close" onClick={() => setSelectedLocation(null)}>×</button>
            </div>
            
            <div className="govuk-grid-row">
              {/* Location Info */}
              <div className="govuk-grid-column-one-half">
                <h3 className="govuk-heading-s">Location Details</h3>
                <dl className="govuk-summary-list govuk-summary-list--no-border">
                  <div className="govuk-summary-list__row">
                    <dt className="govuk-summary-list__key">Identifier</dt>
                    <dd className="govuk-summary-list__value"><strong>{selectedLocation.identifier}</strong></dd>
                  </div>
                  <div className="govuk-summary-list__row">
                    <dt className="govuk-summary-list__key">Coordinates</dt>
                    <dd className="govuk-summary-list__value">{selectedLocation.latitude.toFixed(6)}, {selectedLocation.longitude.toFixed(6)}</dd>
                  </div>
                  <div className="govuk-summary-list__row">
                    <dt className="govuk-summary-list__key">Council</dt>
                    <dd className="govuk-summary-list__value">{selectedLocation.council || <em style={{ color: '#9ca3af' }}>Not set</em>}</dd>
                  </div>
                  <div className="govuk-summary-list__row">
                    <dt className="govuk-summary-list__key">Combined Authority</dt>
                    <dd className="govuk-summary-list__value">{selectedLocation.combined_authority || <em style={{ color: '#9ca3af' }}>Not set</em>}</dd>
                  </div>
                  <div className="govuk-summary-list__row">
                    <dt className="govuk-summary-list__key">Road Classification</dt>
                    <dd className="govuk-summary-list__value">{selectedLocation.road_classification || <em style={{ color: '#9ca3af' }}>Not set</em>}</dd>
                  </div>
                  <div className="govuk-summary-list__row">
                    <dt className="govuk-summary-list__key">Enhanced</dt>
                    <dd className="govuk-summary-list__value">
                      {selectedLocation.is_enhanced ? (
                        <strong className="govuk-tag govuk-tag--green">Yes</strong>
                      ) : (
                        <strong className="govuk-tag govuk-tag--grey">No</strong>
                      )}
                    </dd>
                  </div>
                </dl>

                <h3 className="govuk-heading-s" style={{ marginTop: '24px' }}>Labelling Status</h3>
                <dl className="govuk-summary-list govuk-summary-list--no-border">
                  <div className="govuk-summary-list__row">
                    <dt className="govuk-summary-list__key">Status</dt>
                    <dd className="govuk-summary-list__value">
                      {selectedLocation.labelling_status === 'Labelled' ? (
                        <strong className="govuk-tag govuk-tag--green">Labelled</strong>
                      ) : (
                        <strong className="govuk-tag govuk-tag--grey">Not Labelled</strong>
                      )}
                    </dd>
                  </div>
                  <div className="govuk-summary-list__row">
                    <dt className="govuk-summary-list__key">Labeller</dt>
                    <dd className="govuk-summary-list__value">{selectedLocation.labeller_name || <em style={{ color: '#9ca3af' }}>—</em>}</dd>
                  </div>
                  <div className="govuk-summary-list__row">
                    <dt className="govuk-summary-list__key">Advertising Present</dt>
                    <dd className="govuk-summary-list__value">
                      {selectedLocation.advertising_present === null ? (
                        <em style={{ color: '#9ca3af' }}>Not labelled</em>
                      ) : selectedLocation.advertising_present ? (
                        <strong className="govuk-tag govuk-tag--blue">Yes</strong>
                      ) : (
                        <strong className="govuk-tag govuk-tag--grey">No</strong>
                      )}
                    </dd>
                  </div>
                </dl>
              </div>
              
              {/* Original Data */}
              <div className="govuk-grid-column-one-half">
                <h3 className="govuk-heading-s">Original CSV Data</h3>
                <div style={{ 
                  background: '#f9fafb', 
                  padding: '16px', 
                  borderRadius: '8px',
                  maxHeight: '400px',
                  overflowY: 'auto'
                }}>
                  <dl className="govuk-summary-list govuk-summary-list--no-border">
                    {Object.entries(selectedLocation.original_data || {}).map(([key, value]) => (
                      <div key={key} className="govuk-summary-list__row">
                        <dt className="govuk-summary-list__key" style={{ fontSize: '14px' }}>{key}</dt>
                        <dd className="govuk-summary-list__value" style={{ fontSize: '14px' }}>
                          {value !== null && value !== undefined ? String(value) : <em style={{ color: '#9ca3af' }}>—</em>}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </div>
              </div>
            </div>

            <div style={{ marginTop: '24px', display: 'flex', gap: '12px' }}>
              <a 
                href={`https://www.google.com/maps?q=${selectedLocation.latitude},${selectedLocation.longitude}`}
                target="_blank"
                rel="noopener noreferrer"
                className="govuk-button govuk-button--secondary"
              >
                View on Google Maps
              </a>
              <a 
                href={`https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${selectedLocation.latitude},${selectedLocation.longitude}`}
                target="_blank"
                rel="noopener noreferrer"
                className="govuk-button govuk-button--secondary"
              >
                View Street View
              </a>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
