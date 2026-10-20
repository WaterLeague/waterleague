ALTER TABLE shared_weekly_scores
 ADD COLUMN score_policy_sha256 VARCHAR(64),
 ADD COLUMN comparison_group_hash VARCHAR(64),
 ADD CONSTRAINT shared_weekly_score_context_pair CHECK(
  (score_policy_sha256 IS NULL AND comparison_group_hash IS NULL) OR
  (score_policy_sha256 IS NOT NULL AND comparison_group_hash IS NOT NULL
   AND score_policy_sha256 ~ '^[a-f0-9]{64}$' AND comparison_group_hash ~ '^[a-f0-9]{64}$'));
ALTER TABLE historical_submissions
 ADD COLUMN score_policy_sha256 VARCHAR(64),
 ADD COLUMN comparison_group_hash VARCHAR(64),
 ADD CONSTRAINT historical_submission_score_context_pair CHECK(
  (score_policy_sha256 IS NULL AND comparison_group_hash IS NULL) OR
  (score_policy_sha256 IS NOT NULL AND comparison_group_hash IS NOT NULL
   AND score_policy_sha256 ~ '^[a-f0-9]{64}$' AND comparison_group_hash ~ '^[a-f0-9]{64}$'));
CREATE INDEX historical_submission_comparison_group
 ON historical_submissions(event_id,rules_hash,comparison_group_hash);
