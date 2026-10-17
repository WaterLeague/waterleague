package io.waterleague.optimization.repository;

import io.waterleague.optimization.entity.*;
import java.sql.Timestamp;
import java.util.*;
import org.springframework.jdbc.core.*;
import org.springframework.stereotype.Repository;

@Repository
public class ResearchSearchRepository {
  private final JdbcTemplate db;
  private final RowMapper<ResearchSearch> searchMapper =
      (rs, n) ->
          new ResearchSearch(
              rs.getObject("id", UUID.class),
              rs.getObject("organization_id", UUID.class),
              rs.getObject("requested_by", UUID.class),
              rs.getObject("request_key", UUID.class),
              rs.getString("request_hash"),
              rs.getString("model_hash"),
              new SearchSettings(
                  rs.getInt("top_k"),
                  rs.getBigDecimal("budget_krw"),
                  rs.getLong("seed"),
                  rs.getInt("candidates_per_arm")),
              rs.getString("provenance"),
              rs.getString("provenance_hash"),
              rs.getTimestamp("created_at").toInstant());
  private final RowMapper<ResearchCandidate> candidateMapper =
      (rs, n) ->
          new ResearchCandidate(
              rs.getObject("id", UUID.class),
              rs.getObject("search_id", UUID.class),
              SearchArm.valueOf(rs.getString("arm")),
              rs.getInt("ordinal"),
              rs.getString("placements"),
              rs.getString("model_hash"),
              rs.getString("input_hash"),
              rs.getBigDecimal("cost"),
              rs.getString("state"),
              rs.getString("result"),
              rs.getString("error_code"),
              rs.getTimestamp("created_at").toInstant(),
              rs.getTimestamp("finished_at") == null
                  ? null
                  : rs.getTimestamp("finished_at").toInstant());

  public ResearchSearchRepository(JdbcTemplate db) {
    this.db = db;
  }

  public Optional<ResearchSearch> get(UUID id, UUID org) {
    return db
        .query(
            "SELECT * FROM research_searches WHERE id=? AND organization_id=?",
            searchMapper,
            id,
            org)
        .stream()
        .findFirst();
  }

  public Optional<ResearchSearch> byKey(UUID org, UUID key) {
    return db
        .query(
            "SELECT * FROM research_searches WHERE organization_id=? AND request_key=?",
            searchMapper,
            org,
            key)
        .stream()
        .findFirst();
  }

  public List<ResearchSearch> visible(UUID org) {
    // 접근 불가 행을 제외한 뒤 제한하여 철회된 최근 이력이 오래된 허용 이력을 가리지 않게 한다.
    return db.query(
        """
        SELECT s.* FROM research_searches s WHERE s.organization_id=?
          AND (SELECT COUNT(*) FROM research_search_sources x WHERE x.search_id=s.id) BETWEEN 2 AND 50
          AND NOT EXISTS (
            SELECT 1 FROM research_search_sources x WHERE x.search_id=s.id AND NOT EXISTS (
              SELECT 1 FROM simulation_jobs j JOIN accounts a ON a.id=j.owner_id
                AND a.enabled=true AND a.approval_status='APPROVED'
              JOIN research_consents c ON c.owner_id=j.owner_id AND c.organization_id=s.organization_id AND c.granted=true
              JOIN organizations o ON o.id=c.organization_id AND o.approved=true
              WHERE j.id=x.job_id AND (EXISTS(SELECT 1 FROM submissions p WHERE p.job_id=j.id)
                OR EXISTS(SELECT 1 FROM league_submissions p JOIN leagues l ON l.id=p.league_id
                  WHERE p.job_id=j.id AND l.organization_id=s.organization_id))))
        ORDER BY s.created_at DESC,s.id LIMIT 50
        """,
        searchMapper,
        org);
  }

  public List<UUID> sources(UUID id) {
    return db.query(
        "SELECT job_id FROM research_search_sources WHERE search_id=? ORDER BY job_id",
        (rs, n) -> rs.getObject("job_id", UUID.class),
        id);
  }

  public List<ResearchCandidate> candidates(UUID id) {
    return db.query(
        "SELECT * FROM research_candidates WHERE search_id=? ORDER BY arm,ordinal",
        candidateMapper,
        id);
  }

  public void add(ResearchSearch r, List<UUID> sources, List<ResearchCandidate> candidates) {
    db.update(
        """
        INSERT INTO research_searches(id,organization_id,requested_by,request_key,request_hash,model_hash,
          budget_krw,seed,top_k,candidates_per_arm,provenance,provenance_hash,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        r.id(),
        r.organizationId(),
        r.requestedBy(),
        r.requestKey(),
        r.requestHash(),
        r.modelHash(),
        r.settings().budgetKrw(),
        r.settings().seed(),
        r.settings().topK(),
        r.settings().candidatesPerArm(),
        r.provenance(),
        r.provenanceHash(),
        Timestamp.from(r.createdAt()));
    for (UUID source : sources)
      db.update(
          "INSERT INTO research_search_sources(search_id,job_id) VALUES(?,?)", r.id(), source);
    for (var c : candidates)
      db.update(
          """
          INSERT INTO research_candidates(id,search_id,arm,ordinal,placements,model_hash,input_hash,cost,state,created_at)
          VALUES(?,?,?,?,?,?,?,?,?,?)
          """,
          c.id(),
          c.searchId(),
          c.arm().name(),
          c.ordinal(),
          c.placements(),
          c.modelHash(),
          c.inputHash(),
          c.cost(),
          c.state(),
          Timestamp.from(c.createdAt()));
  }
}
