CREATE TABLE game_competitions (
 id UUID PRIMARY KEY,
 organization_id UUID NOT NULL REFERENCES organizations(id),
 created_by UUID NOT NULL REFERENCES accounts(id),
 request_key UUID NOT NULL,
 title VARCHAR(100) NOT NULL,
 description VARCHAR(4000) NOT NULL,
 mode VARCHAR(16) NOT NULL CHECK(mode IN ('REALTIME','DISASTER')),
 event_id VARCHAR(32),
 opens_at TIMESTAMPTZ NOT NULL,
 closes_at TIMESTAMPTZ NOT NULL,
 rules TEXT NOT NULL,
 rules_hash VARCHAR(64) NOT NULL CHECK(rules_hash ~ '^[a-f0-9]{64}$'),
 score_policy_sha256 VARCHAR(64) NOT NULL CHECK(score_policy_sha256 ~ '^[a-f0-9]{64}$'),
 state VARCHAR(16) NOT NULL DEFAULT 'PUBLISHED' CHECK(state IN ('PUBLISHED','CANCELLED')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(created_by,request_key),
 CHECK(closes_at>opens_at),
 CHECK(opens_at=date_trunc('minute',opens_at) AND closes_at=date_trunc('minute',closes_at)),
 CHECK((mode='REALTIME' AND event_id IS NULL) OR (mode='DISASTER' AND event_id IS NOT NULL))
);
CREATE INDEX game_competitions_dates ON game_competitions(closes_at,created_at DESC);
CREATE TABLE game_competition_participants (
 competition_id UUID NOT NULL REFERENCES game_competitions(id),
 owner_id UUID NOT NULL REFERENCES accounts(id),
 rules_hash VARCHAR(64) NOT NULL,
 joined_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(competition_id,owner_id)
);
CREATE TABLE game_competition_submissions (
 competition_id UUID NOT NULL,
 owner_id UUID NOT NULL,
 job_id UUID NOT NULL REFERENCES historical_submissions(job_id),
 entered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(competition_id,job_id),
 FOREIGN KEY(competition_id,owner_id) REFERENCES game_competition_participants(competition_id,owner_id)
);
CREATE TABLE game_competition_live_scores (
 competition_id UUID NOT NULL,
 installation_id UUID NOT NULL REFERENCES shared_installations(id),
 owner_id UUID NOT NULL,
 score_m3 NUMERIC(24,9) NOT NULL CHECK(score_m3<>'NaN'::numeric),
 evaluated_seconds INTEGER NOT NULL CHECK(evaluated_seconds>0),
 evaluated_through TIMESTAMPTZ NOT NULL,
 comparison_group_hash VARCHAR(64) NOT NULL,
 score_policy_sha256 VARCHAR(64) NOT NULL,
 source_job_id UUID NOT NULL REFERENCES shared_physics_jobs(id),
 PRIMARY KEY(competition_id,installation_id),
 FOREIGN KEY(competition_id,owner_id) REFERENCES game_competition_participants(competition_id,owner_id)
);
CREATE INDEX game_competition_live_owner ON game_competition_live_scores(competition_id,owner_id);
