package io.waterleague.account.service;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import java.util.UUID;
import org.springframework.boot.*;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

@Component
@Profile("bootstrap-admin")
public class DeploymentAdminProvisioning implements ApplicationRunner {
  private final AccountRepository accounts;
  private final JdbcTemplate db;
  private final TransactionTemplate tx;
  private final PasswordEncoder passwords;
  private final Environment env;
  private final ConfigurableApplicationContext context;

  public DeploymentAdminProvisioning(
      AccountRepository accounts,
      JdbcTemplate db,
      TransactionTemplate tx,
      PasswordEncoder passwords,
      Environment env,
      ConfigurableApplicationContext context) {
    this.accounts = accounts;
    this.db = db;
    this.tx = tx;
    this.passwords = passwords;
    this.env = env;
    this.context = context;
  }

  public void run(ApplicationArguments args) {
    provision(
        env.getProperty("waterleague.admin-username", ""),
        env.getProperty("waterleague.admin-password", ""));
    SpringApplication.exit(context, () -> 0);
  }

  public void provision(String username, String password) {
    if (!username.matches("[a-z0-9_]{4,32}") || password.length() < 16 || password.length() > 128)
      throw new IllegalStateException("ADMIN_CONFIGURATION_INVALID");
    tx.executeWithoutResult(
        status -> {
          db.execute("SELECT pg_advisory_xact_lock(745092021)");
          var admins =
              db.queryForList("SELECT username FROM accounts WHERE role='ADMIN'", String.class);
          if (!admins.isEmpty() && (admins.size() != 1 || !admins.getFirst().equals(username)))
            throw new IllegalStateException("ADMIN_IDENTITY_CONFLICT");
          var existing = accounts.byUsername(username);
          if (existing.isPresent()) {
            var admin = existing.get();
            if (!admin.role().equals("ADMIN") || !admin.usable())
              throw new IllegalStateException("ADMIN_IDENTITY_CONFLICT");
            if (!passwords.matches(password, admin.passwordHash())) {
              db.update(
                  "UPDATE accounts SET password_hash=? WHERE id=?",
                  passwords.encode(password),
                  admin.id());
              db.update("DELETE FROM spring_session WHERE principal_name=?", username);
              audit(admin.id(), "ADMIN_PASSWORD_ROTATED");
            }
            return;
          }
          UUID id = UUID.randomUUID();
          accounts.add(
              new Account(
                  id,
                  username,
                  "관리자",
                  passwords.encode(password),
                  "ADMIN",
                  null,
                  "APPROVED",
                  null,
                  "",
                  "",
                  true));
          // 인증 앱 비밀은 CI에서 생성하지 않고 첫 로그인 시 본인이 등록한다.
          audit(id, "ADMIN_BOOTSTRAPPED");
        });
  }

  private void audit(UUID id, String action) {
    db.update(
        "INSERT INTO audit_events(id,actor_id,action,object_id,created_at)"
            + " VALUES(?,?,?,?,CURRENT_TIMESTAMP)",
        UUID.randomUUID(),
        id,
        action,
        id);
  }
}
