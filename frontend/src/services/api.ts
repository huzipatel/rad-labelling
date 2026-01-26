import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor to add auth token and handle FormData
api.interceptors.request.use(
  (config) => {
    // Get token from localStorage (zustand persist)
    const authStorage = localStorage.getItem('auth-storage')
    if (authStorage) {
      try {
        const { state } = JSON.parse(authStorage)
        if (state?.token) {
          config.headers.Authorization = `Bearer ${state.token}`
        }
      } catch (e) {
        console.error('Error parsing auth storage:', e)
      }
    }
    
    // Remove Content-Type for FormData to let browser set it with boundary
    if (config.data instanceof FormData) {
      delete config.headers['Content-Type']
    }
    
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Clear auth state on 401
      localStorage.removeItem('auth-storage')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default api

// Auth API
export const authApi = {
  login: (email: string, password: string) =>
    api.post('/auth/login', { email, password }),
  register: (email: string, password: string, name: string) =>
    api.post('/auth/register', { email, password, name }),
  googleLogin: (token: string) =>
    api.post('/auth/google/token', { token }),
  getMe: () => api.get('/auth/me'),
}

// Tasks API
export const tasksApi = {
  getMyTasks: (status?: string) =>
    api.get('/tasks/my-tasks', { params: { status } }),
  getAllTasks: (params: any) =>
    api.get('/tasks', { params }),
  getTask: (taskId: string) =>
    api.get(`/tasks/${taskId}`),
  generateTasks: (locationTypeId: string) =>
    api.post(`/tasks/generate?location_type_id=${locationTypeId}`),
  assignTask: (taskId: string, labellerId: string) =>
    api.post(`/tasks/${taskId}/assign`, { labeller_id: labellerId }),
  bulkAssign: (taskIds: string[], labellerId: string) =>
    api.post('/tasks/bulk-assign', { task_ids: taskIds, labeller_id: labellerId }),
  startTask: (taskId: string) =>
    api.post(`/tasks/${taskId}/start`),
  getStats: (locationTypeId?: string) =>
    api.get('/tasks/stats', { params: { location_type_id: locationTypeId } }),
  getGlobalImageStats: () =>
    api.get('/tasks/stats/images'),
  syncImageCounts: () =>
    api.post('/tasks/stats/sync-image-counts'),
  
  // Task creation
  getGroupableFields: (locationTypeId: string) =>
    api.get(`/tasks/groupable-fields/${locationTypeId}`),
  previewTaskCreation: (data: {
    location_type_id: string;
    group_field: string;
    selected_values?: string[];
  }) =>
    api.post('/tasks/preview', data),
  createTasksFromField: (data: {
    location_type_id: string;
    group_field: string;
    selected_values?: string[];
  }) =>
    api.post('/tasks/create-from-field', data),
  deleteTask: (taskId: string) =>
    api.delete(`/tasks/${taskId}`),
  bulkDeleteTasks: (taskIds: string[]) =>
    api.delete('/tasks/bulk-delete', { data: taskIds }),
  downloadAllImages: () =>
    api.post('/tasks/download-all-images'),
  pauseAllDownloads: () =>
    api.post('/tasks/pause-all-downloads'),
  resumeAllDownloads: () =>
    api.post('/tasks/resume-all-downloads'),
  downloadTaskImages: (taskId: string) =>
    api.post(`/tasks/${taskId}/download-images`),
  
  // Location filtering
  getLocationFilterFields: (locationTypeId: string) =>
    api.get(`/tasks/location-filter-fields/${locationTypeId}`),
  previewLocationFilter: (data: {
    location_type_id: string;
    filter_field: string;
    filter_value: string;
    action: string;
  }) =>
    api.post('/tasks/filter-locations/preview', data),
  applyLocationFilter: (data: {
    location_type_id: string;
    filter_field: string;
    filter_value: string;
    action: string;
  }) =>
    api.post('/tasks/filter-locations/apply', data),
  
  // Image management
  triggerImageDownload: (taskId: string) =>
    api.post(`/tasks/${taskId}/download-images`),
  cancelDownload: (taskId: string) =>
    api.post(`/tasks/${taskId}/cancel-download`),
  pauseDownload: (taskId: string) =>
    api.post(`/tasks/${taskId}/pause-download`),
  resumeDownload: (taskId: string) =>
    api.post(`/tasks/${taskId}/resume-download`),
  restartDownload: (taskId: string, force: boolean = false) =>
    api.post(`/tasks/${taskId}/restart-download`, null, { params: { force } }),
  getDownloadStatus: (taskId: string) =>
    api.get(`/tasks/${taskId}/download-status`),
  getTaskImages: (taskId: string, page: number = 1, pageSize: number = 20) =>
    api.get(`/tasks/${taskId}/images`, { params: { page, page_size: pageSize } }),
  getDownloadLogs: (taskId: string) =>
    api.get(`/tasks/${taskId}/download-logs`),
  
  // Sample tasks
  getTasksWithImages: () =>
    api.get('/tasks/with-images'),
  createSampleTask: (data: {
    source_task_id: string;
    sample_size: number;
    sample_name?: string;
  }) =>
    api.post('/tasks/sample', data),
}

// Export API
export const exportsApi = {
  // Get task summary
  getTaskSummary: (taskId: string) =>
    api.get(`/exports/task/${taskId}/summary`),
  
  // Export task results as CSV
  exportTaskCsv: (taskId: string, includeUnlabelled: boolean = true) =>
    api.get(`/exports/task/${taskId}/csv`, { 
      params: { include_unlabelled: includeUnlabelled },
      responseType: 'blob'
    }),
  
  // Get task snapshots
  getTaskSnapshots: (taskId: string) =>
    api.get(`/exports/task/${taskId}/snapshots`),
  
  // Export location type results
  exportLocationTypeCsv: (locationTypeId: string, council?: string, includeUnlabelled: boolean = false) =>
    api.get(`/exports/csv/${locationTypeId}`, { 
      params: { council, include_unlabelled: includeUnlabelled },
      responseType: 'blob'
    }),
  
  // Export images as ZIP
  exportImagesZip: (locationTypeId: string, council?: string, onlyWithAdvertising: boolean = true) =>
    api.get(`/exports/images/${locationTypeId}`, { 
      params: { council, only_with_advertising: onlyWithAdvertising },
      responseType: 'blob'
    }),
  
  // Bulk export CSV for multiple tasks
  bulkExportCsv: (taskIds: string[]) =>
    api.post(`/exports/bulk/csv`, { task_ids: taskIds }, {
      responseType: 'blob',
      timeout: 300000 // 5 minute timeout for large exports
    }),
  
  // Bulk export all (CSV + images + snapshots) for multiple tasks
  bulkExportAll: (taskIds: string[]) =>
    api.post(`/exports/bulk/all`, { task_ids: taskIds }, {
      responseType: 'blob',
      timeout: 600000 // 10 minute timeout for large exports
    }),
}

// Labelling API
export const labellingApi = {
  getTaskLocations: (taskId: string, page: number, pageSize: number) =>
    api.get(`/labelling/task/${taskId}/locations`, { params: { page, page_size: pageSize } }),
  getLocationForLabelling: (taskId: string, locationIndex: number) =>
    api.get(`/labelling/task/${taskId}/location/${locationIndex}`),
  searchLocation: (taskId: string, query: string) =>
    api.get(`/labelling/task/${taskId}/search`, { params: { query } }),
  saveLabel: (taskId: string, locationId: string, data: any) =>
    api.post(`/labelling/task/${taskId}/location/${locationId}/label`, data),
  saveSnapshot: (taskId: string, locationId: string, heading: number, pitch: number, panoId?: string) =>
    api.post(`/labelling/task/${taskId}/location/${locationId}/snapshot`, {
      heading,
      pitch,
      pano_id: panoId
    }),
  getProgress: (taskId: string) =>
    api.get(`/labelling/task/${taskId}/progress`),
}

// Spreadsheets API
export const spreadsheetsApi = {
  getLocationTypes: () =>
    api.get('/spreadsheets/location-types'),
  createLocationType: (data: any) =>
    api.post('/spreadsheets/location-types', data),
  deleteLocationType: (typeId: string) =>
    api.delete(`/spreadsheets/location-types/${typeId}`),
  updateLabelFields: (typeId: string, labelFields: any) =>
    api.patch(`/spreadsheets/location-types/${typeId}/label-fields`, labelFields),
  uploadSpreadsheet: (formData: FormData) =>
    api.post('/spreadsheets/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  getUploadJobStatus: (jobId: string) =>
    api.get(`/spreadsheets/upload-jobs/${jobId}`),
  enhanceData: (locationTypeId: string, options: any) =>
    api.post('/spreadsheets/enhance', { location_type_id: locationTypeId, ...options }),
  getCouncils: (locationTypeId: string) =>
    api.get(`/spreadsheets/councils/${locationTypeId}`),
}

// Users API
export const usersApi = {
  getUsers: (params: any) =>
    api.get('/users', { params }),
  getLabellers: () =>
    api.get('/users/labellers'),
  getUser: (userId: string) =>
    api.get(`/users/${userId}`),
  createUser: (data: any) =>
    api.post('/users', data),
  updateUser: (userId: string, data: any) =>
    api.patch(`/users/${userId}`, data),
  deleteUser: (userId: string) =>
    api.delete(`/users/${userId}`),
}

// Invitations API
export const invitationsApi = {
  create: (data: { email: string; name?: string; role: string; message?: string }) =>
    api.post('/invitations/', data),
  list: (status?: string) =>
    api.get('/invitations/', { params: status ? { status_filter: status } : {} }),
  validate: (token: string) =>
    api.get(`/invitations/validate/${token}`),
  accept: (data: { token: string; name: string; password: string; phone_number?: string; whatsapp_number?: string }) =>
    api.post('/invitations/accept', data),
  cancel: (invitationId: string) =>
    api.delete(`/invitations/${invitationId}`),
  resend: (invitationId: string) =>
    api.post(`/invitations/${invitationId}/resend`),
}

// Admin API
export const adminApi = {
  getPerformance: (days: number = 30) =>
    api.get('/admin/performance', { params: { days } }),
  getLabelerView: (labellerId: string) =>
    api.get(`/admin/labeller/${labellerId}/view`),
  getSystemStats: () =>
    api.get('/admin/stats'),
  notifyManagers: (message: string) =>
    api.post('/admin/notify-managers', null, { params: { message } }),
  
  // GSV API Key Management
  getGsvAccounts: () =>
    api.get('/admin/gsv-accounts'),
  addGsvAccount: (data: { email: string; billing_id?: string; target_projects?: number }) =>
    api.post('/admin/gsv-accounts', data),
  deleteGsvAccount: (accountId: string) =>
    api.delete(`/admin/gsv-accounts/${accountId}`),
  addGsvKey: (accountId: string, data: { project_id?: string; api_key: string }) =>
    api.post(`/admin/gsv-accounts/${accountId}/add-key`, data),
  bulkAddGsvKeys: (accountId: string, keys: string) =>
    api.post(`/admin/gsv-accounts/${accountId}/bulk-add-keys`, { keys }),
  getAllGsvKeys: () =>
    api.get('/admin/gsv-all-keys'),
  applyGsvKeys: () =>
    api.post('/admin/gsv-apply-keys'),
  
  // GSV OAuth & Auto-create
  getGsvOAuthConfig: () =>
    api.get('/admin/gsv-oauth-config'),
  getGsvOAuthUrl: () =>
    api.get('/admin/gsv-oauth-url'),
  createGsvProjects: (accountId: string, count: number = 5) =>
    api.post(`/admin/gsv-accounts/${accountId}/create-projects?count=${count}`),
}

// Notifications API
export const notificationsApi = {
  getSettings: () =>
    api.get('/notifications/settings'),
  updateSettings: (data: {
    daily_summary_enabled?: boolean;
    daily_summary_time?: string;
    daily_summary_admin_id?: string;
    task_completion_enabled?: boolean;
    daily_reminders_enabled?: boolean;
    daily_reminder_time?: string;
  }) =>
    api.patch('/notifications/settings', data),
  getMyPreferences: () =>
    api.get('/notifications/preferences'),
  updateMyPreferences: (data: {
    opt_out_daily_reminders?: boolean;
    opt_out_task_assignments?: boolean;
    opt_out_all_whatsapp?: boolean;
  }) =>
    api.patch('/notifications/preferences', data),
  getLogs: (limit?: number, notificationType?: string) =>
    api.get('/notifications/logs', { params: { limit, notification_type: notificationType } }),
  testDailySummary: () =>
    api.post('/notifications/test/daily-summary'),
  testLabellerReminders: () =>
    api.post('/notifications/test/labeller-reminders'),
}

// Data Management API
export const dataApi = {
  // Dataset viewing
  getDatasets: () =>
    api.get('/data/datasets'),
  getLocations: (locationTypeId: string, params: {
    page?: number;
    page_size?: number;
    search?: string;
    council?: string;
    enhanced_only?: boolean;
    labelled_only?: boolean;
    filters?: string;  // JSON string of column filters
  }) =>
    api.get(`/data/locations/${locationTypeId}`, { params }),
  
  // Shapefiles
  getShapefiles: () =>
    api.get('/data/shapefiles'),
  getShapefileTypes: () =>
    api.get('/data/shapefiles/types'),
  analyzeShapefile: (formData: FormData, onProgress?: (percent: number) => void) =>
    api.post('/data/shapefiles/analyze', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress ? (e) => {
        const percent = Math.round((e.loaded * 100) / (e.total || 1))
        onProgress(percent)
      } : undefined
    }),
  uploadShapefile: (formData: FormData, onProgress?: (percent: number) => void) =>
    api.post('/data/shapefiles/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress ? (e) => {
        const percent = Math.round((e.loaded * 100) / (e.total || 1))
        onProgress(percent)
      } : undefined
    }),
  
  // Chunked upload for large files
  startChunkedUpload: (data: {
    filename: string;
    file_size: number;
    name: string;
    display_name: string;
    description?: string;
    shapefile_type: string;
    attribute_mappings: string;
    layer_name?: string;
  }) => {
    const formData = new FormData()
    Object.entries(data).forEach(([key, value]) => {
      if (value !== undefined) formData.append(key, String(value))
    })
    return api.post('/data/shapefiles/upload/start', formData)
  },
  
  uploadChunk: (jobId: string, chunk: ArrayBuffer) =>
    api.post(`/data/shapefiles/upload/${jobId}/chunk`, chunk, {
      headers: { 'Content-Type': 'application/octet-stream' }
    }),
  
  completeUpload: (jobId: string) =>
    api.post(`/data/shapefiles/upload/${jobId}/complete`),
  
  getUploadStatus: (jobId: string) =>
    api.get(`/data/shapefiles/upload/${jobId}/status`),
  
  loadShapefile: (shapefileId: string) =>
    api.post(`/data/shapefiles/${shapefileId}/load`),
  deleteShapefile: (shapefileId: string) =>
    api.delete(`/data/shapefiles/${shapefileId}`),
  
  // Enhancement
  getEnhancementPreview: (locationTypeId: string) =>
    api.get(`/data/enhancement/preview/${locationTypeId}`),
  startEnhancement: (data: {
    location_type_id: string;
    enhance_council?: boolean;
    enhance_road?: boolean;
    enhance_authority?: boolean;
    custom_shapefiles?: string[];
  }) =>
    api.post('/data/enhancement/start', data),
  getEnhancementJobs: (locationTypeId?: string) =>
    api.get('/data/enhancement/jobs', { params: { location_type_id: locationTypeId } }),
  getEnhancementJob: (jobId: string) =>
    api.get(`/data/enhancement/jobs/${jobId}`),
}
