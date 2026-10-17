CREATE TABLE shared_weekly_scores (
 installation_id UUID NOT NULL REFERENCES shared_installations(id),
 week_start DATE NOT NULL CHECK(EXTRACT(ISODOW FROM week_start)=1),
 score_m3 NUMERIC(24,9) NOT NULL CHECK(score_m3<>'NaN'::numeric),
 evaluated_minutes INTEGER NOT NULL CHECK(evaluated_minutes BETWEEN 1 AND 10080),
 evaluated_through TIMESTAMP WITH TIME ZONE NOT NULL,
 source_job_id UUID NOT NULL REFERENCES shared_physics_jobs(id),
 rule_version VARCHAR(48) NOT NULL CHECK(rule_version='OBSERVED_ACCOUNTED_VOLUME_V1'),
 PRIMARY KEY(installation_id,week_start),
 CHECK(evaluated_through>week_start::timestamp AT TIME ZONE 'Asia/Seoul'),
 CHECK(evaluated_through<=(week_start+7)::timestamp AT TIME ZONE 'Asia/Seoul')
);
CREATE INDEX shared_weekly_period ON shared_weekly_scores(week_start);
