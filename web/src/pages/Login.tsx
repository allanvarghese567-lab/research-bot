import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'

export function LoginPage() {
  const { user, signIn, signUp, loading } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (loading) return null
  if (user) return <Navigate to="/" replace />

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    const fn = mode === 'signin' ? signIn : signUp
    const { error: err } = await fn(email, password)
    setBusy(false)
    if (err) setError(err)
  }

  return (
    <div className="max-w-md mx-auto mt-12">
      <h1 className="text-2xl font-bold mb-6 text-center">
        {mode === 'signin' ? 'Sign in' : 'Create account'}
      </h1>
      <form onSubmit={submit} className="space-y-4 bg-white dark:bg-gray-900 p-6 rounded-xl shadow border border-gray-200 dark:border-gray-700">
        <div>
          <label className="block text-sm font-medium mb-1">Email</label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Password</label>
          <input
            type="password"
            required
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        {error && (
          <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
        )}
        <button
          type="submit"
          disabled={busy}
          className="w-full py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-medium disabled:opacity-50"
        >
          {busy ? '…' : mode === 'signin' ? 'Sign in' : 'Sign up'}
        </button>
      </form>
      <p className="mt-4 text-center text-sm text-gray-500">
        {mode === 'signin' ? (
          <>
            No account?{' '}
            <button onClick={() => setMode('signup')} className="text-indigo-600 hover:underline">
              Sign up
            </button>
          </>
        ) : (
          <>
            Already have an account?{' '}
            <button onClick={() => setMode('signin')} className="text-indigo-600 hover:underline">
              Sign in
            </button>
          </>
        )}
      </p>
    </div>
  )
}
