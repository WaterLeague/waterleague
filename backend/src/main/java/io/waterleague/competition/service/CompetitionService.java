package io.waterleague.competition.service;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.competition.dto.CompetitionRequest;
import io.waterleague.competition.entity.Competition;
import io.waterleague.competition.repository.CompetitionRepository;
import io.waterleague.disaster.service.DisasterService;
import io.waterleague.district.repository.DistrictRepository;
import io.waterleague.evaluation.service.ScorePolicyService;
import io.waterleague.research.repository.ResearchRepository;
import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.time.*;
import java.time.temporal.ChronoUnit;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CompetitionService {
  private final CompetitionRepository repo;
  private final ResearchRepository organizations;
  private final AccountRepository accounts;
  private final DistrictRepository districts;
  private final DisasterService disasters;
  private final ScorePolicyService policy;
  private final JsonService json;
  private final io.waterleague.budget.service.BudgetService budget;

  public CompetitionService(
      CompetitionRepository repo,
      ResearchRepository organizations,
      AccountRepository accounts,
      DistrictRepository districts,
      DisasterService disasters,
      ScorePolicyService policy,
      JsonService json,
      io.waterleague.budget.service.BudgetService budget) {
    this.repo = repo;
    this.organizations = organizations;
    this.accounts = accounts;
    this.districts = districts;
    this.disasters = disasters;
    this.policy = policy;
    this.json = json;
    this.budget = budget;
  }

  private Account lock(Account a) {
    organizations.ownerLock(a.id());
    var current =
        accounts.byId(a.id()).orElseThrow(() -> new DomainException(ErrorCode.ACCESS_DENIED));
    if (!current.usable()) throw new DomainException(ErrorCode.ACCESS_DENIED);
    return current;
  }

  private void host(Account a) {
    if (!a.usable()
        || !a.organizationMember()
        || a.organizationId() == null
        || !organizations.approved(a.organizationId()))
      throw new DomainException(ErrorCode.ACCESS_DENIED);
  }

  private boolean manages(Account a, Competition c) {
    return a != null
        && a.usable()
        && (a.role().equals("ADMIN")
            || a.organizationMember()
                && Objects.equals(a.organizationId(), c.organizationId())
                && organizations.approved(c.organizationId()));
  }

  private Competition require(UUID id, boolean locked) {
    var c =
        repo.get(id, locked).orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    if (!json.hash(c.rules()).equals(c.rulesHash()))
      throw new DomainException(ErrorCode.RESULT_QUALITY_FAILED);
    return c;
  }

  private String phase(Competition c, Instant now) {
    return c.state().equals("CANCELLED")
        ? "CANCELLED"
        : now.isBefore(c.opensAt()) ? "UPCOMING" : now.isBefore(c.closesAt()) ? "OPEN" : "ENDED";
  }

  private Map<String, Object> view(Competition c, Account a) {
    var v = new LinkedHashMap<String, Object>();
    v.put("id", c.id());
    v.put("title", c.title());
    v.put("description", c.description());
    v.put("organizationName", c.organizationName());
    v.put("mode", c.mode());
    v.put("eventId", c.eventId());
    v.put("opensAt", c.opensAt());
    v.put("closesAt", c.closesAt());
    v.put("phase", phase(c, repo.now()));
    v.put("rules", json.tree(c.rules()));
    v.put("rulesHash", c.rulesHash());
    v.put("canManage", manages(a, c));
    v.put("joinedAt", a == null ? null : repo.joined(c.id(), a.id()));
    v.put("participantCount", repo.participants(c.id()));
    return v;
  }

  public Object catalog() {
    return Map.of(
        "districts",
        districts.all(),
        "events",
        disasters.catalog().events().stream()
            .map(e -> Map.of("id", e.id(), "title", e.title()))
            .toList(),
        "facilityTypes",
        FacilityType.values(),
        "defaultPersonalBudgetKrw",
        budget.limit(),
        "serverNow",
        repo.now());
  }

  public Object list(Account a, int page) {
    checkPage(page);
    var all = repo.list(page);
    return Map.of(
        "items",
        all.stream().limit(20).map(c -> view(c, a)).toList(),
        "page",
        page,
        "hasMore",
        all.size() > 20);
  }

  public Object detail(Account a, UUID id) {
    return view(require(id, false), a);
  }

  private String rules(CompetitionRequest d, String sha) {
    var v = new TreeMap<String, Object>();
    v.put("schemaVersion", 2);
    String mode = d.budgetMode() == null ? "DEFAULT" : d.budgetMode();
    if (mode.equals("CUSTOM") ? d.personalBudgetKrw() == null : d.personalBudgetKrw() != null)
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    v.put("budgetMode", mode);
    v.put("personalBudgetKrw", mode.equals("CUSTOM") ? d.personalBudgetKrw() : budget.limit());
    v.put("title", d.title().strip());
    v.put("description", d.description().strip());
    v.put("mode", d.mode());
    v.put("eventId", d.eventId());
    v.put("districtIds", d.districtIds().stream().sorted().toList());
    v.put("allowedTypes", d.allowedTypes().stream().map(Enum::name).sorted().toList());
    v.put("opensAt", d.opensAt());
    v.put("closesAt", d.closesAt());
    v.put(
        "awards",
        d.awards().stream()
            .sorted(Comparator.comparingInt(CompetitionRequest.Award::rankFrom))
            .toList());
    v.put("awardNotice", d.awardNotice().strip());
    v.put("scorePolicySha256", sha);
    v.put("scoreRule", "BASELINE_MINUS_ACCOUNTED_VOLUME_M3");
    v.put("realtimePolicy", "DEDICATED_COMPETITION_INSTALLATIONS_V2");
    return json.write(v);
  }

  @Transactional
  public Object create(Account actor, CompetitionRequest d) {
    var a = lock(actor);
    host(a);
    repo.lockOrganization(a.organizationId());
    host(a);
    var previous = repo.byKey(a.id(), d.requestKey());
    if (previous.isPresent()) {
      var c = previous.get();
      String requested = rules(d, c.scorePolicySha256());
      if (json.tree(c.rules()).path("schemaVersion").asInt() == 1) {
        var legacy = (tools.jackson.databind.node.ObjectNode) json.tree(requested);
        if ("CUSTOM".equals(d.budgetMode())) throw new DomainException(ErrorCode.CONFLICT);
        legacy.remove("budgetMode");
        legacy.remove("personalBudgetKrw");
        legacy.put("schemaVersion", 1);
        legacy.put("realtimePolicy", "JOINED_PERIOD_WEEKLY_INSTALLATIONS_V1");
        requested = json.write(legacy);
      }
      if (!c.rules().equals(requested)) throw new DomainException(ErrorCode.CONFLICT);
      return view(c, a);
    }
    var now = repo.now();
    if (d.title().isBlank()
        || d.description().isBlank()
        || !d.closesAt().isAfter(d.opensAt())
        || d.opensAt().isBefore(now.minusSeconds(60))
        || d.closesAt().isAfter(now.plus(366, ChronoUnit.DAYS))
        || !d.opensAt().equals(d.opensAt().truncatedTo(ChronoUnit.MINUTES))
        || !d.closesAt().equals(d.closesAt().truncatedTo(ChronoUnit.MINUTES)))
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    d.districtIds().forEach(districts::require);
    if (d.mode().equals("REALTIME") && d.eventId() != null
        || d.mode().equals("DISASTER")
            && disasters.catalog().events().stream().noneMatch(e -> e.id().equals(d.eventId())))
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    var ranks = new HashSet<Integer>();
    long total = 0;
    for (var award : d.awards()) {
      if (award.title().isBlank() || award.rankFrom() > award.rankTo())
        throw new DomainException(ErrorCode.REQUEST_INVALID);
      for (int rank = award.rankFrom(); rank <= award.rankTo(); rank++)
        if (!ranks.add(rank)) throw new DomainException(ErrorCode.REQUEST_INVALID);
      total += (award.rankTo() - award.rankFrom() + 1L) * award.prizeKrw();
    }
    if (total > 1000000000L || !d.awards().isEmpty() && d.awardNotice().strip().length() < 10)
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    if (repo.active(a.organizationId()) >= 20) throw new DomainException(ErrorCode.RATE_LIMITED);
    String rules = rules(d, policy.sha256());
    var c =
        new Competition(
            UUID.randomUUID(),
            a.organizationId(),
            a.id(),
            a.organizationName(),
            d.title().strip(),
            d.description().strip(),
            d.mode(),
            d.eventId(),
            d.opensAt(),
            d.closesAt(),
            rules,
            json.hash(rules),
            policy.sha256(),
            "PUBLISHED");
    repo.add(c, d.requestKey());
    organizations.audit(a.id(), "COMPETITION_CREATED", c.id());
    return view(require(c.id(), false), a);
  }

  @Transactional
  public Object join(Account actor, UUID id, String hash) {
    var a = lock(actor);
    if (!a.role().equals("MEMBER") || !"PLAYER".equals(a.memberType()))
      throw new DomainException(ErrorCode.ACCESS_DENIED);
    var c = require(id, true);
    if (!c.rulesHash().equals(hash)) throw new DomainException(ErrorCode.CONFLICT);
    if (repo.joined(id, a.id()) != null) return view(c, a);
    if (c.state().equals("CANCELLED")
        || !repo.now().isBefore(c.closesAt())
        || !organizations.approved(c.organizationId()))
      throw new DomainException(ErrorCode.CONFLICT);
    if (repo.participants(id) >= 1000) throw new DomainException(ErrorCode.RATE_LIMITED);
    repo.join(id, a.id(), hash);
    organizations.audit(a.id(), "COMPETITION_JOINED", id);
    return view(c, a);
  }

  @Transactional
  public Object cancel(Account actor, UUID id) {
    var a = lock(actor);
    var c = require(id, true);
    if (!manages(a, c)) throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
    if (!repo.now().isBefore(c.closesAt())) throw new DomainException(ErrorCode.CONFLICT);
    repo.cancel(id);
    organizations.audit(a.id(), "COMPETITION_CANCELLED", id);
    return view(require(id, false), a);
  }

  private Set<String> strings(Competition c, String field) {
    var out = new HashSet<String>();
    json.tree(c.rules()).path(field).forEach(v -> out.add(v.asString()));
    return out;
  }

  private boolean eligible(Competition c, Map<String, Object> job, Instant joined) {
    if (joined == null) return false;
    var rules = json.tree(c.rules());
    if (rules.path("schemaVersion").asInt() >= 2 && !c.id().equals(job.get("competitionId")))
      return false;
    var limit =
        rules.path("personalBudgetKrw").isNumber()
            ? rules.path("personalBudgetKrw").decimalValue()
            : budget.limit();
    if (job.get("cost") instanceof BigDecimal cost && cost.compareTo(limit) > 0) return false;
    var created = (Instant) job.get("createdAt");
    if (created.isBefore(joined)
        || created.isBefore(c.opensAt())
        || !created.isBefore(c.closesAt())) return false;
    var placements = json.tree((String) job.get("placements"));
    if (!placements.isArray() || placements.isEmpty()) return false;
    var allowedDistricts = strings(c, "districtIds");
    var types = strings(c, "allowedTypes");
    for (var p : placements)
      if (!allowedDistricts.contains(p.path("districtId").asString())
          || !types.contains(p.path("facilityType").asString())) return false;
    var raw = placements.get(0).path("submissionRulesRaw").asString("");
    return !raw.isBlank()
        && json.tree(raw)
            .path("scorePolicy")
            .path("sha256")
            .asString()
            .equals(c.scorePolicySha256());
  }

  public Object candidates(Account a, UUID id) {
    var c = require(id, false);
    var joined = repo.joined(id, a.id());
    if (joined == null || !c.mode().equals("DISASTER"))
      throw new DomainException(ErrorCode.ACCESS_DENIED);
    return repo.historicalJobs(a.id(), c.eventId()).stream()
        .filter(j -> eligible(c, j, joined))
        .map(
            j ->
                Map.of(
                    "id",
                    j.get("id"),
                    "state",
                    j.get("state"),
                    "createdAt",
                    j.get("createdAt"),
                    "entered",
                    repo.entered(id, (UUID) j.get("id"), a.id())))
        .toList();
  }

  @Transactional
  public Object submit(Account actor, UUID id, UUID jobId, String hash) {
    var a = lock(actor);
    var c = require(id, true);
    var joined = repo.joined(id, a.id());
    if (joined == null || !c.mode().equals("DISASTER"))
      throw new DomainException(ErrorCode.ACCESS_DENIED);
    if (!c.rulesHash().equals(hash)) throw new DomainException(ErrorCode.CONFLICT);
    if (repo.entered(id, jobId, a.id())) return Map.of("accepted", true);
    if (!phase(c, repo.now()).equals("OPEN") || !organizations.approved(c.organizationId()))
      throw new DomainException(ErrorCode.CONFLICT);
    var job =
        repo.historicalJobs(a.id(), c.eventId()).stream()
            .filter(j -> j.get("id").equals(jobId))
            .findFirst()
            .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    if (!eligible(c, job, joined) || Set.of("FAILED", "REJECTED").contains(job.get("state")))
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    repo.submit(id, a.id(), jobId);
    organizations.audit(a.id(), "COMPETITION_SUBMITTED", id);
    return Map.of("accepted", true);
  }

  public void checkPage(int page) {
    if (page < 0 || page > 1000) throw new DomainException(ErrorCode.REQUEST_INVALID);
  }

  @Transactional(
      readOnly = true,
      isolation = org.springframework.transaction.annotation.Isolation.REPEATABLE_READ)
  public Object results(Account a, UUID id, int page) {
    checkPage(page);
    var c = require(id, false);
    if (!manages(a, c) && repo.joined(id, a.id()) == null)
      throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
    Instant now = repo.now();
    var rows = new ArrayList<Map<String, Object>>();
    boolean pending = false;
    long missing = 0;
    if (c.mode().equals("REALTIME")) {
      Instant target =
          now.isBefore(c.closesAt())
              ? now.minusSeconds(120).truncatedTo(ChronoUnit.MINUTES)
              : c.closesAt();
      var grouped = new LinkedHashMap<UUID, List<Map<String, Object>>>();
      for (var i : repo.liveInstallations(id, target))
        grouped.computeIfAbsent((UUID) i.get("playerId"), k -> new ArrayList<>()).add(i);
      for (var installations : grouped.values()) {
        var first = installations.getFirst();
        var groups = new HashSet<Object>();
        BigDecimal score = BigDecimal.ZERO;
        long evaluated = 0, expected = 0;
        boolean valid = true;
        for (var i : installations) {
          expected += (long) i.get("expectedSeconds");
          evaluated += (long) i.get("evaluatedSeconds");
          if (i.get("scoreM3") != null) {
            groups.add(i.get("group"));
            score = score.add((BigDecimal) i.get("scoreM3"));
            valid &= c.scorePolicySha256().equals(i.get("policy"));
          }
        }
        missing += Math.max(0, expected - evaluated);
        valid &=
            evaluated > 0 && evaluated <= expected && groups.size() == 1 && !groups.contains(null);
        var row = new LinkedHashMap<String, Object>();
        row.put("playerId", first.get("playerId"));
        row.put("nickname", first.get("nickname"));
        row.put("scoreM3", valid ? score : null);
        row.put("group", valid ? groups.iterator().next() : "WITHHELD");
        row.put("comparable", valid);
        row.put("evaluatedSeconds", evaluated);
        row.put("expectedSeconds", expected);
        row.put(
            "installations",
            installations.stream()
                .map(
                    i -> {
                      var v = new LinkedHashMap<>(i);
                      v.remove("policy");
                      v.remove("group");
                      return v;
                    })
                .toList());
        rows.add(row);
      }
    } else {
      rows.addAll(repo.disasterRows(id));
      for (var r : rows)
        if (!c.scorePolicySha256().equals(r.get("policy"))) {
          r.put("comparable", false);
          r.put("scoreM3", null);
        }
      pending = repo.pendingDisaster(id) > 0;
    }
    var groups = new TreeMap<String, List<Map<String, Object>>>();
    for (var row : rows) {
      boolean comparable = Boolean.TRUE.equals(row.get("comparable"));
      row.remove("policy");
      row.put(
          "scoreM3Exact",
          comparable && row.get("scoreM3") != null
              ? ((BigDecimal) row.get("scoreM3")).toPlainString()
              : null);
      if (!comparable) row.put("scoreM3", null);
      groups
          .computeIfAbsent(
              comparable ? (String) row.get("group") : "WITHHELD", k -> new ArrayList<>())
          .add(row);
      row.remove("group");
    }
    var output = new ArrayList<Object>();
    boolean hasMore = false;
    for (var g : groups.entrySet()) {
      var values = g.getValue();
      values.sort(
          Comparator.<Map<String, Object>, BigDecimal>comparing(
                  v -> (BigDecimal) v.get("scoreM3"),
                  Comparator.nullsLast(Comparator.reverseOrder()))
              .thenComparing(v -> v.get("playerId").toString()));
      BigDecimal previous = null;
      int rank = 0;
      for (int index = 0; index < values.size(); index++) {
        var r = values.get(index);
        var score = (BigDecimal) r.get("scoreM3");
        if (score != null && (previous == null || score.compareTo(previous) != 0)) rank = index + 1;
        r.put("rank", score == null ? null : rank);
        previous = score;
      }
      hasMore |= values.size() > (page + 1) * 100;
      output.add(
          Map.of(
              "comparisonGroup",
              g.getKey(),
              "entries",
              values.stream().skip(page * 100L).limit(100).toList(),
              "count",
              values.size(),
              "ownEntries",
              values.stream().filter(v -> a.id().equals(v.get("playerId"))).toList()));
    }
    String phase = phase(c, now);
    String status =
        phase.equals("CANCELLED")
            ? "CANCELLED"
            : phase.equals("UPCOMING")
                ? "UPCOMING"
                : !phase.equals("ENDED")
                    ? "IN_PROGRESS"
                    : pending || missing > 0
                        ? "PROVISIONAL"
                        : groups.containsKey("WITHHELD")
                            ? "WITHHELD"
                            : rows.isEmpty() ? "EMPTY" : "FINAL";
    return Map.of(
        "competition",
        view(c, a),
        "status",
        status,
        "groups",
        output,
        "page",
        page,
        "hasMore",
        hasMore,
        "missingSeconds",
        missing,
        "pendingCalculations",
        pending,
        "generatedAt",
        now);
  }
}
