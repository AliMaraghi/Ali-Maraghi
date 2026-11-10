-- Additive migration in the existing development ledger; no shadow database.
CREATE TABLE IF NOT EXISTS field_runs (
 trace_id TEXT PRIMARY KEY,
 fingerprint TEXT NOT NULL,
 mission TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('STARTED','COMPLETE')),
 result_seq INTEGER REFERENCES events(seq)
);
