import io.waterleague.WaterLeagueApplication;
import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.budget.service.BudgetService;
import io.waterleague.common.exception.DomainException;
import io.waterleague.common.service.JsonService;
import io.waterleague.district.repository.DistrictRepository;
import io.waterleague.evaluation.service.ScorePolicyService;
import io.waterleague.installation.dto.InstallRequest;
import io.waterleague.installation.repository.InstallationRepository;
import io.waterleague.installation.repository.SiteCatalogRepository;
import io.waterleague.installation.service.InstallationService;
import io.waterleague.installation.view.SiteView;
import io.waterleague.strategy.entity.FacilityType;
import java.math.*;
import java.nio.file.*;
import java.time.*;
import java.time.temporal.TemporalAdjusters;
import java.util.*;
import org.springframework.boot.*;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

public class PlayTestWeekly {
  static final Set<String> EMPTY = Set.of("11140", "11305");
  static final BigDecimal STEP = new BigDecimal("0.01");
  static JsonService json;
  static Path directory;
  static LocalDate week;

  static void require(boolean value) {
    if (!value) throw new IllegalStateException("TEST_WEEKLY_CONTRACT_INVALID");
  }

  static void save(Path path, JsonNode value) throws Exception {
    Path next = path.resolveSibling(path.getFileName() + ".next");
    Files.writeString(next, json.write(value));
    Files.setPosixFilePermissions(next, java.nio.file.attribute.PosixFilePermissions.fromString("rw-------"));
    Files.move(next, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
  }

  static Account player(ConfigurableApplicationContext context, String name) {
    require(name.matches("TEST_20261022_11[0-9]{3}_0[1-3]"));
    var a = context.getBean(AccountRepository.class).byUsername(name).orElseThrow();
    require(a.usable() && "MEMBER".equals(a.role()) && "PLAYER".equals(a.memberType())
        && !EMPTY.contains(a.districtId()) && name.contains("_" + a.districtId() + "_"));
    return a;
  }

  record Choice(SiteView site, FacilityType type, BigDecimal area) {
    BigDecimal unit() { return site.unitCosts().get(type.name()); }
    BigDecimal cost() { return area.multiply(unit()).setScale(2); }
    BigDecimal maximum() { return site.maxAreaFor(type).setScale(2, RoundingMode.DOWN); }
    Choice area(BigDecimal amount) { return new Choice(site, type, amount); }
  }

  static List<Choice> design(ConfigurableApplicationContext context, Account a, BigDecimal target,
      Random random, Map<String, List<Choice>> cache) {
    var pool = new ArrayList<>(cache.computeIfAbsent(a.districtId(), district -> {
      var sites = context.getBean(SiteCatalogRepository.class);
      var center = context.getBean(DistrictRepository.class).require(district).center();
      var result = new ArrayList<Choice>();
      for (var type : FacilityType.values())
        for (var s : sites.nearest(district, center.get(0), center.get(1), 0, type, false, null).sites())
          if (s.suitability().explorationAllowed() && s.existingInfrastructure() == null
              && s.allowedTypes().contains(type.name()) && s.maxAreaFor(type).compareTo(BigDecimal.ONE) >= 0)
            result.add(new Choice(s, type, s.maxAreaFor(type).setScale(2, RoundingMode.DOWN)));
      return result;
    }));
    var selected = new ArrayList<Choice>();
    var used = new HashSet<String>();
    var types = new ArrayList<>(List.of(FacilityType.values()));
    Collections.shuffle(types, random);
    int count = 6 + random.nextInt(7);
    BigDecimal left = target;
    for (int slot = 0; slot < count; slot++) {
      var type = types.get(slot % types.size());
      var available = pool.stream().filter(c -> c.type() == type && !used.contains(c.site().cellId()))
          .sorted(Comparator.comparing(Choice::cost).reversed()).limit(30).toList();
      if (available.isEmpty()) continue;
      var c = available.get(random.nextInt(available.size()));
      var share = target.divide(BigDecimal.valueOf(count), 2, RoundingMode.DOWN)
          .multiply(BigDecimal.valueOf(0.55 + random.nextDouble() * 0.55));
      c = c.area(share.divide(c.unit(), 2, RoundingMode.DOWN).min(c.maximum()));
      selected.add(c); used.add(c.site().cellId()); left = left.subtract(c.cost());
    }
    // 계정마다 시설 수·유형·면적을 달리하고 실제 부지 상한 안에서 목표 예산에 맞춘다.
    Collections.shuffle(selected, random);
    for (int n = 0; n < selected.size() && left.signum() > 0; n++) {
      var c = selected.get(n);
      var cap = target.multiply(new BigDecimal("0.28")).divide(c.unit(), 2, RoundingMode.DOWN).min(c.maximum());
      var area = c.area().add(left.divide(c.unit(), 2, RoundingMode.DOWN)).min(cap).max(c.area());
      var replacement = c.area(area);
      left = left.subtract(replacement.cost().subtract(c.cost())); selected.set(n, replacement);
    }
    while (left.compareTo(target.multiply(new BigDecimal("0.00001"))) > 0 && selected.size() < 24) {
      BigDecimal remaining = left;
      var available = pool.stream().filter(c -> !used.contains(c.site().cellId())
              && c.unit().multiply(STEP).compareTo(remaining) <= 0)
          .sorted(Comparator.comparing(Choice::cost).reversed()).limit(20).toList();
      if (available.isEmpty()) break;
      var c = available.get(random.nextInt(available.size()));
      c = c.area(left.min(target.multiply(new BigDecimal("0.22")))
          .divide(c.unit(), 2, RoundingMode.DOWN).min(c.maximum()));
      selected.add(c); used.add(c.site().cellId()); left = left.subtract(c.cost());
    }
    require(selected.size() >= 6 && left.signum() >= 0 && left.compareTo(target.multiply(new BigDecimal("0.00001"))) <= 0
        && selected.stream().allMatch(c -> c.area().compareTo(STEP) >= 0 && c.area().compareTo(c.maximum()) <= 0));
    return selected;
  }

  static void plan(ConfigurableApplicationContext context) throws Exception {
    require(!Files.exists(directory.resolve("plan.json")));
    var usernames = context.getBean(JdbcTemplate.class).queryForList(
        "SELECT username FROM accounts WHERE username ~ '^TEST_20261022_11[0-9]{3}_0[1-3]$' ORDER BY username", String.class);
    require(usernames.size() == 69);
    Path draft = directory.resolve("plan.partial.json");
    var root = (ObjectNode) json.tree(Files.exists(draft) ? Files.readString(draft) : "{}");
    var limit = context.getBean(BudgetService.class).limit();
    if (root.has("weekStart")) require(week.toString().equals(root.path("weekStart").asString())
        && context.getBean(ScorePolicyService.class).sha256().equals(root.path("policySha256").asString()));
    root.put("weekStart", week.toString()).put("limitKrw", limit)
        .put("policySha256", context.getBean(ScorePolicyService.class).sha256());
    var players = root.has("players") ? (tools.jackson.databind.node.ArrayNode) root.path("players") : root.putArray("players");
    var cache = new HashMap<String, List<Choice>>();
    var counts = new HashMap<String, Integer>();
    var done = new HashSet<String>();
    for (var p : players) {
      require(done.add(p.path("username").asString()));
      counts.merge(p.path("districtId").asString(), 1, Integer::sum);
    }
    int[] percentages = {27, 33, 42, 51, 63, 75, 83, 91};
    for (String name : usernames) {
      if (done.contains(name)) continue;
      var a = player(context, name);
      require(context.getBean(InstallationRepository.class).owned(a.id()).isEmpty());
      var random = new Random(a.id().getMostSignificantBits() ^ week.toEpochDay());
      var ratio = BigDecimal.valueOf(percentages[random.nextInt(percentages.length)] * 100L + random.nextInt(401) - 200, 4);
      var target = limit.multiply(ratio).setScale(2, RoundingMode.DOWN);
      var choices = design(context, a, target, random, cache);
      var p = players.addObject().put("username", name).put("ownerId", a.id().toString())
          .put("districtId", a.districtId()).put("targetRatio", ratio).put("targetKrw", target);
      var items = p.putArray("placements");
      for (var c : choices)
        items.addObject().put("cellId", c.site().cellId()).put("facilityType", c.type().name())
            .put("areaM2", c.area()).put("costKrw", c.cost()).put("siteModelHash", c.site().modelHash());
      p.put("spentKrw", choices.stream().map(Choice::cost).reduce(BigDecimal.ZERO, BigDecimal::add));
      counts.merge(a.districtId(), 1, Integer::sum);
      save(draft, root);
    }
    require(counts.size() == 23 && counts.values().stream().allMatch(n -> n == 3));
    save(directory.resolve("plan.json"), root);
    Files.deleteIfExists(draft);
    System.out.println("TEST_WEEKLY_PLANNED players=" + players.size());
  }

  static void apply(ConfigurableApplicationContext context) throws Exception {
    var plan = json.tree(Files.readString(directory.resolve("plan.json")));
    require(week.toString().equals(plan.path("weekStart").asString()) && plan.path("players").size() == 69
        && context.getBean(ScorePolicyService.class).sha256().equals(plan.path("policySha256").asString()));
    var installations = context.getBean(InstallationRepository.class);
    var service = context.getBean(InstallationService.class);
    var progress = (ObjectNode) json.tree("{}");
    var done = progress.putObject("players");
    for (var p : plan.path("players")) {
      var a = player(context, p.path("username").asString());
      require(a.id().toString().equals(p.path("ownerId").asString()) && a.districtId().equals(p.path("districtId").asString()));
      var ids = done.putArray(a.username());
      for (var item : p.path("placements")) {
        var previous = installations.owned(a.id()).stream().filter(i -> i.cellId().equals(item.path("cellId").asString())).findFirst();
        var i = previous.orElseGet(() -> service.install(a.username(), new InstallRequest(a.districtId(),
            item.path("cellId").asString(), FacilityType.valueOf(item.path("facilityType").asString()), item.path("areaM2").decimalValue())));
        require(i.modelHash().equals(item.path("siteModelHash").asString()) && i.areaM2().compareTo(item.path("areaM2").decimalValue()) == 0
            && i.facilityType().name().equals(item.path("facilityType").asString()) && i.cost().compareTo(item.path("costKrw").decimalValue()) == 0);
        ids.add(i.id().toString()); save(directory.resolve("progress.json"), progress);
      }
      System.out.println("TEST_WEEKLY_APPLIED players=" + done.size());
    }
  }

  public static void main(String[] args) {
    int status = 1;
    try {
      require(args.length == 2);
      week = LocalDate.parse(System.getenv("WATERLEAGUE_TEST_WEEK"));
      directory = Path.of(args[1]);
      var app = new SpringApplication(WaterLeagueApplication.class);
      app.setWebApplicationType(WebApplicationType.NONE);
      try (var context = app.run()) {
        var now = context.getBean(io.waterleague.weekly.service.WeeklySeasonService.class).now();
        require(week.equals(now.atZone(ZoneId.of("Asia/Seoul")).toLocalDate()
            .with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))));
        json = context.getBean(JsonService.class);
        if ("plan".equals(args[0])) plan(context);
        else { require("apply".equals(args[0])); apply(context); }
      }
      status = 0;
    } catch (Exception e) {
      System.err.println("TEST_WEEKLY_FAILED " + (e instanceof DomainException d ? d.code().name() : e.getClass().getSimpleName()));
      for (var frame : Arrays.stream(e.getStackTrace()).limit(6).toList())
        System.err.println("TEST_WEEKLY_LOCATION " + frame.getClassName() + "." + frame.getMethodName() + ":" + frame.getLineNumber());
    }
    System.exit(status);
  }
}
