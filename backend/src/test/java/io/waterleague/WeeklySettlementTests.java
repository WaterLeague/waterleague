package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.repository.AccountRepository;
import io.waterleague.weekly.service.WeeklySettlementService;
import java.sql.Timestamp;
import java.time.temporal.ChronoUnit;
import java.util.UUID;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("local")
class WeeklySettlementTests extends PostgresIntegrationTest {
  @org.springframework.test.context.DynamicPropertySource
  static void database(org.springframework.test.context.DynamicPropertyRegistry registry) {
    SharedInstallationTests.integrationDatabase(registry);
  }

  @Autowired JdbcTemplate db;
  @Autowired AccountRepository accounts;
  @Autowired WeeklySettlementService service;
  WeeklyWorkflowTests fixture;

  @BeforeEach
  void prepare() {
    fixture = new WeeklyWorkflowTests();
    fixture.db = db;
    fixture.accounts = accounts;
    fixture.prepare();
    fixture.week = fixture.week.minusWeeks(1);
    fixture.end = fixture.end.minus(7, ChronoUnit.DAYS);
  }

  UUID add(String district, String score, int minutes) {
    var id =
        fixture.contribution(
            district, "gap_" + UUID.randomUUID().toString().substring(0, 12), score, minutes);
    db.update(
        "UPDATE shared_installations SET season_ends_at=? WHERE id=?",
        Timestamp.from(fixture.end),
        id);
    return id;
  }

  void exclude(UUID id, int seconds) {
    db.update(
        """
        INSERT INTO weekly_observation_exclusions(id,installation_id,week_start,excluded_from,
          excluded_until,station_id,evidence_sha256,evidence,rule_version)
        VALUES(?,?,?,?,?,'409',?,'{}'::jsonb,'CLOSED_WEEK_MISSING_SUFFIX_V1')
        """,
        UUID.randomUUID(),
        id,
        java.sql.Date.valueOf(fixture.week),
        Timestamp.from(fixture.end.minusSeconds(seconds)),
        Timestamp.from(fixture.end),
        "a".repeat(64));
  }

  @Test
  void finalizesOnlyConfirmedExcludedTimeAndKeepsScoresAndOriginalDurations() {
    var a = add("11260", "1.25", 5);
    add("11680", "2.5", 10);
    var before = service.archived(fixture.week, 0);
    assertThat(before.status()).isEqualTo("PROVISIONAL");
    exclude(a, 300);
    var after = service.archived(fixture.week, 0);
    assertThat(after.status()).isEqualTo("FINAL");
    assertThat(after.expectedSeconds()).isEqualTo(before.expectedSeconds());
    assertThat(after.evaluatedSeconds()).isEqualTo(before.evaluatedSeconds());
    assertThat(after.players()).isEqualTo(before.players());
    assertThat(after.settlement().excludedSeconds()).isEqualTo(300);
    assertThat(after.settlement().installationCount()).isEqualTo(1);
    assertThat(after.settlement().periods().getFirst().districtName()).isEqualTo("중랑구");
    assertThat(after.winnerDistrictIds()).containsExactly("11680");
  }

  @Test
  void doesNotHidePendingValidPrefixOrMixedCalculationConditions() {
    var a = add("11260", "1.25", 5);
    var b = add("11680", "2.5", 10);
    exclude(a, 120);
    assertThat(service.archived(fixture.week, 0).status()).isEqualTo("PROVISIONAL");
    db.update(
        "UPDATE shared_weekly_scores SET comparison_group_hash=? WHERE installation_id=?",
        "e".repeat(64),
        b);
    var held = service.archived(fixture.week, 0);
    assertThat(held.status()).isEqualTo("WITHHELD");
    assertThat(held.winnerDistrictIds()).isEmpty();
  }

  @Test
  void allMissingHasNoInventedZeroScoreOrWinner() {
    var a = add("11260", "0", 0);
    exclude(a, 600);
    var p = service.archived(fixture.week, 0);
    assertThat(p.status()).isEqualTo("FINAL");
    assertThat(p.evaluatedSeconds()).isZero();
    assertThat(p.players()).allMatch(r -> r.scoreM3() == null && r.rank() == null);
    assertThat(p.winnerDistrictIds()).isEmpty();
  }

  @Test
  void cannotExcludeAnEvaluatedInterval() {
    var a = add("11260", "1.25", 10);
    exclude(a, 300);
    assertThatThrownBy(() -> service.archived(fixture.week, 0))
        .isInstanceOf(io.waterleague.common.exception.DomainException.class);
  }
}
