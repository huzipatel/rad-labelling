import { useEffect, useState } from 'react'
import { usersApi, adminApi } from '../services/api'
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

  const loadData = async () => {
    try {
      const [usersRes, statsRes] = await Promise.all([
        usersApi.getUsers({ page, page_size: 20, role: roleFilter || undefined, search: search || undefined }),
        adminApi.getSystemStats(),
      ])

      setUsers(usersRes.data.users)
      setTotal(usersRes.data.total)
      setStats(statsRes.data)
    } catch (error) {
      console.error('Failed to load data:', error)
    } finally {
      setLoading(false)
    }
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

      {/* User Management */}
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
    </>
  )
}

