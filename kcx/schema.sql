-- KC-X SQLite schema. Applied idempotently at startup by kcx.db.init_db().
-- See docs/ARCHITECTURE.md ("Data model").

PRAGMA foreign_keys = ON;

-- One row per exam / drill / mistakes session.
CREATE TABLE IF NOT EXISTS attempts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    cert          TEXT    NOT NULL,                  -- e.g. 'kcna'
    mode          TEXT    NOT NULL CHECK (mode IN ('exam', 'drill', 'mistakes')),
    domain        TEXT,                              -- set for drills, NULL otherwise
    started_at    TEXT    NOT NULL,                  -- ISO-8601 UTC
    duration_sec  INTEGER,                           -- NULL = untimed
    submitted_at  TEXT,                              -- NULL while in progress
    score_pct     REAL,
    passed        INTEGER                            -- 0/1, NULL until submitted
);

-- The questions served in an attempt, in display order.
CREATE TABLE IF NOT EXISTS attempt_questions (
    attempt_id    INTEGER NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    position      INTEGER NOT NULL,                  -- 1-based
    question_id   TEXT    NOT NULL,                  -- e.g. 'kcna-kf-001'
    option_order  TEXT    NOT NULL,                  -- e.g. 'CABD': displayed slot 1 shows option C, ...
    selected      TEXT,                              -- original option key (A-D) or NULL
    flagged       INTEGER NOT NULL DEFAULT 0,
    is_correct    INTEGER,                           -- 0/1, set on submit
    answered_at   TEXT,
    PRIMARY KEY (attempt_id, position)
);

CREATE INDEX IF NOT EXISTS idx_aq_question ON attempt_questions(question_id);

-- Mistakes pool: questions whose most recent *submitted* answer was wrong (or left blank).
-- A question leaves the pool as soon as it is answered correctly in a later attempt.
CREATE VIEW IF NOT EXISTS mistakes AS
SELECT a.cert, aq.question_id, MAX(a.submitted_at) AS last_seen
FROM attempt_questions aq
JOIN attempts a ON a.id = aq.attempt_id
WHERE a.submitted_at IS NOT NULL
GROUP BY a.cert, aq.question_id
HAVING (
    SELECT aq2.is_correct
    FROM attempt_questions aq2
    JOIN attempts a2 ON a2.id = aq2.attempt_id
    WHERE aq2.question_id = aq.question_id AND a2.submitted_at IS NOT NULL
    ORDER BY a2.submitted_at DESC, a2.id DESC
    LIMIT 1
) = 0;
