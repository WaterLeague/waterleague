package io.waterleague.administration.repository;

import io.waterleague.administration.view.MemberApplicationView;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ApprovalRepository {
  private final JdbcTemplate db;

  public ApprovalRepository(JdbcTemplate db) {
    this.db = db;
  }

  public void lock(UUID id) {
    db.queryForObject("SELECT id FROM accounts WHERE id=? FOR UPDATE", UUID.class, id);
  }

  public List<MemberApplicationView> list(String status, String after) {
    return db.query(
        "SELECT * FROM accounts WHERE role='MEMBER' AND (?='ALL' OR approval_status=?) AND CAST(id"
            + " AS VARCHAR)>? ORDER BY id LIMIT 100",
        (rs, n) ->
            new MemberApplicationView(
                rs.getObject("id", UUID.class),
                rs.getString("username"),
                rs.getString("display_name"),
                rs.getString("member_type"),
                rs.getString("approval_status"),
                rs.getBoolean("enabled"),
                rs.getObject("organization_id", UUID.class),
                rs.getString("requested_organization_name"),
                rs.getString("application_purpose"),
                rs.getTimestamp("created_at").toInstant()),
        status,
        status,
        after);
  }

  public UUID organization(String name) {
    UUID id = UUID.randomUUID();
    db.update("INSERT INTO organizations(id,name,approved) VALUES(?,?,true)", id, name);
    return id;
  }

  public void decide(
      UUID id,
      UUID reviewer,
      String decision,
      String status,
      UUID org,
      String reason,
      String username) {
    db.update(
        "UPDATE accounts SET approval_status=?,organization_id=? WHERE id=?", status, org, id);
    db.update(
        "INSERT INTO"
            + " account_reviews(id,account_id,reviewer_id,decision,reason,organization_id,created_at)"
            + " VALUES(?,?,?,?,?,?,?)",
        UUID.randomUUID(),
        id,
        reviewer,
        decision,
        reason,
        org,
        Timestamp.from(Instant.now()));
    db.update("DELETE FROM SPRING_SESSION WHERE PRINCIPAL_NAME=?", username);
  }

  public List<Map<String, Object>> history(UUID id) {
    return db.query(
        "SELECT decision,reason,created_at FROM account_reviews WHERE account_id=? ORDER BY"
            + " created_at DESC LIMIT 100",
        (rs, n) ->
            Map.of(
                "decision",
                rs.getString("decision"),
                "reason",
                rs.getString("reason"),
                "reviewedAt",
                rs.getTimestamp("created_at").toInstant()),
        id);
  }
}
