import { Outlet, Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'

// Icons as inline SVGs for consistency
const icons = {
  dashboard: (
    <svg viewBox="0 0 24 24" fill="currentColor">
      <path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z"/>
    </svg>
  ),
  tasks: (
    <svg viewBox="0 0 24 24" fill="currentColor">
      <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-9 14l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
    </svg>
  ),
  manager: (
    <svg viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 7V3H2v18h20V7H12zM6 19H4v-2h2v2zm0-4H4v-2h2v2zm0-4H4V9h2v2zm0-4H4V5h2v2zm4 12H8v-2h2v2zm0-4H8v-2h2v2zm0-4H8V9h2v2zm0-4H8V5h2v2zm10 12h-8v-2h2v-2h-2v-2h2v-2h-2V9h8v10zm-2-8h-2v2h2v-2zm0 4h-2v2h2v-2z"/>
    </svg>
  ),
  upload: (
    <svg viewBox="0 0 24 24" fill="currentColor">
      <path d="M9 16h6v-6h4l-7-7-7 7h4zm-4 2h14v2H5z"/>
    </svg>
  ),
  data: (
    <svg viewBox="0 0 24 24" fill="currentColor">
      <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z"/>
    </svg>
  ),
  performance: (
    <svg viewBox="0 0 24 24" fill="currentColor">
      <path d="M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6z"/>
    </svg>
  ),
  exports: (
    <svg viewBox="0 0 24 24" fill="currentColor">
      <path d="M19 12v7H5v-7H3v7c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2v-7h-2zm-6 .67l2.59-2.58L17 11.5l-5 5-5-5 1.41-1.41L11 12.67V3h2z"/>
    </svg>
  ),
  admin: (
    <svg viewBox="0 0 24 24" fill="currentColor">
      <path d="M19.14 12.94c.04-.31.06-.63.06-.94 0-.31-.02-.63-.06-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.04.31-.06.63-.06.94s.02.63.06.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/>
    </svg>
  ),
  logout: (
    <svg viewBox="0 0 24 24" fill="currentColor">
      <path d="M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z"/>
    </svg>
  ),
}

export default function Layout() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const isManager = user?.role === 'labelling_manager' || user?.role === 'admin'
  const isAdmin = user?.role === 'admin'

  const mainNavItems = [
    { path: '/dashboard', label: 'Dashboard', icon: icons.dashboard, show: true },
    { path: '/tasks', label: 'My Tasks', icon: icons.tasks, show: true },
  ]

  const managerNavItems = [
    { path: '/manager', label: 'Manager Dashboard', icon: icons.manager, show: isManager },
    { path: '/upload', label: 'Upload & Enhance', icon: icons.upload, show: isManager },
    { path: '/data', label: 'View Data', icon: icons.data, show: isManager },
    { path: '/performance', label: 'Performance', icon: icons.performance, show: isManager },
    { path: '/exports', label: 'Exports', icon: icons.exports, show: isManager },
  ]

  const adminNavItems = [
    { path: '/admin', label: 'Administration', icon: icons.admin, show: isAdmin },
  ]

  const getRoleLabel = (role: string) => {
    const labels: Record<string, string> = {
      admin: 'Administrator',
      labelling_manager: 'Manager',
      labeller: 'Labeller',
    }
    return labels[role] || role
  }

  const getInitials = (name: string) => {
    return name
      .split(' ')
      .map(n => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2)
  }

  const isActive = (path: string) => {
    return location.pathname === path || location.pathname.startsWith(path + '/')
  }

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className="app-sidebar">
        {/* Logo */}
        <div className="app-sidebar__logo">
          <svg viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect width="36" height="36" rx="8" fill="#2563eb"/>
            <path d="M9 27V9h5.5l4.5 13.5L23.5 9H29v18h-4.5V14.5L21 27h-3.5l-3.5-12.5V27H9z" fill="white"/>
          </svg>
          <span>AdVue UK</span>
        </div>

        {/* Navigation */}
        <nav className="app-sidebar__nav">
          {/* Main Section */}
          <div className="app-sidebar__section">
            <h3 className="app-sidebar__section-title">Main</h3>
            {mainNavItems.filter(item => item.show).map(item => (
              <Link
                key={item.path}
                to={item.path}
                className={`app-sidebar__link ${isActive(item.path) ? 'app-sidebar__link--active' : ''}`}
              >
                {item.icon}
                {item.label}
              </Link>
            ))}
          </div>

          {/* Manager Section */}
          {isManager && (
            <div className="app-sidebar__section">
              <h3 className="app-sidebar__section-title">Management</h3>
              {managerNavItems.filter(item => item.show).map(item => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`app-sidebar__link ${isActive(item.path) ? 'app-sidebar__link--active' : ''}`}
                >
                  {item.icon}
                  {item.label}
                </Link>
              ))}
            </div>
          )}

          {/* Admin Section */}
          {isAdmin && (
            <div className="app-sidebar__section">
              <h3 className="app-sidebar__section-title">System</h3>
              {adminNavItems.filter(item => item.show).map(item => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`app-sidebar__link ${isActive(item.path) ? 'app-sidebar__link--active' : ''}`}
                >
                  {item.icon}
                  {item.label}
                </Link>
              ))}
            </div>
          )}
        </nav>

        {/* User Section */}
        <div className="app-sidebar__user">
          <div className="app-sidebar__user-info">
            <div className="app-sidebar__avatar">
              {getInitials(user?.name || 'U')}
            </div>
            <div className="app-sidebar__user-details">
              <div className="app-sidebar__user-name">{user?.name}</div>
              <div className="app-sidebar__user-role">{getRoleLabel(user?.role || '')}</div>
            </div>
          </div>
          <button className="app-sidebar__logout" onClick={handleLogout}>
            {icons.logout}
            Sign out
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="app-main-wrapper">
        <header className="app-header">
          <div className="app-header__breadcrumb">
            <span style={{ color: '#9ca3af' }}>AdVue UK</span>
            <span style={{ color: '#d1d5db' }}>/</span>
            <span style={{ color: '#374151', fontWeight: 500 }}>
              {location.pathname.split('/')[1]?.charAt(0).toUpperCase() + location.pathname.split('/')[1]?.slice(1) || 'Dashboard'}
            </span>
          </div>
          <div style={{ fontSize: '13px', color: '#6b7280' }}>
            {new Date().toLocaleDateString('en-GB', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
          </div>
        </header>

        <main className="app-main">
          <Outlet />
        </main>

        <footer className="app-footer">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <svg viewBox="0 0 24 24" fill="none" style={{ width: 18, height: 18 }}>
              <rect width="24" height="24" rx="5" fill="#6b7280"/>
              <path d="M6 18V6h3.5l3 9 3-9H19v12h-3v-8.5L13.5 18h-2.5L8.5 9.5V18H6z" fill="white"/>
            </svg>
            <span style={{ fontWeight: 600 }}>AdVue UK</span>
            <span style={{ color: '#d1d5db' }}>•</span>
            <span>Advertising Location Intelligence</span>
          </div>
          <span>© {new Date().getFullYear()} AdVue UK. All rights reserved.</span>
        </footer>
      </div>
    </div>
  )
}
