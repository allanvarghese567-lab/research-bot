-- Research Bot schema (idempotent)
-- Run in Supabase SQL Editor

-- Enable UUID extension if not already present
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------- research_requests
CREATE TABLE IF NOT EXISTS public.research_requests (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id       UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  question      TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'running', 'done', 'error')),
  error_message TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_research_requests_user_id
  ON public.research_requests (user_id);
CREATE INDEX IF NOT EXISTS idx_research_requests_status
  ON public.research_requests (status, created_at);

-- ---------------------------------------------------------------- tickets
CREATE TABLE IF NOT EXISTS public.tickets (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  request_id  UUID NOT NULL REFERENCES public.research_requests(id) ON DELETE CASCADE,
  user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  symbol      TEXT NOT NULL,
  stance      TEXT NOT NULL CHECK (stance IN ('bullish', 'bearish', 'neutral')),
  confidence  INT  NOT NULL CHECK (confidence >= 0 AND confidence <= 100),
  summary     TEXT NOT NULL,
  sources     JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tickets_user_id
  ON public.tickets (user_id);
CREATE INDEX IF NOT EXISTS idx_tickets_request_id
  ON public.tickets (request_id);
CREATE INDEX IF NOT EXISTS idx_tickets_symbol
  ON public.tickets (symbol);

-- ---------------------------------------------------------------- decision_log
CREATE TABLE IF NOT EXISTS public.decision_log (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  request_id            UUID NOT NULL REFERENCES public.research_requests(id) ON DELETE CASCADE,
  decision_type         TEXT NOT NULL,
  input_summary         TEXT,
  probs                 JSONB,
  predicted             TEXT,
  confidence            FLOAT,
  calibrated_confidence FLOAT,
  action                TEXT,
  model                 TEXT,
  outcome               TEXT CHECK (outcome IS NULL OR outcome IN ('relevant', 'irrelevant', 'unsure')),
  correct               BOOLEAN,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_decision_log_request_id
  ON public.decision_log (request_id);
CREATE INDEX IF NOT EXISTS idx_decision_log_decision_type
  ON public.decision_log (decision_type);

-- ---------------------------------------------------------------- calibration_report view
CREATE OR REPLACE VIEW public.calibration_report AS
SELECT
  decision_type,
  ROUND(confidence::numeric, 1) AS bucket,
  COUNT(*)::int AS n,
  ROUND(AVG(confidence)::numeric, 4) AS avg_confidence,
  ROUND(
    AVG(CASE WHEN correct THEN 1.0 ELSE 0.0 END)::numeric,
    4
  ) AS actual_accuracy
FROM public.decision_log
WHERE outcome IS NOT NULL
  AND correct IS NOT NULL
GROUP BY decision_type, ROUND(confidence::numeric, 1)
ORDER BY decision_type, bucket;

-- ---------------------------------------------------------------- RLS
ALTER TABLE public.research_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tickets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.decision_log ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if any (idempotent)
DROP POLICY IF EXISTS "Users can read own requests" ON public.research_requests;
DROP POLICY IF EXISTS "Users can insert own requests" ON public.research_requests;
DROP POLICY IF EXISTS "Users can update own requests" ON public.research_requests;

DROP POLICY IF EXISTS "Users can read own tickets" ON public.tickets;

DROP POLICY IF EXISTS "Users can read own decisions" ON public.decision_log;
DROP POLICY IF EXISTS "Users can update outcome on own decisions" ON public.decision_log;

-- research_requests policies
CREATE POLICY "Users can read own requests"
  ON public.research_requests FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own requests"
  ON public.research_requests FOR INSERT
  WITH CHECK (auth.uid() = user_id);

-- tickets policies (read only for users; worker uses service key)
CREATE POLICY "Users can read own tickets"
  ON public.tickets FOR SELECT
  USING (auth.uid() = user_id);

-- decision_log policies
CREATE POLICY "Users can read own decisions"
  ON public.decision_log FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.research_requests r
      WHERE r.id = decision_log.request_id
        AND r.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can update outcome on own decisions"
  ON public.decision_log FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM public.research_requests r
      WHERE r.id = decision_log.request_id
        AND r.user_id = auth.uid()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.research_requests r
      WHERE r.id = decision_log.request_id
        AND r.user_id = auth.uid()
    )
  );

-- ---------------------------------------------------------------- Realtime
-- Enable realtime for the tables the frontend subscribes to
ALTER PUBLICATION supabase_realtime ADD TABLE public.research_requests;
ALTER PUBLICATION supabase_realtime ADD TABLE public.tickets;

-- Grant usage (Supabase usually does this, but keep explicit)
GRANT SELECT ON public.calibration_report TO authenticated;
GRANT SELECT ON public.calibration_report TO anon;
