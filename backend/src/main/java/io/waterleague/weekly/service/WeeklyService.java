package io.waterleague.weekly.service;

import io.waterleague.account.repository.AccountRepository;
import io.waterleague.common.exception.DomainException;
import io.waterleague.common.exception.ErrorCode;
import io.waterleague.district.repository.DistrictRepository;
import io.waterleague.weekly.entity.WeeklyContribution;
import io.waterleague.weekly.repository.WeeklyRepository;
import io.waterleague.weekly.view.WeeklyView;
import java.math.BigDecimal;
import java.time.*;
import java.time.temporal.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

@Service
public class WeeklyService {
  private static final ZoneId KST = ZoneId.of("Asia/Seoul");
  private final WeeklyRepository scores;
  private final DistrictRepository districts;
  private final AccountRepository accounts;
  private final io.waterleague.evaluation.service.ScorePolicyService scorePolicy;

  public WeeklyService(
      WeeklyRepository scores,
      DistrictRepository districts,
      AccountRepository accounts,
      io.waterleague.evaluation.service.ScorePolicyService scorePolicy) {
    this.scores = scores;
    this.districts = districts;
    this.accounts = accounts;
    this.scorePolicy = scorePolicy;
  }

  @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
  public WeeklyView dashboard(String username) {
    Instant now = scores.now();
    LocalDate monday =
        now.atZone(KST).toLocalDate().with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
    UUID own =
        username == null ? null : accounts.byUsername(username).map(a -> a.id()).orElse(null);
    return new WeeklyView(
        now,
        "OBSERVED_ACCOUNTED_VOLUME_SECONDS_V2",
        "EXPLORATORY",
        scorePolicy.descriptor(),
        period(monday, now, own),
        period(monday.minusWeeks(1), now, own));
  }

  @Transactional(readOnly = true)
  public io.waterleague.weekly.view.SiteScorePage siteScores(
      String district, String cell, UUID after) {
    districts.require(district);
    if (cell == null || !cell.matches("C[a-f0-9]{24}"))
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    var week =
        scores
            .now()
            .atZone(KST)
            .toLocalDate()
            .with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
    var rows = scores.siteScores(district, cell, week, after == null ? new UUID(0, 0) : after);
    var page = rows.stream().limit(50).toList();
    return new io.waterleague.weekly.view.SiteScorePage(
        page, rows.size() > 50 ? page.getLast().id() : null);
  }

  private WeeklyView.Period period(LocalDate week, Instant now, UUID own) {
    Instant start = week.atStartOfDay(KST).toInstant(),
        end = week.plusWeeks(1).atStartOfDay(KST).toInstant();
    Instant target = now.minusSeconds(120).truncatedTo(ChronoUnit.MINUTES);
    if (target.isAfter(end)) target = end;
    if (target.isBefore(start)) target = start;
    var rows = scores.contributions(week, start, target);
    if (rows.stream()
        .anyMatch(r -> r.evaluatedSeconds() > r.expectedSeconds() || r.evaluatedSeconds() < 0))
      throw new DomainException(ErrorCode.SIMULATION_UNAVAILABLE);
    long expected = rows.stream().mapToLong(WeeklyContribution::expectedSeconds).sum();
    long evaluated = rows.stream().mapToLong(WeeklyContribution::evaluatedSeconds).sum();
    var contexts = scores.comparisonGroups(week, start, target);
    boolean withheld = evaluated > 0 && (contexts.size() != 1 || contexts.contains(null));
    String comparisonStatus = evaluated == 0 ? "UNAVAILABLE" : withheld ? "WITHHELD" : "COMPARABLE";
    String comparisonReason =
        evaluated == 0
            ? "NO_EVALUATED_RECORDS"
            : !withheld
                ? null
                : contexts.contains(null)
                    ? "COMPARISON_CONTEXT_MISSING"
                    : "MIXED_COMPARISON_CONTEXTS";
    var districtRows = new ArrayList<WeeklyView.District>();
    for (var district : districts.all()) {
      var members = rows.stream().filter(r -> r.districtId().equals(district.id())).toList();
      districtRows.add(
          new WeeklyView.District(
              district.id(),
              district.name(),
              null,
              withheld
                  ? BigDecimal.ZERO
                  : members.stream()
                      .map(WeeklyContribution::scoreM3)
                      .reduce(BigDecimal.ZERO, BigDecimal::add),
              members.stream().mapToLong(WeeklyContribution::evaluatedSeconds).sum(),
              members.stream().mapToLong(WeeklyContribution::expectedSeconds).sum()));
    }
    districtRows.sort(
        withheld
            ? Comparator.comparing(WeeklyView.District::districtName)
                .thenComparing(WeeklyView.District::districtId)
            : Comparator.comparing((WeeklyView.District r) -> r.evaluatedSeconds() == 0)
                .thenComparing(WeeklyView.District::scoreM3, Comparator.reverseOrder())
                .thenComparing(WeeklyView.District::districtName)
                .thenComparing(WeeklyView.District::districtId));
    var rankedDistricts = new ArrayList<WeeklyView.District>();
    int rank = 0, index = 0;
    BigDecimal last = null;
    for (var row : districtRows) {
      index++;
      if (row.evaluatedSeconds() > 0 && (last == null || last.compareTo(row.scoreM3()) != 0))
        rank = index;
      rankedDistricts.add(
          new WeeklyView.District(
              row.districtId(),
              row.districtName(),
              row.evaluatedSeconds() == 0 || withheld ? null : rank,
              row.evaluatedSeconds() == 0 || withheld ? null : row.scoreM3(),
              row.evaluatedSeconds(),
              row.expectedSeconds()));
      if (row.evaluatedSeconds() > 0) last = row.scoreM3();
    }
    rows = new ArrayList<>(rows);
    rows.sort(
        withheld
            ? Comparator.comparing(WeeklyContribution::playerId)
            : Comparator.comparing((WeeklyContribution r) -> r.evaluatedSeconds() == 0)
                .thenComparing(WeeklyContribution::scoreM3, Comparator.reverseOrder())
                .thenComparing(WeeklyContribution::playerId));
    var players = new ArrayList<WeeklyView.Player>();
    rank = 0;
    index = 0;
    last = null;
    WeeklyView.Player self = null;
    for (var row : rows) {
      index++;
      if (row.evaluatedSeconds() > 0 && (last == null || last.compareTo(row.scoreM3()) != 0))
        rank = index;
      var player =
          new WeeklyView.Player(
              row.playerId(),
              row.nickname(),
              row.districtId(),
              row.evaluatedSeconds() == 0 || withheld ? null : rank,
              row.evaluatedSeconds() == 0 || withheld ? null : row.scoreM3(),
              row.evaluatedSeconds(),
              row.expectedSeconds());
      if (row.playerId().equals(own)) self = player;
      if (players.size() < 100) players.add(player);
      if (row.evaluatedSeconds() > 0) last = row.scoreM3();
    }
    boolean closed = !now.isBefore(end);
    String status =
        withheld
            ? "WITHHELD"
            : expected == 0
                ? "EMPTY"
                : !closed
                    ? "IN_PROGRESS"
                    : evaluated == expected && target.equals(end) ? "FINAL" : "PROVISIONAL";
    var winners =
        status.equals("FINAL")
            ? rankedDistricts.stream()
                .filter(d -> Integer.valueOf(1).equals(d.rank()) && d.scoreM3().signum() > 0)
                .map(WeeklyView.District::districtId)
                .toList()
            : List.<String>of();
    return new WeeklyView.Period(
        week,
        start,
        end,
        target,
        status,
        comparisonStatus,
        comparisonReason,
        !withheld && contexts.size() == 1 ? contexts.getFirst() : null,
        evaluated,
        expected,
        List.copyOf(rankedDistricts),
        List.copyOf(players),
        rows.size(),
        self,
        winners);
  }
}
