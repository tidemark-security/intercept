import { lazy, Suspense } from 'react'
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { SessionProvider } from './contexts/SessionProvider'
import { ToastProvider } from './contexts/ToastProvider'
import { BreakpointProvider } from './contexts/BreakpointContext'
import { WebSocketProvider } from './contexts/WebSocketContext'
import { ProtectedRoute } from './components/auth/ProtectedRoute'

const Alerts = lazy(() => import("./pages/Alerts"))
const Admin = lazy(() => import("./pages/Admin"))
const AdminAuditTrail = lazy(() => import("./pages/AdminAuditTrail"))
const AdminUsers = lazy(() => import("./pages/AdminUsers"))
const AdminLinkTemplates = lazy(() => import("./pages/AdminLinkTemplates"))
const AdminSettings = lazy(() => import("./pages/AdminSettings"))
const AdminQueueStatus = lazy(() => import("./pages/AdminQueueStatus"))
const AIChat = lazy(() => import("./pages/AIChat").then(m => ({ default: m.AIChat })))
const Home = lazy(() => import("./pages/Home"))
const Login = lazy(() => import("./pages/Login"))
const SetPasswordPage = lazy(() => import("./pages/SetPasswordPage"))
const CasesListPage = lazy(() => import("./pages/CaseList"))
const CaseDetailPage = lazy(() => import("./pages/CaseDetail"))
const Logout = lazy(() => import("./pages/Logout"))
const SelfPasswordChange = lazy(() => import("./pages/SelfPasswordChange"))
const ProfileManagement = lazy(() => import("./pages/ProfileManagement"))
const TasksListPage = lazy(() => import("./pages/TaskList"))
const TaskDetailPage = lazy(() => import("./pages/TaskDetail"))
const Reports = lazy(() => import("./pages/Reports"))
const AITriageDetails = lazy(() => import("./pages/AITriageDetails"))
const SearchPage = lazy(() => import("./pages/SearchPage"))

export default function App() {
  return (
    <BreakpointProvider>
      <SessionProvider>
        <WebSocketProvider>
        <ToastProvider>
          <Router>
          <Suspense fallback={null}>
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
          </Suspense>
      </Router>
      </ToastProvider>
    </WebSocketProvider>
    </SessionProvider>
    </BreakpointProvider>
  )
}
