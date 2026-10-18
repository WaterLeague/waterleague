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

  public java.util.List<io.waterleague.weekly.view.SiteScorePage.InstallationScore> siteScores(
      String district, String cell, LocalDate week, UUID after) {
    return db.query(
        """
        SELECT i.id,i.owner_id,a.display_name,i.facility_type,i.area_m2,i.installed_at,i.season_ends_at,s.score_m3,COALESCE(s.evaluated_seconds,s.evaluated_minutes*60,0) evaluated_seconds,s.evaluated_through
        FROM shared_installations i JOIN accounts a ON a.id=i.owner_id
        LEFT JOIN shared_weekly_scores s ON s.installation_id=i.id AND s.week_start=?
        WHERE i.district_id=? AND i.cell_id=? AND i.removed_at IS NULL
          AND (i.season_ends_at IS NULL OR i.season_ends_at>CURRENT_TIMESTAMP) AND i.id>?
        ORDER BY i.id LIMIT 51
        """,
        (r, n) ->
            new io.waterleague.weekly.view.SiteScorePage.InstallationScore(
                r.getObject("id", UUID.class),
                r.getObject("owner_id", UUID.class),
                r.getString("display_name"),
                r.getString("facility_type"),
                r.getBigDecimal("area_m2"),
                r.getTimestamp("installed_at").toInstant(),
                r.getTimestamp("season_ends_at") == null
                    ? null
                    : r.getTimestamp("season_ends_at").toInstant(),
                r.getBigDecimal("score_m3"),
                r.getLong("evaluated_seconds"),
                r.getTimestamp("evaluated_through") == null
                    ? null
                    : r.getTimestamp("evaluated_through").toInstant()),
        java.sql.Date.valueOf(week),
        district,
        cell,
        after);
  }

  public List<WeeklyContribution> contributions(LocalDate week, Instant start, Instant through) {
    return db.query(
        """
        WITH periods AS (
          SELECT i.*,GREATEST(CASE WHEN i.physics_policy='INSTALLATION_SECOND_V2' THEN i.installed_at
            ELSE date_trunc('minute',i.installed_at)+CASE
              WHEN i.installed_at=date_trunc('minute',i.installed_at) THEN interval '0 minutes'
              ELSE interval '1 minute' END END,?::timestamptz) AS begins,
            LEAST(date_trunc('minute',COALESCE(i.removed_at,i.season_ends_at,?::timestamptz)),?::timestamptz) AS ends
          FROM shared_installations i WHERE i.installed_at<?::timestamptz
            AND (COALESCE(i.removed_at,i.season_ends_at) IS NULL OR COALESCE(i.removed_at,i.season_ends_at)>?::timestamptz)
        )
        SELECT p.owner_id,a.display_name,p.district_id,COALESCE(SUM(s.score_m3),0) AS score,
          COALESCE(SUM(COALESCE(s.evaluated_seconds,s.evaluated_minutes*60)),0) AS evaluated,
          SUM(EXTRACT(EPOCH FROM (p.ends-p.begins)))::bigint AS expected,
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
