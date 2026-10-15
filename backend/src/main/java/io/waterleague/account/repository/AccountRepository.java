package io.waterleague.account.repository;

import io.waterleague.account.entity.Account;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class AccountRepository {
  private final JdbcTemplate db;

  public AccountRepository(JdbcTemplate db) {
    this.db = db;
  }

  public Optional<Account> byUsername(String name) {
    return db
        .query(
            "SELECT * FROM accounts WHERE username=?",
            (rs, n) ->
                new Account(
                    rs.getObject("id", UUID.class),
                    rs.getString("username"),
                    rs.getString("display_name"),
                    rs.getString("password_hash"),
                    rs.getString("role"),
                    rs.getObject("organization_id", UUID.class),
                    rs.getBoolean("enabled")),
            name)
        .stream()
        .findFirst();
  }

  public void add(Account a) {
    db.update(
        "INSERT INTO"
            + " accounts(id,username,display_name,password_hash,role,organization_id,created_at)"
            + " VALUES(?,?,?,?,?,?,?)",
        a.id(),
        a.username(),
        a.displayName(),
        a.passwordHash(),
        a.role(),
        a.organizationId(),
        java.sql.Timestamp.from(Instant.now()));
  }
}
