package io.waterleague.physics.repository;

import io.waterleague.physics.entity.PhysicsJob;
import java.util.*;
import org.springframework.jdbc.core.*;
import org.springframework.stereotype.Repository;

@Repository
public class PhysicsRepository {
  private final JdbcTemplate db;
  private final RowMapper<PhysicsJob> mapper =
      (r, n) ->
          new PhysicsJob(
              r.getObject("id", UUID.class),
              r.getString("state"),
              r.getTimestamp("created_at").toInstant(),
              r.getTimestamp("lease_until") == null
                  ? null
                  : r.getTimestamp("lease_until").toInstant(),
              r.getTimestamp("finished_at") == null
                  ? null
                  : r.getTimestamp("finished_at").toInstant(),
              r.getTimestamp("requested_through").toInstant(),
              r.getString("result"),
              r.getString("error_code"));

  public PhysicsRepository(JdbcTemplate db) {
    this.db = db;
  }

  public Optional<PhysicsJob> latest(UUID installation) {
    return db
        .query(
            "SELECT * FROM shared_physics_jobs WHERE installation_id=? ORDER BY created_at DESC,id"
                + " DESC LIMIT 1",
            mapper,
            installation)
        .stream()
        .findFirst();
  }

  public Optional<PhysicsJob> completed(UUID installation) {
    return db
        .query(
            "SELECT * FROM shared_physics_jobs WHERE installation_id=? AND state='SUCCEEDED' ORDER"
                + " BY requested_through DESC,created_at DESC LIMIT 1",
            mapper,
            installation)
        .stream()
        .findFirst();
  }
}
