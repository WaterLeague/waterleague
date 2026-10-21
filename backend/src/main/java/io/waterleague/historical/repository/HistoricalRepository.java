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
        .query(
            "SELECT * FROM historical_experiments WHERE source_dataset='SEOUL_NGII_GAME_V2' AND"
                + " owner_id=? AND id=?",
            mapper,
            owner,
            id)
        .stream()
        .findFirst();
  }

  public Optional<HistoricalExperiment> byKey(UUID owner, UUID key) {
    return db
        .query(
            "SELECT * FROM historical_experiments WHERE source_dataset='SEOUL_NGII_GAME_V2' AND"
                + " owner_id=? AND request_key=?",
            mapper,
            owner,
            key)
        .stream()
        .findFirst();
  }

  public UUID competition(UUID job) {
    return db.queryForObject(
        "SELECT competition_id FROM historical_experiments WHERE id=?", UUID.class, job);
  }

  public List<HistoricalExperiment> list(UUID owner) {
    return list(owner, null);
  }

  public List<HistoricalExperiment> list(UUID owner, UUID competitionId) {
    return db.query(
        "SELECT * FROM historical_experiments WHERE source_dataset='SEOUL_NGII_GAME_V2' AND"
            + " owner_id=? AND competition_id IS NOT DISTINCT FROM ?::uuid ORDER BY created_at"
            + " DESC,id DESC LIMIT 50",
        mapper,
        owner,
        competitionId);
  }

  public int active(UUID owner) {
    return db.queryForObject(
        "SELECT count(*) FROM historical_experiments WHERE source_dataset='SEOUL_NGII_GAME_V2' AND"
            + " owner_id=? AND state IN ('QUEUED','RUNNING')",
        Integer.class,
        owner);
  }

  public List<HistoricalExperiment> submissions(UUID owner, String event) {
    return submissions(owner, event, null);
  }

  public List<HistoricalExperiment> submissions(UUID owner, String event, UUID competitionId) {
    return db.query(
        "SELECT j.* FROM historical_experiments j JOIN historical_submissions s ON s.job_id=j.id"
            + " WHERE j.source_dataset='SEOUL_NGII_GAME_V2' AND j.owner_id=? AND s.event_id=? AND"
            + " j.competition_id IS NOT DISTINCT FROM ?::uuid ORDER BY j.created_at DESC,j.id DESC"
            + " LIMIT 50",
        mapper,
        owner,
        event,
        competitionId);
  }

  public Optional<HistoricalExperiment> guestGet(String guest, UUID id) {
    return db
        .query(
            "SELECT * FROM historical_experiments WHERE source_dataset='SEOUL_NGII_GAME_V2' AND"
                + " guest_key=? AND owner_id IS NULL AND id=?",
            mapper,
            guest,
            id)
        .stream()
        .findFirst();
  }

  public Optional<HistoricalExperiment> guestByKey(String guest, UUID key) {
    return db
        .query(
            "SELECT * FROM historical_experiments WHERE source_dataset='SEOUL_NGII_GAME_V2' AND"
                + " guest_key=? AND owner_id IS NULL AND request_key=?",
            mapper,
            guest,
            key)
        .stream()
        .findFirst();
  }

  public List<HistoricalExperiment> guestList(String guest) {
    return db.query(
        "SELECT * FROM historical_experiments WHERE source_dataset='SEOUL_NGII_GAME_V2' AND"
            + " guest_key=? AND owner_id IS NULL ORDER BY created_at DESC,id DESC LIMIT 50",
        mapper,
        guest);
  }

  public int guestActive(String guest) {
    return db.queryForObject(
        "SELECT count(*) FROM historical_experiments WHERE source_dataset='SEOUL_NGII_GAME_V2' AND"
            + " guest_key=? AND state IN ('QUEUED','RUNNING')",
        Integer.class,
        guest);
  }

  public void addGuest(HistoricalExperiment j, UUID key, String guest) {
    db.update(
        "INSERT INTO"
            + " historical_experiments(id,guest_key,request_key,district_id,model_hash,input_hash,placements,state,created_at)"
            + " VALUES(?,?,?,?,?,?,?,'QUEUED',?)",
        j.id(),
        guest,
        key,
        j.districtId(),
        j.modelHash(),
        j.inputHash(),
        j.placements(),
        java.sql.Timestamp.from(j.createdAt()));
  }

  public void add(HistoricalExperiment j, UUID key) {
    add(j, key, null);
  }

  public void add(HistoricalExperiment j, UUID key, UUID competitionId) {
    db.update(
        "INSERT INTO"
            + " historical_experiments(id,owner_id,request_key,district_id,model_hash,input_hash,placements,state,created_at,competition_id)"
            + " VALUES(?,?,?,?,?,?,?,'QUEUED',?,?)",
        j.id(),
        j.ownerId(),
        key,
        j.districtId(),
        j.modelHash(),
        j.inputHash(),
        j.placements(),
        java.sql.Timestamp.from(j.createdAt()),
        competitionId);
  }
}
