package io.waterleague.historical.repository;

import io.waterleague.historical.entity.HistoricalExperiment;
import java.util.*;
import org.springframework.jdbc.core.*;
import org.springframework.stereotype.Repository;

@Repository
public class HistoricalRepository {
  private final JdbcTemplate db;
  private final RowMapper<HistoricalExperiment> mapper =
      (r, n) ->
          new HistoricalExperiment(
              r.getObject("id", UUID.class),
              r.getObject("owner_id", UUID.class),
              r.getString("district_id"),
              r.getString("model_hash"),
              r.getString("input_hash"),
              r.getString("placements"),
              r.getString("state"),
              r.getObject("lease_token", UUID.class),
              r.getTimestamp("created_at").toInstant(),
              r.getString("result"),
              r.getString("error_code"));

  public HistoricalRepository(JdbcTemplate db) {
    this.db = db;
  }

  public Optional<HistoricalExperiment> get(UUID owner, UUID id) {
    return db
        .query("SELECT * FROM historical_experiments WHERE owner_id=? AND id=?", mapper, owner, id)
        .stream()
        .findFirst();
  }

  public Optional<HistoricalExperiment> byKey(UUID owner, UUID key) {
    return db
        .query(
            "SELECT * FROM historical_experiments WHERE owner_id=? AND request_key=?",
            mapper,
            owner,
            key)
        .stream()
        .findFirst();
  }

  public List<HistoricalExperiment> list(UUID owner) {
    return db.query(
        "SELECT * FROM historical_experiments WHERE owner_id=? ORDER BY created_at DESC,id DESC"
            + " LIMIT 50",
        mapper,
        owner);
  }

  public int active(UUID owner) {
    return db.queryForObject(
        "SELECT count(*) FROM historical_experiments WHERE owner_id=? AND state IN"
            + " ('QUEUED','RUNNING')",
        Integer.class,
        owner);
  }

  public List<HistoricalExperiment> submissions(UUID owner, String event) {
    return db.query(
        "SELECT j.* FROM historical_experiments j JOIN historical_submissions s ON s.job_id=j.id"
            + " WHERE j.owner_id=? AND s.event_id=? ORDER BY j.created_at DESC,j.id DESC LIMIT 50",
        mapper,
        owner,
        event);
  }

  public void add(HistoricalExperiment j, UUID key) {
    db.update(
        "INSERT INTO"
            + " historical_experiments(id,owner_id,request_key,district_id,model_hash,input_hash,placements,state,created_at)"
            + " VALUES(?,?,?,?,?,?,?,'QUEUED',?)",
        j.id(),
        j.ownerId(),
        key,
        j.districtId(),
        j.modelHash(),
        j.inputHash(),
        j.placements(),
        java.sql.Timestamp.from(j.createdAt()));
  }
}
