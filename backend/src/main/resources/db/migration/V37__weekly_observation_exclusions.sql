CREATE TABLE weekly_observation_exclusions (
 id UUID PRIMARY KEY,
 installation_id UUID NOT NULL REFERENCES shared_installations(id) ON DELETE CASCADE,
 week_start DATE NOT NULL CHECK(EXTRACT(ISODOW FROM week_start)=1),
 excluded_from TIMESTAMPTZ NOT NULL,
 excluded_until TIMESTAMPTZ NOT NULL,
 station_id VARCHAR(5) NOT NULL CHECK(station_id ~ '^[0-9]{1,5}$'),
 evidence_sha256 VARCHAR(64) NOT NULL CHECK(evidence_sha256 ~ '^[a-f0-9]{64}$'),
 evidence JSONB NOT NULL CHECK(jsonb_typeof(evidence)='object'),
 rule_version VARCHAR(48) NOT NULL CHECK(rule_version='CLOSED_WEEK_MISSING_SUFFIX_V1'),
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(installation_id,week_start),
 CHECK(excluded_from<excluded_until),
 CHECK(excluded_from>=week_start::timestamp AT TIME ZONE 'Asia/Seoul'),
 CHECK(excluded_until=(week_start+7)::timestamp AT TIME ZONE 'Asia/Seoul'),
 CHECK(created_at>=excluded_until+interval '2 hours')
);
CREATE INDEX weekly_exclusion_week ON weekly_observation_exclusions(week_start);
