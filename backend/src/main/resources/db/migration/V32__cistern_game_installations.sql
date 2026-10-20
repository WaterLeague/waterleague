ALTER TABLE shared_installations DROP CONSTRAINT shared_installations_facility_type_check;
ALTER TABLE shared_installations ADD CONSTRAINT shared_installations_facility_type_check
 CHECK(facility_type IN ('RAIN_GARDEN','PERMEABLE_PAVEMENT','GREEN_ROOF','BIORETENTION','VEGETATIVE_SWALE','INFILTRATION_TRENCH','RAINWATER_CISTERN'));
