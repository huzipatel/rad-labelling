import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'

export default function RegisterPage() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [validationError, setValidationError] = useState('')
  const { register, isLoading, error, clearError } = useAuthStore()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setValidationError('')

    if (password !== confirmPassword) {
      setValidationError('Passwords do not match')
      return
    }

    if (password.length < 8) {
      setValidationError('Password must be at least 8 characters')
      return
    }

    try {
      await register(email, password, name)
      navigate('/dashboard')
    } catch {
      // Error handled by store
    }
  }

  const displayError = validationError || error

  return (
    <div className="govuk-width-container">
      <main className="govuk-main-wrapper">
        <div className="govuk-grid-row">
          <div className="govuk-grid-column-two-thirds">
            
            {/* Back link */}
            <Link to="/login" className="govuk-back-link">Back to sign in</Link>

            {/* Service Header */}
            <span className="govuk-caption-xl">AdVue UK</span>
            <h1 className="govuk-heading-xl">Create an account</h1>

            <div className="govuk-inset-text">
              New accounts are created with the Labeller role. Contact an administrator if you need manager or admin permissions.
            </div>

            {displayError && (
              <div className="govuk-error-summary" data-module="govuk-error-summary">
                <div role="alert">
                  <h2 className="govuk-error-summary__title">There is a problem</h2>
                  <div className="govuk-error-summary__body">
                    <ul className="govuk-list govuk-error-summary__list">
                      <li>{displayError}</li>
                    </ul>
                  </div>
                </div>
              </div>
            )}

            <form onSubmit={handleSubmit}>
              <div className="govuk-form-group">
                <label className="govuk-label" htmlFor="name">
                  Full name
                </label>
                <input
                  className="govuk-input"
                  id="name"
                  name="name"
                  type="text"
                  autoComplete="name"
                  spellCheck="false"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value)
                    clearError()
                    setValidationError('')
                  }}
                  required
                />
              </div>

              <div className="govuk-form-group">
                <label className="govuk-label" htmlFor="email">
                  Email address
                </label>
                <hint className="govuk-hint">
                  We'll use this for your sign in
                </hint>
                <input
                  className="govuk-input"
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  spellCheck="false"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value)
                    clearError()
                    setValidationError('')
                  }}
                  required
                />
              </div>

              <div className="govuk-form-group">
                <label className="govuk-label" htmlFor="password">
                  Create a password
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
                  onChange={(e) => {
                    setPassword(e.target.value)
                    clearError()
                    setValidationError('')
                  }}
                  required
                />
              </div>

              <div className="govuk-form-group">
                <label className="govuk-label" htmlFor="confirmPassword">
                  Confirm your password
                </label>
                <input
                  className="govuk-input"
                  id="confirmPassword"
                  name="confirmPassword"
                  type="password"
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(e) => {
                    setConfirmPassword(e.target.value)
                    clearError()
                    setValidationError('')
                  }}
                  required
                />
              </div>

              <button
                type="submit"
                className="govuk-button"
                data-module="govuk-button"
                disabled={isLoading}
              >
                {isLoading ? 'Creating account...' : 'Create account'}
              </button>
            </form>

            <p className="govuk-body govuk-!-margin-top-6">
              Already have an account?{' '}
              <Link to="/login" className="govuk-link">
                Sign in
              </Link>
            </p>

          </div>
        </div>
      </main>
    </div>
  )
}
