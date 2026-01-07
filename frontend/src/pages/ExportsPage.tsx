import { useEffect, useState } from 'react'
import { spreadsheetsApi, exportsApi } from '../services/api'
import Loading from '../components/common/Loading'

interface LocationType {
  id: string
  name: string
  display_name: string
  location_count: number
}

interface Council {
  council: string
  location_count: number
}

export default function ExportsPage() {
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState(false)
  const [locationTypes, setLocationTypes] = useState<LocationType[]>([])
  const [councils, setCouncils] = useState<Council[]>([])
  
  const [selectedType, setSelectedType] = useState('')
  const [selectedCouncil, setSelectedCouncil] = useState('')
  const [includeUnlabelled, setIncludeUnlabelled] = useState(false)
  const [onlyWithAdvertising, setOnlyWithAdvertising] = useState(true)

  useEffect(() => {
    loadLocationTypes()
  }, [])

  useEffect(() => {
    if (selectedType) {
      loadCouncils()
    }
  }, [selectedType])

  const loadLocationTypes = async () => {
    try {
      const response = await spreadsheetsApi.getLocationTypes()
      setLocationTypes(response.data)
    } catch (error) {
      console.error('Failed to load location types:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadCouncils = async () => {
    try {
      const response = await spreadsheetsApi.getCouncils(selectedType)
      setCouncils(response.data)
    } catch (error) {
      console.error('Failed to load councils:', error)
    }
  }

  const handleExportCSV = async () => {
    if (!selectedType) return

    setExporting(true)
    try {
      const response = await exportsApi.exportCsv(
        selectedType,
        selectedCouncil || undefined
      )

      // Create download link
      const blob = new Blob([response.data], { type: 'text/csv' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `labelling_export_${new Date().toISOString().split('T')[0]}.csv`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error('Failed to export CSV:', error)
      alert('Export failed')
    } finally {
      setExporting(false)
    }
  }

  const handleExportImages = async () => {
    if (!selectedType) return

    setExporting(true)
    try {
      const response = await exportsApi.exportImages(
        selectedType,
        selectedCouncil || undefined
      )

      // Create download link
      const blob = new Blob([response.data], { type: 'application/zip' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `images_export_${new Date().toISOString().split('T')[0]}.zip`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error('Failed to export images:', error)
      alert('Export failed')
    } finally {
      setExporting(false)
    }
  }

  if (loading) return <Loading />

  return (
    <>
      <h1 className="govuk-heading-xl">Export Data</h1>

      <div className="govuk-grid-row">
        <div className="govuk-grid-column-two-thirds">
          {/* Filters */}
          <div className="govuk-form-group">
            <label className="govuk-label" htmlFor="locationType">
              Location Type
            </label>
            <select
              className="govuk-select"
              id="locationType"
              value={selectedType}
              onChange={(e) => {
                setSelectedType(e.target.value)
                setSelectedCouncil('')
              }}
            >
              <option value="">Select a type</option>
              {locationTypes.map((type) => (
                <option key={type.id} value={type.id}>
                  {type.display_name} ({type.location_count.toLocaleString()} locations)
                </option>
              ))}
            </select>
          </div>

          {councils.length > 0 && (
            <div className="govuk-form-group">
              <label className="govuk-label" htmlFor="council">
                Council (optional)
              </label>
              <select
                className="govuk-select"
                id="council"
                value={selectedCouncil}
                onChange={(e) => setSelectedCouncil(e.target.value)}
              >
                <option value="">All councils</option>
                {councils.map((c) => (
                  <option key={c.council} value={c.council}>
                    {c.council} ({c.location_count.toLocaleString()} locations)
                  </option>
                ))}
              </select>
            </div>
          )}

          <hr className="govuk-section-break govuk-section-break--l govuk-section-break--visible" />

          {/* CSV Export */}
          <h2 className="govuk-heading-m">Export Labelling Results (CSV)</h2>
          <p className="govuk-body">
            Download a CSV file containing all labelling results including location identifiers,
            coordinates, label values, and image URLs.
          </p>

          <div className="govuk-checkboxes govuk-checkboxes--small govuk-!-margin-bottom-4">
            <div className="govuk-checkboxes__item">
              <input
                className="govuk-checkboxes__input"
                id="includeUnlabelled"
                type="checkbox"
                checked={includeUnlabelled}
                onChange={(e) => setIncludeUnlabelled(e.target.checked)}
              />
              <label className="govuk-label govuk-checkboxes__label" htmlFor="includeUnlabelled">
                Include unlabelled locations
              </label>
            </div>
          </div>

          <button
            className="govuk-button"
            onClick={handleExportCSV}
            disabled={!selectedType || exporting}
          >
            {exporting ? 'Exporting...' : 'Download CSV'}
          </button>

          <hr className="govuk-section-break govuk-section-break--l govuk-section-break--visible" />

          {/* Image Export */}
          <h2 className="govuk-heading-m">Export Images (ZIP)</h2>
          <p className="govuk-body">
            Download a ZIP file containing all Street View images. Images are organized by council
            and named by location identifier.
          </p>

          <div className="govuk-checkboxes govuk-checkboxes--small govuk-!-margin-bottom-4">
            <div className="govuk-checkboxes__item">
              <input
                className="govuk-checkboxes__input"
                id="onlyWithAdvertising"
                type="checkbox"
                checked={onlyWithAdvertising}
                onChange={(e) => setOnlyWithAdvertising(e.target.checked)}
              />
              <label className="govuk-label govuk-checkboxes__label" htmlFor="onlyWithAdvertising">
                Only include locations with advertising
              </label>
            </div>
          </div>

          <button
            className="govuk-button govuk-button--secondary"
            onClick={handleExportImages}
            disabled={!selectedType || exporting}
          >
            {exporting ? 'Exporting...' : 'Download Images ZIP'}
          </button>

          <div className="govuk-warning-text govuk-!-margin-top-6">
            <span className="govuk-warning-text__icon" aria-hidden="true">!</span>
            <strong className="govuk-warning-text__text">
              <span className="govuk-warning-text__assistive">Warning</span>
              Image exports may take several minutes for large datasets.
            </strong>
          </div>
        </div>

        {/* Help */}
        <div className="govuk-grid-column-one-third">
          <div className="govuk-card">
            <h3 className="govuk-heading-s">Export Format</h3>
            <p className="govuk-body-s">
              CSV exports include the following columns:
            </p>
            <ul className="govuk-list govuk-list--bullet govuk-body-s">
              <li>Location identifier (ATCOCode)</li>
              <li>Latitude & longitude</li>
              <li>Council</li>
              <li>Combined authority</li>
              <li>Road classification</li>
              <li>All label fields</li>
              <li>Image URLs (4 headings + snapshot)</li>
              <li>Labelling timestamp</li>
            </ul>
          </div>
        </div>
      </div>
    </>
  )
}

