package io.waterleague.sharedresearch.repository;

import io.waterleague.sharedresearch.entity.SharedResearchJob;
import io.waterleague.sharedresearch.view.SharedResearchEntry;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDate;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class SharedResearchRepository {
  private final JdbcTemplate db;

  public SharedResearchRepository(JdbcTemplate db) {
    this.db = db;
  }

  public List<Map<String, Object>> consents(UUID owner) {
    return db.query(
        "SELECT o.id,o.name,COALESCE(c.granted,false) granted FROM organizations o LEFT JOIN"
            + " shared_research_consents c ON c.organization_id=o.id AND c.owner_id=? WHERE"
            + " o.approved=true ORDER BY o.name",
        (r, n) ->
            Map.of(
                "organizationId",
                r.getObject("id", UUID.class),
                "name",
                r.getString("name"),
                "granted",
                r.getBoolean("granted")),
        owner);
  }

  public void consent(UUID owner, UUID org, boolean value) {
    var at = Timestamp.from(Instant.now());
    if (db.update(
            "UPDATE shared_research_consents SET granted=?,updated_at=? WHERE owner_id=? AND"
                + " organization_id=?",
            value,
            at,
            owner,
            org)
        == 0)
      db.update(
          "INSERT INTO shared_research_consents(owner_id,organization_id,granted,updated_at)"
              + " VALUES(?,?,?,?)",
          owner,
          org,
          value,
          at);
  }

  public boolean allowed(UUID owner, UUID org) {
    return db.queryForObject(
            "SELECT COUNT(*) FROM shared_research_consents c JOIN accounts a ON a.id=c.owner_id AND"
                + " a.enabled=true AND a.approval_status='APPROVED' JOIN organizations o ON"
                + " o.id=c.organization_id AND o.approved=true WHERE c.owner_id=? AND"
                + " c.organization_id=? AND c.granted=true",
            Integer.class,
            owner,
            org)
        > 0;
  }

  public List<SharedResearchEntry> list(UUID viewer, UUID org, LocalDate week) {
    String scope =
        org == null
            ? "i.owner_id=?"
            : "EXISTS(SELECT 1 FROM shared_research_consents c WHERE c.owner_id=i.owner_id AND"
                + " c.organization_id=? AND c.granted=true)";
    return db.query(
        """
        SELECT j.id job_id,i.id installation_id,i.district_id,a.display_name,i.facility_type,i.area_m2,i.cost,
          i.installed_at,i.removed_at,s.score_m3,SUM(s.score_m3) OVER(PARTITION BY i.owner_id) player_score,
          s.evaluated_minutes,s.evaluated_through,j.artifact_manifest_hash
        FROM shared_weekly_scores s JOIN shared_installations i ON i.id=s.installation_id
        JOIN accounts a ON a.id=i.owner_id AND a.enabled=true AND a.approval_status='APPROVED'
        JOIN shared_physics_jobs j ON j.id=s.source_job_id AND j.installation_id=i.id AND j.state='SUCCEEDED'
        WHERE s.week_start=? AND
        """
            + scope
            + " ORDER BY player_score DESC,s.score_m3 DESC,i.installed_at,i.id LIMIT 100",
        (r, n) ->
            new SharedResearchEntry(
                r.getObject("job_id", UUID.class),
                r.getObject("installation_id", UUID.class),
                r.getString("district_id"),
                r.getString("display_name"),
                r.getString("facility_type"),
                r.getBigDecimal("area_m2"),
                r.getBigDecimal("cost"),
                r.getTimestamp("installed_at").toInstant(),
                r.getTimestamp("removed_at") == null
                    ? null
                    : r.getTimestamp("removed_at").toInstant(),
                r.getBigDecimal("score_m3"),
                r.getBigDecimal("player_score"),
                r.getInt("evaluated_minutes"),
                r.getTimestamp("evaluated_through").toInstant(),
                r.getString("artifact_manifest_hash") != null),
        java.sql.Date.valueOf(week),
        org == null ? viewer : org);
  }

  public Optional<SharedResearchJob> find(UUID id) {
    return db
        .query(
            "SELECT"
                + " j.*,i.owner_id,i.district_id,i.cell_id,i.model_hash,i.facility_type,i.area_m2,i.cost,i.installed_at,i.removed_at,a.display_name"
                + " FROM shared_physics_jobs j JOIN shared_installations i ON"
                + " i.id=j.installation_id JOIN accounts a ON a.id=i.owner_id WHERE j.id=? AND"
                + " j.state='SUCCEEDED'",
            (r, n) ->
                new SharedResearchJob(
                    r.getObject("id", UUID.class),
                    r.getObject("lease_token", UUID.class),
                    r.getObject("owner_id", UUID.class),
                    r.getObject("installation_id", UUID.class),
                    r.getString("district_id"),
                    r.getString("cell_id"),
                    r.getString("model_hash"),
                    r.getString("facility_type"),
                    r.getBigDecimal("area_m2"),
                    r.getBigDecimal("cost"),
                    r.getString("display_name"),
                    r.getTimestamp("installed_at").toInstant(),
                    r.getTimestamp("removed_at") == null
                        ? null
                        : r.getTimestamp("removed_at").toInstant(),
                    r.getTimestamp("simulation_start").toInstant(),
                    r.getTimestamp("requested_through").toInstant(),
                    r.getString("input_hash"),
                    r.getString("artifact_manifest_hash"),
                    r.getString("result")),
            id)
        .stream()
        .findFirst();
  }
}
