import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'
import { useAuth } from '../lib/auth'
import type { Ticket } from '../lib/types'

function StanceBadge({ stance }: { stance: string }) {
  const colors: Record<string, string> = {
    bullish: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    bearish: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    neutral: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200',
  }
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold uppercase ${colors[stance] ?? colors.neutral}`}>
      {stance}
    </span>
  )
}

export function HistoryPage() {
  const { user } = useAuth()
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [symbolFilter, setSymbolFilter] = useState('')
  const [stanceFilter, setStanceFilter] = useState('')

  useEffect(() => {
    if (!user) return
    const load = async () => {
      setLoading(true)
      let q = supabase
        .from('tickets')
        .select('*')
        .eq('user_id', user.id)
        .order('created_at', { ascending: false })
      if (symbolFilter.trim()) {
        q = q.ilike('symbol', `%${symbolFilter.trim()}%`)
      }
      if (stanceFilter) {
        q = q.eq('stance', stanceFilter)
      }
      const { data, error: err } = await q
      if (err) setError(err.message)
      else setTickets(data ?? [])
      setLoading(false)
    }
    load()
  }, [user, symbolFilter, stanceFilter])

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">History</h1>

      <div className="flex flex-wrap gap-3">
        <input
          value={symbolFilter}
          onChange={(e) => setSymbolFilter(e.target.value)}
          placeholder="Filter by symbol…"
          className="px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm"
        />
        <select
          value={stanceFilter}
          onChange={(e) => setStanceFilter(e.target.value)}
          className="px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm"
        >
          <option value="">All stances</option>
          <option value="bullish">Bullish</option>
          <option value="bearish">Bearish</option>
          <option value="neutral">Neutral</option>
        </select>
      </div>

      {loading && <p className="text-gray-500">Loading…</p>}
      {error && <p className="text-red-600">{error}</p>}
      {!loading && tickets.length === 0 && (
        <p className="text-gray-400">No tickets yet. Ask a question in Chat.</p>
      )}

      <div className="space-y-3">
        {tickets.map((t) => (
          <div
            key={t.id}
            className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-4"
          >
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <span className="font-bold">{t.symbol}</span>
              <StanceBadge stance={t.stance} />
              <span className="text-sm text-gray-500">{t.confidence}%</span>
              <span className="text-xs text-gray-400 ml-auto">
                {new Date(t.created_at).toLocaleString()}
              </span>
            </div>
            <p className="text-sm text-gray-700 dark:text-gray-300 line-clamp-3">{t.summary}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
