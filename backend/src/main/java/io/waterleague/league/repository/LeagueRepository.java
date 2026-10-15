package io.waterleague.league.repository;

import io.waterleague.league.entity.*;
import java.math.BigDecimal;
import java.sql.*;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.*;
import org.springframework.stereotype.Repository;

@Repository
public class LeagueRepository {
  private final JdbcTemplate db;
  private final RowMapper<League> mapper =
      (rs, n) ->
          new League(
              rs.getObject("id", UUID.class),
              rs.getObject("organization_id", UUID.class),
              rs.getString("organization_name"),
              rs.getInt("revision"),
              rs.getString("state"),
              rs.getString("title"),
              rs.getString("question"),
              rs.getTimestamp("opens_at").toInstant(),
              rs.getTimestamp("closes_at").toInstant(),
              rs.getString("model_hash"),
              rs.getString("model_source"),
              rs.getString("rules"),
              rs.getString("rules_hash"),
              rs.getString("execution_hash"),
              rs.getTimestamp("published_at") == null
                  ? null
                  : rs.getTimestamp("published_at").toInstant(),
              rs.getString("cancellation_reason"),
              rs.getTimestamp("created_at").toInstant());
  private static final String SELECT =
      "SELECT l.*,o.name organization_name FROM leagues l JOIN organizations o ON"
          + " o.id=l.organization_id ";

  public LeagueRepository(JdbcTemplate db) {
    this.db = db;
  }

  public Optional<League> get(UUID id, boolean lock) {
    if (lock)
      db.query("SELECT id FROM leagues WHERE id=? FOR UPDATE", (rs, n) -> rs.getObject(1), id);
    return db.query(SELECT + "WHERE l.id=?", mapper, id).stream().findFirst();
  }

  public List<League> list(UUID org) {
    if (org != null)
      return db.query(
          SELECT + "WHERE l.organization_id=? ORDER BY l.created_at DESC LIMIT 100", mapper, org);
    return db.query(
        SELECT + "WHERE l.state<>'DRAFT' AND o.approved=true ORDER BY l.created_at DESC LIMIT 100",
        mapper);
  }

  public void lockOrganization(UUID id) {
    db.queryForObject("SELECT id FROM organizations WHERE id=? FOR UPDATE", UUID.class, id);
  }

  public int active(UUID org, Instant now) {
    return db.queryForObject(
        "SELECT COUNT(*) FROM leagues WHERE organization_id=? AND state<>'CANCELLED' AND"
            + " closes_at>?",
        Integer.class,
        org,
        Timestamp.from(now));
  }

  public void create(League l, UUID creator) {
    db.update(
        "INSERT INTO"
            + " leagues(id,organization_id,creator_id,revision,state,title,question,opens_at,closes_at,model_hash,model_source,rules,rules_hash,created_at)"
            + " VALUES(?,?,?,1,'DRAFT',?,?,?,?,?,?,?,?,?)",
        l.id(),
        l.organizationId(),
        creator,
        l.title(),
        l.question(),
        Timestamp.from(l.opensAt()),
        Timestamp.from(l.closesAt()),
        l.modelHash(),
        l.modelSource(),
        l.rules(),
        l.rulesHash(),
        Timestamp.from(l.createdAt()));
  }

  public void update(League l) {
    db.update(
        "UPDATE leagues SET"
            + " revision=revision+1,title=?,question=?,opens_at=?,closes_at=?,model_hash=?,model_source=?,rules=?,rules_hash=?"
            + " WHERE id=? AND state='DRAFT'",
        l.title(),
        l.question(),
        Timestamp.from(l.opensAt()),
        Timestamp.from(l.closesAt()),
        l.modelHash(),
        l.modelSource(),
        l.rules(),
        l.rulesHash(),
        l.id());
  }

  public void publish(UUID id, Instant at) {
    db.update(
        "UPDATE leagues SET state='PUBLISHED',published_at=?,revision=revision+1 WHERE id=? AND"
            + " state='DRAFT'",
        Timestamp.from(at),
        id);
  }

  public void cancel(UUID id, String reason) {
    db.update(
        "UPDATE leagues SET state='CANCELLED',cancellation_reason=?,revision=revision+1 WHERE id=?"
            + " AND state='PUBLISHED'",
        reason,
        id);
  }

  public Optional<Map<String, Object>> existing(UUID league, UUID job, UUID owner) {
    return db
        .query(
            "SELECT score,cost,created_at FROM league_submissions WHERE league_id=? AND job_id=?"
                + " AND owner_id=?",
            (rs, n) ->
                Map.<String, Object>of(
                    "score",
                    rs.getBigDecimal("score"),
                    "cost",
                    rs.getBigDecimal("cost"),
                    "submittedAt",
                    rs.getTimestamp("created_at").toInstant()),
            league,
            job,
            owner)
        .stream()
        .findFirst();
  }

  public int count(UUID league, UUID owner) {
    return db.queryForObject(
        "SELECT COUNT(*) FROM league_submissions WHERE league_id=? AND owner_id=?",
        Integer.class,
        league,
        owner);
  }

  public void submit(
      UUID league,
      UUID job,
      UUID owner,
      BigDecimal score,
      BigDecimal cost,
      String fingerprint,
      Instant now) {
    db.update(
        "UPDATE leagues SET execution_hash=? WHERE id=? AND execution_hash IS NULL",
        fingerprint,
        league);
    db.update(
        "INSERT INTO league_submissions(id,league_id,job_id,owner_id,score,cost,created_at)"
            + " VALUES(?,?,?,?,?,?,?)",
        UUID.randomUUID(),
        league,
        job,
        owner,
        score,
        cost,
        Timestamp.from(now));
  }

  public List<Map<String, Object>> board(UUID league) {
    return db.query(
        "SELECT display_name,score,cost,created_at FROM (SELECT"
            + " a.display_name,s.score,s.cost,s.created_at,s.id,ROW_NUMBER() OVER(PARTITION BY"
            + " s.owner_id ORDER BY s.score DESC,s.created_at,s.id) choice FROM league_submissions"
            + " s JOIN accounts a ON a.id=s.owner_id WHERE s.league_id=? AND a.enabled=true AND"
            + " a.approval_status='APPROVED') ranked WHERE choice=1 ORDER BY score"
            + " DESC,created_at,id LIMIT 100",
        (rs, n) ->
            Map.of(
                "displayName",
                rs.getString("display_name"),
                "score",
                rs.getBigDecimal("score"),
                "cost",
                rs.getBigDecimal("cost"),
                "submittedAt",
                rs.getTimestamp("created_at").toInstant()),
        league);
  }

  public List<Map<String, Object>> own(UUID league, UUID owner) {
    return db.query(
        "SELECT job_id,score,cost,created_at FROM league_submissions WHERE league_id=? AND"
            + " owner_id=? ORDER BY created_at DESC LIMIT 100",
        (rs, n) ->
            Map.of(
                "jobId",
                rs.getObject("job_id"),
                "score",
                rs.getBigDecimal("score"),
                "cost",
                rs.getBigDecimal("cost"),
                "submittedAt",
                rs.getTimestamp("created_at").toInstant()),
        league,
        owner);
  }
}
