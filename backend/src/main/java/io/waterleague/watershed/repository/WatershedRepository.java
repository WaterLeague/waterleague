package io.waterleague.watershed.repository;

import static io.waterleague.watershed.mapper.WatershedMapper.ROW;

import io.waterleague.watershed.entity.WatershedExperiment;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class WatershedRepository {
  private final JdbcTemplate db;

  public WatershedRepository(JdbcTemplate db) {
    this.db = db;
  }

  public Optional<WatershedExperiment> get(UUID owner, UUID id) {
    return db
        .query("SELECT * FROM watershed_experiments WHERE owner_id=? AND id=?", ROW, owner, id)
        .stream()
        .findFirst();
  }

  public Optional<WatershedExperiment> byKey(UUID owner, UUID key) {
    return db
        .query(
            "SELECT * FROM watershed_experiments WHERE owner_id=? AND request_key=?",
            ROW,
            owner,
            key)
        .stream()
        .findFirst();
  }

  public List<WatershedExperiment> list(UUID owner) {
    return db.query(
        "SELECT * FROM watershed_experiments WHERE owner_id=? ORDER BY created_at DESC,id DESC"
            + " LIMIT 50",
        ROW,
        owner);
  }

  public int active(UUID owner) {
    return db.queryForObject(
        "SELECT count(*) FROM watershed_experiments WHERE owner_id=? AND state IN"
            + " ('QUEUED','RUNNING')",
        Integer.class,
        owner);
  }

  public void add(WatershedExperiment j, UUID key) {
    db.update(
        "INSERT INTO"
            + " watershed_experiments(id,owner_id,request_key,model_hash,input_hash,placements,state,created_at)"
            + " VALUES(?,?,?,?,?,?,'QUEUED',?)",
        j.id(),
        j.ownerId(),
        key,
        j.modelHash(),
        j.inputHash(),
        j.placements(),
        java.sql.Timestamp.from(j.createdAt()));
  }
}
