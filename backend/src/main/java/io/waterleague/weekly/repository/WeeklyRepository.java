package io.waterleague.weekly.repository;

import io.waterleague.weekly.entity.WeeklyContribution;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class WeeklyRepository {
  private final JdbcTemplate db;

  public WeeklyRepository(JdbcTemplate db) {
    this.db = db;
  }

  public Instant now() {
    return db.queryForObject("SELECT CURRENT_TIMESTAMP", Timestamp.class).toInstant();
  }

  public List<WeeklyContribution> contributions(LocalDate week, Instant start, Instant through) {
    return db.query(
        """
        WITH periods AS (
          SELECT i.*,GREATEST(date_trunc('minute',i.installed_at)+CASE
            WHEN i.installed_at=date_trunc('minute',i.installed_at) THEN interval '0 minutes'
            ELSE interval '1 minute' END,?::timestamptz) AS begins,
            LEAST(date_trunc('minute',COALESCE(i.removed_at,?::timestamptz)),?::timestamptz) AS ends
          FROM shared_installations i WHERE i.installed_at<?::timestamptz
            AND (i.removed_at IS NULL OR i.removed_at>?::timestamptz)
        )
        SELECT p.owner_id,a.display_name,p.district_id,COALESCE(SUM(s.score_m3),0) AS score,
          COALESCE(SUM(s.evaluated_minutes),0) AS evaluated,
          SUM(EXTRACT(EPOCH FROM (p.ends-p.begins))/60)::bigint AS expected,
          MIN(s.evaluated_through) AS through
        FROM periods p JOIN accounts a ON a.id=p.owner_id
        LEFT JOIN shared_weekly_scores s ON s.installation_id=p.id AND s.week_start=?
        WHERE p.ends>p.begins GROUP BY p.owner_id,a.display_name,p.district_id
        """,
        (r, n) ->
            new WeeklyContribution(
                r.getObject("owner_id", UUID.class),
                r.getString("display_name"),
                r.getString("district_id"),
                r.getBigDecimal("score"),
                r.getLong("evaluated"),
                r.getLong("expected"),
                r.getTimestamp("through") == null ? null : r.getTimestamp("through").toInstant()),
        Timestamp.from(start),
        Timestamp.from(through),
        Timestamp.from(through),
        Timestamp.from(through),
        Timestamp.from(start),
        java.sql.Date.valueOf(week));
  }
}
