package io.waterleague.notification.repository;

import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class NotificationRepository {
  public record Delivery(
      UUID id, String type, UUID source, String payload, int attempts, UUID lease) {}

  private final JdbcTemplate db;

  public NotificationRepository(JdbcTemplate db) {
    this.db = db;
  }

  public void location(UUID installationId, String name, String address, String districtName) {
    db.update(
        """
        UPDATE notification_outbox SET payload=payload || jsonb_build_object(
          'siteName',?::text,'siteAddress',?::text,'districtName',?::text)
        WHERE event_type='WEEKLY_INSTALLED' AND source_id=? AND delivered_at IS NULL
        """,
        name,
        address == null || address.isBlank() ? "공개자료에 주소 없음" : address,
        districtName,
        installationId);
  }

  public Optional<Delivery> claim() {
    return db
        .query(
            """
            WITH candidate AS (
              SELECT id FROM notification_outbox
              WHERE delivered_at IS NULL AND failed_at IS NULL AND attempts<8
                AND available_at<=CURRENT_TIMESTAMP
              ORDER BY available_at,created_at FOR UPDATE SKIP LOCKED LIMIT 1
            )
            UPDATE notification_outbox n SET attempts=attempts+1,lease_token=?,
              available_at=CURRENT_TIMESTAMP+INTERVAL '2 minutes'
            FROM candidate c WHERE n.id=c.id
            RETURNING n.id,event_type,source_id,payload::text,attempts,lease_token
            """,
            (r, n) ->
                new Delivery(
                    r.getObject("id", UUID.class),
                    r.getString("event_type"),
                    r.getObject("source_id", UUID.class),
                    r.getString("payload"),
                    r.getInt("attempts"),
                    r.getObject("lease_token", UUID.class)),
            UUID.randomUUID())
        .stream()
        .findFirst();
  }

  public void finish(Delivery d, boolean success, boolean terminal, long delay, String status) {
    db.update(
        """
        UPDATE notification_outbox SET delivered_at=CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END,
          failed_at=CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END,
          available_at=CURRENT_TIMESTAMP+(? * INTERVAL '1 second'),last_status=?,lease_token=NULL
        WHERE id=? AND lease_token=?
        """,
        success,
        !success && (terminal || d.attempts() >= 8),
        delay,
        status,
        d.id(),
        d.lease());
  }

  public void cleanup() {
    db.update(
        """
        UPDATE notification_outbox SET failed_at=CURRENT_TIMESTAMP,last_status='ATTEMPTS_EXHAUSTED'
        WHERE attempts>=8 AND delivered_at IS NULL AND failed_at IS NULL AND available_at<CURRENT_TIMESTAMP
        """);
    db.update(
        """
        DELETE FROM notification_outbox WHERE delivered_at<CURRENT_TIMESTAMP-INTERVAL '7 days'
          OR created_at<CURRENT_TIMESTAMP-INTERVAL '30 days'
        """);
  }
}
