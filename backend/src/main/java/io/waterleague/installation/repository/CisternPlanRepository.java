package io.waterleague.installation.repository;

import io.waterleague.installation.entity.CisternPlan;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.*;
import org.springframework.stereotype.Repository;

@Repository
public class CisternPlanRepository {
  private final JdbcTemplate db;
  private final RowMapper<CisternPlan> mapper =
      (r, n) ->
          new CisternPlan(
              r.getObject("id", UUID.class),
              r.getObject("owner_id", UUID.class),
              r.getString("input_hash"),
              r.getString("snapshot_text"),
              r.getTimestamp("created_at").toInstant());

  public CisternPlanRepository(JdbcTemplate db) {
    this.db = db;
  }

  public List<CisternPlan> owned(UUID owner) {
    return db.query(
        "SELECT * FROM cistern_map_plans WHERE source_dataset='SEOUL_NGII_GAME_V2' AND owner_id=?"
            + " AND deleted_at IS NULL ORDER BY created_at DESC,id LIMIT 20",
        mapper,
        owner);
  }

  public void add(CisternPlan value) {
    db.update(
        "INSERT INTO cistern_map_plans(id,owner_id,input_hash,snapshot_text,created_at)"
            + " VALUES(?,?,?,?,?)",
        value.id(),
        value.ownerId(),
        value.inputHash(),
        value.snapshot(),
        Timestamp.from(value.createdAt()));
  }

  public boolean occupied(String district, String roof, String ground) {
    return Boolean.TRUE.equals(
        db.queryForObject(
            "SELECT EXISTS(SELECT 1 FROM shared_installations WHERE district_id=? AND cell_id IN"
                + " (?,?) AND source_retired_at IS NULL AND removed_at IS NULL)",
            Boolean.class,
            district,
            roof,
            ground));
  }

  public boolean remove(UUID owner, UUID id) {
    return db.update(
            "UPDATE cistern_map_plans SET deleted_at=? WHERE source_dataset='SEOUL_NGII_GAME_V2'"
                + " AND owner_id=? AND id=? AND deleted_at IS NULL",
            Timestamp.from(Instant.now()),
            owner,
            id)
        == 1;
  }
}
