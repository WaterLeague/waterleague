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
}
