import { useEffect, useState } from 'react'
import { usersApi, adminApi, invitationsApi } from '../services/api'
import Loading from '../components/common/Loading'
import Modal from '../components/common/Modal'

interface User {
  id: string
  email: string
  name: string
  role: string
  hourly_rate: number | null
  whatsapp_number: string | null
  is_active: boolean
}

interface SystemStats {
  total_users: number
  total_labellers: number
  total_managers: number
  total_locations: number
  total_tasks: number
  tasks_in_progress: number
  tasks_completed: number
}

interface Invitation {
  id: string
  email: string
  name: string | null
  role: string
  status: string
  message: string | null
  invited_by_name: string
  created_at: string
  expires_at: string
  accepted_at: string | null
}

interface GsvKey {
  id: string
  api_key: string
  api_key_prefix: string
  label: string | null
  is_active: boolean
  requests_today: number
  requests_total: number
  last_used_at: string | null
  consecutive_errors: number
  last_error_at: string | null
  last_error_message: string | null
  quota_exhausted: boolean
  created_at: string
  status: string
}

interface GsvSummary {
  total_keys: number
  active_keys: number
  exhausted_keys: number
  disabled_keys: number
  total_requests_today: number
  daily_capacity: number
  estimated_hours_for_1_7m: number
}

export default function AdminPage() {
  const [loading, setLoading] = useState(true)
  const [users, setUsers] = useState<User[]>([])
  const [stats, setStats] = useState<SystemStats | null>(null)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [roleFilter, setRoleFilter] = useState('')
  const [search, setSearch] = useState('')
  
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [selectedUser, setSelectedUser] = useState<User | null>(null)
  
  // Tab state
  const [activeTab, setActiveTab] = useState<'users' | 'invitations' | 'gsv-keys'>('users')
  
  // Invitations state
  const [invitations, setInvitations] = useState<Invitation[]>([])
  const [inviteModalOpen, setInviteModalOpen] = useState(false)
  const [inviteStatusFilter, setInviteStatusFilter] = useState('')
  const [sendingInvite, setSendingInvite] = useState(false)
  
  const [inviteFormData, setInviteFormData] = useState({
    email: '',
    name: '',
    role: 'labeller',
    message: '',
  })
  
  // GSV Keys state (simplified)
  const [gsvKeys, setGsvKeys] = useState<GsvKey[]>([])
  const [gsvSummary, setGsvSummary] = useState<GsvSummary | null>(null)
  const [gsvLoading, setGsvLoading] = useState(false)
  const [addKeysModalOpen, setAddKeysModalOpen] = useState(false)
  const [bulkKeysText, setBulkKeysText] = useState('')
  const [syncingKeys, setSyncingKeys] = useState(false)
  
  const [formData, setFormData] = useState({
    email: '',
    name: '',
    password: '',
    role: 'labeller',
    hourly_rate: '',
    whatsapp_number: '',
  })

  useEffect(() => {
    loadData()
  }, [page, roleFilter, search])

  useEffect(() => {
    if (activeTab === 'invitations') {
      loadInvitations()
    }
    if (activeTab === 'gsv-keys') {
      loadGsvData()
    }
  }, [activeTab, inviteStatusFilter])

  const loadData = async () => {
    try {
      const usersRes = await usersApi.getUsers({ page, page_size: 20, role: roleFilter || undefined, search: search || undefined })
      setUsers(usersRes.data?.users || [])
      setTotal(usersRes.data?.total || 0)
    } catch (error) {
      console.error('Failed to load users:', error)
      setUsers([])
      setTotal(0)
    }
    
    try {
      const statsRes = await adminApi.getSystemStats()
      setStats(statsRes.data)
    } catch (error) {
      console.error('Failed to load stats:', error)
      setStats(null)
    }
    
    setLoading(false)
  }

  const loadInvitations = async () => {
    try {
      const response = await invitationsApi.list(inviteStatusFilter || undefined)
      setInvitations(response.data)
    } catch (error) {
      console.error('Failed to load invitations:', error)
    }
  }

  const handleSendInvite = async () => {
    if (!inviteFormData.email) {
      alert('Please enter an email address')
      return
    }

    setSendingInvite(true)
    try {
      await invitationsApi.create({
        email: inviteFormData.email,
        name: inviteFormData.name || undefined,
        role: inviteFormData.role,
        message: inviteFormData.message || undefined,
      })
      setInviteModalOpen(false)
      setInviteFormData({ email: '', name: '', role: 'labeller', message: '' })
      loadInvitations()
      alert('Invitation sent successfully!')
    } catch (error: any) {
      console.error('Failed to send invitation:', error)
      alert(error.response?.data?.detail || 'Failed to send invitation')
    } finally {
      setSendingInvite(false)
    }
  }

  const handleCancelInvite = async (invitationId: string) => {
    if (!confirm('Are you sure you want to cancel this invitation?')) return

    try {
      await invitationsApi.cancel(invitationId)
      loadInvitations()
    } catch (error: any) {
      console.error('Failed to cancel invitation:', error)
      alert(error.response?.data?.detail || 'Failed to cancel invitation')
    }
  }

  const handleResendInvite = async (invitationId: string) => {
    try {
      await invitationsApi.resend(invitationId)
      loadInvitations()
      alert('Invitation resent!')
    } catch (error: any) {
      console.error('Failed to resend invitation:', error)
      alert(error.response?.data?.detail || 'Failed to resend invitation')
    }
  }

  const getStatusTag = (status: string) => {
    const colors: Record<string, string> = {
      pending: 'yellow',
      accepted: 'green',
      expired: 'red',
    }
    return (
      <span className={`govuk-tag govuk-tag--${colors[status] || 'grey'}`}>
        {status}
      </span>
    )
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  const handleCreateUser = async () => {
    try {
      await usersApi.createUser({
        email: formData.email,
        name: formData.name,
        password: formData.password || undefined,
        role: formData.role,
        hourly_rate: formData.hourly_rate ? parseFloat(formData.hourly_rate) : undefined,
        whatsapp_number: formData.whatsapp_number || undefined,
      })

      setCreateModalOpen(false)
      resetForm()
      loadData()
    } catch (error: any) {
      console.error('Failed to create user:', error)
      alert(error.response?.data?.detail || 'Failed to create user')
    }
  }

  const handleUpdateUser = async () => {
    if (!selectedUser) return

    try {
      await usersApi.updateUser(selectedUser.id, {
        name: formData.name,
        role: formData.role,
        hourly_rate: formData.hourly_rate ? parseFloat(formData.hourly_rate) : null,
        whatsapp_number: formData.whatsapp_number || null,
      })

      setEditModalOpen(false)
      setSelectedUser(null)
      resetForm()
      loadData()
    } catch (error: any) {
      console.error('Failed to update user:', error)
      alert(error.response?.data?.detail || 'Failed to update user')
    }
  }

  const handleDeactivateUser = async (userId: string) => {
    if (!confirm('Are you sure you want to deactivate this user?')) return

    try {
      await usersApi.deleteUser(userId)
      loadData()
    } catch (error: any) {
      console.error('Failed to deactivate user:', error)
      alert(error.response?.data?.detail || 'Failed to deactivate user')
    }
  }

  const openEditModal = (user: User) => {
    setSelectedUser(user)
    setFormData({
      email: user.email,
      name: user.name,
      password: '',
      role: user.role,
      hourly_rate: user.hourly_rate?.toString() || '',
      whatsapp_number: user.whatsapp_number || '',
    })
    setEditModalOpen(true)
  }

  const resetForm = () => {
    setFormData({
      email: '',
      name: '',
      password: '',
      role: 'labeller',
      hourly_rate: '',
      whatsapp_number: '',
    })
  }

  const getRoleTag = (role: string) => {
    const colors: Record<string, string> = {
      labeller: 'blue',
      labelling_manager: 'purple',
      admin: 'red',
    }
    return (
      <span className={`govuk-tag govuk-tag--${colors[role] || 'grey'}`}>
        {role.replace('_', ' ')}
      </span>
    )
  }

  // GSV Key Management Functions (simplified)
  const loadGsvData = async () => {
    setGsvLoading(true)
    try {
      const response = await adminApi.getGsvKeys()
      setGsvKeys(response.data?.keys || [])
      setGsvSummary(response.data?.summary || null)
    } catch (error) {
      console.error('Failed to load GSV keys:', error)
      setGsvKeys([])
      setGsvSummary(null)
    }
    setGsvLoading(false)
  }

  const handleBulkAddKeys = async () => {
    if (!bulkKeysText.trim()) {
      alert('Please enter API keys')
      return
    }
    try {
      const result = await adminApi.bulkAddGsvKeys(bulkKeysText)
      alert(result.data.message || `Added ${result.data.added} keys`)
      setAddKeysModalOpen(false)
      setBulkKeysText('')
      loadGsvData()
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Failed to add keys')
    }
  }

  const handleDeleteGsvKey = async (keyId: string) => {
    if (!confirm('Delete this API key?')) return
    try {
      await adminApi.deleteGsvKey(keyId)
      loadGsvData()
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Failed to delete key')
    }
  }

  const handleToggleGsvKey = async (keyId: string, currentActive: boolean) => {
    try {
      await adminApi.updateGsvKey(keyId, { is_active: !currentActive })
      loadGsvData()
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Failed to update key')
    }
  }

  const handleResetGsvKey = async (keyPrefix: string) => {
    try {
      await adminApi.resetGsvKey(keyPrefix)
      alert('Key reset successfully')
      loadGsvData()
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Failed to reset key')
    }
  }

  const handleSyncGsvKeys = async () => {
    setSyncingKeys(true)
    try {
      await adminApi.syncGsvKeys()
      loadGsvData()
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Failed to sync keys')
    } finally {
      setSyncingKeys(false)
    }
  }


  if (loading) return <Loading />

  return (
    <>
      <h1 className="govuk-heading-xl">Admin Panel</h1>

      {/* System Stats */}
      {stats && (
        <div className="stats-grid govuk-!-margin-bottom-6">
          <div className="stat-card">
            <span className="stat-card__value">{stats.total_users}</span>
            <span className="stat-card__label">Total Users</span>
          </div>
          <div className="stat-card">
            <span className="stat-card__value">{stats.total_locations.toLocaleString()}</span>
            <span className="stat-card__label">Total Locations</span>
          </div>
          <div className="stat-card">
            <span className="stat-card__value">{stats.total_tasks}</span>
            <span className="stat-card__label">Total Tasks</span>
          </div>
          <div className="stat-card">
            <span className="stat-card__value">{stats.tasks_completed}</span>
            <span className="stat-card__label">Tasks Completed</span>
          </div>
        </div>
      )}

      {/* Tab Navigation */}
      <div className="govuk-tabs" data-module="govuk-tabs">
        <ul className="govuk-tabs__list" style={{ display: 'flex', flexWrap: 'wrap', gap: '0' }}>
          <li className="govuk-tabs__list-item" style={{ marginRight: '20px' }}>
            <a 
              className={`govuk-tabs__tab ${activeTab === 'users' ? 'govuk-tabs__tab--selected' : ''}`}
              href="#users"
              onClick={(e) => { e.preventDefault(); setActiveTab('users'); }}
            >
              User Management
            </a>
          </li>
          <li className="govuk-tabs__list-item" style={{ marginRight: '20px' }}>
            <a 
              className={`govuk-tabs__tab ${activeTab === 'invitations' ? 'govuk-tabs__tab--selected' : ''}`}
              href="#invitations"
              onClick={(e) => { e.preventDefault(); setActiveTab('invitations'); }}
            >
              Invitations
            </a>
          </li>
          <li className="govuk-tabs__list-item" style={{ marginRight: '20px' }}>
            <a 
              className={`govuk-tabs__tab ${activeTab === 'gsv-keys' ? 'govuk-tabs__tab--selected' : ''}`}
              href="#gsv-keys"
              onClick={(e) => { e.preventDefault(); setActiveTab('gsv-keys'); }}
              style={{ whiteSpace: 'nowrap' }}
            >
              🔑 GSV API Keys
            </a>
          </li>
        </ul>

        {/* User Management Tab */}
        {activeTab === 'users' && (
          <section className="govuk-tabs__panel" id="users">
            <h2 className="govuk-heading-l">User Management</h2>

      <div className="govuk-grid-row govuk-!-margin-bottom-4">
        <div className="govuk-grid-column-one-third">
          <div className="govuk-form-group">
            <label className="govuk-label" htmlFor="roleFilter">
              Filter by role
            </label>
            <select
              className="govuk-select"
              id="roleFilter"
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
            >
              <option value="">All roles</option>
              <option value="labeller">Labeller</option>
              <option value="labelling_manager">Labelling Manager</option>
              <option value="admin">Admin</option>
            </select>
          </div>
        </div>
        <div className="govuk-grid-column-one-third">
          <div className="govuk-form-group">
            <label className="govuk-label" htmlFor="search">
              Search
            </label>
            <input
              className="govuk-input"
              id="search"
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Name or email..."
            />
          </div>
        </div>
        <div className="govuk-grid-column-one-third" style={{ display: 'flex', alignItems: 'flex-end' }}>
          <button className="govuk-button" onClick={() => setCreateModalOpen(true)}>
            Create User
          </button>
        </div>
      </div>

      <table className="govuk-table">
        <thead className="govuk-table__head">
          <tr className="govuk-table__row">
            <th className="govuk-table__header">Name</th>
            <th className="govuk-table__header">Email</th>
            <th className="govuk-table__header">Role</th>
            <th className="govuk-table__header">Hourly Rate</th>
            <th className="govuk-table__header">Status</th>
            <th className="govuk-table__header">Actions</th>
          </tr>
        </thead>
        <tbody className="govuk-table__body">
          {users.map((user) => (
            <tr key={user.id} className="govuk-table__row">
              <td className="govuk-table__cell">{user.name}</td>
              <td className="govuk-table__cell">{user.email}</td>
              <td className="govuk-table__cell">{getRoleTag(user.role)}</td>
              <td className="govuk-table__cell">
                {user.hourly_rate ? `£${user.hourly_rate.toFixed(2)}` : '-'}
              </td>
              <td className="govuk-table__cell">
                {user.is_active ? (
                  <span className="govuk-tag govuk-tag--green">Active</span>
                ) : (
                  <span className="govuk-tag govuk-tag--grey">Inactive</span>
                )}
              </td>
              <td className="govuk-table__cell">
                <button
                  className="govuk-link govuk-!-margin-right-2"
                  style={{ background: 'none', border: 'none', cursor: 'pointer' }}
                  onClick={() => openEditModal(user)}
                >
                  Edit
                </button>
                {user.is_active && (
                  <button
                    className="govuk-link"
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#d4351c' }}
                    onClick={() => handleDeactivateUser(user.id)}
                  >
                    Deactivate
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Pagination */}
            <nav className="govuk-pagination">
              <p className="govuk-body">
                Showing {(page - 1) * 20 + 1} to {Math.min(page * 20, total)} of {total} users
              </p>
              <div>
                <button
                  className="govuk-button govuk-button--secondary govuk-!-margin-right-2"
                  disabled={page === 1}
                  onClick={() => setPage(page - 1)}
                >
                  Previous
                </button>
                <button
                  className="govuk-button govuk-button--secondary"
                  disabled={page * 20 >= total}
                  onClick={() => setPage(page + 1)}
                >
                  Next
                </button>
              </div>
            </nav>
          </section>
        )}

        {/* Invitations Tab */}
        {activeTab === 'invitations' && (
          <section className="govuk-tabs__panel" id="invitations">
            <h2 className="govuk-heading-l">Invitations</h2>
            
            <div className="govuk-grid-row govuk-!-margin-bottom-4">
              <div className="govuk-grid-column-one-half">
                <div className="govuk-form-group">
                  <label className="govuk-label" htmlFor="inviteStatusFilter">
                    Filter by status
                  </label>
                  <select
                    className="govuk-select"
                    id="inviteStatusFilter"
                    value={inviteStatusFilter}
                    onChange={(e) => setInviteStatusFilter(e.target.value)}
                  >
                    <option value="">All statuses</option>
                    <option value="pending">Pending</option>
                    <option value="accepted">Accepted</option>
                    <option value="expired">Expired</option>
                  </select>
                </div>
              </div>
              <div className="govuk-grid-column-one-half" style={{ display: 'flex', alignItems: 'flex-end' }}>
                <button className="govuk-button" onClick={() => setInviteModalOpen(true)}>
                  Send Invitation
                </button>
              </div>
            </div>

            {invitations.length === 0 ? (
              <p className="govuk-body" style={{ color: '#6b7280', textAlign: 'center', padding: '40px' }}>
                No invitations found. Click "Send Invitation" to invite new users.
              </p>
            ) : (
              <table className="govuk-table">
                <thead className="govuk-table__head">
                  <tr className="govuk-table__row">
                    <th className="govuk-table__header">Email</th>
                    <th className="govuk-table__header">Name</th>
                    <th className="govuk-table__header">Role</th>
                    <th className="govuk-table__header">Status</th>
                    <th className="govuk-table__header">Invited By</th>
                    <th className="govuk-table__header">Sent</th>
                    <th className="govuk-table__header">Expires</th>
                    <th className="govuk-table__header">Actions</th>
                  </tr>
                </thead>
                <tbody className="govuk-table__body">
                  {invitations.map((invite) => (
                    <tr key={invite.id} className="govuk-table__row">
                      <td className="govuk-table__cell">{invite.email}</td>
                      <td className="govuk-table__cell">{invite.name || '-'}</td>
                      <td className="govuk-table__cell">{getRoleTag(invite.role)}</td>
                      <td className="govuk-table__cell">{getStatusTag(invite.status)}</td>
                      <td className="govuk-table__cell">{invite.invited_by_name}</td>
                      <td className="govuk-table__cell">{formatDate(invite.created_at)}</td>
                      <td className="govuk-table__cell">{formatDate(invite.expires_at)}</td>
                      <td className="govuk-table__cell">
                        {invite.status === 'pending' && (
                          <>
                            <button
                              className="govuk-link govuk-!-margin-right-2"
                              style={{ background: 'none', border: 'none', cursor: 'pointer' }}
                              onClick={() => handleResendInvite(invite.id)}
                            >
                              Resend
                            </button>
                            <button
                              className="govuk-link"
                              style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#d4351c' }}
                              onClick={() => handleCancelInvite(invite.id)}
                            >
                              Cancel
                            </button>
                          </>
                        )}
                        {invite.status === 'accepted' && (
                          <span style={{ color: '#6b7280' }}>
                            Accepted {invite.accepted_at ? formatDate(invite.accepted_at) : ''}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        )}

        {/* GSV API Keys Tab - Simplified */}
        {activeTab === 'gsv-keys' && (
          <section className="govuk-tabs__panel" id="gsv-keys">
            <h2 className="govuk-heading-l">GSV API Key Management</h2>
            
            {/* Summary Stats */}
            {gsvSummary && (
              <div className="stats-grid govuk-!-margin-bottom-6" style={{ gridTemplateColumns: 'repeat(5, 1fr)' }}>
                <div className="stat-card">
                  <span className="stat-card__value">{gsvSummary.total_keys}</span>
                  <span className="stat-card__label">Total Keys</span>
                </div>
                <div className="stat-card">
                  <span className="stat-card__value" style={{ color: '#10b981' }}>{gsvSummary.active_keys}</span>
                  <span className="stat-card__label">Active</span>
                </div>
                <div className="stat-card">
                  <span className="stat-card__value" style={{ color: '#ef4444' }}>{gsvSummary.exhausted_keys}</span>
                  <span className="stat-card__label">Exhausted</span>
                </div>
                <div className="stat-card">
                  <span className="stat-card__value" style={{ color: '#f59e0b' }}>{gsvSummary.total_requests_today.toLocaleString()}</span>
                  <span className="stat-card__label">Requests Today</span>
                </div>
                <div className="stat-card">
                  <span className="stat-card__value" style={{ color: '#7c3aed' }}>{gsvSummary.daily_capacity.toLocaleString()}</span>
                  <span className="stat-card__label">Daily Capacity</span>
                </div>
              </div>
            )}

            {/* Instructions */}
            <div style={{ 
              background: 'rgba(124, 58, 237, 0.1)', 
              border: '1px solid rgba(124, 58, 237, 0.3)',
              borderRadius: '8px',
              padding: '16px',
              marginBottom: '24px'
            }}>
              <h3 style={{ color: '#7c3aed', marginBottom: '12px', fontSize: '1rem' }}>📋 How to Add API Keys</h3>
              <ol style={{ marginLeft: '20px', color: '#666', marginBottom: 0 }}>
                <li>Create projects in <a href="https://console.cloud.google.com" target="_blank" rel="noopener noreferrer">Google Cloud Console</a></li>
                <li>Enable the Street View Static API for each project</li>
                <li>Generate API keys (restrict to Street View Static API)</li>
                <li>Click "Add Keys" below and paste all keys (comma or newline separated)</li>
              </ol>
            </div>

            {/* Action Buttons */}
            <div className="govuk-button-group govuk-!-margin-bottom-4">
              <button 
                className="govuk-button"
                onClick={() => setAddKeysModalOpen(true)}
              >
                + Add Keys
              </button>
              <button 
                className="govuk-button govuk-button--secondary" 
                onClick={handleSyncGsvKeys}
                disabled={syncingKeys}
              >
                {syncingKeys ? 'Syncing...' : '🔄 Sync Keys'}
              </button>
            </div>

            {/* Keys List */}
            {gsvLoading ? (
              <Loading />
            ) : gsvKeys.length === 0 ? (
              <p className="govuk-body" style={{ color: '#6b7280', textAlign: 'center', padding: '40px' }}>
                No API keys added yet. Click "Add Keys" to get started.
              </p>
            ) : (
              <table className="govuk-table">
                <thead className="govuk-table__head">
                  <tr className="govuk-table__row">
                    <th className="govuk-table__header">Key</th>
                    <th className="govuk-table__header">Label</th>
                    <th className="govuk-table__header">Status</th>
                    <th className="govuk-table__header">Requests Today</th>
                    <th className="govuk-table__header">Total Requests</th>
                    <th className="govuk-table__header">Last Used</th>
                    <th className="govuk-table__header">Actions</th>
                  </tr>
                </thead>
                <tbody className="govuk-table__body">
                  {gsvKeys.map((key) => (
                    <tr key={key.id} className="govuk-table__row" style={{ 
                      opacity: key.is_active ? 1 : 0.5,
                      background: key.quota_exhausted ? 'rgba(239, 68, 68, 0.1)' : 'transparent'
                    }}>
                      <td className="govuk-table__cell" style={{ fontFamily: 'monospace', fontSize: '12px' }}>
                        {key.api_key}
                      </td>
                      <td className="govuk-table__cell">{key.label || '-'}</td>
                      <td className="govuk-table__cell">
                        <span style={{ 
                          padding: '4px 8px', 
                          borderRadius: '12px',
                          fontSize: '0.75rem',
                          background: key.status === 'active' ? 'rgba(16, 185, 129, 0.2)' 
                            : key.status === 'quota_exhausted' ? 'rgba(239, 68, 68, 0.2)'
                            : key.status === 'errors' ? 'rgba(245, 158, 11, 0.2)'
                            : 'rgba(107, 114, 128, 0.2)',
                          color: key.status === 'active' ? '#10b981' 
                            : key.status === 'quota_exhausted' ? '#ef4444'
                            : key.status === 'errors' ? '#f59e0b'
                            : '#6b7280'
                        }}>
                          {key.status === 'active' ? '✓ Active' 
                            : key.status === 'quota_exhausted' ? '✗ Exhausted'
                            : key.status === 'errors' ? '⚠ Errors'
                            : '○ Disabled'}
                        </span>
                      </td>
                      <td className="govuk-table__cell">{key.requests_today.toLocaleString()}</td>
                      <td className="govuk-table__cell">{key.requests_total.toLocaleString()}</td>
                      <td className="govuk-table__cell" style={{ fontSize: '0.85rem' }}>
                        {key.last_used_at 
                          ? new Date(key.last_used_at).toLocaleString() 
                          : 'Never'}
                      </td>
                      <td className="govuk-table__cell">
                        <div style={{ display: 'flex', gap: '4px' }}>
                          <button
                            onClick={() => handleToggleGsvKey(key.id, key.is_active)}
                            style={{ 
                              padding: '4px 8px', 
                              fontSize: '12px',
                              background: key.is_active ? '#6b7280' : '#10b981',
                              color: '#fff',
                              border: 'none',
                              borderRadius: '4px',
                              cursor: 'pointer'
                            }}
                          >
                            {key.is_active ? 'Disable' : 'Enable'}
                          </button>
                          {(key.quota_exhausted || key.consecutive_errors > 0) && (
                            <button
                              onClick={() => handleResetGsvKey(key.api_key_prefix)}
                              style={{ 
                                padding: '4px 8px', 
                                fontSize: '12px',
                                background: '#f59e0b',
                                color: '#fff',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: 'pointer'
                              }}
                            >
                              Reset
                            </button>
                          )}
                          <button
                            onClick={() => handleDeleteGsvKey(key.id)}
                            style={{ 
                              padding: '4px 8px', 
                              fontSize: '12px',
                              background: '#ef4444',
                              color: '#fff',
                              border: 'none',
                              borderRadius: '4px',
                              cursor: 'pointer'
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        )}
      </div>

      {/* Create User Modal */}
      <Modal
        isOpen={createModalOpen}
        onClose={() => {
          setCreateModalOpen(false)
          resetForm()
        }}
        title="Create User"
      >
        <div className="govuk-form-group">
          <label className="govuk-label" htmlFor="email">Email</label>
          <input
            className="govuk-input"
            id="email"
            type="email"
            value={formData.email}
            onChange={(e) => setFormData({ ...formData, email: e.target.value })}
            required
          />
        </div>
        <div className="govuk-form-group">
          <label className="govuk-label" htmlFor="name">Name</label>
          <input
            className="govuk-input"
            id="name"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            required
          />
        </div>
        <div className="govuk-form-group">
          <label className="govuk-label" htmlFor="password">Password (optional if using SSO)</label>
          <input
            className="govuk-input"
            id="password"
            type="password"
            value={formData.password}
            onChange={(e) => setFormData({ ...formData, password: e.target.value })}
          />
        </div>
        <div className="govuk-form-group">
          <label className="govuk-label" htmlFor="role">Role</label>
          <select
            className="govuk-select"
            id="role"
            value={formData.role}
            onChange={(e) => setFormData({ ...formData, role: e.target.value })}
          >
            <option value="labeller">Labeller</option>
            <option value="labelling_manager">Labelling Manager</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <div className="govuk-form-group">
          <label className="govuk-label" htmlFor="hourly_rate">Hourly Rate (£)</label>
          <input
            className="govuk-input govuk-input--width-10"
            id="hourly_rate"
            type="number"
            step="0.01"
            value={formData.hourly_rate}
            onChange={(e) => setFormData({ ...formData, hourly_rate: e.target.value })}
          />
        </div>
        <div className="govuk-form-group">
          <label className="govuk-label" htmlFor="whatsapp">WhatsApp Number</label>
          <input
            className="govuk-input"
            id="whatsapp"
            value={formData.whatsapp_number}
            onChange={(e) => setFormData({ ...formData, whatsapp_number: e.target.value })}
            placeholder="+44..."
          />
        </div>
        <div className="govuk-button-group">
          <button className="govuk-button" onClick={handleCreateUser}>Create User</button>
          <button
            className="govuk-button govuk-button--secondary"
            onClick={() => {
              setCreateModalOpen(false)
              resetForm()
            }}
          >
            Cancel
          </button>
        </div>
      </Modal>

      {/* Edit User Modal */}
      <Modal
        isOpen={editModalOpen}
        onClose={() => {
          setEditModalOpen(false)
          setSelectedUser(null)
          resetForm()
        }}
        title="Edit User"
      >
        <div className="govuk-form-group">
          <label className="govuk-label">Email</label>
          <p className="govuk-body">{formData.email}</p>
        </div>
        <div className="govuk-form-group">
          <label className="govuk-label" htmlFor="editName">Name</label>
          <input
            className="govuk-input"
            id="editName"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          />
        </div>
        <div className="govuk-form-group">
          <label className="govuk-label" htmlFor="editRole">Role</label>
          <select
            className="govuk-select"
            id="editRole"
            value={formData.role}
            onChange={(e) => setFormData({ ...formData, role: e.target.value })}
          >
            <option value="labeller">Labeller</option>
            <option value="labelling_manager">Labelling Manager</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <div className="govuk-form-group">
          <label className="govuk-label" htmlFor="editHourlyRate">Hourly Rate (£)</label>
          <input
            className="govuk-input govuk-input--width-10"
            id="editHourlyRate"
            type="number"
            step="0.01"
            value={formData.hourly_rate}
            onChange={(e) => setFormData({ ...formData, hourly_rate: e.target.value })}
          />
        </div>
        <div className="govuk-form-group">
          <label className="govuk-label" htmlFor="editWhatsapp">WhatsApp Number</label>
          <input
            className="govuk-input"
            id="editWhatsapp"
            value={formData.whatsapp_number}
            onChange={(e) => setFormData({ ...formData, whatsapp_number: e.target.value })}
          />
        </div>
        <div className="govuk-button-group">
          <button className="govuk-button" onClick={handleUpdateUser}>Save Changes</button>
          <button
            className="govuk-button govuk-button--secondary"
            onClick={() => {
              setEditModalOpen(false)
              setSelectedUser(null)
              resetForm()
            }}
          >
            Cancel
          </button>
        </div>
      </Modal>

      {/* Invite User Modal */}
      <Modal
        isOpen={inviteModalOpen}
        onClose={() => {
          setInviteModalOpen(false)
          setInviteFormData({ email: '', name: '', role: 'labeller', message: '' })
        }}
        title="Send Invitation"
      >
        <p className="govuk-body govuk-!-margin-bottom-4">
          Send an invitation email to a new user. They'll receive a link to create their account.
        </p>
        <div className="govuk-form-group">
          <label className="govuk-label" htmlFor="inviteEmail">Email *</label>
          <input
            className="govuk-input"
            id="inviteEmail"
            type="email"
            value={inviteFormData.email}
            onChange={(e) => setInviteFormData({ ...inviteFormData, email: e.target.value })}
            required
          />
        </div>
        <div className="govuk-form-group">
          <label className="govuk-label" htmlFor="inviteName">Name (optional)</label>
          <p className="govuk-hint">They can change this when accepting the invitation</p>
          <input
            className="govuk-input"
            id="inviteName"
            value={inviteFormData.name}
            onChange={(e) => setInviteFormData({ ...inviteFormData, name: e.target.value })}
          />
        </div>
        <div className="govuk-form-group">
          <label className="govuk-label" htmlFor="inviteRole">Role</label>
          <select
            className="govuk-select"
            id="inviteRole"
            value={inviteFormData.role}
            onChange={(e) => setInviteFormData({ ...inviteFormData, role: e.target.value })}
          >
            <option value="labeller">Labeller</option>
            <option value="labelling_manager">Labelling Manager</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <div className="govuk-form-group">
          <label className="govuk-label" htmlFor="inviteMessage">Personal message (optional)</label>
          <p className="govuk-hint">Add a personal note to the invitation email</p>
          <textarea
            className="govuk-textarea"
            id="inviteMessage"
            rows={3}
            value={inviteFormData.message}
            onChange={(e) => setInviteFormData({ ...inviteFormData, message: e.target.value })}
            placeholder="Welcome to the team! Looking forward to working with you."
          />
        </div>
        <div className="govuk-button-group">
          <button 
            className="govuk-button" 
            onClick={handleSendInvite}
            disabled={sendingInvite || !inviteFormData.email}
          >
            {sendingInvite ? 'Sending...' : 'Send Invitation'}
          </button>
          <button
            className="govuk-button govuk-button--secondary"
            onClick={() => {
              setInviteModalOpen(false)
              setInviteFormData({ email: '', name: '', role: 'labeller', message: '' })
            }}
          >
            Cancel
          </button>
        </div>
      </Modal>

      {/* Add GSV Keys Modal - Simplified */}
      <Modal
        isOpen={addKeysModalOpen}
        onClose={() => {
          setAddKeysModalOpen(false)
          setBulkKeysText('')
        }}
        title="Add API Keys"
      >
        <p className="govuk-body govuk-!-margin-bottom-4">
          Paste your Google Street View API keys below. You can use comma-separated or one key per line.
          Keys should start with "AIza".
        </p>
        <div className="govuk-form-group">
          <label className="govuk-label" htmlFor="bulkKeys">API Keys *</label>
          <textarea
            className="govuk-textarea"
            id="bulkKeys"
            rows={10}
            value={bulkKeysText}
            onChange={(e) => setBulkKeysText(e.target.value)}
            placeholder="AIzaSyB1234567890abcdefghijklmnopqrst
AIzaSyC1234567890abcdefghijklmnopqrst
AIzaSyD1234567890abcdefghijklmnopqrst"
            style={{ fontFamily: 'monospace', fontSize: '12px' }}
          />
          <p className="govuk-hint">
            {bulkKeysText.split(/[,\n]/).filter(k => k.trim() && k.trim().startsWith('AIza')).length} valid keys detected
          </p>
        </div>
        <div className="govuk-button-group">
          <button 
            className="govuk-button" 
            onClick={handleBulkAddKeys}
            disabled={!bulkKeysText.trim()}
          >
            Add Keys
          </button>
          <button
            className="govuk-button govuk-button--secondary"
            onClick={() => {
              setAddKeysModalOpen(false)
              setBulkKeysText('')
            }}
          >
            Cancel
          </button>
        </div>
      </Modal>
    </>
  )
}

