package io.waterleague.account.repository;

import io.waterleague.account.entity.Account;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.*;
import org.springframework.stereotype.Repository;

@Repository
public class AccountRepository {
  private final JdbcTemplate db;
  private final RowMapper<Account> mapper =
      (rs, n) ->
          new Account(
              rs.getObject("id", UUID.class),
              rs.getString("username"),
              rs.getString("display_name"),
              rs.getString("password_hash"),
              rs.getString("role"),
              rs.getString("member_type"),
              rs.getString("approval_status"),
              rs.getObject("organization_id", UUID.class),
              rs.getString("requested_organization_name"),
              rs.getString("application_purpose"),
              rs.getBoolean("enabled"),
              rs.getString("district_id"),
              rs.getString("affiliation_type"));

  public AccountRepository(JdbcTemplate db) {
    this.db = db;
  }

  public Optional<Account> byUsername(String name) {
    return db.query("SELECT * FROM accounts WHERE username=?", mapper, name).stream().findFirst();
  }

  public Optional<Account> byId(UUID id) {
    return db.query("SELECT * FROM accounts WHERE id=?", mapper, id).stream().findFirst();
  }

  public void add(Account a) {
    db.update(
        "INSERT INTO"
            + " accounts(id,username,display_name,password_hash,role,member_type,approval_status,organization_id,requested_organization_name,application_purpose,enabled,admin_slot,created_at,district_id,affiliation_type)"
            + " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        a.id(),
        a.username(),
        a.displayName(),
        a.passwordHash(),
        a.role(),
        a.memberType(),
        a.approvalStatus(),
        a.organizationId(),
        a.organizationName(),
        a.applicationPurpose(),
        a.enabled(),
        a.role().equals("ADMIN") ? 1 : null,
        java.sql.Timestamp.from(Instant.now()),
        a.districtId(),
        a.affiliationType());
  }

  public boolean selectDistrict(UUID id, String district, String type) {
    return db.update(
            "UPDATE accounts SET district_id=?,affiliation_type=? WHERE id=? AND district_id IS"
                + " NULL AND role='MEMBER' AND approval_status='APPROVED' AND enabled=TRUE",
            district,
            type,
            id)
        == 1;
  }

  public Account lock(UUID id) {
    return db.query("SELECT * FROM accounts WHERE id=? FOR UPDATE", mapper, id).stream()
        .findFirst()
        .orElseThrow(
            () ->
                new io.waterleague.common.exception.DomainException(
                    io.waterleague.common.exception.ErrorCode.AUTHENTICATION_REQUIRED));
  }
}
