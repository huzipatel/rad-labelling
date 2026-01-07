import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const { login, isLoading, error, clearError } = useAuthStore()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await login(email, password)
      navigate('/dashboard')
    } catch {
      // Error handled by store
    }
  }

  return (
    <div className="govuk-width-container">
      <main className="govuk-main-wrapper">
        <div className="govuk-grid-row">
          <div className="govuk-grid-column-two-thirds">
            
            {/* Service Header */}
            <span className="govuk-caption-xl">AdVue UK</span>
            <h1 className="govuk-heading-xl">Sign in</h1>

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
                  }}
                  required
                />
              </div>

              <div className="govuk-form-group">
                <label className="govuk-label" htmlFor="password">
                  Password
                </label>
                <input
                  className="govuk-input"
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value)
                    clearError()
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
                {isLoading ? 'Signing in...' : 'Sign in'}
              </button>
            </form>

            <h2 className="govuk-heading-m govuk-!-margin-top-6">
              Do not have an account?
            </h2>
            <p className="govuk-body">
              <Link to="/register" className="govuk-link">
                Create an account
              </Link>
              {' '}to start labelling advertising locations.
            </p>

          </div>
        </div>
      </main>
    </div>
  )
}
