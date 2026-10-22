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
    return board(event, 0);
  }

  public List<Map<String, Object>> board(String event, int page) {
    return board(event, page, null);
  }

  public List<Map<String, Object>> board(String event, int page, UUID owner) {
    return board(event, page, owner, false);
  }

  public List<Map<String, Object>> analysisRows(String event) {
    return board(event, 0, null, true);
  }

  private List<Map<String, Object>> board(String event, int page, UUID owner, boolean all) {
    return db.query(
        "SELECT * FROM (SELECT ranked.*,RANK() OVER(PARTITION BY rules_hash,comparison_group_hash"
            + " ORDER BY difference_m3 DESC) board_rank,ROW_NUMBER() OVER(PARTITION BY"
            + " rules_hash,comparison_group_hash ORDER BY difference_m3 DESC,created_at,id)"
            + " board_position FROM (SELECT"
            + " j.id,j.owner_id,a.display_name,j.created_at,s.rules_hash,s.score_policy_sha256,s.comparison_group_hash,s.cost,s.difference_m3,"
            + " ROW_NUMBER() OVER(PARTITION BY j.owner_id,s.rules_hash,s.comparison_group_hash"
            + " ORDER BY s.difference_m3 DESC,j.created_at,j.id) choice FROM historical_submissions"
            + " s JOIN historical_experiments j ON j.id=s.job_id JOIN accounts a ON a.id=j.owner_id"
            + " WHERE s.event_id=? AND j.source_dataset='SEOUL_NGII_GAME_V2' AND j.competition_id"
            + " IS NULL AND j.state='SUCCEEDED' AND s.difference_m3 IS NOT NULL AND"
            + " s.comparison_group_hash IS NOT NULL AND s.score_policy_sha256 IS NOT NULL AND"
            + " a.enabled=true AND a.approval_status='APPROVED') ranked WHERE choice=1) board WHERE"
            + " (? OR (?::uuid IS NULL AND board_position>? AND board_position<=?) OR"
            + " owner_id=?::uuid) ORDER BY rules_hash,comparison_group_hash,difference_m3"
            + " DESC,created_at,id",
        (r, n) ->
            Map.<String, Object>of(
                "rank",
                r.getInt("board_rank"),
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
                "scorePolicySha256",
                r.getString("score_policy_sha256"),
                "comparisonGroupHash",
                r.getString("comparison_group_hash"),
                "differenceM3Exact",
                r.getBigDecimal("difference_m3").toPlainString(),
                "costKrw",
                r.getBigDecimal("cost")),
        event,
        all,
        owner,
        page * 100,
        (page + 1) * 100,
        owner);
  }

  public long withheldCount(String event) {
    return db.queryForObject(
        "SELECT COUNT(*) FROM historical_submissions s JOIN historical_experiments j ON"
            + " j.id=s.job_id JOIN accounts a ON a.id=j.owner_id WHERE s.event_id=? AND"
            + " j.source_dataset='SEOUL_NGII_GAME_V2' AND j.competition_id IS NULL AND"
            + " j.state='SUCCEEDED' AND (s.comparison_group_hash IS NULL OR s.score_policy_sha256"
            + " IS NULL OR s.difference_m3 IS NULL) AND a.enabled=true AND"
            + " a.approval_status='APPROVED'",
        Long.class,
        event);
  }
}
