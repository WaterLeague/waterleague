package io.waterleague.league.service;

import io.waterleague.account.entity.Account;
import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.league.dto.LeagueDraftRequest;
import io.waterleague.league.entity.*;
import io.waterleague.league.exception.LeagueException;
import io.waterleague.league.mapper.LeagueMapper;
import io.waterleague.league.repository.LeagueRepository;
import io.waterleague.model.repository.LabModelRepository;
import io.waterleague.ranking.service.ExploratoryResultService;
import io.waterleague.research.repository.ResearchRepository;
import io.waterleague.simulation.repository.SimulationRepository;
import io.waterleague.strategy.repository.StrategyRepository;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LeagueService {
  private final LeagueRepository leagues;
  private final ResearchRepository research;
  private final LabModelRepository model;
  private final SimulationRepository jobs;
  private final StrategyRepository strategies;
  private final ExploratoryResultService results;
  private final JsonService json;
  private final LeagueMapper mapper;
  private final LeagueParticipationService participation;

  public LeagueService(
      LeagueRepository l,
      ResearchRepository r,
      LabModelRepository m,
      SimulationRepository j,
      StrategyRepository s,
      ExploratoryResultService e,
      JsonService x,
      LeagueMapper v,
      LeagueParticipationService p) {
    leagues = l;
    research = r;
    model = m;
    jobs = j;
    strategies = s;
    results = e;
    json = x;
    mapper = v;
    participation = p;
  }

  private void institution(Account a) {
    if (!a.usable()
        || !a.organizationMember()
        || a.organizationId() == null
        || !research.approved(a.organizationId()))
      throw new DomainException(ErrorCode.ACCESS_DENIED);
  }

  private League get(UUID id, boolean lock) {
    return leagues
        .get(id, lock)
        .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
  }

  private League managed(Account a, UUID id) {
    a = participation.lockAccount(a);
    institution(a);
    var l = get(id, true);
    if (!a.organizationId().equals(l.organizationId()))
      throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
    return l;
  }

  private League visible(UUID id, Account a) {
    var l = get(id, false);
    if (l.state().equals("DRAFT") || !research.approved(l.organizationId()))
      throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
    participation.requireView(l, a);
    return l;
  }

  public Object list() {
    return leagues.list(null).stream()
        .map(l -> mapper.view(l, model.contains(l.modelHash()), Instant.now()))
        .toList();
  }

  public Object managedList(Account a) {
    institution(a);
    return leagues.list(a.organizationId()).stream()
        .map(l -> mapper.view(l, model.contains(l.modelHash()), Instant.now()))
        .toList();
  }

  public Object detail(UUID id, Account a) {
    var l = visible(id, a);
    if (!json.hash(l.modelSource()).equals(l.modelHash())
        || !json.hash(l.rules()).equals(l.rulesHash()))
      throw new DomainException(ErrorCode.RESULT_QUALITY_FAILED);
    boolean boardVisible = participation.boardVisible(l, a);
    return Map.of(
        "league",
        mapper.view(l, model.contains(l.modelHash()), Instant.now()),
        "lab",
        Map.of("modelHash", l.modelHash(), "model", json.tree(l.modelSource())),
        "entries",
        boardVisible ? mapper.ranks(leagues.board(id)) : List.of(),
        "boardVisible",
        boardVisible);
  }

  private League draft(Account a, UUID id, LeagueDraftRequest d, Instant created) {
    Instant now = Instant.now();
    var selected = model.require(d.modelHash());
    if (!d.closesAt().isAfter(d.opensAt())
        || !d.closesAt().isAfter(now)
        || d.opensAt().isBefore(now.minus(Duration.ofMinutes(10)))
        || d.closesAt().isAfter(now.plus(Duration.ofDays(366)))
        || d.budget() > selected.model().path("budget").longValue())
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    if (!selected.model().path("simulationAvailable").asBoolean())
      throw new DomainException(ErrorCode.MODEL_NOT_ELIGIBLE);
    int availableCells = 0;
    BigDecimal availableArea = BigDecimal.ZERO;
    for (var cell : selected.model().path("cells")) {
      boolean allowed = false;
      for (var type : cell.path("allowedTypes"))
        if (d.allowedTypes().stream().anyMatch(t -> t.name().equals(type.asString())))
          allowed = true;
      if (allowed) {
        availableCells++;
        availableArea = availableArea.add(cell.path("maxAreaM2").decimalValue());
      }
    }
    int maximum = Math.min(availableCells, selected.model().path("maxPlacements").asInt());
    int placementLimit = d.placementLimit() == null ? maximum : d.placementLimit();
    BigDecimal areaLimit = d.areaLimitM2() == null ? availableArea : d.areaLimitM2();
    if (placementLimit < 1
        || placementLimit > maximum
        || areaLimit.signum() <= 0
        || areaLimit.compareTo(availableArea) > 0)
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    var award =
        d.award() == null
            ? new LeagueAward(0, 0, "")
            : new LeagueAward(
                d.award().prizeKrw(), d.award().winnerCount(), d.award().notice().strip());
    if ((award.prizeKrw() == 0 && award.winnerCount() != 0)
        || (award.prizeKrw() > 0 && (award.winnerCount() < 1 || award.notice().length() < 10)))
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    LeagueParticipationRules entry = null;
    if (d.participation() != null) {
      var p = d.participation();
      if ((p.entryMode() == LeagueParticipationRules.EntryMode.TEAM) != (p.teamSizeLimit() != null))
        throw new DomainException(ErrorCode.REQUEST_INVALID);
      entry =
          new LeagueParticipationRules(p.access(), p.admission(), p.entryMode(), p.teamSizeLimit());
    }
    var rules =
        new LeagueRules(
            entry == null ? 2 : 3,
            selected.hash(),
            selected.model().path("engineRevision").asString(),
            selected.model().path("generatorSha256").asString(),
            "ACCOUNTED_DISCHARGE_REDUCTION_V1",
            "KRW",
            d.budget(),
            d.allowedTypes().stream().sorted().toList(),
            d.submissionLimit(),
            d.opensAt(),
            d.closesAt(),
            "EXPLORATORY",
            false,
            placementLimit,
            areaLimit,
            award,
            entry);
    String rulesText = json.write(rules);
    return new League(
        id,
        a.organizationId(),
        "",
        d.baseRevision() + 1,
        "DRAFT",
        d.title().strip(),
        d.question().strip(),
        d.opensAt(),
        d.closesAt(),
        selected.hash(),
        selected.source(),
        rulesText,
        json.hash(rulesText),
        null,
        null,
        null,
        created);
  }

  @Transactional
  public Object create(Account a, LeagueDraftRequest d) {
    a = participation.lockAccount(a);
    institution(a);
    if (d.baseRevision() != 0) throw new DomainException(ErrorCode.CONFLICT);
    leagues.lockOrganization(a.organizationId());
    if (leagues.active(a.organizationId(), Instant.now()) >= 20)
      throw new DomainException(ErrorCode.RATE_LIMITED);
    var l = draft(a, UUID.randomUUID(), d, Instant.now());
    leagues.create(l, a.id());
    research.audit(a.id(), "LEAGUE_CREATED", l.id());
    return mapper.view(get(l.id(), false), model.contains(l.modelHash()), Instant.now());
  }

  @Transactional
  public Object update(Account a, UUID id, LeagueDraftRequest d) {
    var l = managed(a, id);
    if (!l.state().equals("DRAFT") || l.revision() != d.baseRevision())
      throw new LeagueException(ErrorCode.LEAGUE_IMMUTABLE);
    leagues.update(draft(a, id, d, l.createdAt()));
    research.audit(a.id(), "LEAGUE_EDITED", id);
    return mapper.view(get(id, false), model.contains(get(id, false).modelHash()), Instant.now());
  }

  @Transactional
  public Object publish(Account a, UUID id, int revision, String hash) {
    var l = managed(a, id);
    if (!l.state().equals("DRAFT")
        || l.revision() != revision
        || !l.rulesHash().equals(hash)
        || !model.contains(l.modelHash())
        || !l.closesAt().isAfter(Instant.now()))
      throw new LeagueException(ErrorCode.LEAGUE_IMMUTABLE);
    leagues.publish(id, Instant.now());
    research.audit(a.id(), "LEAGUE_PUBLISHED", id);
    return mapper.view(get(id, false), model.contains(get(id, false).modelHash()), Instant.now());
  }

  @Transactional
  public Object cancel(Account a, UUID id, String reason) {
    var l = managed(a, id);
    if (!l.state().equals("PUBLISHED")) throw new LeagueException(ErrorCode.LEAGUE_IMMUTABLE);
    leagues.cancel(id, reason.strip());
    research.audit(a.id(), "LEAGUE_CANCELLED", id);
    return mapper.view(get(id, false), model.contains(get(id, false).modelHash()), Instant.now());
  }

  public Object mine(Account a, UUID id) {
    visible(id, a);
    return leagues.own(id, a.id());
  }

  @Transactional
  public Object submit(Account a, UUID id, UUID jobId, String rulesHash) {
    if (!a.usable() || !a.role().equals("MEMBER") || !a.memberType().equals("PLAYER"))
      throw new DomainException(ErrorCode.ACCESS_DENIED);
    a = participation.lockPlayer(a);
    var l = get(id, true);
    if (l.state().equals("DRAFT") || !research.approved(l.organizationId()))
      throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
    if (!l.rulesHash().equals(rulesHash) || !json.hash(l.rules()).equals(rulesHash))
      throw new LeagueException(ErrorCode.LEAGUE_RULES_MISMATCH);
    participation.requireView(l, a);
    UUID team = participation.submissionTeam(l, a);
    var existing = leagues.existing(id, jobId, a.id());
    if (existing.isPresent()) return existing.get();
    Instant now = Instant.now();
    if (!l.state().equals("PUBLISHED") || now.isBefore(l.opensAt()) || !now.isBefore(l.closesAt()))
      throw new LeagueException(ErrorCode.LEAGUE_CLOSED);
    var rules = json.read(l.rules(), LeagueRules.class);
    if (participation.submissions(id, a.id(), team) >= rules.submissionLimit())
      throw new LeagueException(ErrorCode.LEAGUE_SUBMISSION_LIMIT);
    var job =
        jobs.get(jobId, a.id())
            .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    if (!l.modelHash().equals(job.modelHash()) || job.createdAt().isBefore(l.publishedAt()))
      throw new LeagueException(ErrorCode.LEAGUE_RULES_MISMATCH);
    var score = results.score(job);
    var version = strategies.version(job.versionId(), a.id()).orElseThrow();
    if (!version.currency().equals("KRW")
        || !version.modelHash().equals(l.modelHash())
        || !version.inputHash().equals(job.inputHash()))
      throw new LeagueException(ErrorCode.LEAGUE_RULES_MISMATCH);
    if (version.cost().compareTo(BigDecimal.valueOf(rules.budget())) > 0)
      throw new DomainException(ErrorCode.BUDGET_EXCEEDED);
    var placements = json.tree(version.placements());
    if (rules.placementLimit() != null && placements.size() > rules.placementLimit())
      throw new LeagueException(ErrorCode.LEAGUE_RULES_MISMATCH);
    BigDecimal totalArea = BigDecimal.ZERO;
    for (var p : placements) totalArea = totalArea.add(p.path("areaM2").decimalValue());
    if (rules.areaLimitM2() != null && totalArea.compareTo(rules.areaLimitM2()) > 0)
      throw new LeagueException(ErrorCode.LEAGUE_RULES_MISMATCH);
    for (var p : json.tree(version.placements()))
      if (rules.allowedTypes().stream()
          .noneMatch(t -> t.name().equals(p.path("facilityType").asString())))
        throw new LeagueException(ErrorCode.LEAGUE_RULES_MISMATCH);
    var engine = json.tree(job.result()).path("engine");
    if (!engine.path("revision").asString().equals(rules.engineRevision())
        || !engine.path("generatorSha256").asString().equals(rules.generatorSha256())
        || !engine.path("binarySha256").asString().matches("[a-f0-9]{64}"))
      throw new LeagueException(ErrorCode.LEAGUE_RULES_MISMATCH);
    String fingerprint =
        json.hash(
            rules.engineRevision()
                + "\n"
                + rules.generatorSha256()
                + "\n"
                + engine.path("binarySha256").asString());
    if (l.executionHash() != null && !l.executionHash().equals(fingerprint))
      throw new LeagueException(ErrorCode.LEAGUE_RULES_MISMATCH);
    leagues.submit(id, jobId, a.id(), score, version.cost(), fingerprint, now, team);
    // 첫 유효 제출과 팀 구성 고정을 같은 트랜잭션에서 기록한다.
    participation.freeze(team);
    research.audit(a.id(), "LEAGUE_SUBMITTED", id);
    return leagues.existing(id, jobId, a.id()).orElseThrow();
  }
}
