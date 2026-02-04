import { useState, useEffect } from 'react'
import { Link, useSearchParams, useNavigate } from 'react-router-dom'
import api from '../services/api'

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token')

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isVerifying, setIsVerifying] = useState(true)
  const [isSubmitted, setIsSubmitted] = useState(false)
  const [error, setError] = useState('')
  const [tokenError, setTokenError] = useState('')

  // Verify token on mount
  useEffect(() => {
    const verifyToken = async () => {
      if (!token) {
        setTokenError('No reset token provided')
        setIsVerifying(false)
        return
      }

      try {
        const response = await api.get(`/auth/verify-reset-token?token=${token}`)
        if (!response.data.valid) {
          setTokenError(response.data.error || 'Invalid reset link')
        }
      } catch (err) {
        setTokenError('Unable to verify reset link')
      } finally {
        setIsVerifying(false)
      }
    }

    verifyToken()
  }, [token])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    // Validate passwords match
    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }

    // Validate password length
    if (password.length < 8) {
      setError('Password must be at least 8 characters long')
      return
    }

    setIsLoading(true)

    try {
      await api.post('/auth/reset-password', {
        token,
        new_password: password
      })
      setIsSubmitted(true)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to reset password. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  // Loading state
  if (isVerifying) {
    return (
      <div className="govuk-width-container">
        <main className="govuk-main-wrapper">
          <div className="govuk-grid-row">
            <div className="govuk-grid-column-two-thirds">
              <h1 className="govuk-heading-xl">Verifying reset link...</h1>
              <p className="govuk-body">Please wait while we verify your password reset link.</p>
            </div>
          </div>
        </main>
      </div>
    )
  }

  // Invalid token
  if (tokenError) {
    return (
      <div className="govuk-width-container">
        <main className="govuk-main-wrapper">
          <div className="govuk-grid-row">
            <div className="govuk-grid-column-two-thirds">
              <div className="govuk-error-summary" data-module="govuk-error-summary">
                <div role="alert">
                  <h2 className="govuk-error-summary__title">Unable to reset password</h2>
                  <div className="govuk-error-summary__body">
                    <ul className="govuk-list govuk-error-summary__list">
                      <li>{tokenError}</li>
                    </ul>
                  </div>
                </div>
              </div>

              <h1 className="govuk-heading-xl">Reset link invalid</h1>
              <p className="govuk-body">
                This password reset link is invalid or has expired.
              </p>
              <p className="govuk-body">
                <Link to="/forgot-password" className="govuk-link">
                  Request a new password reset link
                </Link>
              </p>
              <p className="govuk-body">
                <Link to="/login" className="govuk-link">
                  Return to sign in
                </Link>
              </p>
            </div>
          </div>
        </main>
      </div>
    )
  }

  // Success state
  if (isSubmitted) {
    return (
      <div className="govuk-width-container">
        <main className="govuk-main-wrapper">
          <div className="govuk-grid-row">
            <div className="govuk-grid-column-two-thirds">
              <div className="govuk-panel govuk-panel--confirmation">
                <h1 className="govuk-panel__title">Password reset successfully</h1>
              </div>

              <p className="govuk-body-l">
                Your password has been changed. You can now sign in with your new password.
              </p>

              <button
                className="govuk-button"
                onClick={() => navigate('/login')}
              >
                Sign in
              </button>
            </div>
          </div>
        </main>
      </div>
    )
  }

  // Reset form
  return (
    <div className="govuk-width-container">
      <main className="govuk-main-wrapper">
        <div className="govuk-grid-row">
          <div className="govuk-grid-column-two-thirds">
            
            <span className="govuk-caption-xl">AdVue UK</span>
            <h1 className="govuk-heading-xl">Create new password</h1>

            <p className="govuk-body-l">
              Enter your new password below.
            </p>

            {error && (
              <div className="govuk-error-summary" data-module="govuk-error-summary">
                <div role="alert">
                  <h2 className="govuk-error-summary__title">There is a problem</h2>
                  <div className="govuk-error-summary__body">
                    <ul className="govuk-list govuk-error-summary__list">
                      <li>{error}</li>
                    </ul>
                  </div>
                </div>
              </div>
            )}

            <form onSubmit={handleSubmit}>
              <div className="govuk-form-group">
                <label className="govuk-label" htmlFor="password">
                  New password
                </label>
                <div className="govuk-hint">
                  Must be at least 8 characters
                </div>
                <input
                  className="govuk-input"
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                />
              </div>

              <div className="govuk-form-group">
                <label className="govuk-label" htmlFor="confirm-password">
                  Confirm new password
                </label>
                <input
                  className="govuk-input"
                  id="confirm-password"
                  name="confirm-password"
                  type="password"
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                />
              </div>

              <button
                type="submit"
                className="govuk-button"
                data-module="govuk-button"
                disabled={isLoading}
              >
                {isLoading ? 'Resetting...' : 'Reset password'}
              </button>
            </form>

          </div>
        </div>
      </main>
    </div>
  )
}
