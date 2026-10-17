package io.waterleague.strategy.repository;

import io.waterleague.strategy.entity.StrategyVersion;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.*;
import org.springframework.stereotype.Repository;

@Repository
public class StrategyRepository {
  private final JdbcTemplate db;
  private final RowMapper<StrategyVersion> mapper =
      (rs, n) ->
          new StrategyVersion(
              rs.getObject("id", UUID.class),
              rs.getObject("strategy_id", UUID.class),
              rs.getInt("revision"),
              rs.getString("model_hash"),
              rs.getString("input_hash"),
              rs.getString("placements"),
              rs.getString("events"),
              rs.getString("design_note"),
              rs.getBigDecimal("cost"),
              rs.getString("currency"),
              rs.getTimestamp("created_at").toInstant());

  public StrategyRepository(JdbcTemplate d) {
    db = d;
  }

  public boolean own(UUID id, UUID owner, boolean lock) {
    return !db.queryForList(
            "SELECT id FROM strategies WHERE id=? AND owner_id=?" + (lock ? " FOR UPDATE" : ""),
            id,
            owner)
        .isEmpty();
  }

  public void create(UUID id, UUID owner, String title) {
    db.update(
        "INSERT INTO strategies(id,owner_id,title,created_at) VALUES(?,?,?,?)",
        id,
        owner,
        title,
        Timestamp.from(Instant.now()));
  }

  public void rename(UUID id, String title) {
    db.update("UPDATE strategies SET title=? WHERE id=?", title, id);
  }

  public List<Map<String, Object>> list(UUID owner) {
    return db.query(
        "SELECT s.id,s.title,MAX(v.revision) revision,MAX(v.created_at) updated_at FROM strategies"
            + " s JOIN strategy_versions v ON v.strategy_id=s.id WHERE owner_id=? GROUP BY"
            + " s.id,s.title ORDER BY updated_at DESC LIMIT 100",
        (rs, n) ->
            Map.of(
                "id",
                rs.getObject("id"),
                "title",
                rs.getString("title"),
                "revision",
                rs.getInt("revision"),
                "updatedAt",
                rs.getTimestamp("updated_at").toInstant()),
        owner);
  }

  public String title(UUID id) {
    return db.queryForObject("SELECT title FROM strategies WHERE id=?", String.class, id);
  }

  public List<StrategyVersion> versions(UUID id) {
    return db.query(
        "SELECT * FROM strategy_versions WHERE strategy_id=? ORDER BY revision", mapper, id);
  }

  public Optional<StrategyVersion> version(UUID id, UUID owner) {
    return db
        .query(
            "SELECT v.* FROM strategy_versions v JOIN strategies s ON s.id=v.strategy_id WHERE"
                + " v.id=? AND s.owner_id=?",
            mapper,
            id,
            owner)
        .stream()
        .findFirst();
  }

  public void add(StrategyVersion v) {
    db.update(
        "INSERT INTO"
            + " strategy_versions(id,strategy_id,revision,model_hash,input_hash,placements,events,design_note,cost,currency,created_at)"
            + " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        v.id(),
        v.strategyId(),
        v.revision(),
        v.modelHash(),
        v.inputHash(),
        v.placements(),
        v.events(),
        v.designNote(),
        v.cost(),
        v.currency(),
        Timestamp.from(v.createdAt()));
  }
}
