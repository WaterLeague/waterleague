package io.waterleague.comparison.repository;

import io.waterleague.comparison.entity.RainfallComparison;
import java.sql.Timestamp;
import java.util.*;
import org.springframework.jdbc.core.*;
import org.springframework.stereotype.Repository;

@Repository
public class ComparisonRepository {
  private final JdbcTemplate db;
  private final RowMapper<RainfallComparison> mapper =
      (rs, n) ->
          new RainfallComparison(
              rs.getObject("id", UUID.class),
              rs.getObject("owner_id", UUID.class),
              rs.getObject("source_version_id", UUID.class),
              rs.getString("request_hash"),
              rs.getString("title"),
              rs.getTimestamp("created_at").toInstant());

  public ComparisonRepository(JdbcTemplate db) {
    this.db = db;
  }

  public Optional<RainfallComparison> byKey(UUID owner, UUID key) {
    return db
        .query(
            "SELECT * FROM rainfall_comparisons WHERE owner_id=? AND request_key=?",
            mapper,
            owner,
            key)
        .stream()
        .findFirst();
  }

  public Optional<RainfallComparison> get(UUID id, UUID owner) {
    return db
        .query("SELECT * FROM rainfall_comparisons WHERE id=? AND owner_id=?", mapper, id, owner)
        .stream()
        .findFirst();
  }

  public List<RainfallComparison> list(UUID owner) {
    return db.query(
        "SELECT * FROM rainfall_comparisons WHERE owner_id=? ORDER BY created_at DESC LIMIT 50",
        mapper,
        owner);
  }

  public void add(RainfallComparison c, UUID key) {
    db.update(
        "INSERT INTO"
            + " rainfall_comparisons(id,owner_id,source_version_id,request_key,request_hash,title,created_at)"
            + " VALUES(?,?,?,?,?,?,?)",
        c.id(),
        c.ownerId(),
        c.sourceVersionId(),
        key,
        c.requestHash(),
        c.title(),
        Timestamp.from(c.createdAt()));
  }

  public void link(UUID comparisonId, int ordinal, String modelHash, UUID jobId) {
    db.update(
        "INSERT INTO rainfall_comparison_jobs(comparison_id,ordinal,model_hash,job_id)"
            + " VALUES(?,?,?,?)",
        comparisonId,
        ordinal,
        modelHash,
        jobId);
  }

  public List<UUID> jobs(UUID comparisonId, UUID owner) {
    return db.query(
        "SELECT j.job_id FROM rainfall_comparison_jobs j JOIN rainfall_comparisons c ON"
            + " c.id=j.comparison_id WHERE c.id=? AND c.owner_id=? ORDER BY j.ordinal",
        (rs, n) -> rs.getObject("job_id", UUID.class),
        comparisonId,
        owner);
  }
}
