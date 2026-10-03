import { BrowserRouter, Routes, Route, Navigate, Link, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './lib/auth'
import { ChatPage } from './pages/Chat'
import { HistoryPage } from './pages/History'
import { DecisionsPage } from './pages/Decisions'
import { CalibrationPage } from './pages/Calibration'
import { LoginPage } from './pages/Login'
import { useEffect, useState } from 'react'

// Match Vite base: only set basename when deployed to GitHub Pages
const BASENAME = import.meta.env.BASE_URL.replace(/\/$/, '') || undefined

function ThemeToggle() {
  const [dark, setDark] = useState(() =>
    localStorage.getItem('theme') === 'dark' ||
    (!localStorage.getItem('theme') && window.matchMedia('(prefers-color-scheme: dark)').matches)
  )

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  return (
    <button
      onClick={() => setDark((d) => !d)}
      className="p-2 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 text-sm"
      aria-label="Toggle theme"
    >
      {dark ? '☀️' : '🌙'}
    </button>
  )
}

function Nav() {
  const { user, signOut } = useAuth()
  const loc = useLocation()
  const link = (to: string, label: string) => (
    <Link
      to={to}
      className={`px-3 py-2 rounded-md text-sm font-medium ${
        loc.pathname === to
          ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900 dark:text-indigo-200'
          : 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800'
      }`}
    >
      {label}
    </Link>
  )

  return (
    <header className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 sticky top-0 z-10">
      <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-1 sm:gap-2">
          <span className="font-bold text-lg text-indigo-600 dark:text-indigo-400">Research Bot</span>
          <nav className="hidden sm:flex gap-1 ml-4">
            {link('/', 'Chat')}
            {link('/history', 'History')}
            {link('/decisions', 'Decisions')}
            {link('/calibration', 'Calibration')}
          </nav>
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          {user && (
            <button
              onClick={() => signOut()}
              className="text-sm text-gray-500 hover:text-gray-800 dark:hover:text-gray-200"
            >
              Sign out
            </button>
          )}
        </div>
      </div>
      {/* Mobile nav */}
      <nav className="sm:hidden flex gap-1 px-4 pb-2 overflow-x-auto">
        {link('/', 'Chat')}
        {link('/history', 'History')}
        {link('/decisions', 'Decisions')}
        {link('/calibration', 'Calibration')}
      </nav>
    </header>
  )
}

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh] text-gray-500">
        Loading…
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

function AppRoutes() {
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950 text-gray-900 dark:text-gray-100">
      <Nav />
      <main className="max-w-5xl mx-auto px-4 py-6">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<Protected><ChatPage /></Protected>} />
          <Route path="/history" element={<Protected><HistoryPage /></Protected>} />
          <Route path="/decisions" element={<Protected><DecisionsPage /></Protected>} />
          <Route path="/calibration" element={<Protected><CalibrationPage /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter basename={BASENAME}>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  )
}
