import { useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../services/api'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isSubmitted, setIsSubmitted] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    setError('')

    try {
      await api.post('/auth/forgot-password', { email })
      setIsSubmitted(true)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to send reset email. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  if (isSubmitted) {
    return (
      <div className="govuk-width-container">
        <main className="govuk-main-wrapper">
          <div className="govuk-grid-row">
            <div className="govuk-grid-column-two-thirds">
              <div className="govuk-panel govuk-panel--confirmation">
                <h1 className="govuk-panel__title">Check your email</h1>
              </div>

              <p className="govuk-body-l">
                If an account exists for <strong>{email}</strong>, we've sent a password reset link.
              </p>

              <h2 className="govuk-heading-m">What happens next</h2>
              <p className="govuk-body">
                Check your email inbox (and spam folder) for a message from AdVue UK.
                The link in the email will expire in 1 hour.
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

  return (
    <div className="govuk-width-container">
      <main className="govuk-main-wrapper">
        <div className="govuk-grid-row">
          <div className="govuk-grid-column-two-thirds">
            
            <Link to="/login" className="govuk-back-link">Back to sign in</Link>

            <span className="govuk-caption-xl">AdVue UK</span>
            <h1 className="govuk-heading-xl">Reset your password</h1>

            <p className="govuk-body-l">
              Enter your email address and we'll send you a link to reset your password.
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
                <label className="govuk-label" htmlFor="email">
                  Email address
                </label>
                <div className="govuk-hint">
                  Enter the email address you used to create your account
                </div>
                <input
                  className="govuk-input"
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  spellCheck="false"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>

              <button
                type="submit"
                className="govuk-button"
                data-module="govuk-button"
                disabled={isLoading}
              >
                {isLoading ? 'Sending...' : 'Send reset link'}
              </button>
            </form>

          </div>
        </div>
      </main>
    </div>
  )
}
