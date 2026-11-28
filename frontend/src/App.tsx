import { lazy, Suspense } from 'react'
import { BrowserRouter as Router, Outlet, Route, Routes } from 'react-router-dom'
import { SessionProvider } from './contexts/SessionProvider'
import { ToastProvider } from './contexts/ToastProvider'
import { BreakpointProvider } from './contexts/BreakpointContext'
import { WebSocketProvider } from './contexts/WebSocketContext'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { AuthenticatedAppShell } from './components/layout/AuthenticatedAppShell'
import { adminPages, signedInPages } from './routes/routePages'

const Login = lazy(() => import('./pages/Login'))
const McpConsent = lazy(() => import('./pages/McpConsent'))
const SetPasswordPage = lazy(() => import('./pages/SetPasswordPage'))
const Logout = lazy(() => import('./pages/Logout'))
const SelfPasswordChange = lazy(() => import('./pages/SelfPasswordChange'))

export default function App() {
  return (
    <BreakpointProvider>
      <SessionProvider>
        <ToastProvider>
          <WebSocketProvider>
            <Router>
              <Suspense fallback={null}>
                <Routes>
                  <Route path="/login" element={<Login />} />
                  <Route path="/oauth/mcp/consent" element={<McpConsent />} />
                  <Route path="/reset-password" element={<SetPasswordPage />} />
                  <Route path="/logout" element={<Logout />} />
                  <Route path="/change-password" element={<ProtectedRoute><SelfPasswordChange /></ProtectedRoute>} />

                  <Route element={<ProtectedRoute><AuthenticatedAppShell /></ProtectedRoute>}>
                    {Object.entries(signedInPages).map(([path, { Component }]) => (
                      <Route key={path} path={path} element={<Component />} />
                    ))}
                    <Route element={<ProtectedRoute requiredRole="ADMIN"><Outlet /></ProtectedRoute>}>
                      {Object.entries(adminPages).map(([path, { Component }]) => (
                        <Route key={path} path={path} element={<Component />} />
                      ))}
                    </Route>
                  </Route>
                </Routes>
              </Suspense>
            </Router>
          </WebSocketProvider>
        </ToastProvider>
      </SessionProvider>
    </BreakpointProvider>
  )
}
