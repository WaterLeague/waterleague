package io.waterleague.simulation.repository;

import io.waterleague.simulation.entity.SimulationJob;
import java.sql.Timestamp;
import java.util.*;
import org.springframework.jdbc.core.*;
import org.springframework.stereotype.Repository;

@Repository
public class SimulationRepository {
  private final JdbcTemplate db;
  private final RowMapper<SimulationJob> mapper =
      (rs, n) ->
          new SimulationJob(
              rs.getObject("id", UUID.class),
              rs.getObject("version_id", UUID.class),
              rs.getObject("owner_id", UUID.class),
              rs.getString("state"),
              rs.getString("model_hash"),
              rs.getString("input_hash"),
              rs.getString("result"),
              rs.getString("error_code"),
              rs.getTimestamp("created_at").toInstant());

  public SimulationRepository(JdbcTemplate d) {
    db = d;
  }

  public void lockAdmission() {
    db.queryForObject("SELECT id FROM queue_admission WHERE id=1 FOR UPDATE", Integer.class);
  }

  public void lockOwner(UUID owner) {
    db.queryForObject("SELECT id FROM accounts WHERE id=? FOR UPDATE", UUID.class, owner);
  }

  public Optional<SimulationJob> byKey(UUID owner, UUID key) {
    return db
        .query(
            "SELECT * FROM simulation_jobs WHERE owner_id=? AND request_key=?", mapper, owner, key)
        .stream()
        .findFirst();
  }

  public Optional<SimulationJob> get(UUID id, UUID owner) {
    return db
        .query("SELECT * FROM simulation_jobs WHERE id=? AND owner_id=?", mapper, id, owner)
        .stream()
        .findFirst();
  }

  public Optional<SimulationJob> get(UUID id) {
    return db.query("SELECT * FROM simulation_jobs WHERE id=?", mapper, id).stream().findFirst();
  }

  public List<SimulationJob> list(UUID owner) {
    return db.query(
        "SELECT * FROM simulation_jobs WHERE owner_id=? ORDER BY created_at DESC LIMIT 50",
        mapper,
        owner);
  }

  public int active(UUID owner) {
    return db.queryForObject(
        "SELECT COUNT(*) FROM simulation_jobs WHERE owner_id=? AND state IN ('QUEUED','RUNNING')",
        Integer.class,
        owner);
  }

  public int totalActive() {
    return db.queryForObject(
        "SELECT (SELECT COUNT(*) FROM simulation_jobs WHERE state IN ('QUEUED','RUNNING')) +"
            + " (SELECT COUNT(*) FROM research_candidates WHERE state IN ('QUEUED','RUNNING')) +"
            + " (SELECT COUNT(*) FROM historical_experiments WHERE state IN ('QUEUED','RUNNING'))",
        Integer.class);
  }

  public void add(SimulationJob j, UUID key) {
    db.update(
        "INSERT INTO"
            + " simulation_jobs(id,version_id,owner_id,request_key,state,model_hash,input_hash,created_at)"
            + " VALUES(?,?,?,?,?,?,?,?)",
        j.id(),
        j.versionId(),
        j.ownerId(),
        key,
        j.state(),
        j.modelHash(),
        j.inputHash(),
        Timestamp.from(j.createdAt()));
  }
}
