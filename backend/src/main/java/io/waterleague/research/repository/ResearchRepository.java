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
            "SELECT COUNT(*) FROM simulation_jobs j JOIN accounts a ON a.id=j.owner_id AND"
                + " a.enabled=true AND a.approval_status='APPROVED' JOIN research_consents c ON"
                + " c.owner_id=j.owner_id AND c.organization_id=? AND c.granted=true JOIN"
                + " organizations o ON o.id=c.organization_id AND o.approved=true WHERE j.id=? AND"
                + " (EXISTS(SELECT 1 FROM submissions s WHERE s.job_id=j.id) OR EXISTS(SELECT 1"
                + " FROM league_submissions ls JOIN leagues l ON l.id=ls.league_id WHERE"
                + " ls.job_id=j.id AND l.organization_id=c.organization_id))",
            Integer.class,
            org,
            job)
        > 0;
  }

  public List<Map<String, Object>> list(UUID org, String hash) {
    return db.query(
        "SELECT job_id,score,cost,design_note,revision,created_at FROM (SELECT"
            + " s.*,v.design_note,v.revision,ROW_NUMBER() OVER(PARTITION BY s.job_id ORDER BY"
            + " s.created_at) choice FROM (SELECT job_id,owner_id,model_hash,score,cost,created_at"
            + " FROM submissions UNION ALL SELECT"
            + " ls.job_id,ls.owner_id,j.model_hash,ls.score,ls.cost,ls.created_at FROM"
            + " league_submissions ls JOIN leagues l ON l.id=ls.league_id AND l.organization_id=?"
            + " JOIN simulation_jobs j ON j.id=ls.job_id) s JOIN research_consents c ON"
            + " c.owner_id=s.owner_id AND c.organization_id=? AND c.granted=true JOIN accounts a ON"
            + " a.id=s.owner_id AND a.enabled=true AND a.approval_status='APPROVED' JOIN"
            + " simulation_jobs j ON j.id=s.job_id JOIN strategy_versions v ON v.id=j.version_id"
            + " WHERE s.model_hash=?) ranked WHERE choice=1 ORDER BY score DESC,created_at LIMIT"
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
        org,
        hash);
  }

  public List<Map<String, Object>> leagueContexts(UUID job) {
    return db.query(
        "SELECT l.id,l.title,l.rules,l.rules_hash,l.state,l.cancellation_reason FROM leagues l JOIN"
            + " league_submissions s ON s.league_id=l.id WHERE s.job_id=? ORDER BY s.created_at",
        (rs, n) ->
            Map.of(
                "id",
                rs.getObject("id"),
                "title",
                rs.getString("title"),
                "rules",
                rs.getString("rules"),
                "rulesHash",
                rs.getString("rules_hash"),
                "state",
                rs.getString("state"),
                "cancellationReason",
                rs.getString("cancellation_reason") == null
                    ? ""
                    : rs.getString("cancellation_reason")),
        job);
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
