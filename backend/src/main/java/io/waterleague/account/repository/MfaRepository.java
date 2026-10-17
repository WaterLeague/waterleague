package io.waterleague.account.repository;

import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class MfaRepository {
  private final JdbcTemplate db;

  public MfaRepository(JdbcTemplate db) {
    this.db = db;
  }

  public Optional<String> encrypted(UUID id) {
    return db
        .query(
            "SELECT encrypted_secret FROM account_mfa WHERE account_id=?",
            (rs, n) -> rs.getString(1),
            id)
        .stream()
        .findFirst();
  }

  public boolean consume(UUID id, long counter) {
    return db.update(
            "UPDATE account_mfa SET last_counter=? WHERE account_id=? AND last_counter<?",
            counter,
            id,
            counter)
        == 1;
  }

  public void provision(UUID id, String encrypted) {
    db.update("DELETE FROM account_mfa WHERE account_id=?", id);
    db.update(
        "INSERT INTO account_mfa(account_id,encrypted_secret,last_counter) VALUES(?,?,-1)",
        id,
        encrypted);
  }

  public void lock(UUID id) {
    db.queryForObject("SELECT id FROM accounts WHERE id=? FOR UPDATE", UUID.class, id);
  }

  public boolean confirmed(UUID id) {
    return db.queryForObject(
            "SELECT COUNT(*) FROM account_mfa WHERE account_id=? AND confirmed=true",
            Integer.class,
            id)
        > 0;
  }

  public void confirm(UUID id, boolean confirmed) {
    db.update("UPDATE account_mfa SET confirmed=? WHERE account_id=?", confirmed, id);
  }
}
