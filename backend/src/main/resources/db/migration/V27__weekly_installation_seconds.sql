ALTER TABLE shared_installations ADD COLUMN physics_policy VARCHAR(48) NOT NULL DEFAULT 'FULL_MINUTE_V1';
ALTER TABLE shared_installations ADD CONSTRAINT installation_physics_policy_check
 CHECK(physics_policy IN ('FULL_MINUTE_V1','INSTALLATION_SECOND_V2'));
ALTER TABLE shared_installations ADD CONSTRAINT installation_second_boundary_check
 CHECK(physics_policy='FULL_MINUTE_V1' OR
       (installed_at=date_trunc('second',installed_at) AND season_ends_at IS NOT NULL));
ALTER TABLE shared_weekly_scores ADD COLUMN evaluated_seconds INTEGER;
ALTER TABLE shared_weekly_scores DROP CONSTRAINT shared_weekly_scores_rule_version_check;
ALTER TABLE shared_weekly_scores ADD CONSTRAINT weekly_seconds_rule_check CHECK(
 (rule_version='OBSERVED_ACCOUNTED_VOLUME_V1' AND evaluated_seconds IS NULL) OR
 (rule_version='OBSERVED_ACCOUNTED_VOLUME_SECONDS_V2' AND evaluated_seconds BETWEEN 1 AND 604800
  AND evaluated_seconds IS NOT NULL AND evaluated_minutes=(evaluated_seconds+59)/60));
