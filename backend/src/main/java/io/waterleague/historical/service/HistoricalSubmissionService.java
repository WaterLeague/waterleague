package io.waterleague.historical.service;

import io.waterleague.budget.service.BudgetService;
import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.cost.service.CostService;
import io.waterleague.disaster.service.DisasterService;
import io.waterleague.disaster.view.DisasterView;
import io.waterleague.historical.dto.HistoricalDesignSubmissionRequest;
import io.waterleague.historical.dto.HistoricalSubmissionRequest;
import io.waterleague.historical.entity.HistoricalDesign;
import io.waterleague.historical.entity.HistoricalExperiment;
import io.waterleague.historical.repository.*;
import io.waterleague.historical.view.HistoricalSubmissionView;
import io.waterleague.installation.repository.SiteCatalogRepository;
import io.waterleague.simulation.repository.SimulationRepository;
import io.waterleague.strategy.entity.*;
import io.waterleague.strategy.service.PlacementValidationService;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class HistoricalSubmissionService {
  public static final String POLICY = "FULL_EVENT_INDEPENDENT_SURFACES_V1";
  private final HistoricalRepository jobs;
  private final HistoricalSubmissionRepository submissions;
  private final HistoricalService history;
  private final SimulationRepository admission;
  private final DisasterService disasters;
  private final SiteCatalogRepository sites;
  private final BudgetService budget;
  private final CostService costs;
  private final PlacementValidationService validation;
  private final JsonService json;
  private final io.waterleague.competition.service.CompetitionBudgetService competitions;
  private final HistoricalDesignRepository designs;
  private final io.waterleague.evaluation.service.ScorePolicyService scorePolicy;

  public HistoricalSubmissionService(
      HistoricalRepository jobs,
      HistoricalSubmissionRepository submissions,
      HistoricalService history,
      SimulationRepository admission,
      DisasterService disasters,
      SiteCatalogRepository sites,
      BudgetService budget,
      CostService costs,
      PlacementValidationService validation,
      JsonService json,
      HistoricalDesignRepository designs,
      io.waterleague.evaluation.service.ScorePolicyService scorePolicy,
      io.waterleague.competition.service.CompetitionBudgetService competitions) {
    this.jobs = jobs;
    this.submissions = submissions;
    this.history = history;
    this.admission = admission;
    this.disasters = disasters;
    this.sites = sites;
    this.budget = budget;
    this.costs = costs;
    this.validation = validation;
    this.json = json;
    this.competitions = competitions;
    this.designs = designs;
    this.scorePolicy = scorePolicy;
  }

  private DisasterView.Event event(String id) {
    return disasters.catalog().events().stream()
        .filter(e -> e.id().equals(id))
        .findFirst()
        .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
  }

  @Transactional
  public HistoricalSubmissionView submit(UUID owner, HistoricalSubmissionRequest dto) {
    return create(owner, dto, null, null);
  }

  @Transactional
  public HistoricalSubmissionView submitSaved(
      UUID owner, String eventId, HistoricalDesignSubmissionRequest dto) {
    return submitSaved(owner, eventId, dto, null);
  }

  @Transactional
  public HistoricalSubmissionView submitSaved(
      UUID owner, String eventId, HistoricalDesignSubmissionRequest dto, UUID competitionId) {
    return create(
        owner,
        new HistoricalSubmissionRequest(dto.requestKey(), eventId, List.of()),
        dto,
        competitionId);
  }

  private HistoricalSubmissionView create(
      UUID owner,
      HistoricalSubmissionRequest dto,
      HistoricalDesignSubmissionRequest reference,
      UUID competitionId) {
    if (reference == null
        && (dto.placements() == null || dto.placements().isEmpty() || dto.placements().size() > 50))
      throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    List<HistoricalSubmissionRequest.Item> sorted =
        dto.placements().stream()
            .sorted(
                Comparator.comparing(HistoricalSubmissionRequest.Item::districtId)
                    .thenComparing(HistoricalSubmissionRequest.Item::cellId))
            .toList();
    String raw =
        reference == null
            ? json.write(new HistoricalSubmissionRequest(dto.requestKey(), dto.eventId(), sorted))
            : json.write(
                new TreeMap<>(
                    Map.of(
                        "mode",
                        "SAVED_DESIGN_SUBMISSION_V1",
                        "eventId",
                        dto.eventId(),
                        "request",
                        reference)));
    if (competitionId != null) {
      var requestNode = (tools.jackson.databind.node.ObjectNode) json.tree(raw);
      requestNode.put("competitionId", competitionId.toString());
      raw = json.write(requestNode);
    }
    admission.lockAdmission();
    admission.lockOwner(owner);
    var previous = jobs.byKey(owner, dto.requestKey());
    if (previous.isPresent()) {
      if (!submissions.request(previous.get().id()).orElse("").equals(raw))
        throw new DomainException(ErrorCode.CONFLICT);
      return summary(previous.get());
    }
    var contest = competitions.require(owner, competitionId, "DISASTER", dto.eventId(), true);
    var selectedBudget = competitions.policy(contest);
    var event = event(dto.eventId());
    HistoricalDesign saved = null;
    var savedRows = new HashMap<String, tools.jackson.databind.JsonNode>();
    if (reference != null) {
      saved =
          designs
              .latest(owner, dto.eventId(), competitionId)
              .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
      if (reference.revision() != saved.revision()
          || !reference.snapshotSha256().equals(saved.snapshotSha256()))
        throw new DomainException(ErrorCode.HISTORICAL_DESIGN_CONFLICT);
      if (!json.hash(saved.snapshotRaw()).equals(saved.snapshotSha256()))
        throw new DomainException(ErrorCode.HISTORICAL_DESIGN_INVALID);
      var snapshot = json.tree(saved.snapshotRaw());
      if (!snapshot.path("budgetPolicy").equals(json.tree(json.write(selectedBudget)))
          || !snapshot
              .path("publicAssetPolicy")
              .equals(json.tree(json.write(sites.publicAssetPolicy()))))
        throw new DomainException(ErrorCode.HISTORICAL_SITE_CHANGED);
      var items = new ArrayList<HistoricalSubmissionRequest.Item>();
      for (var row : snapshot.path("placements")) {
        var item = row.path("item");
        String district = item.path("districtId").asString(), cell = item.path("cellId").asString();
        savedRows.put(district + "/" + cell, row);
        items.add(
            new HistoricalSubmissionRequest.Item(
                district,
                cell,
                FacilityType.valueOf(item.path("facilityType").asString()),
                item.path("areaM2").decimalValue(),
                Instant.parse(item.path("installedAt").asString()),
                null));
      }
      if (items.isEmpty() || items.size() > 50 || savedRows.size() != items.size())
        throw new DomainException(ErrorCode.PLACEMENT_INVALID);
      sorted =
          items.stream()
              .sorted(
                  Comparator.comparing(HistoricalSubmissionRequest.Item::districtId)
                      .thenComparing(HistoricalSubmissionRequest.Item::cellId))
              .toList();
    }
    var regions = new TreeMap<String, DisasterView.Region>();
    event.regions().forEach(r -> regions.put(r.districtId(), r));
    var frozen = new ArrayList<Map<String, Object>>();
    var allocated = new EnumMap<FacilityType, BigDecimal>(FacilityType.class);
    var seen = new HashSet<String>();
    for (var p : sorted) {
      competitions.permits(contest, p.districtId(), p.facilityType());
      var region = regions.get(p.districtId());
      if (region == null
          || p.installedAt() == null
          || p.installedAt().getNano() != 0
          || p.installedAt().isBefore(Instant.parse(region.start()))
          || !p.installedAt().isBefore(Instant.parse(region.end()))
          || !seen.add(p.districtId() + "/" + p.cellId()))
        throw new DomainException(ErrorCode.PLACEMENT_INVALID);
      if (p.experimentId() != null) {
        var parent = history.require(owner, p.experimentId());
        if (!parent.modelHash().equals(region.modelHash())
            || submissions.request(parent.id()).isPresent())
          throw new DomainException(ErrorCode.PLACEMENT_INVALID);
      }
      var site = sites.requireInstallable(p.districtId(), p.cellId());
      var savedRow = savedRows.get(p.districtId() + "/" + p.cellId());
      if (savedRow != null)
        site =
            costs.recordedSite(
                site,
                p.facilityType(),
                p.areaM2(),
                savedRow.path("costSnapshotRaw").asString(),
                savedRow.path("costSnapshotSha256").asString());
      var types = new HashSet<FacilityType>();
      site.allowedTypes().forEach(t -> types.add(FacilityType.valueOf(t)));
      var units = new EnumMap<FacilityType, BigDecimal>(FacilityType.class);
      site.unitCosts().forEach((t, v) -> units.put(FacilityType.valueOf(t), v));
      var amount =
          validation.validate(
              List.of(new Placement(p.cellId(), p.facilityType(), p.areaM2())),
              Map.of(
                  p.cellId(),
                  new PlacementCell(p.cellId(), types, site.maxAreaFor(p.facilityType()), true)),
              units,
              selectedBudget.personalLimitKrw(),
              1);
      allocated.merge(p.facilityType(), amount, BigDecimal::add);
      var cost = costs.snapshot(site, p.facilityType(), p.areaM2(), amount.setScale(2));
      if (savedRow != null
          && (!savedRow.path("site").path("modelHash").asString().equals(site.modelHash())
              || !savedRow.path("rainfallModelHash").asString().equals(region.modelHash())
              || savedRow.path("cost").decimalValue().compareTo(amount) != 0
              || !json.hash(savedRow.path("costSnapshotRaw").asString())
                  .equals(savedRow.path("costSnapshotSha256").asString())))
        throw new DomainException(ErrorCode.HISTORICAL_SITE_CHANGED);
      var row = new TreeMap<String, Object>();
      row.put("districtId", p.districtId());
      row.put("cellId", p.cellId());
      row.put("facilityType", p.facilityType());
      row.put("areaM2", p.areaM2());
      row.put("siteModelHash", site.modelHash());
      row.put("rainfallModelHash", region.modelHash());
      row.put("budgetPolicy", selectedBudget);
      row.put("publicAssetPolicy", sites.publicAssetPolicy());
      row.put(
          "costSnapshotRaw",
          savedRow == null ? cost.raw() : savedRow.path("costSnapshotRaw").asString());
      row.put(
          "costSnapshotSha256",
          savedRow == null ? cost.sha256() : savedRow.path("costSnapshotSha256").asString());
      row.put("experimentInstalledAt", p.installedAt().toString());
      if (p.experimentId() != null) row.put("parentExperimentId", p.experimentId().toString());
      frozen.add(row);
    }
    // 여러 구를 선택해도 회원 한 명의 사업군 한도를 한 번만 적용한다.
    var accounting = budget.validateDesign(allocated, selectedBudget);
    var rules = new TreeMap<String, Object>();
    rules.put("policy", POLICY);
    if (competitionId != null) rules.put("competitionId", competitionId);
    rules.put("eventId", event.id());
    rules.put("modelGrade", "CURRENT_GEOMETRY_HISTORICAL_RAINFALL_STRESS_TEST");
    rules.put("engineVersion", "5.2.4");
    rules.put("metric", "BASELINE_MINUS_STRATEGY_RUNOFF_DRAINAGE_AND_NET_STORAGE_M3");
    rules.put("officialTotalScore", false);
    rules.put("scorePolicy", scorePolicy.descriptor());
    rules.put("budgetPolicy", selectedBudget);
    rules.put("budgetAccountingPolicy", budget.validateDesign(Map.of(), selectedBudget));
    rules.put("siteCatalogs", sites.versions());
    rules.put("publicAssetPolicy", sites.publicAssetPolicy());
    var forcing = new TreeMap<String, String>();
    regions.forEach((id, r) -> forcing.put(id, r.modelHash()));
    rules.put("rainfallModels", forcing);
    rules.put("start", event.regions().getFirst().start());
    rules.put("end", event.regions().getFirst().end());
    String rulesRaw = json.write(rules), rulesHash = json.hash(rulesRaw);
    frozen.getFirst().put("submissionPolicy", POLICY);
    frozen.getFirst().put("submissionRulesRaw", rulesRaw);
    frozen.getFirst().put("submissionRulesHash", rulesHash);
    frozen.getFirst().put("submissionRequestRaw", raw);
    frozen.getFirst().put("budgetAccounting", accounting);
    if (saved != null) {
      // 확정 버튼이 가리킨 원 저장본을 제출에 묶고 실험 설치 시각은 계산 시각과 구분한다.
      frozen.getFirst().put("submissionDesignRevision", saved.revision());
      frozen.getFirst().put("submissionDesignSnapshotRaw", saved.snapshotRaw());
      frozen.getFirst().put("submissionDesignSnapshotSha256", saved.snapshotSha256());
    }
    String model = regions.get(sorted.getFirst().districtId()).modelHash(),
        body = json.write(frozen);
    if (jobs.active(owner) >= 2 || admission.totalActive() >= 20)
      throw new DomainException(ErrorCode.SIMULATION_QUOTA_EXCEEDED);
    var job =
        new HistoricalExperiment(
            UUID.randomUUID(),
            owner,
            sorted.getFirst().districtId(),
            model,
            json.hash(model + "\n" + body),
            body,
            "QUEUED",
            null,
            Instant.now(),
            null,
            null);
    jobs.add(job, dto.requestKey(), competitionId);
    submissions.add(
        job.id(),
        event.id(),
        rulesHash,
        raw,
        allocated.values().stream().reduce(BigDecimal.ZERO, BigDecimal::add));
    return summary(job);
  }

  public Object board(String eventId) {
    return board(eventId, 0);
  }

  public Object board(String eventId, int page) {
    return board(eventId, page, null);
  }

  public Object board(String eventId, int page, UUID owner) {
    if (page < 0 || page > 1000) throw new DomainException(ErrorCode.REQUEST_INVALID);
    var event = event(eventId);
    var groups = new LinkedHashMap<String, List<Map<String, Object>>>();
    for (var row : submissions.board(eventId, page)) {
      String key = row.get("rulesHash") + ":" + row.get("comparisonGroupHash");
      var group = groups.computeIfAbsent(key, k -> new ArrayList<>());
      if (group.size() >= 100) continue;
      var entry = new LinkedHashMap<>(row);
      group.add(entry);
    }
    return Map.of(
        "eventId",
        eventId,
        "title",
        event.title(),
        "policy",
        POLICY,
        "modelGrade",
        "CURRENT_GEOMETRY_HISTORICAL_RAINFALL_STRESS_TEST",
        "officialTotalScore",
        false,
        "scorePolicy",
        scorePolicy.descriptor(),
        "ownEntries",
        owner == null ? List.of() : submissions.board(eventId, 0, owner),
        "withheldSubmissionCount",
        submissions.withheldCount(eventId),
        "groups",
        groups.entrySet().stream()
            .map(
                g ->
                    Map.of(
                        "rulesHash",
                        g.getValue().getFirst().get("rulesHash"),
                        "comparisonGroupHash",
                        g.getValue().getFirst().get("comparisonGroupHash"),
                        "scorePolicySha256",
                        g.getValue().getFirst().get("scorePolicySha256"),
                        "entries",
                        g.getValue()))
            .toList());
  }

  public List<HistoricalSubmissionView> list(UUID owner, String eventId) {
    return list(owner, eventId, null);
  }

  public List<HistoricalSubmissionView> list(UUID owner, String eventId, UUID competitionId) {
    competitions.require(owner, competitionId, "DISASTER", eventId, false);
    event(eventId);
    return jobs.submissions(owner, eventId, competitionId).stream().map(this::summary).toList();
  }

  public HistoricalSubmissionView get(UUID owner, UUID id) {
    var job = history.require(owner, id);
    if (submissions.request(id).isEmpty()) throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
    return summary(job);
  }

  private HistoricalSubmissionView summary(HistoricalExperiment job) {
    tools.jackson.databind.node.ObjectNode result = null;
    if (job.result() != null) {
      var source = json.tree(job.result());
      result = (tools.jackson.databind.node.ObjectNode) json.tree("{}");
      result.put(
          "rankingStatus",
          source.path("scoreContext").isObject() && source.path("rankingScoreM3Exact").isString()
              ? "COMPARABLE"
              : "COMPARISON_CONTEXT_MISSING");
      for (var field :
          List.of(
              "submissionPolicy",
              "rulesHash",
              "start",
              "end",
              "differenceM3",
              "rankingScoreM3Exact",
              "scoreContext",
              "baselineAccountedM3",
              "designAccountedM3",
              "totalScoreStatus",
              "assumptions")) if (source.has(field)) result.set(field, source.get(field));
    }
    return new HistoricalSubmissionView(
        job.id(),
        job.state(),
        job.createdAt(),
        json.tree(job.placements()).size(),
        json.tree(job.placements()).get(0).has("submissionDesignRevision")
            ? json.tree(job.placements()).get(0).path("submissionDesignRevision").longValue()
            : null,
        result,
        Set.of("FAILED", "REJECTED").contains(job.state()) ? "전체 기간 계산 실패 · 순위 미게시" : "");
  }
}
