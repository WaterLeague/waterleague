package io.waterleague.weekly.repository;

import java.sql.Timestamp;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.*;
import org.springframework.jdbc.core.*;
import org.springframework.stereotype.Repository;

@Repository
public class WeeklySeasonRepository {
  private final JdbcTemplate db;
  private final String clockSql;

  public WeeklySeasonRepository(JdbcTemplate db) {
    this.db = db;
    var database =
        db.execute((ConnectionCallback<String>) c -> c.getMetaData().getDatabaseProductName());
    // 예산 잠금 대기 중 주가 바뀌어도 확정 시각으로 시즌을 결정한다.
    clockSql =
        "PostgreSQL".equals(database) ? "SELECT clock_timestamp()" : "SELECT CURRENT_TIMESTAMP";
  }

  public Instant now() {
    return db.queryForObject(clockSql, Timestamp.class).toInstant();
  }

  public List<UUID> dueOwners() {
    return db.query(
        "SELECT DISTINCT owner_id FROM shared_installations WHERE removed_at IS NULL AND"
            + " season_ends_at<=CURRENT_TIMESTAMP ORDER BY owner_id LIMIT 250",
        (r, n) -> r.getObject("owner_id", UUID.class));
  }

  public List<UUID> lockExpired(UUID owner, Instant at) {
    // JDBC의 마이크로초 반올림으로 시즌 종료 전에 예산이 반환되지 않도록 내림한다.
    return db.query(
        "SELECT id FROM shared_installations WHERE owner_id=? AND removed_at IS NULL AND"
            + " season_ends_at<=? ORDER BY id FOR UPDATE",
        (r, n) -> r.getObject("id", UUID.class),
        owner,
        Timestamp.from(at.truncatedTo(ChronoUnit.MICROS)));
  }

  public void close(UUID id) {
    db.update(
        "UPDATE shared_installations SET removed_at=season_ends_at,occupied_site=NULL WHERE id=?"
            + " AND removed_at IS NULL",
        id);
  }
}
