import { useEffect, useState } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Legend,
} from 'recharts'
import { supabase } from '../lib/supabase'
import type { CalibrationRow } from '../lib/types'

export function CalibrationPage() {
  const [rows, setRows] = useState<CalibrationRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dtype, setDtype] = useState('page_relevance')

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      const { data, error: err } = await supabase
        .from('calibration_report')
        .select('*')
        .eq('decision_type', dtype)
        .order('bucket')
      if (err) setError(err.message)
      else setRows(data ?? [])
      setLoading(false)
    }
    load()
  }, [dtype])

  const chartData = rows.map((r) => ({
    bucket: Number(r.bucket),
    avg_confidence: Number(r.avg_confidence),
    actual_accuracy: Number(r.actual_accuracy),
    n: Number(r.n),
  }))

  const totalN = rows.reduce((s, r) => s + Number(r.n), 0)
  const needMore = totalN < 20

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Calibration</h1>
      <p className="text-sm text-gray-500">
        Stated confidence vs observed accuracy. The diagonal is perfect calibration.
      </p>

      <select
        value={dtype}
        onChange={(e) => setDtype(e.target.value)}
        className="px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm"
      >
        <option value="page_relevance">page_relevance</option>
        <option value="page_relevance_deep">page_relevance_deep</option>
      </select>

      {loading && <p className="text-gray-500">Loading…</p>}
      {error && <p className="text-red-600">{error}</p>}

      {!loading && needMore && (
        <div className="bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-700 rounded-lg p-4 text-sm text-amber-800 dark:text-amber-200">
          Need more graded data (currently n={totalN}). Grade decisions on the Decisions page until n ≥ 20.
        </div>
      )}

      {!loading && chartData.length > 0 && (
        <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-4 h-80">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis
                dataKey="bucket"
                type="number"
                domain={[0, 1]}
                tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                label={{ value: 'Stated confidence', position: 'insideBottom', offset: -5 }}
              />
              <YAxis
                domain={[0, 1]}
                tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                label={{ value: 'Accuracy', angle: -90, position: 'insideLeft' }}
              />
              <Tooltip
                formatter={(value: number, name: string) => [
                  `${(value * 100).toFixed(1)}%`,
                  name === 'avg_confidence' ? 'Avg confidence' : 'Actual accuracy',
                ]}
                labelFormatter={(l) => `Bucket ${(Number(l) * 100).toFixed(0)}%`}
              />
              <Legend />
              <ReferenceLine
                segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]}
                stroke="#9ca3af"
                strokeDasharray="4 4"
                label="perfect"
              />
              <Line
                type="monotone"
                dataKey="avg_confidence"
                stroke="#6366f1"
                name="Avg confidence"
                strokeWidth={2}
                dot={{ r: 4 }}
              />
              <Line
                type="monotone"
                dataKey="actual_accuracy"
                stroke="#10b981"
                name="Actual accuracy"
                strokeWidth={2}
                dot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {!loading && chartData.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-200 dark:border-gray-700">
                <th className="py-2 pr-4">Bucket</th>
                <th className="py-2 pr-4">n</th>
                <th className="py-2 pr-4">Avg conf</th>
                <th className="py-2">Actual accuracy</th>
              </tr>
            </thead>
            <tbody>
              {chartData.map((r) => (
                <tr key={r.bucket} className="border-b border-gray-100 dark:border-gray-800">
                  <td className="py-2 pr-4">{(r.bucket * 100).toFixed(0)}%</td>
                  <td className="py-2 pr-4">{r.n}</td>
                  <td className="py-2 pr-4">{(r.avg_confidence * 100).toFixed(1)}%</td>
                  <td className="py-2">{(r.actual_accuracy * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
