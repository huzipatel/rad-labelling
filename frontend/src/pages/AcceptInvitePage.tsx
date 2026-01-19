import { useEffect, useState } from 'react'
import { useSearchParams, useNavigate, Link } from 'react-router-dom'
import { invitationsApi } from '../services/api'
import Loading from '../components/common/Loading'

interface InvitationInfo {
  valid: boolean
  email: string
  name: string | null
  role: string
  message: string | null
  inviter_name: string
}

export default function AcceptInvitePage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token')

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [invitation, setInvitation] = useState<InvitationInfo | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [success, setSuccess] = useState(false)

  // Form state
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [whatsappNumber, setWhatsappNumber] = useState('')
  const [sameAsPhone, setSameAsPhone] = useState(true)

  useEffect(() => {
    if (!token) {
      setError('No invitation token provided')
      setLoading(false)
      return
    }

    validateInvitation()
  }, [token])

  const validateInvitation = async () => {
    try {
      const response = await invitationsApi.validate(token!)
      setInvitation(response.data)
      if (response.data.name) {
        setName(response.data.name)
      }
    } catch (err: any) {
      const detail = err.response?.data?.detail
      setError(detail || 'Invalid or expired invitation')
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (password !== confirmPassword) {
      alert('Passwords do not match')
      return
    }

    if (password.length < 8) {
      alert('Password must be at least 8 characters')
      return
    }

    setSubmitting(true)
    try {
      await invitationsApi.accept({
        token: token!,
        name,
        password,
        phone_number: phoneNumber || undefined,
        whatsapp_number: sameAsPhone ? phoneNumber : whatsappNumber || undefined
      })
      setSuccess(true)
    } catch (err: any) {
      const detail = err.response?.data?.detail
      alert(detail || 'Failed to create account')
    } finally {
      setSubmitting(false)
    }
  }

  const getRoleDisplay = (role: string) => {
    const roles: Record<string, string> = {
      labeller: 'Labeller',
      labelling_manager: 'Manager',
      admin: 'Administrator'
    }
    return roles[role] || role
  }

  if (loading) return <Loading />

  if (error) {
    return (
      <div className="auth-container">
        <div className="auth-card">
          <div className="auth-header">
            <h1>AdVue UK</h1>
          </div>
          <div style={{ textAlign: 'center', padding: '40px 20px' }}>
            <div style={{ fontSize: '48px', marginBottom: '16px' }}>❌</div>
            <h2 className="govuk-heading-m">Invalid Invitation</h2>
            <p className="govuk-body" style={{ color: '#6b7280' }}>{error}</p>
            <Link to="/login" className="govuk-button" style={{ marginTop: '24px' }}>
              Go to Login
            </Link>
          </div>
        </div>
      </div>
    )
  }

  if (success) {
    return (
      <div className="auth-container">
        <div className="auth-card">
          <div className="auth-header">
            <h1>AdVue UK</h1>
          </div>
          <div style={{ textAlign: 'center', padding: '40px 20px' }}>
            <div style={{ fontSize: '48px', marginBottom: '16px' }}>✅</div>
            <h2 className="govuk-heading-m">Account Created!</h2>
            <p className="govuk-body" style={{ color: '#6b7280' }}>
              Your account has been created successfully. You can now log in.
            </p>
            <Link to="/login" className="govuk-button" style={{ marginTop: '24px' }}>
              Go to Login
            </Link>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="auth-container">
      <div className="auth-card" style={{ maxWidth: '500px' }}>
        <div className="auth-header">
          <h1>AdVue UK</h1>
        </div>

        <div style={{ padding: '32px' }}>
          <h2 className="govuk-heading-m" style={{ marginBottom: '8px' }}>Accept Invitation</h2>
          
          {invitation?.message && (
            <div style={{ 
              background: '#f0fdf4', 
              border: '1px solid #10b981', 
              borderRadius: '8px', 
              padding: '16px',
              marginBottom: '24px'
            }}>
              <p className="govuk-body-s" style={{ margin: 0, fontWeight: 600, color: '#166534' }}>
                Message from {invitation.inviter_name}:
              </p>
              <p className="govuk-body" style={{ margin: '8px 0 0', fontStyle: 'italic', color: '#166534' }}>
                "{invitation.message}"
              </p>
            </div>
          )}

          <div style={{ 
            background: '#f9fafb', 
            borderRadius: '8px', 
            padding: '16px',
            marginBottom: '24px'
          }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <p className="govuk-body-s" style={{ margin: 0, color: '#6b7280' }}>Email</p>
                <p className="govuk-body" style={{ margin: 0, fontWeight: 600 }}>{invitation?.email}</p>
              </div>
              <div>
                <p className="govuk-body-s" style={{ margin: 0, color: '#6b7280' }}>Role</p>
                <p className="govuk-body" style={{ margin: 0, fontWeight: 600 }}>{getRoleDisplay(invitation?.role || '')}</p>
              </div>
              <div style={{ gridColumn: 'span 2' }}>
                <p className="govuk-body-s" style={{ margin: 0, color: '#6b7280' }}>Invited by</p>
                <p className="govuk-body" style={{ margin: 0, fontWeight: 600 }}>{invitation?.inviter_name}</p>
              </div>
            </div>
          </div>

          <form onSubmit={handleSubmit}>
            <div className="govuk-form-group">
              <label className="govuk-label" htmlFor="name">
                Your Name
              </label>
              <input
                className="govuk-input"
                id="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                autoFocus
              />
            </div>

            <div className="govuk-form-group">
              <label className="govuk-label" htmlFor="password">
                Create Password
              </label>
              <p className="govuk-hint">Must be at least 8 characters</p>
              <input
                className="govuk-input"
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
              />
            </div>

            <div className="govuk-form-group">
              <label className="govuk-label" htmlFor="confirmPassword">
                Confirm Password
              </label>
              <input
                className="govuk-input"
                id="confirmPassword"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
              />
              {confirmPassword && password !== confirmPassword && (
                <p style={{ color: '#dc2626', marginTop: '8px', fontSize: '14px' }}>
                  Passwords do not match
                </p>
              )}
            </div>

            <hr className="govuk-section-break govuk-section-break--m govuk-section-break--visible" />
            
            <p className="govuk-body-s" style={{ color: '#6b7280', marginBottom: '16px' }}>
              Optional: Add your phone number to receive notifications
            </p>

            <div className="govuk-form-group">
              <label className="govuk-label" htmlFor="phoneNumber">
                Phone Number (optional)
              </label>
              <input
                className="govuk-input"
                id="phoneNumber"
                type="tel"
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
                placeholder="+44 7xxx xxx xxx"
              />
            </div>

            <div className="govuk-checkboxes govuk-checkboxes--small govuk-!-margin-bottom-4">
              <div className="govuk-checkboxes__item">
                <input
                  className="govuk-checkboxes__input"
                  id="sameAsPhone"
                  type="checkbox"
                  checked={sameAsPhone}
                  onChange={(e) => setSameAsPhone(e.target.checked)}
                />
                <label className="govuk-label govuk-checkboxes__label" htmlFor="sameAsPhone">
                  Use same number for WhatsApp notifications
                </label>
              </div>
            </div>

            {!sameAsPhone && (
              <div className="govuk-form-group">
                <label className="govuk-label" htmlFor="whatsappNumber">
                  WhatsApp Number
                </label>
                <input
                  className="govuk-input"
                  id="whatsappNumber"
                  type="tel"
                  value={whatsappNumber}
                  onChange={(e) => setWhatsappNumber(e.target.value)}
                  placeholder="+44 7xxx xxx xxx"
                />
              </div>
            )}

            <button
              type="submit"
              className="govuk-button"
              disabled={submitting || !name || !password || password !== confirmPassword}
              style={{ width: '100%', marginTop: '16px' }}
            >
              {submitting ? 'Creating Account...' : 'Create Account'}
            </button>
          </form>

          <p className="govuk-body-s" style={{ textAlign: 'center', marginTop: '24px', color: '#6b7280' }}>
            Already have an account? <Link to="/login" className="govuk-link">Log in</Link>
          </p>
        </div>
      </div>
    </div>
  )
}

