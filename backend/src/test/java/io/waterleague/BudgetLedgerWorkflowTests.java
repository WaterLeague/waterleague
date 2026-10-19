package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.budget.service.BudgetService;
import io.waterleague.common.exception.DomainException;
import io.waterleague.common.service.JsonService;
import io.waterleague.installation.dto.InstallRequest;
import io.waterleague.installation.service.InstallationService;
import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.net.*;
import java.net.http.*;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.*;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("local")
class BudgetLedgerWorkflowTests extends PostgresIntegrationTest {
  @DynamicPropertySource
  static void database(DynamicPropertyRegistry r) {
    if (System.getProperty("waterleague.integration.jdbc") == null)
      throw new IllegalStateException("전용 임시 DB 필요");
    SharedInstallationTests.integrationDatabase(r);
  }

  @Value("${local.server.port}")
  int port;

  @Autowired AccountRepository accounts;
  @Autowired PasswordEncoder passwords;
  @Autowired InstallationService installations;
  @Autowired io.waterleague.weekly.service.WeeklySeasonService seasons;
  @Autowired io.waterleague.installation.repository.SiteCatalogRepository sites;
  @Autowired BudgetService budget;
  @Autowired JdbcTemplate db;
  @Autowired JsonService json;
  @Autowired PlatformTransactionManager manager;

  record Actor(Account account, HttpClient client) {}

  @BeforeEach
  void clear() {
    db.update("DELETE FROM shared_weekly_scores");
    db.update("DELETE FROM shared_physics_jobs");
    db.update("DELETE FROM budget_ledger_entries");
    db.update("DELETE FROM shared_installations");
  }

  Actor actor() throws Exception {
    var id = UUID.randomUUID();
    var name = "budget_" + id.toString().substring(0, 8);
    var account =
        new Account(
            id,
            name,
            name,
            passwords.encode("budget-test-1234"),
            "MEMBER",
            "PLAYER",
            "APPROVED",
            null,
            "",
            "",
            true,
            "2410520",
            "AFFILIATED");
    accounts.add(account);
    var actor =
        new Actor(
            account,
            HttpClient.newBuilder()
                .cookieHandler(new CookieManager(null, CookiePolicy.ACCEPT_ALL))
                .build());
    var csrf = json.tree(get(actor, "/auth/csrf").body()).path("token").asString();
    var login =
        HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/v1/auth/login"))
            .header("X-CSRF-TOKEN", csrf)
            .header("Content-Type", "application/json")
            .POST(
                HttpRequest.BodyPublishers.ofString(
                    json.write(Map.of("username", name, "password", "budget-test-1234"))))
            .build();
    assertThat(actor.client().send(login, HttpResponse.BodyHandlers.ofString()).statusCode())
        .isEqualTo(200);
    return actor;
  }

  HttpResponse<String> get(Actor actor, String path) throws Exception {
    return actor
        .client()
        .send(
            HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/v1" + path))
                .build(),
            HttpResponse.BodyHandlers.ofString());
  }

  InstallRequest request(String cell) {
    return new InstallRequest(
        "2410520", cell, FacilityType.PERMEABLE_PAVEMENT, new BigDecimal("20"));
  }

  @Test
  void ledgerIsPrivatePagedAndFrozenAcrossRelease() throws Exception {
    var a = actor();
    var b = actor();
    var anon = new Actor(null, HttpClient.newHttpClient());
    assertThat(get(anon, "/budget/ledger").statusCode()).isEqualTo(401);
    var candidates =
        sites.district("2410520").values().stream()
            .filter(
                site ->
                    site.allowedTypes().contains("PERMEABLE_PAVEMENT")
                        && site.existingInfrastructure() == null
                        && site.maxAreaM2().compareTo(new BigDecimal("20")) >= 0)
            .limit(26)
            .toList();
    assertThat(candidates).hasSize(26);
    for (var site : candidates)
      installations.install(a.account().username(), request(site.cellId()));
    seasons.closeOwnerAt(a.account().id(), installations.active().getFirst().seasonEndsAt());
    var response = get(a, "/budget/ledger");
    assertThat(response.statusCode()).isEqualTo(200);
    assertThat(response.headers().firstValue("Cache-Control")).contains("no-store");
    var page = json.tree(response.body());
    assertThat(page.path("entries").size()).isEqualTo(50);
    assertThat(page.path("entries").get(0).path("eventType").asString()).isEqualTo("RELEASE");
    assertThat(
            page.path("entries").get(0).path("sourceBudgetPolicy").path("ruleVersion").asString())
        .isEqualTo("SEOUL_PERSONAL_FULL_2026_V3");
    var older =
        json.tree(get(a, "/budget/ledger?beforeId=" + page.path("nextBeforeId").asString()).body());
    assertThat(older.path("entries").size()).isEqualTo(2);
    assertThat(older.path("nextBeforeId").isNull()).isTrue();
    assertThat(
            json.tree(get(b, "/budget/ledger?ownerId=" + a.account().id()).body())
                .path("entries")
                .isEmpty())
        .isTrue();
    assertThat(get(a, "/budget/ledger?beforeId=-1").statusCode()).isEqualTo(400);
    assertThat(budget.view(a.account().id()).allocatedKrw()).isZero();
    assertThat(budget.view(a.account().id()).remainingKrw()).isEqualByComparingTo("2000000000");
    assertThat(budget.view(a.account().id()).accounting().facilities())
        .allSatisfy(
            f -> {
              assertThat(f.limitKrw()).isNull();
              assertThat(f.allocatedKrw()).isZero();
            });
  }

  @Test
  void failuresRollbackAndConcurrentSeasonExpiryOnlyReleasesOnce() throws Exception {
    var a = actor();
    var b = actor();
    var tx = new TransactionTemplate(manager);
    assertThatThrownBy(
            () ->
                tx.execute(
                    status -> {
                      installations.install(a.account().username(), request("G1"));
                      throw new IllegalStateException("검사 롤백");
                    }))
        .isInstanceOf(IllegalStateException.class);
    assertThat(budget.history(a.account().id(), null).entries()).isEmpty();
    assertThat(installations.active()).isEmpty();
    var installed = installations.install(a.account().username(), request("G1"));
    assertThatThrownBy(() -> installations.install(a.account().username(), request("G1")))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> installations.remove(b.account().username(), installed.id()))
        .isInstanceOf(DomainException.class);
    assertThat(budget.history(b.account().id(), null).entries()).isEmpty();
    var start = new CountDownLatch(1);
    try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
      var futures = new ArrayList<Future<Boolean>>();
      for (int n = 0; n < 2; n++)
        futures.add(
            executor.submit(
                () -> {
                  start.await();
                  try {
                    seasons.closeOwnerAt(a.account().id(), installed.seasonEndsAt());
                    return true;
                  } catch (DomainException e) {
                    return false;
                  }
                }));
      start.countDown();
      assertThat(
              List.of(
                  futures.get(0).get(10, TimeUnit.SECONDS),
                  futures.get(1).get(10, TimeUnit.SECONDS)))
          .containsExactly(true, true);
    }
    var entries = budget.history(a.account().id(), null).entries();
    assertThat(entries).hasSize(2);
    assertThat(entries.get(0).amountKrw()).isEqualByComparingTo(entries.get(1).amountKrw());
    assertThat(budget.view(a.account().id()).remainingKrw()).isEqualByComparingTo("2000000000");
  }

  @Test
  void publicSiteListsBothMembersWithMissingScoreDistinctFromZero() throws Exception {
    var a = actor();
    var b = actor();
    var one = installations.install(a.account().username(), request("G1"));
    var two = installations.install(b.account().username(), request("G1"));
    var anonymous = new Actor(null, HttpClient.newHttpClient());
    var response = get(anonymous, "/weekly/sites/2410520/G1");
    assertThat(response.statusCode()).isEqualTo(200);
    assertThat(response.body()).contains(one.id().toString(), two.id().toString());
    var page = json.tree(response.body());
    assertThat(page.path("installations").size()).isEqualTo(2);
    for (var row : page.path("installations")) {
      assertThat(row.path("scoreM3").isNull()).isTrue();
      assertThat(row.path("seasonEndsAt").asString()).isEqualTo(one.seasonEndsAt().toString());
    }
    assertThat(response.body()).doesNotContain("password", "sourceBudgetPolicy", "costSnapshot");
    assertThat(get(anonymous, "/weekly/sites/2410520/G1?after=invalid").statusCode())
        .isEqualTo(400);
  }

  @Test
  void memberSeasonMigrationPreservesInputsCostsAndPastRemoval() throws Exception {
    String schema = "season_upgrade_" + UUID.randomUUID().toString().replace("-", "");
    try (var connection = Objects.requireNonNull(db.getDataSource()).getConnection();
        var sql = connection.createStatement()) {
      String original = connection.getSchema();
      sql.execute("CREATE SCHEMA " + schema);
      try {
        connection.setSchema(schema);
        sql.execute(
            "CREATE TABLE shared_installations(id UUID PRIMARY KEY,occupied_site VARCHAR(64)"
                + " UNIQUE,owner_id UUID,district_id VARCHAR(30),cell_id VARCHAR(20),installed_at"
                + " TIMESTAMP WITH TIME ZONE,removed_at TIMESTAMP WITH TIME ZONE,cost"
                + " NUMERIC(14,2),budget_policy TEXT,model_hash VARCHAR(64),CHECK((removed_at IS"
                + " NULL AND occupied_site=district_id || ':' || cell_id AND occupied_site IS NOT"
                + " NULL) OR (removed_at IS NOT NULL AND occupied_site IS NULL)))");
        var owner = UUID.randomUUID();
        var active = UUID.randomUUID();
        try (var insert =
            connection.prepareStatement(
                "INSERT INTO shared_installations"
                    + " VALUES(?,?,?,?,?,'2025-01-01T00:00:00Z',?,1234.56,?,?)")) {
          for (int n = 0; n < 2; n++) {
            insert.setObject(1, n == 0 ? active : UUID.randomUUID());
            insert.setString(2, n == 0 ? "D:G1" : null);
            insert.setObject(3, owner);
            insert.setString(4, "D");
            insert.setString(5, "G1");
            insert.setObject(
                6, n == 0 ? null : java.time.OffsetDateTime.parse("2025-02-01T00:00:00Z"));
            insert.setString(7, "{\"rule\":\"OLD_POLICY\"}");
            insert.setString(8, "a".repeat(64));
            insert.executeUpdate();
          }
        }
        new db.migration.V25__weekly_member_seasons()
            .migrate(
                new org.flywaydb.core.api.migration.Context() {
                  public org.flywaydb.core.api.configuration.Configuration getConfiguration() {
                    return null;
                  }

                  public java.sql.Connection getConnection() {
                    return connection;
                  }
                });
        try (var rows =
            sql.executeQuery(
                "SELECT * FROM shared_installations ORDER BY removed_at NULLS FIRST")) {
          assertThat(rows.next()).isTrue();
          assertThat(rows.getObject("id", UUID.class)).isEqualTo(active);
          assertThat(rows.getString("occupied_site")).isEqualTo(owner + ":D:G1");
          assertThat(rows.getTimestamp("season_ends_at").toInstant())
              .isEqualTo(
                  io.waterleague.weekly.service.WeeklySeasonService.endFor(
                      java.time.Instant.now()));
          assertThat(rows.getTimestamp("installed_at").toInstant())
              .isEqualTo(java.time.Instant.parse("2025-01-01T00:00:00Z"));
          assertThat(rows.getBigDecimal("cost")).isEqualByComparingTo("1234.56");
          assertThat(rows.getString("budget_policy")).isEqualTo("{\"rule\":\"OLD_POLICY\"}");
          assertThat(rows.getString("model_hash")).isEqualTo("a".repeat(64));
          assertThat(rows.next()).isTrue();
          assertThat(rows.getTimestamp("removed_at").toInstant())
              .isEqualTo(java.time.Instant.parse("2025-02-01T00:00:00Z"));
          assertThat(rows.getTimestamp("season_ends_at")).isNull();
          assertThat(rows.getString("occupied_site")).isNull();
        }
      } finally {
        connection.setSchema(original);
        sql.execute("DROP SCHEMA " + schema + " CASCADE");
      }
    }
  }

  @Test
  void migrationPreservesLegacyCostsPoliciesAndCancellationTimes() throws Exception {
    String schema = "budget_upgrade_" + UUID.randomUUID().toString().replace("-", "");
    try (var connection = java.util.Objects.requireNonNull(db.getDataSource()).getConnection();
        var sql = connection.createStatement()) {
      String originalSchema = connection.getSchema();
      sql.execute("CREATE SCHEMA " + schema);
      try {
        connection.setSchema(schema);
        sql.execute("CREATE TABLE accounts(id UUID PRIMARY KEY)");
        sql.execute(
            "CREATE TABLE shared_installations(id UUID PRIMARY KEY,owner_id UUID,facility_type"
                + " VARCHAR(30),cost NUMERIC(14,2),installed_at TIMESTAMP WITH TIME ZONE,removed_at"
                + " TIMESTAMP WITH TIME ZONE,budget_policy TEXT)");
        var owner = UUID.randomUUID();
        try (var insert = connection.prepareStatement("INSERT INTO accounts VALUES(?)")) {
          insert.setObject(1, owner);
          insert.executeUpdate();
        }
        try (var insert =
            connection.prepareStatement(
                "INSERT INTO shared_installations VALUES(?,?,?,?,'2025-01-01T00:00:00Z',?,?)")) {
          for (int n = 0; n < 2; n++) {
            insert.setObject(1, UUID.randomUUID());
            insert.setObject(2, owner);
            insert.setString(3, n == 0 ? "RAIN_GARDEN" : "GREEN_ROOF");
            insert.setBigDecimal(4, new BigDecimal(n == 0 ? "1000.25" : "500.50"));
            insert.setObject(
                5, n == 0 ? java.time.OffsetDateTime.parse("2025-02-01T00:00:00Z") : null);
            insert.setString(6, n == 0 ? "{\"ruleVersion\":\"TEST_OLD_POLICY\"}" : null);
            insert.executeUpdate();
          }
        }
        org.springframework.jdbc.datasource.init.ScriptUtils.executeSqlScript(
            connection,
            new org.springframework.core.io.ClassPathResource(
                "db/migration/V17__budget_ledger.sql"));
        try (var result =
            sql.executeQuery(
                "SELECT count(*),sum(CASE WHEN event_type='ALLOCATE' THEN amount_krw ELSE"
                    + " -amount_krw END) FROM budget_ledger_entries")) {
          result.next();
          assertThat(result.getInt(1)).isEqualTo(3);
          assertThat(result.getBigDecimal(2)).isEqualByComparingTo("500.50");
        }
        try (var result =
            sql.executeQuery(
                "SELECT count(*) FROM budget_ledger_entries e JOIN shared_installations i ON"
                    + " i.id=e.installation_id WHERE e.amount_krw=i.cost AND e.source_budget_policy"
                    + " IS NOT DISTINCT FROM i.budget_policy AND e.provenance='LEGACY_IMPORT' AND"
                    + " e.effective_at=CASE WHEN e.event_type='ALLOCATE' THEN i.installed_at ELSE"
                    + " i.removed_at END")) {
          result.next();
          assertThat(result.getInt(1)).isEqualTo(3);
        }
        try (var result = sql.executeQuery("SELECT count(*),sum(cost) FROM shared_installations")) {
          result.next();
          assertThat(result.getInt(1)).isEqualTo(2);
          assertThat(result.getBigDecimal(2)).isEqualByComparingTo("1500.75");
        }
      } finally {
        connection.setSchema(originalSchema);
        sql.execute("DROP SCHEMA " + schema + " CASCADE");
      }
    }
  }
}
