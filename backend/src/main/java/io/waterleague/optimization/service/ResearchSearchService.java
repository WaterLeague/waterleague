package io.waterleague.optimization.service;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.analysis.exception.IncompatibleAnalysisException;
import io.waterleague.analysis.repository.ResearchAnalysisRepository;
import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.model.repository.LabModelRepository;
import io.waterleague.model.service.LabModelService;
import io.waterleague.optimization.dto.CreateSearchRequest;
import io.waterleague.optimization.entity.*;
import io.waterleague.optimization.mapper.ResearchSearchMapper;
import io.waterleague.optimization.repository.ResearchSearchRepository;
import io.waterleague.optimization.view.SearchView;
import io.waterleague.ranking.service.ExploratoryResultService;
import io.waterleague.research.repository.ResearchRepository;
import io.waterleague.simulation.repository.SimulationRepository;
import io.waterleague.strategy.entity.Placement;
import io.waterleague.strategy.repository.StrategyRepository;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ResearchSearchService {
  private final ResearchSearchRepository searches;
  private final ResearchRepository research;
  private final ResearchAnalysisRepository analyses;
  private final AccountRepository accounts;
  private final SimulationRepository jobs;
  private final StrategyRepository strategies;
  private final LabModelRepository models;
  private final LabModelService validation;
  private final CandidateGenerationService generator;
  private final ExploratoryResultService scores;
  private final ResearchSearchMapper mapper;
  private final SearchArtifactService artifacts;
  private final JsonService json;

  public ResearchSearchService(
      ResearchSearchRepository searches,
      ResearchRepository research,
      ResearchAnalysisRepository analyses,
      AccountRepository accounts,
      SimulationRepository jobs,
      StrategyRepository strategies,
      LabModelRepository models,
      LabModelService validation,
      CandidateGenerationService generator,
      ExploratoryResultService scores,
      ResearchSearchMapper mapper,
      SearchArtifactService artifacts,
      JsonService json) {
    this.searches = searches;
    this.research = research;
    this.analyses = analyses;
    this.accounts = accounts;
    this.jobs = jobs;
    this.strategies = strategies;
    this.models = models;
    this.validation = validation;
    this.generator = generator;
    this.scores = scores;
    this.mapper = mapper;
    this.artifacts = artifacts;
    this.json = json;
  }

  private Account organization(Account actor) {
    var a = accounts.byId(actor.id()).orElseThrow(ResearchSearchService::missing);
    if (!a.usable()
        || !a.organizationMember()
        || a.organizationId() == null
        || !research.approved(a.organizationId()))
      throw new DomainException(ErrorCode.ACCESS_DENIED);
    if (!Objects.equals(a.organizationId(), actor.organizationId())) throw missing();
    return a;
  }

  private void allowed(Account a, List<UUID> sources) {
    var current = organization(a);
    if (sources.size() < 2 || sources.size() > 50) throw quality();
    for (var id : sources) if (!research.allowed(id, current.organizationId())) throw missing();
  }

  private ResearchSearch require(Account a, UUID id) {
    var current = organization(a);
    var r = searches.get(id, current.organizationId()).orElseThrow(ResearchSearchService::missing);
    allowed(current, searches.sources(id));
    return r;
  }

  private SearchGeneration checked(ResearchSearch r, List<ResearchCandidate> candidates) {
    if (!json.hash(r.provenance()).equals(r.provenanceHash())) throw quality();
    var g = json.read(r.provenance(), SearchGeneration.class);
    var s = r.settings();
    if (!g.modelHash().equals(r.modelHash())
        || g.schemaVersion() != 1
        || !g.policy().equals(CandidateGenerationService.POLICY)
        || g.settings().topK() != s.topK()
        || g.settings().seed() != s.seed()
        || g.settings().candidatesPerArm() != s.candidatesPerArm()
        || g.settings().budgetKrw().compareTo(s.budgetKrw()) != 0
        || g.candidates().size() != 2 * s.candidatesPerArm()
        || candidates.size() != g.candidates().size()) throw quality();
    var ids = g.sources().stream().map(x -> x.sample().jobId()).toList();
    if (ids.size() != g.requestedCount()
        || new HashSet<>(ids).size() != ids.size()
        || !new HashSet<>(ids).equals(new HashSet<>(searches.sources(r.id())))) throw quality();
    for (var c : candidates) {
      var expected =
          g.candidates().stream()
              .filter(x -> x.arm() == c.arm() && x.ordinal() == c.ordinal())
              .findFirst()
              .orElseThrow(ResearchSearchService::quality);
      if (!r.id().equals(c.searchId())
          || !r.modelHash().equals(c.modelHash())
          || !expected.inputHash().equals(c.inputHash())
          || !expected.placementsSource().equals(c.placements())
          || expected.costKrw().compareTo(c.cost()) != 0
          || !json.hash(c.modelHash() + "\n" + c.placements()).equals(c.inputHash()))
        throw quality();
    }
    return g;
  }

  public List<SearchView.Summary> list(Account actor) {
    var a = organization(actor);
    List<SearchView.Summary> result = new ArrayList<>();
    var rows = searches.visible(a.organizationId());
    for (var r : rows) {
      var candidates = searches.candidates(r.id());
      result.add(mapper.summary(mapper.view(r, checked(r, candidates), candidates)));
    }
    for (var r : rows) allowed(a, searches.sources(r.id()));
    organization(a);
    return List.copyOf(result);
  }

  public SearchView get(Account actor, UUID id) {
    var a = organization(actor);
    var r = require(a, id);
    var candidates = searches.candidates(id);
    var view = mapper.view(r, checked(r, candidates), candidates);
    allowed(a, searches.sources(id));
    research.audit(a.id(), "RESEARCH_SEARCH_READ", id);
    return view;
  }

  @Transactional
  public SearchView create(Account actor, CreateSearchRequest dto) {
    var a = organization(actor);
    var ids = dto.jobIds().stream().sorted(Comparator.comparing(UUID::toString)).toList();
    if (ids.size() < 2 || ids.size() > 50 || new HashSet<>(ids).size() != ids.size())
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    BigDecimal budget;
    try {
      budget = new BigDecimal(dto.budgetKrw().toBigIntegerExact());
    } catch (ArithmeticException e) {
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    }
    var settings = new SearchSettings(dto.topK(), budget, dto.seed(), dto.candidatesPerArm());
    allowed(a, ids);
    var owners =
        ids.stream()
            .map(id -> jobs.get(id).orElseThrow(ResearchSearchService::missing).ownerId())
            .distinct()
            .sorted(Comparator.comparing(UUID::toString))
            .toList();
    // 여러 원본의 동의 철회와 생성이 경합해도 같은 잠금 순서로 처리한다.
    for (var owner : owners) research.ownerLock(owner);
    allowed(a, ids);
    List<SearchSample> samples = new ArrayList<>();
    String modelHash = null;
    for (var id : ids) {
      var job = jobs.get(id).orElseThrow(ResearchSearchService::missing);
      var version =
          strategies
              .version(job.versionId(), job.ownerId())
              .orElseThrow(ResearchSearchService::missing);
      if (!version.inputHash().equals(job.inputHash())
          || !version.modelHash().equals(job.modelHash())
          || !json.hash(version.modelHash() + "\n" + version.placements())
              .equals(version.inputHash())
          || validation
                  .validate(
                      version.modelHash(),
                      List.of(json.read(version.placements(), Placement[].class)))
                  .compareTo(version.cost())
              != 0) throw quality();
      if (modelHash != null && !modelHash.equals(job.modelHash()))
        throw new IncompatibleAnalysisException();
      modelHash = job.modelHash();
      samples.add(
          new SearchSample(
              id,
              version.id(),
              version.inputHash(),
              version.placements(),
              scores.score(job),
              version.cost()));
    }
    validation.requireRunnable(modelHash);
    String requestHash =
        json.hash(json.write(List.of(CandidateGenerationService.POLICY, modelHash, ids, settings)));
    jobs.lockAdmission();
    var old = searches.byKey(a.organizationId(), dto.requestKey());
    if (old.isPresent()) {
      if (!old.get().requestHash().equals(requestHash))
        throw new DomainException(ErrorCode.CONFLICT);
      return get(a, old.get().id());
    }
    int count = settings.candidatesPerArm() * 2;
    if (jobs.totalActive() + count > 500 || analyses.active(a.organizationId()) + count > 9)
      throw new DomainException(ErrorCode.RATE_LIMITED);
    var generation = generator.generate(models.require(modelHash), samples, settings);
    String provenance = json.write(generation);
    var r =
        new ResearchSearch(
            UUID.randomUUID(),
            a.organizationId(),
            a.id(),
            dto.requestKey(),
            requestHash,
            modelHash,
            settings,
            provenance,
            json.hash(provenance),
            Instant.now());
    var candidates =
        generation.candidates().stream()
            .map(
                c ->
                    new ResearchCandidate(
                        UUID.randomUUID(),
                        r.id(),
                        c.arm(),
                        c.ordinal(),
                        c.placementsSource(),
                        r.modelHash(),
                        c.inputHash(),
                        c.costKrw(),
                        "QUEUED",
                        null,
                        null,
                        r.createdAt(),
                        null))
            .toList();
    searches.add(r, ids, candidates);
    allowed(a, ids);
    research.audit(a.id(), "RESEARCH_SEARCH_CREATED", r.id());
    return mapper.view(r, generation, candidates);
  }

  public String provenance(Account actor, UUID id) {
    var a = organization(actor);
    var r = require(a, id);
    checked(r, searches.candidates(id));
    allowed(a, searches.sources(id));
    research.audit(a.id(), "RESEARCH_SEARCH_PROVENANCE", id);
    return r.provenance();
  }

  public byte[] bundle(Account actor, UUID id, UUID candidateId) {
    var a = organization(actor);
    var r = require(a, id);
    var candidates = searches.candidates(id);
    checked(r, candidates);
    var candidate =
        candidates.stream()
            .filter(c -> c.id().equals(candidateId))
            .findFirst()
            .orElseThrow(ResearchSearchService::missing);
    scores.score(
        candidate.state(), candidate.modelHash(), candidate.inputHash(), candidate.result());
    var result = artifacts.bundle(r, candidate, searches.sources(id), () -> require(a, id));
    research.audit(a.id(), "RESEARCH_SEARCH_EXPORT", id);
    return result;
  }

  private static DomainException missing() {
    return new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
  }

  private static DomainException quality() {
    return new DomainException(ErrorCode.RESULT_QUALITY_FAILED);
  }
}
