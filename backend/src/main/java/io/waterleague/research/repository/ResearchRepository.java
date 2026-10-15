package io.waterleague.research.repository;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ResearchRepository {
  private final JdbcTemplate db;

  public ResearchRepository(JdbcTemplate d) {
    db = d;
  }

  public List<Map<String, Object>> organizations() {
    return db.query(
        "SELECT id,name FROM organizations WHERE approved=true ORDER BY name",
        (rs, n) -> Map.of("id", rs.getObject("id"), "name", rs.getString("name")));
  }

  public boolean approved(UUID id) {
    return db.queryForObject(
            "SELECT COUNT(*) FROM organizations WHERE id=? AND approved=true", Integer.class, id)
        > 0;
  }

  public void ownerLock(UUID owner) {
    db.queryForObject("SELECT id FROM accounts WHERE id=? FOR UPDATE", UUID.class, owner);
  }

  public void consent(UUID owner, UUID org, boolean value) {
    int n =
        db.update(
            "UPDATE research_consents SET granted=?,updated_at=? WHERE owner_id=? AND"
                + " organization_id=?",
            value,
            Timestamp.from(Instant.now()),
            owner,
            org);
    if (n == 0)
      db.update(
          "INSERT INTO research_consents(owner_id,organization_id,granted,updated_at)"
              + " VALUES(?,?,?,?)",
          owner,
          org,
          value,
          Timestamp.from(Instant.now()));
  }

  public List<Map<String, Object>> consents(UUID owner) {
    return db.query(
        "SELECT o.id,o.name,COALESCE(c.granted,false) granted FROM organizations o LEFT JOIN"
            + " research_consents c ON c.organization_id=o.id AND c.owner_id=? WHERE"
            + " o.approved=true ORDER BY o.name",
        (rs, n) ->
            Map.of(
                "organizationId",
                rs.getObject("id"),
                "name",
                rs.getString("name"),
                "granted",
                rs.getBoolean("granted")),
        owner);
  }

  public boolean allowed(UUID job, UUID org) {
    return db.queryForObject(
            "SELECT COUNT(*) FROM submissions s JOIN research_consents c ON c.owner_id=s.owner_id"
                + " AND c.organization_id=? AND c.granted=true JOIN organizations o ON"
                + " o.id=c.organization_id AND o.approved=true WHERE s.job_id=?",
            Integer.class,
            org,
            job)
        > 0;
  }

  public List<Map<String, Object>> list(UUID org, String hash) {
    return db.query(
        "SELECT s.job_id,s.score,s.cost,v.design_note,v.revision,s.created_at FROM submissions s"
            + " JOIN research_consents c ON c.owner_id=s.owner_id AND c.organization_id=? AND"
            + " c.granted=true JOIN simulation_jobs j ON j.id=s.job_id JOIN strategy_versions v ON"
            + " v.id=j.version_id WHERE s.model_hash=? ORDER BY s.score DESC,s.created_at LIMIT"
            + " 100",
        (rs, n) ->
            Map.of(
                "jobId",
                rs.getObject("job_id"),
                "score",
                rs.getBigDecimal("score"),
                "cost",
                rs.getBigDecimal("cost"),
                "designNote",
                rs.getString("design_note"),
                "revision",
                rs.getInt("revision"),
                "submittedAt",
                rs.getTimestamp("created_at").toInstant()),
        org,
        hash);
  }

  public void audit(UUID actor, String action, UUID object) {
    db.update(
        "INSERT INTO audit_events(id,actor_id,action,object_id,created_at) VALUES(?,?,?,?,?)",
        UUID.randomUUID(),
        actor,
        action,
        object,
        Timestamp.from(Instant.now()));
  }
}
