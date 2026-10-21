ALTER TABLE shared_installations ADD COLUMN competition_id UUID REFERENCES game_competitions(id);
ALTER TABLE shared_installations DROP CONSTRAINT shared_member_site;
ALTER TABLE shared_installations ADD CONSTRAINT shared_member_site CHECK (
 (removed_at IS NULL AND occupied_site IS NOT NULL AND (
   occupied_site=owner_id::text || ':' || COALESCE(competition_id::text || ':','') || district_id || ':' || cell_id
   OR (competition_id IS NULL AND season_ends_at IS NULL AND occupied_site=district_id || ':' || cell_id)))
 OR (removed_at IS NOT NULL AND occupied_site IS NULL));
CREATE INDEX shared_competition_owner ON shared_installations(competition_id,owner_id);
ALTER TABLE historical_design_revisions ADD COLUMN competition_id UUID REFERENCES game_competitions(id);
ALTER TABLE historical_design_revisions DROP CONSTRAINT historical_design_revisions_pkey;
ALTER TABLE historical_design_revisions ADD COLUMN id UUID NOT NULL DEFAULT gen_random_uuid();
ALTER TABLE historical_design_revisions ADD PRIMARY KEY(id);
ALTER TABLE historical_design_revisions ADD CONSTRAINT historical_design_scope UNIQUE NULLS NOT DISTINCT(owner_id,event_id,source_dataset,competition_id,revision);
ALTER TABLE historical_experiments ADD COLUMN competition_id UUID REFERENCES game_competitions(id);
CREATE INDEX historical_competition_owner ON historical_experiments(competition_id,owner_id);
