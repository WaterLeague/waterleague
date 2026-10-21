package io.waterleague.administration.repository;

import java.sql.Timestamp;
import java.time.*;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ResultsRepository {
  private final JdbcTemplate db;

  public ResultsRepository(JdbcTemplate db) {
    this.db = db;
  }

  public List<LocalDate> seasons() {
    return db.query(
        "SELECT week FROM (SELECT week_start week FROM shared_weekly_scores UNION SELECT"
            + " date_trunc('week',installed_at AT TIME ZONE 'Asia/Seoul')::date FROM"
            + " shared_installations UNION SELECT date_trunc('week',CURRENT_TIMESTAMP AT TIME ZONE"
            + " 'Asia/Seoul')::date) seasons ORDER BY week DESC",
        (r, n) -> r.getDate(1).toLocalDate());
  }

  public List<Map<String, Object>> installations(LocalDate week, List<UUID> owners) {
    if (owners.isEmpty()) return List.of();
    var args = new ArrayList<Object>();
    args.add(java.sql.Date.valueOf(week));
    args.addAll(owners);
    args.add(Timestamp.from(week.plusWeeks(1).atStartOfDay(ZoneId.of("Asia/Seoul")).toInstant()));
    args.add(Timestamp.from(week.atStartOfDay(ZoneId.of("Asia/Seoul")).toInstant()));
    return db.query(
        "SELECT i.*,s.score_m3 FROM shared_installations i LEFT JOIN shared_weekly_scores s ON"
            + " s.installation_id=i.id AND s.week_start=? WHERE i.owner_id IN ("
            + String.join(",", Collections.nCopies(owners.size(), "?"))
            + ") AND i.installed_at<? AND"
            + " COALESCE(i.removed_at,i.season_ends_at,'infinity'::timestamptz)>? ORDER BY"
            + " i.installed_at,i.id",
        (r, n) -> {
          var v = new LinkedHashMap<String, Object>();
          v.put("id", r.getObject("id", UUID.class));
          v.put("playerId", r.getObject("owner_id", UUID.class));
          v.put("districtId", r.getString("district_id"));
          v.put("facilityType", r.getString("facility_type"));
          v.put("areaM2", r.getBigDecimal("area_m2"));
          v.put("installedAt", r.getTimestamp("installed_at").toInstant());
          v.put(
              "scoreM3Exact",
              r.getBigDecimal("score_m3") == null
                  ? null
                  : r.getBigDecimal("score_m3").toPlainString());
          return v;
        },
        args.toArray());
  }
}
