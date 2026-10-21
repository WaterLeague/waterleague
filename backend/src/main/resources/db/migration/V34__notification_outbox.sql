CREATE TABLE notification_outbox (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 event_type VARCHAR(32) NOT NULL CHECK(event_type IN ('MEMBER_REGISTERED','WEEKLY_INSTALLED','DISASTER_SUBMITTED')),
 source_id UUID NOT NULL,
 payload JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 8),
 lease_token UUID,
 delivered_at TIMESTAMPTZ,
 failed_at TIMESTAMPTZ,
 last_status VARCHAR(32),
 UNIQUE(event_type,source_id)
);
CREATE INDEX notification_outbox_pending ON notification_outbox(available_at,created_at)
 WHERE delivered_at IS NULL AND failed_at IS NULL;

-- 업무 저장과 알림 기록을 같은 트랜잭션에 묶어 롤백·중복 요청의 오발송을 막는다.
CREATE FUNCTION enqueue_activity_notification() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
 actor accounts%ROWTYPE;
 event_kind TEXT;
 source UUID;
 detail JSONB;
BEGIN
 IF TG_TABLE_NAME='accounts' THEN
  IF NEW.role<>'MEMBER' THEN RETURN NEW; END IF;
  actor := NEW;
  event_kind := 'MEMBER_REGISTERED';
  source := NEW.id;
  detail := jsonb_build_object('approvalStatus',NEW.approval_status);
 ELSIF TG_TABLE_NAME='shared_installations' THEN
  SELECT * INTO STRICT actor FROM accounts WHERE id=NEW.owner_id;
  event_kind := 'WEEKLY_INSTALLED';
  source := NEW.id;
  detail := jsonb_build_object('districtId',NEW.district_id,'facilityType',NEW.facility_type,
    'areaM2',NEW.area_m2,'installedAt',NEW.installed_at);
 ELSE
  SELECT a.* INTO STRICT actor FROM accounts a
    JOIN historical_experiments h ON h.owner_id=a.id WHERE h.id=NEW.job_id;
  event_kind := 'DISASTER_SUBMITTED';
  source := NEW.job_id;
  detail := jsonb_build_object('eventId',NEW.event_id);
 END IF;
 INSERT INTO notification_outbox(event_type,source_id,payload)
 VALUES(event_kind,source,jsonb_build_object('userId',actor.id,'username',actor.username,
   'displayName',actor.display_name,'memberType',actor.member_type,'districtId',actor.district_id) || detail)
 ON CONFLICT(event_type,source_id) DO NOTHING;
 RETURN NEW;
END;
$$;
CREATE TRIGGER notify_member_registered AFTER INSERT ON accounts
 FOR EACH ROW EXECUTE FUNCTION enqueue_activity_notification();
CREATE TRIGGER notify_weekly_installed AFTER INSERT ON shared_installations
 FOR EACH ROW EXECUTE FUNCTION enqueue_activity_notification();
CREATE TRIGGER notify_disaster_submitted AFTER INSERT ON historical_submissions
 FOR EACH ROW EXECUTE FUNCTION enqueue_activity_notification();
