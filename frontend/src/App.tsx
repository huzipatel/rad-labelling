import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/authStore'
import Layout from './components/common/Layout'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import DashboardPage from './pages/DashboardPage'
import TasksPage from './pages/TasksPage'
import LabellingPage from './pages/LabellingPage'
import ManagerDashboard from './pages/ManagerDashboard'
import AdminPage from './pages/AdminPage'
import UploadPage from './pages/UploadPage'
import DataViewerPage from './pages/DataViewerPage'
import PerformancePage from './pages/PerformancePage'
import ExportsPage from './pages/ExportsPage'

function ProtectedRoute({ children, allowedRoles }: { children: React.ReactNode; allowedRoles?: string[] }) {
  const { user, isAuthenticated } = useAuthStore()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  if (allowedRoles && user && !allowedRoles.includes(user.role)) {
    return <Navigate to="/dashboard" replace />
  }

  return <>{children}</>
}

function App() {
  const { isAuthenticated } = useAuthStore()

  return (
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/dashboard" /> : <LoginPage />} />
      <Route path="/register" element={isAuthenticated ? <Navigate to="/dashboard" /> : <RegisterPage />} />
      
      <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="labelling/:taskId" element={<LabellingPage />} />
        
        {/* Manager routes */}
        <Route 
          path="manager" 
          element={
            <ProtectedRoute allowedRoles={['labelling_manager', 'admin']}>
              <ManagerDashboard />
            </ProtectedRoute>
          } 
        />
        <Route 
          path="upload" 
          element={
            <ProtectedRoute allowedRoles={['labelling_manager', 'admin']}>
              <UploadPage />
            </ProtectedRoute>
          } 
        />
        <Route 
          path="data" 
          element={
            <ProtectedRoute allowedRoles={['labelling_manager', 'admin']}>
              <DataViewerPage />
            </ProtectedRoute>
          } 
        />
        <Route 
          path="data/:locationTypeId" 
          element={
            <ProtectedRoute allowedRoles={['labelling_manager', 'admin']}>
              <DataViewerPage />
            </ProtectedRoute>
          } 
        />
        <Route 
          path="performance" 
          element={
            <ProtectedRoute allowedRoles={['labelling_manager', 'admin']}>
              <PerformancePage />
            </ProtectedRoute>
          } 
        />
        <Route 
          path="exports" 
          element={
            <ProtectedRoute allowedRoles={['labelling_manager', 'admin']}>
              <ExportsPage />
            </ProtectedRoute>
          } 
        />
        
        {/* Admin routes */}
        <Route 
          path="admin" 
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <AdminPage />
            </ProtectedRoute>
          } 
        />
      </Route>
      
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}

export default App

