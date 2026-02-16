import { useState, useEffect } from 'react'
import { tasksApi } from '../services/api'
import Modal from './common/Modal'

interface FilterField {
  field: string
  sample_values: string[]
  total_distinct: number
}

interface Filter {
  field: string
  operator: string
  value: any
}

interface TaskFilterModalProps {
  isOpen: boolean
  onClose: () => void
  taskId: string
  taskName: string
  currentFilters: Filter[]
  onFiltersUpdated: () => void
}

const OPERATORS = [
  { value: 'equals', label: 'Equals' },
  { value: 'not_equals', label: 'Does not equal' },
  { value: 'contains', label: 'Contains' },
  { value: 'is_null', label: 'Is empty' },
  { value: 'is_not_null', label: 'Is not empty' },
]

export default function TaskFilterModal({
  isOpen,
  onClose,
  taskId,
  taskName,
  currentFilters,
  onFiltersUpdated
}: TaskFilterModalProps) {
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [fields, setFields] = useState<FilterField[]>([])
  const [filters, setFilters] = useState<Filter[]>(currentFilters || [])
  const [error, setError] = useState('')

  useEffect(() => {
    if (isOpen && taskId) {
      loadFilterFields()
      setFilters(currentFilters || [])
    }
  }, [isOpen, taskId, currentFilters])

  const loadFilterFields = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await tasksApi.getTaskFilterFields(taskId)
      setFields(response.data.fields || [])
    } catch (err: any) {
      setError('Failed to load filter fields')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const addFilter = () => {
    setFilters([...filters, { field: '', operator: 'equals', value: '' }])
  }

  const removeFilter = (index: number) => {
    setFilters(filters.filter((_, i) => i !== index))
  }

  const updateFilter = (index: number, updates: Partial<Filter>) => {
    const newFilters = [...filters]
    newFilters[index] = { ...newFilters[index], ...updates }
    setFilters(newFilters)
  }

  const handleSave = async () => {
    // Validate filters
    const validFilters = filters.filter(f => f.field && f.operator)
    
    // For operators that need values, check if value is provided
    for (const filter of validFilters) {
      if (!['is_null', 'is_not_null'].includes(filter.operator) && !filter.value) {
        setError(`Please provide a value for the "${filter.field}" filter`)
        return
      }
    }

    setSaving(true)
    setError('')
    try {
      await tasksApi.updateTaskFilters(taskId, validFilters)
      onFiltersUpdated()
      onClose()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save filters')
    } finally {
      setSaving(false)
    }
  }

  const handleClear = async () => {
    setSaving(true)
    setError('')
    try {
      await tasksApi.clearTaskFilters(taskId)
      setFilters([])
      onFiltersUpdated()
      onClose()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to clear filters')
    } finally {
      setSaving(false)
    }
  }

  const getFieldValues = (fieldName: string): string[] => {
    const field = fields.find(f => f.field === fieldName)
    return field?.sample_values || []
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={`Filter Task: ${taskName}`}>
      <div style={{ minWidth: '500px' }}>
        {error && (
          <div className="govuk-error-summary" style={{ marginBottom: '20px' }}>
            <p className="govuk-error-summary__body">{error}</p>
          </div>
        )}

        <p className="govuk-body" style={{ marginBottom: '20px' }}>
          Add filters to limit which locations are shown in this task. 
          Filters are applied to columns from the original spreadsheet data.
        </p>

        {loading ? (
          <p className="govuk-body">Loading available fields...</p>
        ) : (
          <>
            {/* Current Filters */}
            <div style={{ marginBottom: '24px' }}>
              <h3 className="govuk-heading-s" style={{ marginBottom: '12px' }}>
                Active Filters
              </h3>
              
              {filters.length === 0 ? (
                <p className="govuk-body" style={{ color: '#6b7280', fontStyle: 'italic' }}>
                  No filters applied. All locations in this task will be shown.
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {filters.map((filter, index) => (
                    <div 
                      key={index} 
                      style={{ 
                        display: 'grid', 
                        gridTemplateColumns: '1fr 140px 1fr auto', 
                        gap: '8px',
                        alignItems: 'end',
                        padding: '12px',
                        background: '#f9fafb',
                        borderRadius: '8px'
                      }}
                    >
                      {/* Field selector */}
                      <div>
                        <label className="govuk-label" style={{ fontSize: '12px', marginBottom: '4px' }}>
                          Field
                        </label>
                        <select
                          className="govuk-select"
                          value={filter.field}
                          onChange={(e) => updateFilter(index, { field: e.target.value, value: '' })}
                          style={{ width: '100%' }}
                        >
                          <option value="">Select field...</option>
                          {fields.map(f => (
                            <option key={f.field} value={f.field}>
                              {f.field} ({f.total_distinct} values)
                            </option>
                          ))}
                        </select>
                      </div>

                      {/* Operator selector */}
                      <div>
                        <label className="govuk-label" style={{ fontSize: '12px', marginBottom: '4px' }}>
                          Condition
                        </label>
                        <select
                          className="govuk-select"
                          value={filter.operator}
                          onChange={(e) => updateFilter(index, { operator: e.target.value })}
                          style={{ width: '100%' }}
                        >
                          {OPERATORS.map(op => (
                            <option key={op.value} value={op.value}>{op.label}</option>
                          ))}
                        </select>
                      </div>

                      {/* Value selector/input */}
                      <div>
                        <label className="govuk-label" style={{ fontSize: '12px', marginBottom: '4px' }}>
                          Value
                        </label>
                        {['is_null', 'is_not_null'].includes(filter.operator) ? (
                          <input
                            className="govuk-input"
                            disabled
                            placeholder="(no value needed)"
                            style={{ width: '100%', background: '#e5e7eb' }}
                          />
                        ) : filter.field && getFieldValues(filter.field).length > 0 ? (
                          <select
                            className="govuk-select"
                            value={filter.value}
                            onChange={(e) => updateFilter(index, { value: e.target.value })}
                            style={{ width: '100%' }}
                          >
                            <option value="">Select value...</option>
                            {getFieldValues(filter.field).map(v => (
                              <option key={v} value={v}>{v}</option>
                            ))}
                          </select>
                        ) : (
                          <input
                            className="govuk-input"
                            type="text"
                            value={filter.value || ''}
                            onChange={(e) => updateFilter(index, { value: e.target.value })}
                            placeholder="Enter value..."
                            style={{ width: '100%' }}
                          />
                        )}
                      </div>

                      {/* Remove button */}
                      <button
                        type="button"
                        onClick={() => removeFilter(index)}
                        style={{
                          padding: '8px 12px',
                          background: '#fee2e2',
                          color: '#dc2626',
                          border: 'none',
                          borderRadius: '6px',
                          cursor: 'pointer',
                          fontSize: '14px'
                        }}
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <button
                type="button"
                onClick={addFilter}
                className="govuk-button govuk-button--secondary"
                style={{ marginTop: '12px' }}
              >
                + Add Filter
              </button>
            </div>

            {/* Example filters */}
            {fields.length > 0 && (
              <div style={{ 
                padding: '16px', 
                background: '#eff6ff', 
                borderRadius: '8px',
                marginBottom: '24px'
              }}>
                <h4 className="govuk-heading-s" style={{ marginBottom: '8px', fontSize: '14px' }}>
                  💡 Example: Filter by BusStopType
                </h4>
                <p className="govuk-body-s" style={{ margin: 0 }}>
                  To show only locations where <strong>BusStopType = "MKD"</strong>, add a filter with:
                  <br />
                  Field: <code>BusStopType</code> | Condition: <code>Equals</code> | Value: <code>MKD</code>
                </p>
              </div>
            )}

            {/* Actions */}
            <div className="govuk-button-group">
              <button
                className="govuk-button"
                onClick={handleSave}
                disabled={saving}
              >
                {saving ? 'Saving...' : 'Apply Filters'}
              </button>
              {currentFilters && currentFilters.length > 0 && (
                <button
                  className="govuk-button govuk-button--warning"
                  onClick={handleClear}
                  disabled={saving}
                >
                  Clear All Filters
                </button>
              )}
              <button
                className="govuk-button govuk-button--secondary"
                onClick={onClose}
              >
                Cancel
              </button>
            </div>
          </>
        )}
      </div>
    </Modal>
  )
}
