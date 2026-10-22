import io.waterleague.WaterLeagueApplication;
import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.budget.service.BudgetService;
import io.waterleague.common.exception.DomainException;
import io.waterleague.common.service.JsonService;
import io.waterleague.competition.entity.Competition;
import io.waterleague.competition.repository.CompetitionRepository;
import io.waterleague.competition.service.CompetitionService;
import io.waterleague.disaster.service.DisasterService;
import io.waterleague.district.repository.DistrictRepository;
import io.waterleague.evaluation.service.ScorePolicyService;
import io.waterleague.historical.dto.HistoricalSubmissionRequest;
import io.waterleague.historical.service.HistoricalSubmissionService;
import io.waterleague.installation.dto.InstallRequest;
import io.waterleague.installation.entity.SharedInstallation;
import io.waterleague.installation.repository.InstallationRepository;
import io.waterleague.installation.repository.SiteCatalogRepository;
import io.waterleague.installation.service.InstallationService;
import io.waterleague.installation.view.SiteView;
import io.waterleague.strategy.entity.FacilityType;
import java.math.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import org.springframework.boot.*;
import org.springframework.context.ConfigurableApplicationContext;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

public class PlayTestCompetition {
  static final String BATCH = "TEST_COMPETITIONS_20261022";
  static final BigDecimal STEP = new BigDecimal("0.01");
  static JsonService json;
  static Path directory;

  static void require(boolean value) {
    if (!value) throw new IllegalStateException("TEST_COMPETITION_CONTRACT_INVALID");
  }

  static UUID key(String name) {
    return UUID.nameUUIDFromBytes((BATCH + "/" + name).getBytes(StandardCharsets.UTF_8));
  }

  static void save(Path path, JsonNode value) throws Exception {
    Path next = path.resolveSibling(path.getFileName() + ".next");
    Files.writeString(next, json.write(value));
    Files.setPosixFilePermissions(
        next, java.nio.file.attribute.PosixFilePermissions.fromString("rw-------"));
    Files.move(next, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
  }

  record Choice(SiteView site, FacilityType type, BigDecimal area) {
    BigDecimal unit() {
      return site.unitCosts().get(type.name());
    }

    BigDecimal cost() {
      return area.multiply(unit()).setScale(2);
    }

    Choice area(BigDecimal value) {
      return new Choice(site, type, value);
    }
  }

  static List<Choice> optimize(List<Choice> source, BigDecimal limit) {
    var result = new ArrayList<>(source);
    BigDecimal total = result.stream().map(Choice::cost).reduce(BigDecimal.ZERO, BigDecimal::add);
    // 마지막 잔액은 서로 다른 단가의 0.01㎡ 조합으로 줄이며 부지 상한은 유지한다.
    for (int i = 0; i < result.size() && total.compareTo(limit) < 0; i++) {
      for (int j = i + 1; j < result.size() && total.compareTo(limit) < 0; j++) {
        Choice a = result.get(i), b = result.get(j);
        long pa = a.unit().longValueExact(), pb = b.unit().longValueExact();
        if (pa == pb) continue;
        long target =
            limit.subtract(total).add(a.cost()).add(b.cost()).movePointRight(2).longValueExact();
        long ca = a.site().maxAreaFor(a.type()).movePointRight(2).longValue();
        long cb = b.site().maxAreaFor(b.type()).movePointRight(2).longValue();
        long from = Math.max(1, Math.floorDiv(target - pb * cb + pa - 1, pa));
        long to = Math.min(ca, (target - pb) / pa);
        long best = limit.subtract(total).movePointRight(2).longValueExact(), ax = 0, bx = 0;
        for (long x = from; x <= to; x++) {
          long y = Math.min(cb, (target - pa * x) / pb);
          long rest = target - pa * x - pb * y;
          if (y >= 1 && rest < best) {
            best = rest;
            ax = x;
            bx = y;
            if (best == 0) break;
          }
        }
        if (ax > 0) {
          result.set(i, a.area(BigDecimal.valueOf(ax, 2)));
          result.set(j, b.area(BigDecimal.valueOf(bx, 2)));
          total = limit.subtract(BigDecimal.valueOf(best, 2));
        }
      }
    }
    return result;
  }

  static List<Choice> design(
      ConfigurableApplicationContext context,
      String district,
      List<FacilityType> types,
      BigDecimal limit,
      int variant,
      Map<String, List<SiteView>> cache) {
    var sites = context.getBean(SiteCatalogRepository.class);
    var center = context.getBean(DistrictRepository.class).require(district).center();
    var pool = new ArrayList<Choice>();
    for (var type : types) {
      var values =
          cache.computeIfAbsent(
              district + "/" + type,
              ignored ->
                  sites
                      .nearest(district, center.get(0), center.get(1), 0, type, false, null)
                      .sites());
      for (var site : values)
        if (site.suitability().explorationAllowed()
            && site.existingInfrastructure() == null
            && site.allowedTypes().contains(type.name())
            && site.maxAreaFor(type).compareTo(STEP) >= 0)
          pool.add(new Choice(site, type, site.maxAreaFor(type).setScale(2, RoundingMode.DOWN)));
    }
    var selected = new ArrayList<Choice>();
    var used = new HashSet<String>();
    BigDecimal left = limit;
    for (int n = 0; n < types.size(); n++) {
      var type = types.get((n + variant) % types.size());
      var choices =
          pool.stream()
              .filter(c -> c.type() == type && !used.contains(c.site().cellId()))
              .sorted(Comparator.comparing(Choice::cost).reversed())
              .toList();
      if (choices.isEmpty()) continue;
      var chosen = choices.get(Math.min(variant % 4, choices.size() - 1));
      var area =
          limit
              .multiply(new BigDecimal("0.08"))
              .min(left)
              .divide(chosen.unit(), 2, RoundingMode.DOWN)
              .min(chosen.area());
      if (area.signum() <= 0) continue;
      chosen = chosen.area(area);
      selected.add(chosen);
      used.add(chosen.site().cellId());
      left = left.subtract(chosen.cost());
    }
    while (left.signum() > 0 && selected.size() < 30) {
      BigDecimal remaining = left;
      var choices =
          pool.stream()
              .filter(
                  c ->
                      !used.contains(c.site().cellId())
                          && c.unit().multiply(STEP).compareTo(remaining) <= 0)
              .sorted(Comparator.comparing(Choice::cost).reversed())
              .toList();
      if (choices.isEmpty()) break;
      var chosen = choices.get(Math.min(variant % 3, choices.size() - 1));
      chosen = chosen.area(left.divide(chosen.unit(), 2, RoundingMode.DOWN).min(chosen.area()));
      selected.add(chosen);
      used.add(chosen.site().cellId());
      left = left.subtract(chosen.cost());
    }
    selected = new ArrayList<>(optimize(selected, limit));
    BigDecimal total = selected.stream().map(Choice::cost).reduce(BigDecimal.ZERO, BigDecimal::add);
    require(
        selected.size() >= 3
            && total.compareTo(limit) <= 0
            && total.compareTo(limit.multiply(new BigDecimal("0.99999"))) >= 0);
    return selected;
  }

  static Account player(ConfigurableApplicationContext context, String username) {
    require(username.matches("TEST_20261022_11[0-9]{3}_0[1-3]"));
    var a = context.getBean(AccountRepository.class).byUsername(username).orElseThrow();
    require(a.usable() && "MEMBER".equals(a.role()) && "PLAYER".equals(a.memberType()));
    return a;
  }

  static void plan(ConfigurableApplicationContext context, JsonNode input, Competition c)
      throws Exception {
    Path path = directory.resolve("plan.json");
    require(!Files.exists(path));
    var rules = json.tree(c.rules());
    var limit =
        rules.path("personalBudgetKrw").isNumber()
            ? rules.path("personalBudgetKrw").decimalValue()
            : context.getBean(BudgetService.class).limit();
    var types = new ArrayList<FacilityType>();
    for (var t : rules.path("allowedTypes")) types.add(FacilityType.valueOf(t.asString()));
    var allowed = new HashSet<String>();
    rules.path("districtIds").forEach(d -> allowed.add(d.asString()));
    var output = json.tree("{}");
    var root = (ObjectNode) output;
    root.put("competitionId", c.id().toString())
        .put("rulesHash", c.rulesHash())
        .put("runtimePolicySha256", context.getBean(ScorePolicyService.class).sha256())
        .put("mode", c.mode())
        .put("limitKrw", limit);
    var players = root.putArray("players");
    var cache = new HashMap<String, List<SiteView>>();
    int index = 0;
    for (var row : input.path("players")) {
      var a = player(context, row.path("username").asString());
      String district = row.path("districtId").asString();
      require(allowed.contains(district));
      var selected = design(context, district, types, limit, index++, cache);
      var p = players.addObject();
      p.put("username", a.username()).put("ownerId", a.id().toString());
      var items = p.putArray("placements");
      for (var item : selected)
        items
            .addObject()
            .put("districtId", district)
            .put("cellId", item.site().cellId())
            .put("facilityType", item.type().name())
            .put("areaM2", item.area())
            .put("unitCostKrw", item.unit())
            .put("costKrw", item.cost())
            .put("maxAreaM2", item.site().maxAreaFor(item.type()))
            .put("siteModelHash", item.site().modelHash());
      p.put(
          "spentKrw", selected.stream().map(Choice::cost).reduce(BigDecimal.ZERO, BigDecimal::add));
    }
    require(players.size() == 10);
    save(path, root);
    System.out.println("TEST_COMPETITION_PLAN " + c.mode() + " players=" + players.size());
  }

  @SuppressWarnings("unchecked")
  static void apply(ConfigurableApplicationContext context, Competition c) throws Exception {
    var plan = json.tree(Files.readString(directory.resolve("plan.json")));
    require(
        c.id().toString().equals(plan.path("competitionId").asString())
            && c.rulesHash().equals(plan.path("rulesHash").asString())
            && context
                .getBean(ScorePolicyService.class)
                .sha256()
                .equals(plan.path("runtimePolicySha256").asString()));
    var service = context.getBean(CompetitionService.class);
    Path path = directory.resolve("progress.json");
    var progress =
        (ObjectNode) json.tree(Files.exists(path) ? Files.readString(path) : "{\"players\":{}}");
    var report = (ObjectNode) progress.path("players");
    for (var row : plan.path("players")) {
      var a = player(context, row.path("username").asString());
      require(a.id().toString().equals(row.path("ownerId").asString()));
      service.join(a, c.id(), c.rulesHash());
      var p =
          report.has(a.username())
              ? (ObjectNode) report.path(a.username())
              : report.putObject(a.username());
      if ("REALTIME".equals(c.mode())) {
        var installations = context.getBean(InstallationRepository.class);
        var install = context.getBean(InstallationService.class);
        var ids = p.putArray("installationIds");
        for (var item : row.path("placements")) {
          var own =
              (List<SharedInstallation>)
                  installations
                      .getClass()
                      .getMethod("owned", UUID.class, UUID.class)
                      .invoke(installations, a.id(), c.id());
          var old =
              own.stream()
                  .filter(v -> v.cellId().equals(item.path("cellId").asString()))
                  .findFirst();
          var value =
              old.isPresent()
                  ? old.get()
                  : (SharedInstallation)
                      install
                          .getClass()
                          .getMethod("install", String.class, InstallRequest.class, UUID.class)
                          .invoke(
                              install,
                              a.username(),
                              new InstallRequest(
                                  item.path("districtId").asString(),
                                  item.path("cellId").asString(),
                                  FacilityType.valueOf(item.path("facilityType").asString()),
                                  item.path("areaM2").decimalValue()),
                              c.id());
          require(
              value.facilityType().name().equals(item.path("facilityType").asString())
                  && value.areaM2().compareTo(item.path("areaM2").decimalValue()) == 0
                  && value.cost().compareTo(item.path("costKrw").decimalValue()) == 0);
          ids.add(value.id().toString());
          save(path, progress);
        }
      } else {
        // 구 규칙의 일반 제출 연결을 유지하며 개최 당시의 계산 버전으로 접수한다.
        require(
            json.tree(c.rules()).path("schemaVersion").asInt() == 1
                && c.scorePolicySha256()
                    .equals(context.getBean(ScorePolicyService.class).sha256()));
        var event =
            context.getBean(DisasterService.class).catalog().events().stream()
                .filter(v -> v.id().equals(c.eventId()))
                .findFirst()
                .orElseThrow();
        Instant start = Instant.parse(event.regions().getFirst().start());
        var items = new ArrayList<HistoricalSubmissionRequest.Item>();
        int slot = 0;
        for (var item : row.path("placements"))
          items.add(
              new HistoricalSubmissionRequest.Item(
                  item.path("districtId").asString(),
                  item.path("cellId").asString(),
                  FacilityType.valueOf(item.path("facilityType").asString()),
                  item.path("areaM2").decimalValue(),
                  start.plusSeconds(60 + slot++ * 300L),
                  null));
        var value =
            context
                .getBean(HistoricalSubmissionService.class)
                .submit(
                    a.id(),
                    new HistoricalSubmissionRequest(
                        key(c.id() + "/" + a.username()), c.eventId(), items));
        service.submit(a, c.id(), value.id(), c.rulesHash());
        p.put("jobId", value.id().toString());
        save(path, progress);
      }
      p.put("spentKrw", row.path("spentKrw").decimalValue());
      save(path, progress);
      System.out.println("TEST_COMPETITION_APPLIED " + c.mode() + " players=" + report.size());
    }
  }

  public static void main(String[] args) {
    int status = 1;
    try {
      require(args.length == 2 && BATCH.equals(System.getenv("WATERLEAGUE_TEST_COMPETITION")));
      directory = Path.of(args[1]);
      var app = new SpringApplication(WaterLeagueApplication.class);
      app.setWebApplicationType(WebApplicationType.NONE);
      try (var context = app.run()) {
        json = context.getBean(JsonService.class);
        var input = json.tree(Files.readString(directory.resolve("input.json")));
        var c =
            context
                .getBean(CompetitionRepository.class)
                .get(UUID.fromString(input.path("competitionId").asString()), false)
                .orElseThrow();
        require(
            c.rulesHash().equals(input.path("rulesHash").asString())
                && json.hash(c.rules()).equals(c.rulesHash())
                && "PUBLISHED".equals(c.state())
                && Instant.now().isAfter(c.opensAt())
                && Instant.now().isBefore(c.closesAt()));
        if ("plan".equals(args[0])) plan(context, input, c);
        else {
          require("apply".equals(args[0]));
          apply(context, c);
        }
      }
      status = 0;
    } catch (Exception error) {
      while (error instanceof java.lang.reflect.InvocationTargetException
          && error.getCause() instanceof Exception nested) error = nested;
      System.err.println(
          "TEST_COMPETITION_FAILED "
              + (error instanceof DomainException domain
                  ? domain.code().name()
                  : error.getClass().getSimpleName()));
    }
    System.exit(status);
  }
}
