package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.weekly.service.WeeklyService;
import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.*;
import java.time.temporal.TemporalAdjusters;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("local")
class WeeklyWorkflowTests {
  @org.springframework.test.context.DynamicPropertySource
  static void database(org.springframework.test.context.DynamicPropertyRegistry registry) {
    SharedInstallationTests.integrationDatabase(registry);
  }

  @Autowired JdbcTemplate db;
  @Autowired AccountRepository accounts;
  @Autowired WeeklyService service;
  @Autowired io.waterleague.common.service.JsonService json;
  LocalDate week;
  Instant end;

  @BeforeEach
  void prepare() {
    db.update("DELETE FROM shared_weekly_scores");
    db.update("DELETE FROM shared_physics_jobs");
    db.update("DELETE FROM budget_ledger_entries");
    db.update("DELETE FROM shared_installations");
    week =
        LocalDate.now(ZoneId.of("Asia/Seoul"))
            .with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))
            .minusWeeks(1);
    end = week.plusWeeks(1).atStartOfDay(ZoneId.of("Asia/Seoul")).toInstant();
  }

  UUID contribution(String district, String name, String score, int minutes) {
    UUID owner = UUID.randomUUID(), installation = UUID.randomUUID(), job = UUID.randomUUID();
    accounts.add(
        new Account(
            owner,
            name,
            "시험 " + name,
            "NOT_A_LOGIN",
            "MEMBER",
            "PLAYER",
            "APPROVED",
            null,
            "",
            "",
            true,
            district,
            "AFFILIATED"));
    db.update(
        """
        INSERT INTO shared_installations(id,district_id,cell_id,owner_id,model_hash,facility_type,area_m2,cost,installed_at,removed_at)
        VALUES(?,?,?,? ,?,'RAIN_GARDEN',1,560000,?,?)
        """,
        installation,
        district,
        "TEST",
        owner,
        "a".repeat(64),
        Timestamp.from(end.minusSeconds(600)),
        Timestamp.from(end));
    Instant through = end.minusSeconds((10 - minutes) * 60L);
    db.update(
        """
        INSERT INTO shared_physics_jobs(id,installation_id,simulation_start,requested_through,state,lease_token,created_at,finished_at,input_hash,result)
        VALUES(?,?,?,?,'SUCCEEDED',?,?,?,?,'{}')
        """,
        job,
        installation,
        Timestamp.from(end.minusSeconds(600)),
        Timestamp.from(through),
        UUID.randomUUID(),
        Timestamp.from(end),
        Timestamp.from(end),
        "b".repeat(64));
    db.update(
        """
        INSERT INTO shared_weekly_scores(installation_id,week_start,score_m3,evaluated_minutes,evaluated_through,source_job_id,rule_version)
        VALUES(?,?,?,?,?,?,'OBSERVED_ACCOUNTED_VOLUME_V1')
        """,
        installation,
        java.sql.Date.valueOf(week),
        new BigDecimal(score),
        minutes,
        Timestamp.from(through),
        job);
    return installation;
  }

  @Test
  void tiesSumExactlyAndMissingMinutePreventsWinner() {
    String name = "weekly_" + UUID.randomUUID().toString().substring(0, 8);
    contribution("2419953", name, "1.25", 10);
    contribution("2419953", name + "c", "0.75", 10);
    UUID delayed = contribution("2410520", name + "b", "2", 9);
    var pending = service.dashboard(name).previous();
    assertThat(pending.status()).isEqualTo("PROVISIONAL");
    assertThat(pending.expectedMinutes() - pending.evaluatedMinutes()).isEqualTo(1);
    assertThat(pending.winnerDistrictIds()).isEmpty();
    assertThat(pending.districts().subList(0, 2))
        .allMatch(d -> Integer.valueOf(1).equals(d.rank()));
    assertThat(
            pending.districts().stream()
                .map(d -> d.scoreM3())
                .reduce(BigDecimal.ZERO, BigDecimal::add))
        .isEqualByComparingTo(
            pending.players().stream()
                .map(p -> p.scoreM3())
                .reduce(BigDecimal.ZERO, BigDecimal::add));
    assertThat(pending.own().nickname()).isEqualTo("시험 " + name);
    db.update(
        "UPDATE shared_weekly_scores SET evaluated_minutes=10,evaluated_through=? WHERE"
            + " installation_id=?",
        Timestamp.from(end),
        delayed);
    var completed = service.dashboard(null).previous();
    assertThat(completed.status()).isEqualTo("FINAL");
    assertThat(completed.winnerDistrictIds()).containsExactlyInAnyOrder("2419953", "2410520");
    assertThat(completed.own()).isNull();
  }

  @Test
  void expiredSeasonCapsExpectedMinutesBeforeCleanupAndPreservesFinalRank() {
    var installation =
        contribution(
            "2419953", "season_" + UUID.randomUUID().toString().substring(0, 8), "1.25", 10);
    var original = service.dashboard(null).previous();
    db.update(
        "UPDATE shared_installations SET"
            + " season_ends_at=removed_at,removed_at=NULL,occupied_site=CAST(owner_id AS VARCHAR)"
            + " || ':' || district_id || ':' || cell_id WHERE id=?",
        installation);
    var beforeCleanup = service.dashboard(null).previous();
    assertThat(beforeCleanup).isEqualTo(original);
    assertThat(service.dashboard(null).current().status()).isEqualTo("EMPTY");
    db.update(
        "UPDATE shared_installations SET removed_at=season_ends_at,occupied_site=NULL WHERE id=?",
        installation);
    assertThat(service.dashboard(null).previous()).isEqualTo(original);
  }

  @Test
  void seasonBoundaryUsesKoreanMondayMidnight() {
    assertThat(
            io.waterleague.weekly.service.WeeklySeasonService.endFor(
                Instant.parse("2026-10-18T14:59:59.999999Z")))
        .isEqualTo(Instant.parse("2026-10-18T15:00:00Z"));
    assertThat(
            io.waterleague.weekly.service.WeeklySeasonService.endFor(
                Instant.parse("2026-10-18T15:00:00Z")))
        .isEqualTo(Instant.parse("2026-10-25T15:00:00Z"));
  }

  @Test
  void emptyWeeksAndNegativeContributionsHaveNoInventedWinner() {
    var empty = service.dashboard(null).previous();
    assertThat(empty.status()).isEqualTo("EMPTY");
    assertThat(empty.districts()).hasSize(25).allMatch(d -> d.rank() == null);
    assertThat(empty.players()).isEmpty();
    contribution(
        "2419953", "negative_" + UUID.randomUUID().toString().substring(0, 8), "-0.125", 10);
    var result = service.dashboard(null).previous();
    assertThat(result.players().getFirst().scoreM3()).isEqualByComparingTo("-0.125");
    assertThat(result.winnerDistrictIds()).isEmpty();
  }

  @Test
  void partialMinuteUsesSecondsAndDoesNotFinalizeWithOneSecondMissing() {
    var id =
        contribution(
            "2419953", "partial_" + UUID.randomUUID().toString().substring(0, 8), "0.25", 1);
    db.update(
        "UPDATE shared_installations SET"
            + " installed_at=?,season_ends_at=?,physics_policy='INSTALLATION_SECOND_V2' WHERE id=?",
        Timestamp.from(end.minusSeconds(43)),
        Timestamp.from(end),
        id);
    db.update(
        "UPDATE shared_weekly_scores SET"
            + " evaluated_minutes=1,evaluated_seconds=42,rule_version='OBSERVED_ACCOUNTED_VOLUME_SECONDS_V2'"
            + " WHERE installation_id=?",
        id);
    var pending = service.dashboard(null).previous();
    assertThat(pending.expectedSeconds()).isEqualTo(43);
    assertThat(pending.evaluatedSeconds()).isEqualTo(42);
    assertThat(pending.status()).isEqualTo("PROVISIONAL");
    assertThat(pending.winnerDistrictIds()).isEmpty();
    assertThat(pending.players().getFirst().rank()).isEqualTo(1);
    db.update(
        "UPDATE shared_weekly_scores SET evaluated_seconds=43,evaluated_through=? WHERE"
            + " installation_id=?",
        Timestamp.from(end),
        id);
    var complete = service.dashboard(null).previous();
    assertThat(complete.status()).isEqualTo("FINAL");
    assertThat(complete.evaluatedSeconds()).isEqualTo(43);
    var encoded = json.tree(json.write(complete));
    assertThat(encoded.path("evaluatedSeconds").asLong()).isEqualTo(43);
    assertThat(encoded.path("evaluatedMinutes").asLong()).isEqualTo(1);
    assertThat(complete.players().getFirst().scoreM3()).isEqualByComparingTo("0.25");
  }

  @Test
  void legacyPartialMinuteStillUsesOriginalStartAndDuration() {
    var id =
        contribution(
            "2419953", "legacy_" + UUID.randomUUID().toString().substring(0, 8), "0.5", 10);
    db.update(
        "UPDATE shared_installations SET installed_at=installed_at-interval '42.5 seconds' WHERE"
            + " id=?",
        id);
    var result = service.dashboard(null).previous();
    assertThat(result.expectedSeconds()).isEqualTo(600);
    assertThat(result.evaluatedSeconds()).isEqualTo(600);
    assertThat(result.status()).isEqualTo("FINAL");
  }

  @Test
  void migrationPreservesExistingFractionalTimestampAndSignedScore() throws Exception {
    try (var connection = db.getDataSource().getConnection()) {
      connection.setAutoCommit(false);
      try {
        try (var statement = connection.createStatement()) {
          statement.execute(
              "CREATE TEMP TABLE shared_installations(id UUID,installed_at"
                  + " TIMESTAMPTZ,season_ends_at TIMESTAMPTZ) ON COMMIT DROP");
          statement.execute(
              "CREATE TEMP TABLE shared_weekly_scores(score_m3 NUMERIC(24,9),evaluated_minutes"
                  + " INTEGER,rule_version VARCHAR(48) CONSTRAINT"
                  + " shared_weekly_scores_rule_version_check"
                  + " CHECK(rule_version='OBSERVED_ACCOUNTED_VOLUME_V1')) ON COMMIT DROP");
          statement.execute(
              "INSERT INTO shared_installations"
                  + " VALUES('00000000-0000-4000-8000-000000000001','2022-08-08T09:00:17.123456Z',NULL)");
          statement.execute(
              "INSERT INTO shared_weekly_scores"
                  + " VALUES(-0.123456789,7,'OBSERVED_ACCOUNTED_VOLUME_V1')");
        }
        org.springframework.jdbc.datasource.init.ScriptUtils.executeSqlScript(
            connection,
            new org.springframework.core.io.ClassPathResource(
                "db/migration/V27__weekly_installation_seconds.sql"));
        try (var statement = connection.createStatement();
            var rows =
                statement.executeQuery(
                    "SELECT installed_at,physics_policy FROM shared_installations")) {
          assertThat(rows.next()).isTrue();
          assertThat(rows.getTimestamp(1).toInstant())
              .isEqualTo(Instant.parse("2022-08-08T09:00:17.123456Z"));
          assertThat(rows.getString(2)).isEqualTo("FULL_MINUTE_V1");
        }
        try (var statement = connection.createStatement();
            var rows =
                statement.executeQuery(
                    "SELECT score_m3,evaluated_minutes,evaluated_seconds,rule_version FROM"
                        + " shared_weekly_scores")) {
          assertThat(rows.next()).isTrue();
          assertThat(rows.getBigDecimal(1)).isEqualByComparingTo("-0.123456789");
          assertThat(rows.getInt(2)).isEqualTo(7);
          assertThat(rows.getObject(3)).isNull();
          assertThat(rows.getString(4)).isEqualTo("OBSERVED_ACCOUNTED_VOLUME_V1");
        }
      } finally {
        connection.rollback();
      }
    }
  }
}
