-- SRE Agent iz kayitlari
CREATE TABLE IF NOT EXISTS agent_runs (
    id            bigserial PRIMARY KEY,
    user_name     text        NOT NULL,
    question      text        NOT NULL,
    context       jsonb       NOT NULL DEFAULT '{}',
    answer        text,
    status        text        NOT NULL DEFAULT 'running',   -- running | done | step_limit | error
    error         text,
    model         text,
    prompt_tokens     integer DEFAULT 0,
    completion_tokens integer DEFAULT 0,
    started_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz,
    feedback      text,                                     -- 'faydali' | 'yanlis'
    feedback_note text,
    feedback_by   text,
    feedback_at   timestamptz
);
CREATE INDEX IF NOT EXISTS agent_runs_started_idx ON agent_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS agent_steps (
    id          bigserial PRIMARY KEY,
    run_id      bigint      NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    step_no     integer     NOT NULL,
    tool_name   text        NOT NULL,
    arguments   jsonb       NOT NULL DEFAULT '{}',
    result      jsonb,
    reasoning   text,                                       -- modelin neden bu araci cagirdigi
    duration_ms integer,
    error       text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS agent_steps_run_idx ON agent_steps (run_id, step_no);
