package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.dto.RegistrationRequest;
import io.waterleague.account.entity.MemberType;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.account.service.*;
import io.waterleague.notification.repository.NotificationRepository;
import java.util.UUID;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
@ActiveProfiles("local")
class DeploymentRuntimeTests extends PostgresIntegrationTest {
  @Autowired JdbcTemplate db;
  @Autowired AccountService auth;
  @Autowired AccountRepository accounts;
  @Autowired NotificationRepository outbox;
  @Autowired PasswordEncoder encoder;
  @Autowired TransactionTemplate tx;
  @Autowired Environment env;

  @Test
  void registrationRollbackClaimsAndLeaseFencingPreserveExactlyOneEvent() throws Exception {
    db.execute("TRUNCATE notification_outbox");
    String name = "notice_" + UUID.randomUUID().toString().substring(0, 8);
    var registration =
        new RegistrationRequest(
            name, "example-password-for-tests", MemberType.PLAYER, "", "", "11680", "RESIDENT");
    tx.executeWithoutResult(
        status -> {
          auth.register(registration);
          status.setRollbackOnly();
        });
    assertThat(accounts.byUsername(name)).isEmpty();
    assertThat(outbox.claim()).isEmpty();
    var member = auth.register(registration);
    assertThat(
            db.queryForObject(
                "SELECT count(*) FROM notification_outbox WHERE source_id=?",
                Integer.class,
                member.id()))
        .isEqualTo(1);
    try (var executor = Executors.newFixedThreadPool(2)) {
      var a = executor.submit(() -> outbox.claim());
      var b = executor.submit(() -> outbox.claim());
      var claims =
          java.util.stream.Stream.of(a.get(), b.get()).flatMap(java.util.Optional::stream).toList();
      assertThat(claims).hasSize(1);
      var old = claims.getFirst();
      db.update(
          "UPDATE notification_outbox SET available_at=CURRENT_TIMESTAMP WHERE id=?", old.id());
      var current = outbox.claim().orElseThrow();
      outbox.finish(old, true, false, 1, "HTTP_200");
      assertThat(
              db.queryForObject(
                  "SELECT delivered_at IS NULL FROM notification_outbox WHERE id=?",
                  Boolean.class,
                  old.id()))
          .isTrue();
      outbox.finish(current, true, false, 1, "HTTP_200");
      assertThat(outbox.claim()).isEmpty();
    }
  }

  @Test
  void administratorIsUniqueMfaRequiredAndPasswordRotationIsAudited() {
    var provision = new DeploymentAdminProvisioning(accounts, db, tx, encoder, env, null);
    String username = "deploy_admin";
    provision.provision(username, "initial-admin-password-test");
    var before = accounts.byUsername(username).orElseThrow();
    assertThat(before.requiresMfa()).isTrue();
    assertThat(
            db.queryForObject(
                "SELECT count(*) FROM account_mfa WHERE account_id=?", Integer.class, before.id()))
        .isZero();
    provision.provision(username, "initial-admin-password-test");
    assertThat(accounts.byUsername(username).orElseThrow().passwordHash())
        .isEqualTo(before.passwordHash());
    assertThatThrownBy(() -> provision.provision("another_admin", "other-admin-password-test"))
        .hasMessage("ADMIN_IDENTITY_CONFLICT");
    provision.provision(username, "rotated-admin-password-test");
    assertThat(
            encoder.matches(
                "rotated-admin-password-test",
                accounts.byUsername(username).orElseThrow().passwordHash()))
        .isTrue();
    assertThat(db.queryForObject("SELECT count(*) FROM accounts WHERE role='ADMIN'", Integer.class))
        .isEqualTo(1);
    assertThat(
            db.queryForObject(
                "SELECT count(*) FROM audit_events WHERE action='ADMIN_PASSWORD_ROTATED' AND"
                    + " actor_id=?",
                Integer.class,
                before.id()))
        .isEqualTo(1);
    assertThat(
            db.queryForObject(
                "SELECT count(*) FROM notification_outbox WHERE source_id=?",
                Integer.class,
                before.id()))
        .isZero();
  }
}
