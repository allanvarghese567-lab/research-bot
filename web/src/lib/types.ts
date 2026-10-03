export type ResearchStatus = 'pending' | 'running' | 'done' | 'error'

export interface ResearchRequest {
  id: string
  user_id: string
  question: string
  status: ResearchStatus
  error_message?: string | null
  created_at: string
}

export interface Ticket {
  id: string
  request_id: string
  user_id: string
  symbol: string
  stance: 'bullish' | 'bearish' | 'neutral'
  confidence: number
  summary: string
  sources: {
    urls?: string[]
    key_points?: string[]
    risks?: string[]
  }
  created_at: string
}

export interface DecisionLog {
  id: string
  request_id: string
  decision_type: string
  input_summary?: string
  probs?: Record<string, number>
  predicted?: string
  confidence?: number
  calibrated_confidence?: number
  action?: string
  model?: string
  outcome?: 'relevant' | 'irrelevant' | 'unsure' | null
  correct?: boolean | null
  created_at: string
}

export interface CalibrationRow {
  decision_type: string
  bucket: number
  n: number
  avg_confidence: number
  actual_accuracy: number
}
