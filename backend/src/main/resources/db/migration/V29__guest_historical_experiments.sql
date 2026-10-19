ALTER TABLE historical_experiments ALTER COLUMN owner_id DROP NOT NULL;
ALTER TABLE historical_experiments ADD COLUMN guest_key VARCHAR(64);
ALTER TABLE historical_experiments ADD CONSTRAINT historical_actor_exclusive
 CHECK ((owner_id IS NOT NULL AND guest_key IS NULL) OR (owner_id IS NULL AND guest_key IS NOT NULL));
CREATE UNIQUE INDEX historical_guest_request ON historical_experiments(guest_key,request_key);
CREATE INDEX historical_guest_time ON historical_experiments(guest_key,created_at DESC);
