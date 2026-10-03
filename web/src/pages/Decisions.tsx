import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'
import { useAuth } from '../lib/auth'
import type { DecisionLog } from '../lib/types'

export function DecisionsPage() {
  const { user } = useAuth()
  const [rows, setRows] = useState<DecisionLog[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [grading, setGrading] = useState<string | null>(null)

  const load = async () => {
    if (!user) return
    setLoading(true)
    const { data, error: err } = await supabase
      .from('decision_log')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(100)
    if (err) setError(err.message)
    else setRows(data ?? [])
    setLoading(false)
  }

  useEffect(() => {
    load()
  }, [user])

  const grade = async (id: string, outcome: 'relevant' | 'irrelevant' | 'unsure') => {
    setGrading(id)
    const row = rows.find((r) => r.id === id)
    const correct = row?.predicted === outcome
    const { error: err } = await supabase
      .from('decision_log')
      .update({ outcome, correct })
      .eq('id', id)
    if (err) {
      alert(err.message)
    } else {
      setRows((prev) =>
        prev.map((r) => (r.id === id ? { ...r, outcome, correct } : r))
      )
    }
    setGrading(null)
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Decisions</h1>
      <p className="text-sm text-gray-500">
        Grade page-relevance decisions to improve calibration. Mark whether the page was relevant, irrelevant, or you are unsure.
      </p>

      {loading && <p className="text-gray-500">Loading…</p>}
      {error && <p className="text-red-600">{error}</p>}
      {!loading && rows.length === 0 && (
        <p className="text-gray-400">No decisions logged yet.</p>
      )}

      <div className="space-y-3">
        {rows.map((r) => (
          <div
            key={r.id}
            className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-4 text-sm"
          >
            <div className="flex flex-wrap gap-2 items-center mb-1">
              <span className="font-medium">{r.decision_type}</span>
              <span className="text-gray-500">predicted: {r.predicted}</span>
              <span className="text-gray-500">
                conf {((r.confidence ?? 0) * 100).toFixed(0)}% → cal {((r.calibrated_confidence ?? 0) * 100).toFixed(0)}%
              </span>
              {r.outcome && (
                <span className={`text-xs px-2 py-0.5 rounded ${r.correct ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                  {r.outcome} {r.correct ? '✓' : '✗'}
                </span>
              )}
            </div>
            {r.input_summary && (
              <p className="text-gray-600 dark:text-gray-400 line-clamp-2 mb-2">{r.input_summary}</p>
            )}
            {!r.outcome && (
              <div className="flex gap-2">
                {(['relevant', 'irrelevant', 'unsure'] as const).map((o) => (
                  <button
                    key={o}
                    disabled={grading === r.id}
                    onClick={() => grade(r.id, o)}
                    className="px-3 py-1 rounded-lg text-xs font-medium border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50"
                  >
                    {o}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
