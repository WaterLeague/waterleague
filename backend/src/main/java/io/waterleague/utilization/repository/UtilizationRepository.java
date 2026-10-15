package io.waterleague.utilization.repository;

import io.waterleague.utilization.entity.*;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.*;
import org.springframework.stereotype.Repository;

@Repository
public class UtilizationRepository {
  private final JdbcTemplate db;
  private static final String REQUESTS =
      "SELECT r.*,o.name organization_name FROM utilization_requests r JOIN organizations o ON"
          + " o.id=r.organization_id ";
  private static final String REVIEWS =
      "SELECT r.*,o.name organization_name FROM strategy_reviews r JOIN organizations o ON"
          + " o.id=r.organization_id JOIN simulation_jobs j ON j.id=r.job_id ";
  private final RowMapper<UtilizationRequest> requestMapper =
      (r, n) ->
          new UtilizationRequest(
              r.getObject("id", UUID.class),
              r.getObject("job_id", UUID.class),
              r.getObject("version_id", UUID.class),
              r.getString("model_hash"),
              r.getObject("owner_id", UUID.class),
              r.getObject("organization_id", UUID.class),
              r.getString("organization_name"),
              r.getObject("requested_by", UUID.class),
              r.getObject("request_key", UUID.class),
              r.getString("title"),
              r.getString("purpose"),
              r.getString("policy_version"),
              r.getString("terms_hash"),
              r.getString("state"),
              r.getInt("revision"),
              r.getTimestamp("created_at").toInstant(),
              r.getTimestamp("updated_at").toInstant());
  private final RowMapper<StrategyReview> reviewMapper =
      (r, n) ->
          new StrategyReview(
              r.getObject("id", UUID.class),
              r.getObject("job_id", UUID.class),
              r.getObject("organization_id", UUID.class),
              r.getString("organization_name"),
              r.getObject("reviewer_id", UUID.class),
              r.getString("state"),
              r.getString("reason"),
              r.getString("limitations"),
              r.getTimestamp("created_at").toInstant());

  public UtilizationRepository(JdbcTemplate db) {
    this.db = db;
  }

  public Optional<UtilizationRequest> get(UUID id) {
    return db.query(REQUESTS + "WHERE r.id=?", requestMapper, id).stream().findFirst();
  }

  public Optional<UtilizationRequest> byKey(UUID org, UUID key) {
    return db
        .query(REQUESTS + "WHERE r.organization_id=? AND r.request_key=?", requestMapper, org, key)
        .stream()
        .findFirst();
  }

  public boolean active(UUID job, UUID org) {
    return db.queryForObject(
            "SELECT COUNT(*) FROM utilization_requests WHERE job_id=? AND organization_id=? AND"
                + " state IN ('PENDING','GRANTED')",
            Integer.class,
            job,
            org)
        > 0;
  }

  public void add(UtilizationRequest r) {
    db.update(
        "INSERT INTO"
            + " utilization_requests(id,job_id,version_id,model_hash,owner_id,organization_id,requested_by,request_key,title,purpose,policy_version,terms_hash,state,revision,created_at,updated_at)"
            + " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        r.id(),
        r.jobId(),
        r.versionId(),
        r.modelHash(),
        r.ownerId(),
        r.organizationId(),
        r.requestedBy(),
        r.requestKey(),
        r.title(),
        r.purpose(),
        r.policyVersion(),
        r.termsHash(),
        r.state(),
        r.revision(),
        Timestamp.from(r.createdAt()),
        Timestamp.from(r.updatedAt()));
  }

  public List<UtilizationRequest> list(
      UUID subject, boolean organization, UtilizationRequest cursor) {
    String scope = organization ? "r.organization_id=?" : "r.owner_id=?";
    var args = new ArrayList<Object>();
    args.add(subject);
    String page = "";
    if (cursor != null) {
      page = " AND (r.created_at<? OR (r.created_at=? AND r.id<?))";
      args.add(Timestamp.from(cursor.createdAt()));
      args.add(Timestamp.from(cursor.createdAt()));
      args.add(cursor.id());
    }
    return db.query(
        REQUESTS + "WHERE " + scope + page + " ORDER BY r.created_at DESC,r.id DESC LIMIT 51",
        requestMapper,
        args.toArray());
  }

  public int transition(UtilizationRequest r, String state, Instant now) {
    return db.update(
        "UPDATE utilization_requests SET state=?,revision=revision+1,updated_at=? WHERE id=? AND"
            + " revision=? AND state=?",
        state,
        Timestamp.from(now),
        r.id(),
        r.revision(),
        r.state());
  }

  public void decision(UtilizationRequest r, UUID actor, String decision, Instant now) {
    db.update(
        "INSERT INTO"
            + " utilization_decisions(id,request_id,actor_id,decision,revision,terms_hash,created_at)"
            + " VALUES(?,?,?,?,?,?,?)",
        UUID.randomUUID(),
        r.id(),
        actor,
        decision,
        r.revision() + 1,
        r.termsHash(),
        Timestamp.from(now));
  }

  public List<Map<String, Object>> decisions(UUID request) {
    return db.query(
        "SELECT decision,revision,terms_hash,created_at FROM utilization_decisions WHERE"
            + " request_id=? ORDER BY revision",
        (r, n) ->
            Map.of(
                "decision",
                r.getString("decision"),
                "revision",
                r.getInt("revision"),
                "termsHash",
                r.getString("terms_hash"),
                "createdAt",
                r.getTimestamp("created_at").toInstant()),
        request);
  }

  public void addReview(StrategyReview r) {
    db.update(
        "INSERT INTO"
            + " strategy_reviews(id,job_id,organization_id,reviewer_id,state,reason,limitations,created_at)"
            + " VALUES(?,?,?,?,?,?,?,?)",
        r.id(),
        r.jobId(),
        r.organizationId(),
        r.reviewerId(),
        r.state(),
        r.reason(),
        r.limitations(),
        Timestamp.from(r.createdAt()));
  }

  public Optional<StrategyReview> review(UUID id) {
    return db.query(REVIEWS + "WHERE r.id=?", reviewMapper, id).stream().findFirst();
  }

  public List<StrategyReview> reviews(UUID subject, UUID job, StrategyReview cursor) {
    String scope = job == null ? "j.owner_id=?" : "r.organization_id=? AND r.job_id=?";
    var args = new ArrayList<Object>();
    args.add(subject);
    if (job != null) args.add(job);
    String page = "";
    if (cursor != null) {
      page = " AND (r.created_at<? OR (r.created_at=? AND r.id<?))";
      args.add(Timestamp.from(cursor.createdAt()));
      args.add(Timestamp.from(cursor.createdAt()));
      args.add(cursor.id());
    }
    return db.query(
        REVIEWS + "WHERE " + scope + page + " ORDER BY r.created_at DESC,r.id DESC LIMIT 51",
        reviewMapper,
        args.toArray());
  }
}
