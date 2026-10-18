CREATE TABLE historical_submissions (
 job_id UUID PRIMARY KEY REFERENCES historical_experiments(id) ON DELETE CASCADE,
 event_id VARCHAR(32) NOT NULL,
 rules_hash VARCHAR(64) NOT NULL,
 request_raw TEXT NOT NULL,
 cost NUMERIC(18,2) NOT NULL CHECK(cost >= 0),
 difference_m3 NUMERIC(38,18)
);
CREATE INDEX historical_submission_event ON historical_submissions(event_id,rules_hash);
