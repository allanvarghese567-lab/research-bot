import { useEffect, useRef, useState } from 'react'
import { supabase } from '../lib/supabase'
import { useAuth } from '../lib/auth'
import type { ResearchRequest, Ticket } from '../lib/types'

interface Message {
  id: string
  role: 'user' | 'assistant' | 'status'
  text?: string
  ticket?: Ticket
  status?: string
  error?: string
}

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

function TicketCard({ ticket }: { ticket: Ticket }) {
  const sources = ticket.sources ?? {}
  const urls = sources.urls ?? []
  const keyPoints = sources.key_points ?? []
  const risks = sources.risks ?? []

  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-4 space-y-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-bold text-lg">{ticket.symbol}</span>
        <StanceBadge stance={ticket.stance} />
        <span className="text-sm text-gray-500">{ticket.confidence}% confidence</span>
      </div>
      <p className="text-sm leading-relaxed">{ticket.summary}</p>
      {keyPoints.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold uppercase text-gray-500 mb-1">Key points</h4>
          <ul className="list-disc list-inside text-sm space-y-0.5">
            {keyPoints.map((p, i) => <li key={i}>{p}</li>)}
          </ul>
        </div>
      )}
      {risks.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold uppercase text-gray-500 mb-1">Risks</h4>
          <ul className="list-disc list-inside text-sm space-y-0.5 text-amber-700 dark:text-amber-300">
            {risks.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>
      )}
      {urls.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold uppercase text-gray-500 mb-1">Sources</h4>
          <ul className="space-y-1">
            {urls.map((u, i) => (
              <li key={i}>
                <a
                  href={u}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-indigo-600 dark:text-indigo-400 hover:underline break-all"
                >
                  {u}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-xs text-gray-400 italic pt-1 border-t border-gray-100 dark:border-gray-800">
        Research only, not financial advice.
      </p>
    </div>
  )
}

export function ChatPage() {
  const { user } = useAuth()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Subscribe to realtime updates for research_requests and tickets
  useEffect(() => {
    if (!user) return

    const reqChannel = supabase
      .channel('requests')
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'research_requests', filter: `user_id=eq.${user.id}` },
        (payload) => {
          const req = payload.new as ResearchRequest
          setMessages((prev) => {
            const idx = prev.findIndex((m) => m.id === req.id && m.role === 'status')
            if (idx === -1) return prev
            const next = [...prev]
            if (req.status === 'error') {
              next[idx] = { ...next[idx], status: 'error', error: req.error_message ?? 'Unknown error' }
            } else if (req.status === 'done') {
              next[idx] = { ...next[idx], status: 'done' }
            } else {
              next[idx] = { ...next[idx], status: req.status }
            }
            return next
          })
        }
      )
      .subscribe()

    const ticketChannel = supabase
      .channel('tickets')
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'tickets', filter: `user_id=eq.${user.id}` },
        (payload) => {
          const ticket = payload.new as Ticket
          setMessages((prev) => {
            const without = prev.filter((m) => !(m.id === ticket.request_id && m.role === 'status'))
            return [
              ...without,
              { id: ticket.id, role: 'assistant', ticket },
            ]
          })
        }
      )
      .subscribe()

    return () => {
      supabase.removeChannel(reqChannel)
      supabase.removeChannel(ticketChannel)
    }
  }, [user])

  const send = async (e: React.FormEvent) => {
    e.preventDefault()
    const q = input.trim()
    if (!q || !user || busy) return
    setBusy(true)
    setInput('')

    const tempId = crypto.randomUUID()
    setMessages((prev) => [
      ...prev,
      { id: tempId, role: 'user', text: q },
      { id: tempId, role: 'status', status: 'pending' },
    ])

    const { data, error } = await supabase
      .from('research_requests')
      .insert({ question: q, user_id: user.id, status: 'pending' })
      .select()
      .single()

    if (error) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === tempId && m.role === 'status'
            ? { ...m, status: 'error', error: error.message }
            : m
        )
      )
      setBusy(false)
      return
    }

    setMessages((prev) =>
      prev.map((m) =>
        m.id === tempId && m.role === 'status'
          ? { ...m, id: data.id, status: 'pending' }
          : m.id === tempId && m.role === 'user'
          ? { ...m, id: data.id }
          : m
      )
    )

    const apiUrl = import.meta.env.VITE_API_URL
    if (apiUrl) {
      try {
        const { data: { session } } = await supabase.auth.getSession()
        if (session?.access_token) {
          await fetch(`${apiUrl}/requests/${data.id}/run`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${session.access_token}` },
          })
        }
      } catch {
        // ignore – cron will pick it up
      }
    }

    setBusy(false)
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 mt-20">
            <p className="text-lg">Ask a research question</p>
            <p className="text-sm mt-1">e.g. “What is the outlook for NVDA this quarter?”</p>
          </div>
        )}
        {messages.map((m) => {
          if (m.role === 'user') {
            return (
              <div key={`u-${m.id}`} className="flex justify-end">
                <div className="bg-indigo-600 text-white rounded-2xl rounded-br-md px-4 py-2 max-w-[85%] text-sm">
                  {m.text}
                </div>
              </div>
            )
          }
          if (m.role === 'status') {
            return (
              <div key={`s-${m.id}`} className="flex justify-start">
                <div className="bg-gray-100 dark:bg-gray-800 rounded-2xl rounded-bl-md px-4 py-2 text-sm text-gray-500">
                  {m.status === 'error' ? (
                    <span className="text-red-600">Error: {m.error}</span>
                  ) : m.status === 'done' ? (
                    <span>Done – loading ticket…</span>
                  ) : (
                    <span className="flex items-center gap-2">
                      <span className="inline-block w-2 h-2 bg-indigo-500 rounded-full animate-pulse" />
                      {m.status === 'running' ? 'Researching…' : 'Queued…'}
                    </span>
                  )}
                </div>
              </div>
            )
          }
          if (m.role === 'assistant' && m.ticket) {
            return (
              <div key={`a-${m.id}`} className="flex justify-start max-w-[95%]">
                <TicketCard ticket={m.ticket} />
              </div>
            )
          }
          return null
        })}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={send} className="flex gap-2 pt-2 border-t border-gray-200 dark:border-gray-700">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a research question…"
          disabled={busy}
          className="flex-1 px-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-medium disabled:opacity-50 text-sm"
        >
          Send
        </button>
      </form>
    </div>
  )
}
