package io.waterleague.weekly.repository;

import io.waterleague.weekly.view.WeeklyView;
import java.time.LocalDate;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class WeeklySettlementRepository {
  private final JdbcTemplate db;

  public WeeklySettlementRepository(JdbcTemplate db) {
    this.db = db;
  }

  public List<WeeklyView.ExcludedPeriod> exclusions(LocalDate week, boolean archive) {
    return db.query(
        """
        SELECT i.district_id,e.station_id,e.excluded_from,e.excluded_until,count(*) installations,
          SUM(EXTRACT(EPOCH FROM(e.excluded_until-GREATEST(e.excluded_from,
            CASE WHEN i.physics_policy='INSTALLATION_SECOND_V2' THEN i.installed_at
              ELSE date_trunc('minute',i.installed_at)+CASE
                WHEN i.installed_at=date_trunc('minute',i.installed_at) THEN interval '0 minutes'
                ELSE interval '1 minute' END END))))::bigint excluded_seconds
        FROM weekly_observation_exclusions e JOIN shared_installations i ON i.id=e.installation_id
        WHERE e.week_start=? AND i.competition_id IS NULL AND (? OR i.source_retired_at IS NULL)
          AND e.excluded_until=i.season_ends_at AND e.excluded_until<=CURRENT_TIMESTAMP
          AND (i.removed_at IS NULL OR i.removed_at>=e.excluded_until)
          AND e.excluded_from>=date_trunc('minute',i.installed_at)
          AND e.excluded_from>=?::date::timestamp AT TIME ZONE 'Asia/Seoul'
        GROUP BY i.district_id,e.station_id,e.excluded_from,e.excluded_until
        ORDER BY i.district_id,e.excluded_from
        """,
        (r, n) ->
            new WeeklyView.ExcludedPeriod(
                r.getString("district_id"),
                "",
                r.getString("station_id"),
                r.getTimestamp("excluded_from").toInstant(),
                r.getTimestamp("excluded_until").toInstant(),
                r.getLong("installations"),
                r.getLong("excluded_seconds")),
        java.sql.Date.valueOf(week),
        archive,
        java.sql.Date.valueOf(week));
  }
}
