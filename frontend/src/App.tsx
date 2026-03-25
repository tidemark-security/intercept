import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { SessionProvider } from './contexts/SessionProvider'
import { ToastProvider } from './contexts/ToastProvider'
import { BreakpointProvider } from './contexts/BreakpointContext'
import { WebSocketProvider } from './contexts/WebSocketContext'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
import Alerts from "./pages/Alerts"
import Admin from "./pages/Admin"
import AdminAuditTrail from "./pages/AdminAuditTrail"
import AdminUsers from "./pages/AdminUsers"
import AdminLinkTemplates from "./pages/AdminLinkTemplates"
import AdminSettings from "./pages/AdminSettings"
import AdminQueueStatus from "./pages/AdminQueueStatus"
import { AIChat } from "./pages/AIChat"
import Home from "./pages/Home"
import Login from "./pages/Login"
import SetPasswordPage from './pages/SetPasswordPage'
import CasesListPage from './pages/CaseList'
import CaseDetailPage from './pages/CaseDetail'
import Logout from './pages/Logout'
import SelfPasswordChange from './pages/SelfPasswordChange'
import ProfileManagement from './pages/ProfileManagement'
import TasksListPage from './pages/TaskList'
import TaskDetailPage from './pages/TaskDetail'
import Reports from './pages/Reports'
import AITriageDetails from './pages/AITriageDetails'
import SearchPage from './pages/SearchPage'

export default function App() {
  return (
    <BreakpointProvider>
      <SessionProvider>
        <WebSocketProvider>
        <ToastProvider>
          <Router>
          <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/reset-password" element={<SetPasswordPage />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Home />
              </ProtectedRoute>
            }
          />
          <Route
            path="/alerts"
            element={
              <ProtectedRoute>
                <Alerts />
              </ProtectedRoute>
            }
          />
          <Route
            path="/alerts/:humanId"
            element={
              <ProtectedRoute>
                <Alerts />
              </ProtectedRoute>
            }
          />
          <Route
            path="/cases"
            element={
              <ProtectedRoute>
                <CasesListPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/cases/:humanId"
            element={
              <ProtectedRoute>
                <CaseDetailPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/tasks"
            element={
              <ProtectedRoute>
                <TasksListPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/tasks/:humanId"
            element={
              <ProtectedRoute>
                <TaskDetailPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/reports"
            element={
              <ProtectedRoute>
                <Reports />
              </ProtectedRoute>
            }
          />
          <Route
            path="/reports/ai-triage/details"
            element={
              <ProtectedRoute requiredRole="ADMIN">
                <AITriageDetails />
              </ProtectedRoute>
            }
          />
          <Route
            path="/search"
            element={
              <ProtectedRoute>
                <SearchPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin"
            element={
              <ProtectedRoute requiredRole="ADMIN">
                <Admin />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/users"
            element={
              <ProtectedRoute requiredRole="ADMIN">
                <AdminUsers />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/audit"
            element={
              <ProtectedRoute requiredRole="ADMIN">
                <AdminAuditTrail />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/link-templates"
            element={
              <ProtectedRoute requiredRole="ADMIN">
                <AdminLinkTemplates />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/settings"
            element={
              <ProtectedRoute requiredRole="ADMIN">
                <AdminSettings />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/queue"
            element={
              <ProtectedRoute requiredRole="ADMIN">
                <AdminQueueStatus />
              </ProtectedRoute>
            }
          />
          <Route
            path="/ai-chat"
            element={
              <ProtectedRoute>
                <AIChat />
              </ProtectedRoute>
            }
          />
          <Route
            path="/change-password"
            element={
              <ProtectedRoute>
                <SelfPasswordChange />
              </ProtectedRoute>
            }
          />
          <Route
            path="/profile"
            element={
              <ProtectedRoute>
                <ProfileManagement />
              </ProtectedRoute>
            }
          />
          <Route path="/logout" element={<Logout />} />
        </Routes>
      </Router>
      </ToastProvider>
    </WebSocketProvider>
    </SessionProvider>
    </BreakpointProvider>
  )
}
