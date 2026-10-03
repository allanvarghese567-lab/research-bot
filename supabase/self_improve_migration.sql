-- Self-improving strategy agent storage
-- Run in Supabase SQL Editor (same project as research-bot / aiprojectcreation Option A)

CREATE TABLE IF NOT EXISTS public.strategy_improve_runs (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  summary              text NOT NULL,
  score_biased         jsonb NOT NULL DEFAULT '{}'::jsonb,
  score_point_in_time  jsonb NOT NULL DEFAULT '{}'::jsonb,
  best_rules           jsonb NOT NULL DEFAULT '{}'::jsonb,
  learnings            jsonb NOT NULL DEFAULT '[]'::jsonb,
  iterations           jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS strategy_improve_runs_user_id_idx
  ON public.strategy_improve_runs (user_id, created_at DESC);

ALTER TABLE public.strategy_improve_runs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users read own strategy runs" ON public.strategy_improve_runs;
CREATE POLICY "Users read own strategy runs"
  ON public.strategy_improve_runs FOR SELECT
  USING (user_id IS NULL OR auth.uid() = user_id);

DROP POLICY IF EXISTS "Users insert own strategy runs" ON public.strategy_improve_runs;
CREATE POLICY "Users insert own strategy runs"
  ON public.strategy_improve_runs FOR INSERT
  WITH CHECK (user_id IS NULL OR auth.uid() = user_id);

-- Service role (worker) bypasses RLS
