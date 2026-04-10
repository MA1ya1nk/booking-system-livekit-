import { Navigate, Route, Routes } from 'react-router-dom'
import VoiceAssistantButton from './components/VoiceAssistantButton'
import { useAuth } from './context/AuthContext'
import AdminServicesPage from './pages/AdminServicesPage'
import DashboardPage from './pages/DashboardPage'
import LandingPage from './pages/LandingPage'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'

function ProtectedRoute({ children, adminOnly = false }) {
  const { isAuthenticated, isAdmin, loadingUser } = useAuth()
  if (loadingUser) return <p className="center">Loading...</p>
  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (adminOnly && !isAdmin) return <Navigate to="/dashboard" replace />
  return children
}

function App() {
  return (
    <>
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <DashboardPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/services"
        element={
          <ProtectedRoute adminOnly>
            <AdminServicesPage />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    <VoiceAssistantButton />
    </>
  )
}

export default App
