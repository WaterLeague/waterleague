package io.waterleague.ranking.repository;

import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class RankingRepository {
  private final JdbcTemplate db;

  public RankingRepository(JdbcTemplate d) {
    db = d;
  }

  public boolean exists(UUID job) {
    return db.queryForObject("SELECT COUNT(*) FROM submissions WHERE job_id=?", Integer.class, job)
        > 0;
  }

  public void add(UUID job, UUID owner, String hash, BigDecimal score, BigDecimal cost) {
    db.update(
        "INSERT INTO submissions(id,job_id,owner_id,model_hash,score,cost,created_at)"
            + " VALUES(?,?,?,?,?,?,?)",
        UUID.randomUUID(),
        job,
        owner,
        hash,
        score,
        cost,
        Timestamp.from(Instant.now()));
  }

  public List<Map<String, Object>> board(String hash) {
    return db.query(
        "SELECT display_name,score,cost,created_at FROM (SELECT"
            + " a.display_name,s.score,s.cost,s.created_at,ROW_NUMBER() OVER(PARTITION BY"
            + " s.owner_id ORDER BY s.score DESC,s.created_at,s.id) choice FROM submissions s JOIN"
            + " accounts a ON a.id=s.owner_id WHERE s.model_hash=? AND a.enabled=true AND"
            + " a.approval_status='APPROVED') ranked WHERE choice=1 ORDER BY score DESC,created_at"
            + " LIMIT 100",
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
        hash);
  }
}
