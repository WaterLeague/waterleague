import io.waterleague.WaterLeagueApplication;
import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.common.exception.DomainException;
import io.waterleague.common.service.JsonService;
import io.waterleague.disaster.service.DisasterService;
import io.waterleague.district.repository.DistrictRepository;
import io.waterleague.historical.dto.*;
import io.waterleague.historical.service.*;
import io.waterleague.installation.dto.InstallRequest;
import io.waterleague.installation.repository.*;
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

public class SeedTestPlayers {
  static JsonService json;
  static Path report;
  static ObjectNode progress;
  static final String BATCH = "TEST_20261022";
  static final Set<String> EMPTY = Set.of("11140", "11305");

  static UUID key(String name) {
    return UUID.nameUUIDFromBytes((BATCH + "/" + name).getBytes(StandardCharsets.UTF_8));
  }

  static void save() throws Exception {
    Path next = report.resolveSibling("progress.next");
    Files.writeString(next, json.write(progress));
    Files.move(next, report, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
  }

  static void require(boolean condition) {
    if (!condition) throw new IllegalStateException("TEST_BATCH_CONTRACT_INVALID");
  }

  static JsonNode retry(java.util.concurrent.Callable<JsonNode> action) throws Exception {
    for (int attempt = 0; ; attempt++) {
      try {
        return action.call();
      } catch (DomainException error) {
        if (!error.code().name().equals("SIMULATION_QUOTA_EXCEEDED") || attempt >= 300) throw error;
        Thread.sleep(2000);
      }
    }
  }

  static void run(ConfigurableApplicationContext context, Path input) throws Exception {
    json = context.getBean(JsonService.class);
    var manifest = json.tree(Files.readString(input));
    require(BATCH.equals(manifest.path("batch").asString()));
    var rows = manifest.path("accounts");
    require(rows.size() == 69);
    report = input.resolveSibling("progress.json");
    progress =
        (ObjectNode)
            json.tree(Files.exists(report) ? Files.readString(report) : "{\"players\":{}}");
    var players = (ObjectNode) progress.path("players");
    var accounts = context.getBean(AccountRepository.class);
    var installations = context.getBean(InstallationRepository.class);
    var service = context.getBean(InstallationService.class);
    var sites = context.getBean(SiteCatalogRepository.class);
    var districts = context.getBean(DistrictRepository.class);
    var counts = new HashMap<String, Integer>();
    var names = new HashSet<String>();
    for (var row : rows) {
      String name = row.path("username").asString(), district = row.path("districtId").asString();
      require(name.matches("TEST_20261022_11[0-9]{3}_0[1-3]") && names.add(name));
      require(!EMPTY.contains(district) && name.contains("_" + district + "_"));
      require(row.path("displayName").asString().startsWith("TEST_"));
      require(row.path("passwordHash").asString().startsWith("$argon2id$v=19$m=19456,t=2,p=1$"));
      counts.merge(district, 1, Integer::sum);
    }
    require(counts.size() == 23 && counts.values().stream().allMatch(n -> n == 3));
    require(installations.active().stream().noneMatch(i -> EMPTY.contains(i.districtId())));
    // 재실행은 같은 계정·부지·요청 키를 재사용하며 기존 이용자의 기록을 수정하지 않는다.
    var used = new HashMap<String, Set<String>>();
    for (var player : players) {
      for (var plan : player.path("plan"))
        used.computeIfAbsent(plan.path("districtId").asString(), ignored -> new HashSet<>())
            .add(plan.path("cellId").asString());
    }
    int total = 0;
    for (var row : rows) {
      String username = row.path("username").asString(),
          district = row.path("districtId").asString();
      UUID id = UUID.fromString(row.path("id").asString());
      var existing = accounts.byUsername(username);
      if (existing.isEmpty()) {
        accounts.add(
            new Account(
                id,
                username,
                row.path("displayName").asString(),
                row.path("passwordHash").asString(),
                "MEMBER",
                "PLAYER",
                "APPROVED",
                null,
                "",
                "",
                true,
                district,
                "RESIDENT"));
      } else {
        var account = existing.get();
        require(
            account.id().equals(id)
                && account.role().equals("MEMBER")
                && account.memberType().equals("PLAYER")
                && district.equals(account.districtId()));
      }
      var player =
          players.has(username) ? (ObjectNode) players.path(username) : players.putObject(username);
      player.put("ownerId", id.toString());
      if (!player.has("plan")) {
        var plan = player.putArray("plan");
        int variant = Integer.parseInt(username.substring(username.length() - 2)) - 1;
        FacilityType[] types = {
          variant == 1 ? FacilityType.RAINWATER_CISTERN : FacilityType.GREEN_ROOF,
          variant == 1 ? FacilityType.BIORETENTION : FacilityType.RAIN_GARDEN,
          variant == 0
              ? FacilityType.PERMEABLE_PAVEMENT
              : variant == 1 ? FacilityType.VEGETATIVE_SWALE : FacilityType.INFILTRATION_TRENCH
        };
        var center = districts.require(district).center();
        var taken = used.computeIfAbsent(district, ignored -> new HashSet<>());
        for (int slot = 0; slot < types.length; slot++) {
          var type = types[slot];
          SiteView chosen =
              sites
                  .nearest(district, center.get(0), center.get(1), 0, type, false, null)
                  .sites()
                  .stream()
                  .filter(
                      s ->
                          !taken.contains(s.cellId())
                              && s.suitability().explorationAllowed()
                              && s.existingInfrastructure() == null
                              && s.allowedTypes().contains(type.name())
                              && s.maxAreaFor(type).compareTo(new BigDecimal("1")) >= 0)
                  .findFirst()
                  .orElseThrow();
          taken.add(chosen.cellId());
          var area =
              BigDecimal.valueOf(20 + variant * 5 + slot * 3)
                  .min(chosen.maxAreaFor(type).multiply(new BigDecimal("0.3")))
                  .setScale(2, RoundingMode.DOWN);
          var item = plan.addObject();
          item.put("districtId", district)
              .put("cellId", chosen.cellId())
              .put("facilityType", type.name())
              .put("areaM2", area)
              .put("siteModelHash", chosen.modelHash());
        }
        save();
      }
      var owned = installations.owned(id);
      var ids = player.putArray("installationIds");
      for (var plan : player.path("plan")) {
        String cell = plan.path("cellId").asString();
        var value = owned.stream().filter(i -> i.cellId().equals(cell)).findFirst();
        var installed =
            value.isPresent()
                ? value.get()
                : service.install(
                    username,
                    new InstallRequest(
                        district,
                        cell,
                        FacilityType.valueOf(plan.path("facilityType").asString()),
                        plan.path("areaM2").decimalValue()));
        ids.add(installed.id().toString());
        save();
      }
      total += 3;
      System.out.println("TEST_INSTALLATIONS_READY " + total);
    }
    var event =
        context.getBean(DisasterService.class).catalog().events().stream()
            .filter(e -> e.id().equals("seoul-20220808"))
            .findFirst()
            .orElseThrow();
    var designs = context.getBean(HistoricalDesignService.class);
    var history = context.getBean(HistoricalService.class);
    var submissions = context.getBean(HistoricalSubmissionService.class);
    int participants = 0;
    for (var row : rows) {
      String username = row.path("username").asString();
      if (!username.endsWith("_01") || participants >= 10) continue;
      var player = (ObjectNode) players.path(username);
      String district = row.path("districtId").asString();
      UUID owner = UUID.fromString(row.path("id").asString());
      var region =
          event.regions().stream()
              .filter(r -> r.districtId().equals(district))
              .findFirst()
              .orElseThrow();
      Instant start = Instant.parse(region.start());
      var items = new ArrayList<HistoricalDesignRequest.Item>();
      var experiment = new ArrayList<HistoricalRequest.Item>();
      int slot = 0;
      for (var plan : player.path("plan")) {
        Instant installedAt = start.plusSeconds(60 + slot++ * 300L + participants * 7L);
        String cell = plan.path("cellId").asString();
        var type = FacilityType.valueOf(plan.path("facilityType").asString());
        var area = plan.path("areaM2").decimalValue();
        items.add(
            new HistoricalDesignRequest.Item(
                key(username + "/" + cell), district, cell, type, area, installedAt));
        experiment.add(
            new HistoricalRequest.Item(
                cell, type, area, installedAt, plan.path("siteModelHash").asString()));
      }
      var design =
          designs.save(
              owner,
              event.id(),
              new HistoricalDesignRequest(key(username + "/design"), 0, 1800, items));
      var play =
          retry(
              () ->
                  json.tree(
                      json.write(
                          history.create(
                              owner,
                              new HistoricalRequest(
                                  key(username + "/play"),
                                  district,
                                  region.modelHash(),
                                  experiment,
                                  null,
                                  "INSTALLATION_TIME_EXPERIMENT_V1",
                                  null,
                                  design.revision(),
                                  event.id())))));
      player.put("experimentId", play.path("id").asString());
      save();
      var submitted =
          retry(
              () ->
                  json.tree(
                      json.write(
                          submissions.submitSaved(
                              owner,
                              event.id(),
                              new HistoricalDesignSubmissionRequest(
                                  key(username + "/submit"),
                                  design.revision(),
                                  design.snapshotSha256())))));
      player.put("submissionId", submitted.path("id").asString());
      save();
      participants++;
      System.out.println("TEST_DISASTER_SUBMITTED " + participants);
    }
    require(participants == 10 && total == 207);
    progress.put("accounts", 69).put("installations", total).put("submissions", participants);
    save();
    System.out.println("TEST_BATCH_ENQUEUED accounts=69 installations=207 submissions=10");
  }

  public static void main(String[] args) {
    int status = 1;
    try {
      require(args.length == 1 && BATCH.equals(System.getenv("WATERLEAGUE_TEST_BATCH")));
      var app = new SpringApplication(WaterLeagueApplication.class);
      app.setWebApplicationType(WebApplicationType.NONE);
      try (var context = app.run()) {
        run(context, Path.of(args[0]));
      }
      status = 0;
    } catch (Exception error) {
      System.err.println(
          "TEST_BATCH_FAILED "
              + (error instanceof DomainException domain
                  ? domain.code().name()
                  : error.getClass().getSimpleName()));
    }
    System.exit(status);
  }
}
