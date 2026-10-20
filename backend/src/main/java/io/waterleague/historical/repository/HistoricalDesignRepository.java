package io.waterleague.historical.repository;

import io.waterleague.historical.entity.HistoricalDesign;
import java.util.*;
import org.springframework.jdbc.core.*;
import org.springframework.stereotype.Repository;

@Repository
public class HistoricalDesignRepository {
  private final JdbcTemplate db;
  private final RowMapper<HistoricalDesign> mapper =
      (r, n) ->
          new HistoricalDesign(
              r.getObject("owner_id", UUID.class),
              r.getString("event_id"),
              r.getLong("revision"),
              r.getObject("request_key", UUID.class),
              r.getString("request_raw"),
              r.getString("snapshot_raw"),
              r.getString("snapshot_sha256"),
              r.getTimestamp("created_at").toInstant());

  public HistoricalDesignRepository(JdbcTemplate db) {
    this.db = db;
  }

  public Optional<HistoricalDesign> latest(UUID owner, String event) {
    return db
        .query(
            "SELECT * FROM historical_design_revisions WHERE source_dataset='SEOUL_NGII_GAME_V2'"
                + " AND owner_id=? AND event_id=? ORDER BY revision DESC LIMIT 1",
            mapper,
            owner,
            event)
        .stream()
        .findFirst();
  }

  public Optional<HistoricalDesign> byKey(UUID owner, UUID key) {
    return db
        .query(
            "SELECT * FROM historical_design_revisions WHERE source_dataset='SEOUL_NGII_GAME_V2'"
                + " AND owner_id=? AND request_key=?",
            mapper,
            owner,
            key)
        .stream()
        .findFirst();
  }

  public Optional<HistoricalDesign> revision(UUID owner, String event, long revision) {
    return db
        .query(
            "SELECT * FROM historical_design_revisions WHERE source_dataset='SEOUL_NGII_GAME_V2'"
                + " AND owner_id=? AND event_id=? AND revision=?",
            mapper,
            owner,
            event,
            revision)
        .stream()
        .findFirst();
  }

  public void add(HistoricalDesign value) {
    db.update(
        "INSERT INTO"
            + " historical_design_revisions(owner_id,event_id,revision,request_key,request_raw,snapshot_raw,snapshot_sha256,created_at)"
            + " VALUES(?,?,?,?,?,?,?,?)",
        value.ownerId(),
        value.eventId(),
        value.revision(),
        value.requestKey(),
        value.requestRaw(),
        value.snapshotRaw(),
        value.snapshotSha256(),
        java.sql.Timestamp.from(value.createdAt()));
  }
}
