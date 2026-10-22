package io.waterleague.gameanalysis.service;

import io.waterleague.account.entity.Account;
import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.competition.service.CompetitionService;
import io.waterleague.disaster.service.DisasterService;
import io.waterleague.district.repository.DistrictRepository;
import io.waterleague.gameanalysis.repository.GameAnalysisRepository;
import io.waterleague.gameanalysis.view.GameAnalysisView;
import io.waterleague.gameanalysis.view.GameAnalysisView.*;
import io.waterleague.historical.repository.HistoricalSubmissionRepository;
import io.waterleague.weekly.repository.WeeklyRepository;
import io.waterleague.weekly.service.WeeklyService;
import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

@Service
public class GameAnalysisService {
  private final GameAnalysisRepository repo;
  private final WeeklyService weekly;
  private final WeeklyRepository weeklyRows;
  private final HistoricalSubmissionRepository historical;
  private final CompetitionService competitions;
  private final DistrictRepository districts;
  private final DisasterService disasters;
  private final JsonService json;
  private final GameSummaryService summaries;

  public GameAnalysisService(
      GameAnalysisRepository repo,
      WeeklyService weekly,
      WeeklyRepository weeklyRows,
      HistoricalSubmissionRepository historical,
      CompetitionService competitions,
      DistrictRepository districts,
      DisasterService disasters,
      JsonService json,
      GameSummaryService summaries) {
    this.repo = repo;
    this.weekly = weekly;
    this.weeklyRows = weeklyRows;
    this.historical = historical;
    this.competitions = competitions;
    this.districts = districts;
    this.disasters = disasters;
    this.json = json;
    this.summaries = summaries;
  }

  private void admin(Account a) {
    if (a == null || !a.usable() || !a.role().equals("ADMIN"))
      throw new DomainException(ErrorCode.ACCESS_DENIED);
  }

  @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
  public GameAnalysisView weekly(Account a, LocalDate week) {
    admin(a);
    var period = weekly.archived(week, 0);
    var records = repo.weekly(period.startsAt(), period.evaluatedTarget(), week);
    var scores = new TreeMap<String, List<BigDecimal>>();
    if (period.comparisonStatus().equals("COMPARABLE")) {
      scores.put(
          period.comparisonGroupHash(),
          weeklyRows.contributions(week, period.startsAt(), period.evaluatedTarget(), true).stream()
              .filter(r -> r.evaluatedSeconds() > 0)
              .map(r -> r.scoreM3())
              .toList());
    }
    return snapshot(
        "weekly",
        week.toString(),
        new Facts(
            "WEEKLY",
            period.status(),
            period.participantCount(),
            records.size(),
            period.comparisonStatus().equals("COMPARABLE")
                ? records.stream().filter(r -> r.get("score_m3") != null).count()
                : 0,
            measures(records, "facility_type", false),
            measures(records, "district_id", true),
            activity(records),
            groups(scores)));
  }

  @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
  public GameAnalysisView historical(Account a, String event) {
    admin(a);
    if (disasters.catalog().events().stream().noneMatch(e -> e.id().equals(event)))
      throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
    var rows = repo.historical(event, null);
    var scores = new TreeMap<String, List<BigDecimal>>();
    // 고정된 순위 계산 코드는 유지하고 같은 스냅샷에서 모든 페이지를 집계한다.
    for (int page = 0; ; page++) {
      var ranked = historical.board(event, page);
      if (ranked.isEmpty()) break;
      for (var r : ranked)
        scores
            .computeIfAbsent(
                r.get("rulesHash") + ":" + r.get("comparisonGroupHash"), k -> new ArrayList<>())
            .add((BigDecimal) r.get("differenceM3"));
    }
    return historicalSnapshot(
        "historical",
        event,
        rows,
        null,
        rows.stream().map(r -> r.get("owner_id")).distinct().count(),
        scores,
        "RECORDED");
  }

  @SuppressWarnings("unchecked")
  @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
  public GameAnalysisView competition(Account a, UUID id) {
    var c = competitions.requireManager(a, id);
    var results = json.tree(json.write(competitions.analysisResults(a, id)));
    var scores = new TreeMap<String, List<BigDecimal>>();
    var installs = new ArrayList<Map<String, Object>>();
    long scored = 0;
    for (var g : results.path("groups")) {
      for (var e : g.path("entries")) {
        boolean comparable = !e.path("scoreM3").isNull();
        if (comparable)
          scores
              .computeIfAbsent(g.path("comparisonGroup").asString(), k -> new ArrayList<>())
              .add(e.path("scoreM3").decimalValue());
        for (var i : e.path("installations")) {
          installs.add(
              Map.of(
                  "facility_type",
                  i.path("facilityType").asString(),
                  "district_id",
                  i.path("districtId").asString(),
                  "area_m2",
                  i.path("areaM2").decimalValue(),
                  "created_at",
                  Instant.parse(i.path("installedAt").asString())));
          if (comparable && !i.path("scoreM3").isNull()) scored++;
        }
      }
    }
    long participants = results.path("competition").path("participantCount").longValue();
    String status = results.path("status").asString();
    if (c.mode().equals("DISASTER"))
      return historicalSnapshot(
          "competition",
          id.toString(),
          repo.historical(c.eventId(), id),
          c.scorePolicySha256(),
          participants,
          scores,
          status);
    return snapshot(
        "competition",
        id.toString(),
        new Facts(
            "REALTIME",
            status,
            participants,
            installs.size(),
            scored,
            measures(installs, "facility_type", false),
            measures(installs, "district_id", true),
            activity(installs),
            groups(scores)));
  }

  private GameAnalysisView historicalSnapshot(
      String scope,
      String id,
      List<Map<String, Object>> rows,
      String policy,
      long participants,
      Map<String, List<BigDecimal>> scores,
      String status) {
    var placements = new ArrayList<Map<String, Object>>();
    for (var row : rows)
      for (var p : json.tree((String) row.get("placements"))) {
        placements.add(
            Map.of(
                "facility_type",
                p.path("facilityType").asString(),
                "district_id",
                p.path("districtId").asString(),
                "area_m2",
                p.path("areaM2").decimalValue()));
      }
    long scored =
        rows.stream()
            .filter(
                r ->
                    "SUCCEEDED".equals(r.get("state"))
                        && r.get("difference_m3") != null
                        && r.get("comparison_group_hash") != null
                        && r.get("score_policy_sha256") != null
                        && (policy == null || policy.equals(r.get("score_policy_sha256"))))
            .count();
    return snapshot(
        scope,
        id,
        new Facts(
            "DISASTER",
            status,
            participants,
            rows.size(),
            scored,
            measures(placements, "facility_type", false),
            measures(placements, "district_id", true),
            activity(rows),
            groups(scores)));
  }

  private List<Measure> measures(List<Map<String, Object>> rows, String key, boolean district) {
    var grouped = new TreeMap<String, List<Map<String, Object>>>();
    for (var r : rows) grouped.computeIfAbsent((String) r.get(key), k -> new ArrayList<>()).add(r);
    return grouped.entrySet().stream()
        .map(
            e ->
                new Measure(
                    e.getKey(),
                    district ? districts.require(e.getKey()).name() : e.getKey(),
                    e.getValue().size(),
                    e.getValue().stream()
                        .map(r -> (BigDecimal) r.get("area_m2"))
                        .reduce(BigDecimal.ZERO, BigDecimal::add)))
        .toList();
  }

  private List<Activity> activity(List<Map<String, Object>> rows) {
    var counts = new TreeMap<String, Long>();
    for (var row : rows) {
      Object raw = row.get("created_at");
      Instant time =
          raw instanceof Timestamp t
              ? t.toInstant()
              : raw instanceof OffsetDateTime t ? t.toInstant() : (Instant) raw;
      counts.merge(time.atZone(ZoneId.of("Asia/Seoul")).toLocalDate().toString(), 1L, Long::sum);
    }
    return counts.entrySet().stream().map(e -> new Activity(e.getKey(), e.getValue())).toList();
  }

  private List<ScoreGroup> groups(Map<String, List<BigDecimal>> source) {
    return source.entrySet().stream()
        .filter(e -> !e.getValue().isEmpty())
        .map(
            e -> {
              var values = e.getValue();
              return new ScoreGroup(
                  e.getKey(),
                  values.size(),
                  values.stream().reduce(BigDecimal.ZERO, BigDecimal::add),
                  values.stream().min(BigDecimal::compareTo).orElseThrow(),
                  values.stream().max(BigDecimal::compareTo).orElseThrow(),
                  values.stream().filter(v -> v.signum() < 0).count(),
                  values.stream().filter(v -> v.signum() == 0).count(),
                  values.stream().filter(v -> v.signum() > 0).count());
            })
        .toList();
  }

  private GameAnalysisView snapshot(String scope, String id, Facts facts) {
    String hash = json.hash(json.write(Map.of("scope", scope, "scopeId", id, "facts", facts)));
    return new GameAnalysisView(scope, id, Instant.now(), hash, summaries.available(), facts);
  }
}
