package io.waterleague.historical.repository;

import java.math.BigDecimal;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class HistoricalSubmissionRepository {
  private final JdbcTemplate db;

  public HistoricalSubmissionRepository(JdbcTemplate db) {
    this.db = db;
  }

  public Optional<String> request(UUID id) {
    return db
        .query(
            "SELECT request_raw FROM historical_submissions WHERE job_id=?",
            (r, n) -> r.getString(1),
            id)
        .stream()
        .findFirst();
  }

  public void add(UUID id, String event, String rules, String request, BigDecimal cost) {
    db.update(
        "INSERT INTO historical_submissions(job_id,event_id,rules_hash,request_raw,cost)"
            + " VALUES(?,?,?,?,?)",
        id,
        event,
        rules,
        request,
        cost);
  }

  public List<Map<String, Object>> board(String event) {
    return db.query(
        "SELECT * FROM (SELECT ranked.*,ROW_NUMBER() OVER(PARTITION BY rules_hash ORDER BY"
            + " difference_m3 DESC,created_at,id) board_position FROM (SELECT"
            + " j.id,a.display_name,j.created_at,s.rules_hash,s.cost,s.difference_m3, ROW_NUMBER()"
            + " OVER(PARTITION BY j.owner_id,s.rules_hash ORDER BY s.difference_m3"
            + " DESC,j.created_at,j.id) choice FROM historical_submissions s JOIN"
            + " historical_experiments j ON j.id=s.job_id JOIN accounts a ON a.id=j.owner_id WHERE"
            + " s.event_id=? AND j.state='SUCCEEDED' AND s.difference_m3 IS NOT NULL AND"
            + " a.enabled=true AND a.approval_status='APPROVED') ranked WHERE choice=1) board"
            + " WHERE board_position<=100 ORDER BY"
            + " rules_hash,difference_m3 DESC,created_at,id",
        (r, n) ->
            Map.<String, Object>of(
                "id",
                r.getObject("id", UUID.class),
                "displayName",
                r.getString("display_name"),
                "submittedAt",
                r.getTimestamp("created_at").toInstant(),
                "differenceM3",
                r.getBigDecimal("difference_m3"),
                "rulesHash",
                r.getString("rules_hash"),
                "costKrw",
                r.getBigDecimal("cost")),
        event);
  }
}
