ALTER TABLE accounts ADD COLUMN district_id VARCHAR(20);
ALTER TABLE accounts ADD COLUMN affiliation_type VARCHAR(20);
ALTER TABLE accounts ADD CONSTRAINT account_district CHECK(district_id IS NULL OR district_id IN ('2410520','2419944','2419943','2414775','2414778','2419945','2414777','2414776','2419950','2419940','2419941','2414774','2419949','2419951','2414779','2419953','2419952','2419954','2414780','2414781','2419955','2419942','2419946','2419947','2419948'));
ALTER TABLE accounts ADD CONSTRAINT account_affiliation CHECK((district_id IS NULL AND affiliation_type IS NULL) OR (district_id IS NOT NULL AND affiliation_type IS NOT NULL AND affiliation_type IN ('RESIDENT','AFFILIATED')));
CREATE TABLE shared_installations (
 id UUID PRIMARY KEY,
 occupied_site VARCHAR(64) UNIQUE,
 district_id VARCHAR(20) NOT NULL,
 cell_id VARCHAR(20) NOT NULL,
 owner_id UUID NOT NULL REFERENCES accounts(id),
 model_hash VARCHAR(64) NOT NULL,
 facility_type VARCHAR(30) NOT NULL CHECK(facility_type IN ('RAIN_GARDEN','PERMEABLE_PAVEMENT','GREEN_ROOF')),
 area_m2 NUMERIC(14,2) NOT NULL CHECK(area_m2>0),
 cost NUMERIC(14,2) NOT NULL CHECK(cost>0),
 installed_at TIMESTAMP WITH TIME ZONE NOT NULL,
 removed_at TIMESTAMP WITH TIME ZONE,
 CHECK((removed_at IS NULL AND occupied_site=district_id || ':' || cell_id AND occupied_site IS NOT NULL) OR (removed_at IS NOT NULL AND occupied_site IS NULL)),
 CHECK(removed_at IS NULL OR removed_at>=installed_at)
);
CREATE INDEX shared_installations_district ON shared_installations(district_id,removed_at);
CREATE INDEX shared_installations_owner ON shared_installations(owner_id,removed_at);
