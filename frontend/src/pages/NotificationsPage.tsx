import { useEffect, useState } from 'react'
import { notificationsApi, usersApi } from '../services/api'
import { useAuthStore } from '../store/authStore'
import Loading from '../components/common/Loading'

interface NotificationSettings {
  id: string
  daily_summary_enabled: boolean
  daily_summary_time: string
  daily_summary_admin_id: string | null
  daily_summary_admin_name: string | null
  task_completion_enabled: boolean
  daily_reminders_enabled: boolean
  daily_reminder_time: string
  updated_at: string
}

interface UserPreferences {
  opt_out_daily_reminders: boolean
  opt_out_task_assignments: boolean
  opt_out_all_whatsapp: boolean
  opt_out_date: string | null
}

interface NotificationLog {
  id: string
  notification_type: string
  recipient_number: string
  message_preview: string
  status: string
  error_message: string | null
  created_at: string
  sent_at: string | null
}

interface AdminUser {
  id: string
  name: string
  email: string
  whatsapp_number: string | null
}

export default function NotificationsPage() {
  const { user } = useAuthStore()
  const isAdmin = user?.role === 'admin'
  const isManager = user?.role === 'labelling_manager' || user?.role === 'admin'

  const [loading, setLoading] = useState(true)
  const [settings, setSettings] = useState<NotificationSettings | null>(null)
  const [preferences, setPreferences] = useState<UserPreferences | null>(null)
  const [logs, setLogs] = useState<NotificationLog[]>([])
  const [admins, setAdmins] = useState<AdminUser[]>([])
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      const [prefsRes] = await Promise.all([
        notificationsApi.getMyPreferences(),
      ])
      setPreferences(prefsRes.data)

      // Load admin-specific data
      if (isManager) {
        const [settingsRes, logsRes, usersRes] = await Promise.all([
          notificationsApi.getSettings(),
          notificationsApi.getLogs(50),
          usersApi.getUsers({ role: 'admin', page_size: 100 }),
        ])
        setSettings(settingsRes.data)
        setLogs(logsRes.data)
        // Filter users with WhatsApp numbers
        setAdmins(usersRes.data.users.filter((u: AdminUser) => u.whatsapp_number))
      }
    } catch (error) {
      console.error('Failed to load notification data:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleUpdateSettings = async (updates: Partial<NotificationSettings>) => {
    if (!settings) return
    setSaving(true)
    try {
      const response = await notificationsApi.updateSettings(updates)
      setSettings(response.data)
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Failed to update settings')
    } finally {
      setSaving(false)
    }
  }

  const handleUpdatePreferences = async (updates: Partial<UserPreferences>) => {
    setSaving(true)
    try {
      const response = await notificationsApi.updateMyPreferences(updates)
      setPreferences(response.data)
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Failed to update preferences')
    } finally {
      setSaving(false)
    }
  }

  const handleTestDailySummary = async () => {
    setTesting(true)
    try {
      await notificationsApi.testDailySummary()
      alert('Daily summary notification sent!')
      loadData()
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Failed to send test notification')
    } finally {
      setTesting(false)
    }
  }

  const handleTestReminders = async () => {
    setTesting(true)
    try {
      await notificationsApi.testLabellerReminders()
      alert('Labeller reminders sent!')
      loadData()
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Failed to send test notifications')
    } finally {
      setTesting(false)
    }
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const getStatusTag = (status: string) => {
    const colors: Record<string, string> = {
      sent: 'green',
      failed: 'red',
      pending: 'yellow'
    }
    return (
      <span className={`govuk-tag govuk-tag--${colors[status] || 'grey'}`}>
        {status}
      </span>
    )
  }

  const getTypeLabel = (type: string) => {
    const labels: Record<string, string> = {
      daily_summary: 'Daily Summary',
      task_completion: 'Task Completed',
      daily_reminder: 'Daily Reminder'
    }
    return labels[type] || type
  }

  if (loading) return <Loading />

  return (
    <>
      <h1 className="govuk-heading-xl">Notification Settings</h1>

      {/* User Preferences */}
      <section className="govuk-!-margin-bottom-8">
        <h2 className="govuk-heading-l">Your Preferences</h2>
        
        {!user?.whatsapp_number ? (
          <div className="govuk-inset-text">
            <p className="govuk-body">
              You don't have a WhatsApp number configured. Update your profile to receive notifications.
            </p>
          </div>
        ) : (
          <>
            <p className="govuk-body">
              WhatsApp notifications will be sent to: <strong>{user.whatsapp_number}</strong>
            </p>

            {preferences && (
              <div className="govuk-form-group">
                <fieldset className="govuk-fieldset">
                  <legend className="govuk-fieldset__legend govuk-fieldset__legend--m">
                    <h3 className="govuk-fieldset__heading">WhatsApp Notification Preferences</h3>
                  </legend>
                  
                  <div className="govuk-checkboxes govuk-checkboxes--small">
                    <div className="govuk-checkboxes__item">
                      <input
                        className="govuk-checkboxes__input"
                        id="opt-out-reminders"
                        type="checkbox"
                        checked={preferences.opt_out_daily_reminders}
                        onChange={(e) => handleUpdatePreferences({ opt_out_daily_reminders: e.target.checked })}
                        disabled={saving}
                      />
                      <label className="govuk-label govuk-checkboxes__label" htmlFor="opt-out-reminders">
                        Opt out of daily task reminders
                      </label>
                    </div>
                    
                    <div className="govuk-checkboxes__item">
                      <input
                        className="govuk-checkboxes__input"
                        id="opt-out-assignments"
                        type="checkbox"
                        checked={preferences.opt_out_task_assignments}
                        onChange={(e) => handleUpdatePreferences({ opt_out_task_assignments: e.target.checked })}
                        disabled={saving}
                      />
                      <label className="govuk-label govuk-checkboxes__label" htmlFor="opt-out-assignments">
                        Opt out of task assignment notifications
                      </label>
                    </div>
                    
                    <div className="govuk-checkboxes__item">
                      <input
                        className="govuk-checkboxes__input"
                        id="opt-out-all"
                        type="checkbox"
                        checked={preferences.opt_out_all_whatsapp}
                        onChange={(e) => handleUpdatePreferences({ opt_out_all_whatsapp: e.target.checked })}
                        disabled={saving}
                      />
                      <label className="govuk-label govuk-checkboxes__label" htmlFor="opt-out-all">
                        Opt out of all WhatsApp notifications
                      </label>
                    </div>
                  </div>

                  {preferences.opt_out_date && (
                    <p className="govuk-body-s govuk-!-margin-top-2" style={{ color: '#6b7280' }}>
                      Opted out on: {formatDate(preferences.opt_out_date)}
                    </p>
                  )}
                </fieldset>
              </div>
            )}
          </>
        )}
      </section>

      {/* Admin Settings */}
      {isAdmin && settings && (
        <section className="govuk-!-margin-bottom-8">
          <h2 className="govuk-heading-l">Admin Settings</h2>
          
          <div className="govuk-grid-row">
            <div className="govuk-grid-column-two-thirds">
              {/* Daily Performance Summary */}
              <div style={{ 
                background: '#f9fafb', 
                borderRadius: '8px', 
                padding: '24px',
                marginBottom: '24px'
              }}>
                <h3 className="govuk-heading-m govuk-!-margin-bottom-4">
                  📊 Daily Performance Summary
                </h3>
                
                <div className="govuk-checkboxes govuk-checkboxes--small govuk-!-margin-bottom-4">
                  <div className="govuk-checkboxes__item">
                    <input
                      className="govuk-checkboxes__input"
                      id="daily-summary-enabled"
                      type="checkbox"
                      checked={settings.daily_summary_enabled}
                      onChange={(e) => handleUpdateSettings({ daily_summary_enabled: e.target.checked })}
                      disabled={saving}
                    />
                    <label className="govuk-label govuk-checkboxes__label" htmlFor="daily-summary-enabled">
                      Enable daily performance summary
                    </label>
                  </div>
                </div>

                {settings.daily_summary_enabled && (
                  <div className="govuk-grid-row">
                    <div className="govuk-grid-column-one-half">
                      <div className="govuk-form-group">
                        <label className="govuk-label" htmlFor="daily-summary-time">
                          Send time
                        </label>
                        <input
                          className="govuk-input govuk-input--width-5"
                          id="daily-summary-time"
                          type="time"
                          value={settings.daily_summary_time}
                          onChange={(e) => handleUpdateSettings({ daily_summary_time: e.target.value })}
                          disabled={saving}
                        />
                      </div>
                    </div>
                    <div className="govuk-grid-column-one-half">
                      <div className="govuk-form-group">
                        <label className="govuk-label" htmlFor="daily-summary-admin">
                          Send to
                        </label>
                        <select
                          className="govuk-select"
                          id="daily-summary-admin"
                          value={settings.daily_summary_admin_id || ''}
                          onChange={(e) => handleUpdateSettings({ daily_summary_admin_id: e.target.value || undefined })}
                          disabled={saving}
                        >
                          <option value="">Select admin...</option>
                          {admins.map((admin) => (
                            <option key={admin.id} value={admin.id}>
                              {admin.name} ({admin.whatsapp_number})
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  </div>
                )}

                <button
                  className="govuk-button govuk-button--secondary"
                  onClick={handleTestDailySummary}
                  disabled={testing || !settings.daily_summary_enabled || !settings.daily_summary_admin_id}
                >
                  {testing ? 'Sending...' : 'Send Test Summary'}
                </button>
              </div>

              {/* Task Completion Notifications */}
              <div style={{ 
                background: '#f9fafb', 
                borderRadius: '8px', 
                padding: '24px',
                marginBottom: '24px'
              }}>
                <h3 className="govuk-heading-m govuk-!-margin-bottom-4">
                  🎉 Task Completion Notifications
                </h3>
                
                <div className="govuk-checkboxes govuk-checkboxes--small">
                  <div className="govuk-checkboxes__item">
                    <input
                      className="govuk-checkboxes__input"
                      id="task-completion-enabled"
                      type="checkbox"
                      checked={settings.task_completion_enabled}
                      onChange={(e) => handleUpdateSettings({ task_completion_enabled: e.target.checked })}
                      disabled={saving}
                    />
                    <label className="govuk-label govuk-checkboxes__label" htmlFor="task-completion-enabled">
                      Notify managers when labellers complete tasks
                    </label>
                  </div>
                </div>
                <p className="govuk-hint govuk-!-margin-top-2">
                  All managers with WhatsApp numbers will receive notifications.
                </p>
              </div>

              {/* Daily Labeller Reminders */}
              <div style={{ 
                background: '#f9fafb', 
                borderRadius: '8px', 
                padding: '24px',
                marginBottom: '24px'
              }}>
                <h3 className="govuk-heading-m govuk-!-margin-bottom-4">
                  ⏰ Daily Labeller Reminders
                </h3>
                
                <div className="govuk-checkboxes govuk-checkboxes--small govuk-!-margin-bottom-4">
                  <div className="govuk-checkboxes__item">
                    <input
                      className="govuk-checkboxes__input"
                      id="daily-reminders-enabled"
                      type="checkbox"
                      checked={settings.daily_reminders_enabled}
                      onChange={(e) => handleUpdateSettings({ daily_reminders_enabled: e.target.checked })}
                      disabled={saving}
                    />
                    <label className="govuk-label govuk-checkboxes__label" htmlFor="daily-reminders-enabled">
                      Send daily reminders to labellers about pending tasks
                    </label>
                  </div>
                </div>

                {settings.daily_reminders_enabled && (
                  <div className="govuk-form-group">
                    <label className="govuk-label" htmlFor="daily-reminder-time">
                      Send time
                    </label>
                    <input
                      className="govuk-input govuk-input--width-5"
                      id="daily-reminder-time"
                      type="time"
                      value={settings.daily_reminder_time}
                      onChange={(e) => handleUpdateSettings({ daily_reminder_time: e.target.value })}
                      disabled={saving}
                    />
                  </div>
                )}

                <button
                  className="govuk-button govuk-button--secondary"
                  onClick={handleTestReminders}
                  disabled={testing || !settings.daily_reminders_enabled}
                >
                  {testing ? 'Sending...' : 'Send Test Reminders'}
                </button>
                <p className="govuk-hint govuk-!-margin-top-2">
                  Labellers can opt out via WhatsApp by replying STOP.
                </p>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Notification Logs */}
      {isManager && (
        <section>
          <h2 className="govuk-heading-l">Recent Notifications</h2>
          
          {logs.length === 0 ? (
            <p className="govuk-body" style={{ color: '#6b7280' }}>
              No notifications have been sent yet.
            </p>
          ) : (
            <table className="govuk-table">
              <thead className="govuk-table__head">
                <tr className="govuk-table__row">
                  <th className="govuk-table__header">Type</th>
                  <th className="govuk-table__header">Recipient</th>
                  <th className="govuk-table__header">Preview</th>
                  <th className="govuk-table__header">Status</th>
                  <th className="govuk-table__header">Sent</th>
                </tr>
              </thead>
              <tbody className="govuk-table__body">
                {logs.map((log) => (
                  <tr key={log.id} className="govuk-table__row">
                    <td className="govuk-table__cell">{getTypeLabel(log.notification_type)}</td>
                    <td className="govuk-table__cell">{log.recipient_number}</td>
                    <td className="govuk-table__cell" style={{ maxWidth: '300px' }}>
                      <span style={{ 
                        display: 'block',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap'
                      }}>
                        {log.message_preview}
                      </span>
                    </td>
                    <td className="govuk-table__cell">{getStatusTag(log.status)}</td>
                    <td className="govuk-table__cell">
                      {log.sent_at ? formatDate(log.sent_at) : formatDate(log.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </>
  )
}

