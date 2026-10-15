package io.waterleague.analysis.repository;

import io.waterleague.analysis.entity.ResearchComparison;
import java.sql.Timestamp;
import java.util.*;
import org.springframework.jdbc.core.*;
import org.springframework.stereotype.Repository;

@Repository
public class ResearchAnalysisRepository {
  private final JdbcTemplate db;
  private static final String SELECT =
      "SELECT r.*,c.title FROM research_comparisons r JOIN rainfall_comparisons c ON"
          + " c.id=r.comparison_id";
  private final RowMapper<ResearchComparison> mapper =
      (rs, n) ->
          new ResearchComparison(
              rs.getObject("id", UUID.class),
              rs.getObject("organization_id", UUID.class),
              rs.getObject("requested_by", UUID.class),
              rs.getObject("source_job_id", UUID.class),
              rs.getObject("comparison_id", UUID.class),
              rs.getObject("request_key", UUID.class),
              rs.getString("request_hash"),
              rs.getString("title"),
              rs.getTimestamp("created_at").toInstant());

  public ResearchAnalysisRepository(JdbcTemplate db) {
    this.db = db;
  }

  public Optional<ResearchComparison> get(UUID id, UUID org) {
    return db.query(SELECT + " WHERE r.id=? AND r.organization_id=?", mapper, id, org).stream()
        .findFirst();
  }

  public Optional<ResearchComparison> byKey(UUID org, UUID key) {
    return db
        .query(SELECT + " WHERE r.organization_id=? AND r.request_key=?", mapper, org, key)
        .stream()
        .findFirst();
  }

  public List<ResearchComparison> list(UUID org) {
    return db.query(
        SELECT + " WHERE r.organization_id=? ORDER BY r.created_at DESC,r.id LIMIT 50",
        mapper,
        org);
  }

  public void add(ResearchComparison r) {
    db.update(
        "INSERT INTO"
            + " research_comparisons(id,organization_id,requested_by,source_job_id,comparison_id,request_key,request_hash,created_at)"
            + " VALUES(?,?,?,?,?,?,?,?)",
        r.id(),
        r.organizationId(),
        r.requestedBy(),
        r.sourceJobId(),
        r.comparisonId(),
        r.requestKey(),
        r.requestHash(),
        Timestamp.from(r.createdAt()));
  }

  public int active(UUID org) {
    return db.queryForObject(
        "SELECT COUNT(*) FROM research_comparisons r JOIN rainfall_comparison_jobs c ON"
            + " c.comparison_id=r.comparison_id JOIN simulation_jobs j ON j.id=c.job_id WHERE"
            + " r.organization_id=? AND j.state IN ('QUEUED','RUNNING')",
        Integer.class,
        org);
  }

  public boolean contains(UUID comparison, UUID job) {
    return db.queryForObject(
            "SELECT COUNT(*) FROM rainfall_comparison_jobs WHERE comparison_id=? AND job_id=?",
            Integer.class,
            comparison,
            job)
        > 0;
  }
}
