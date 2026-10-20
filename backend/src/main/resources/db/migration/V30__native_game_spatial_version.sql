ALTER TABLE accounts DROP CONSTRAINT account_district;
UPDATE accounts a SET district_id=m.current_id FROM (VALUES
 ('2410520','11680'),
 ('2419944','11740'),
 ('2419943','11305'),
 ('2414775','11500'),
 ('2414778','11620'),
 ('2419945','11215'),
 ('2414777','11530'),
 ('2414776','11545'),
 ('2419950','11350'),
 ('2419940','11320'),
 ('2419941','11230'),
 ('2414774','11590'),
 ('2419949','11440'),
 ('2419951','11410'),
 ('2414779','11650'),
 ('2419953','11200'),
 ('2419952','11290'),
 ('2419954','11710'),
 ('2414780','11470'),
 ('2414781','11560'),
 ('2419955','11170'),
 ('2419942','11380'),
 ('2419946','11110'),
 ('2419947','11140'),
 ('2419948','11260')) AS m(previous_id,current_id) WHERE a.district_id=m.previous_id;
ALTER TABLE accounts ADD CONSTRAINT account_district CHECK(district_id IS NULL OR district_id IN ('11110','11140','11170','11200','11215','11230','11260','11290','11305','11320','11350','11380','11410','11440','11470','11500','11530','11545','11560','11590','11620','11650','11680','11710','11740'));

ALTER TABLE shared_installations ALTER COLUMN cell_id TYPE VARCHAR(64);
ALTER TABLE shared_installations ALTER COLUMN occupied_site TYPE VARCHAR(128);
ALTER TABLE shared_installations ADD COLUMN source_retired_at TIMESTAMP WITH TIME ZONE;
UPDATE shared_installations SET source_retired_at=GREATEST(installed_at,CURRENT_TIMESTAMP)
 WHERE removed_at IS NULL AND model_hash<>'4ec7535e7cbaf41dc73f73519d77ba11f956f4c75c1a574fffa08f16625919b7';
ALTER TABLE shared_installations ADD CONSTRAINT shared_source_retirement CHECK(source_retired_at IS NULL OR source_retired_at>=installed_at);
CREATE INDEX shared_source_retirement_pending ON shared_installations(source_retired_at,owner_id) WHERE removed_at IS NULL;

ALTER TABLE historical_design_revisions ADD COLUMN source_dataset VARCHAR(64) NOT NULL DEFAULT 'PRE_NATIVE_20261020';
ALTER TABLE historical_design_revisions ALTER COLUMN source_dataset SET DEFAULT 'SEOUL_NGII_GAME_V2';
ALTER TABLE historical_design_revisions DROP CONSTRAINT historical_design_revisions_pkey;
ALTER TABLE historical_design_revisions ADD PRIMARY KEY(owner_id,event_id,source_dataset,revision);
ALTER TABLE historical_experiments ADD COLUMN source_dataset VARCHAR(64) NOT NULL DEFAULT 'PRE_NATIVE_20261020';
ALTER TABLE historical_experiments ALTER COLUMN source_dataset SET DEFAULT 'SEOUL_NGII_GAME_V2';
ALTER TABLE cistern_map_plans ADD COLUMN source_dataset VARCHAR(64) NOT NULL DEFAULT 'PRE_NATIVE_20261020';
ALTER TABLE cistern_map_plans ALTER COLUMN source_dataset SET DEFAULT 'SEOUL_NGII_GAME_V2';

-- 이전 공간의 대기·실행 작업은 원문을 보존하고 현재 워커의 재시도를 차단한다.
UPDATE historical_experiments SET state='REJECTED',error_code='SPATIAL_SOURCE_RETIRED',finished_at=clock_timestamp(),lease_until=NULL
 WHERE source_dataset='PRE_NATIVE_20261020' AND state IN ('QUEUED','RUNNING');
UPDATE shared_physics_jobs j SET state='FAILED',error_code='SPATIAL_SOURCE_RETIRED',finished_at=clock_timestamp(),lease_until=NULL
 FROM shared_installations i WHERE j.installation_id=i.id AND i.source_retired_at IS NOT NULL AND j.state='RUNNING';
UPDATE simulation_jobs SET state='REJECTED',error_code='SPATIAL_SOURCE_RETIRED',finished_at=clock_timestamp(),lease_until=NULL
 WHERE state IN ('QUEUED','RUNNING') AND model_hash NOT IN ('c55a68302a99b815a25c7f403a38fa7e395f6635037c6abbaa6a2a6436a6c684','0bd06d394f6dd0d36b0e98fc1f32ea7b2bc00597b0c0aaa944d097733f9de0b2','53955844bce2e3717530d8605cb59f386b67e2b4dc6c47bbd53cc4c25d0e9009','618cc8cc889c36953891e8e62ff42e1702f675dcfa1fd2b7218873cca005d2fa');
UPDATE research_candidates SET state='REJECTED',error_code='SPATIAL_SOURCE_RETIRED',finished_at=clock_timestamp(),lease_until=NULL
 WHERE state IN ('QUEUED','RUNNING') AND model_hash NOT IN ('c55a68302a99b815a25c7f403a38fa7e395f6635037c6abbaa6a2a6436a6c684','0bd06d394f6dd0d36b0e98fc1f32ea7b2bc00597b0c0aaa944d097733f9de0b2','53955844bce2e3717530d8605cb59f386b67e2b4dc6c47bbd53cc4c25d0e9009','618cc8cc889c36953891e8e62ff42e1702f675dcfa1fd2b7218873cca005d2fa');
