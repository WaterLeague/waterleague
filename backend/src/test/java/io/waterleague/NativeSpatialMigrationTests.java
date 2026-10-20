package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.budget.repository.BudgetRepository;
import io.waterleague.installation.repository.InstallationRepository;
import io.waterleague.weekly.repository.WeeklySeasonRepository;
import io.waterleague.weekly.service.WeeklySeasonService;
import java.math.BigDecimal;
import java.util.*;
import java.util.concurrent.*;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
@ActiveProfiles("local")
class NativeSpatialMigrationTests extends PostgresIntegrationTest {
  @Autowired JdbcTemplate database;

  @Test
  void retiresOldSourcesPreservesInputsAndReleasesOriginalAllocationExactlyOnce() throws Exception {
    String name = "waterleague_native_test_" + UUID.randomUUID().toString().replace("-", "");
    String source = System.getProperty("waterleague.integration.jdbc");
    String url = source.substring(0, source.lastIndexOf('/') + 1) + name;
    var datasource =
        new DriverManagerDataSource(
            url, System.getenv("WL_INTEGRATION_USER"), System.getenv("WL_INTEGRATION_PASSWORD"));
    database.execute("CREATE DATABASE " + name);
    try {
      Flyway.configure().dataSource(datasource).target("29").load().migrate();
      var db = new JdbcTemplate(datasource);
      UUID owner = account(db, "2419953"), nativeOwner = account(db, "2410520");
      UUID old = installation(db, owner, "2419953", "G1", "a".repeat(64), "1234.56");
      var budget = new BudgetRepository(db);
      budget.allocate(old, owner, "SEOUL_RAINWATER", "ARCHIVED_POLICY");
      UUID historical = UUID.randomUUID(), running = UUID.randomUUID();
      db.update(
          "INSERT INTO"
              + " historical_experiments(id,owner_id,request_key,district_id,model_hash,input_hash,placements,state,created_at)"
              + " VALUES(?,?,?,'2419953',?,?,'[]','QUEUED',clock_timestamp())",
          historical,
          owner,
          UUID.randomUUID(),
          "a".repeat(64),
          "b".repeat(64));
      db.update(
          "INSERT INTO"
              + " shared_physics_jobs(id,installation_id,simulation_start,requested_through,state,lease_token,lease_until,created_at)"
              + " VALUES(?,?,clock_timestamp()-interval '2 hours',clock_timestamp()-interval '1"
              + " hour','RUNNING',?,clock_timestamp()+interval '1 hour',clock_timestamp())",
          running,
          old,
          UUID.randomUUID());
      UUID key = UUID.randomUUID();
      db.update(
          "INSERT INTO"
              + " historical_design_revisions(owner_id,event_id,revision,request_key,request_raw,snapshot_raw,snapshot_sha256,created_at)"
              + " VALUES(?,'seoul-20220808',1,?,'{}','{}',?,clock_timestamp())",
          owner,
          key,
          "c".repeat(64));
      var before =
          db.queryForMap(
              "SELECT cost,budget_policy,cost_snapshot,installed_at FROM shared_installations WHERE"
                  + " id=?",
              old);
      Flyway.configure().dataSource(datasource).load().migrate();
      UUID current =
          installation(
              db,
              nativeOwner,
              "11680",
              "C568718a66e486e3e9b27c6b0",
              "4ec7535e7cbaf41dc73f73519d77ba11f956f4c75c1a574fffa08f16625919b7",
              "2345.67");
      budget.allocate(current, nativeOwner, "SEOUL_RAINWATER", "ARCHIVED_POLICY");
      assertThat(
              db.queryForObject("SELECT district_id FROM accounts WHERE id=?", String.class, owner))
          .isEqualTo("11200");
      assertThat(
              db.queryForObject("SELECT member_type FROM accounts WHERE id=?", String.class, owner))
          .isEqualTo("PLAYER");
      assertThat(
              db.queryForMap(
                  "SELECT cost,budget_policy,cost_snapshot,installed_at FROM shared_installations"
                      + " WHERE id=?",
                  old))
          .isEqualTo(before);
      assertThat(new InstallationRepository(db).active())
          .extracting(i -> i.id())
          .containsExactly(current);
      assertThat(
              db.queryForObject(
                  "SELECT state FROM historical_experiments WHERE id=?", String.class, historical))
          .isEqualTo("REJECTED");
      assertThat(
              db.queryForObject(
                  "SELECT source_dataset FROM historical_experiments WHERE id=?",
                  String.class,
                  historical))
          .isEqualTo("PRE_NATIVE_20261020");
      assertThat(
              db.queryForObject(
                  "SELECT state FROM shared_physics_jobs WHERE id=?", String.class, running))
          .isEqualTo("FAILED");
      assertThat(
              db.queryForObject(
                  "SELECT error_code FROM shared_physics_jobs WHERE id=?", String.class, running))
          .isEqualTo("SPATIAL_SOURCE_RETIRED");
      db.update(
          "INSERT INTO"
              + " historical_design_revisions(owner_id,event_id,revision,request_key,request_raw,snapshot_raw,snapshot_sha256,created_at)"
              + " VALUES(?,'seoul-20220808',1,?,'{}','{}',?,clock_timestamp())",
          owner,
          UUID.randomUUID(),
          "d".repeat(64));
      assertThat(
              db.queryForList(
                  "SELECT source_dataset FROM historical_design_revisions ORDER BY source_dataset",
                  String.class))
          .containsExactly("PRE_NATIVE_20261020", "SEOUL_NGII_GAME_V2");
      var seasons = new WeeklySeasonService(new WeeklySeasonRepository(db), budget);
      var transaction = new TransactionTemplate(new DataSourceTransactionManager(datasource));
      var gate = new CountDownLatch(1);
      try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
        var tasks = new ArrayList<Future<?>>();
        for (int i = 0; i < 2; i++)
          tasks.add(
              executor.submit(
                  () -> {
                    gate.await();
                    transaction.executeWithoutResult(status -> seasons.closeOwner(owner));
                    return null;
                  }));
        gate.countDown();
        for (var task : tasks) task.get(20, TimeUnit.SECONDS);
      }
      assertThat(budget.allocatedByFacility(owner).values()).allMatch(value -> value.signum() == 0);
      assertThat(
              db.queryForObject(
                  "SELECT COUNT(*) FROM budget_ledger_entries WHERE installation_id=? AND"
                      + " event_type='RELEASE'",
                  Integer.class,
                  old))
          .isEqualTo(1);
      assertThat(
              db.queryForObject(
                  "SELECT amount_krw FROM budget_ledger_entries WHERE installation_id=? AND"
                      + " event_type='RELEASE'",
                  BigDecimal.class,
                  old))
          .isEqualByComparingTo("1234.56");
      assertThat(budget.allocatedByFacility(nativeOwner).values())
          .containsExactly(new BigDecimal("2345.67"));
    } finally {
      database.execute("DROP DATABASE " + name + " WITH (FORCE)");
    }
  }

  private UUID account(JdbcTemplate db, String district) {
    UUID id = UUID.randomUUID();
    db.update(
        "INSERT INTO"
            + " accounts(id,username,display_name,password_hash,role,member_type,approval_status,enabled,created_at,district_id,affiliation_type)"
            + " VALUES(?,?,?,'NOT_A_LOGIN','MEMBER','PLAYER','APPROVED',true,clock_timestamp(),?,'AFFILIATED')",
        id,
        "native_" + id.toString().substring(0, 8),
        "공간 전환 시험",
        district);
    return id;
  }

  private UUID installation(
      JdbcTemplate db, UUID owner, String district, String cell, String hash, String cost) {
    UUID id = UUID.randomUUID();
    db.update(
        "INSERT INTO"
            + " shared_installations(id,occupied_site,district_id,cell_id,owner_id,model_hash,facility_type,area_m2,cost,installed_at,season_ends_at,budget_policy,cost_snapshot,cost_snapshot_sha256)"
            + " VALUES(?,?,?,?,?,?,'PERMEABLE_PAVEMENT',1,?,clock_timestamp()-interval '1"
            + " hour',clock_timestamp()+interval '7"
            + " days','{\"rule\":\"ARCHIVED_POLICY\"}','{\"original\":true}',?)",
        id,
        owner + ":" + district + ":" + cell,
        district,
        cell,
        owner,
        hash,
        new BigDecimal(cost),
        "f".repeat(64));
    return id;
  }
}
