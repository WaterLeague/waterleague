package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.common.service.JsonService;
import io.waterleague.disaster.service.DisasterService;
import io.waterleague.historical.dto.*;
import io.waterleague.historical.service.HistoricalService;
import io.waterleague.installation.repository.SiteCatalogRepository;
import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.net.*;
import java.net.http.*;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("local")
class GuestHistoricalTests extends PostgresIntegrationTest {
  @org.springframework.test.context.DynamicPropertySource
  static void database(org.springframework.test.context.DynamicPropertyRegistry registry) {
    SharedInstallationTests.integrationDatabase(registry);
  }

  @Value("${local.server.port}")
  int port;

  @Autowired HistoricalService service;
  @Autowired SiteCatalogRepository sites;
  @Autowired DisasterService disasters;
  @Autowired JsonService json;
  @Autowired JdbcTemplate db;

  @BeforeEach
  void clean() {
    db.update("DELETE FROM historical_experiments");
    db.update("DELETE FROM rate_limits");
  }

  HttpClient client() {
    return HttpClient.newBuilder()
        .cookieHandler(new CookieManager(null, CookiePolicy.ACCEPT_ALL))
        .build();
  }

  HttpResponse<String> get(HttpClient c, String path) throws Exception {
    return c.send(
        HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/v1" + path))
            .GET()
            .build(),
        HttpResponse.BodyHandlers.ofString());
  }

  HttpResponse<String> post(HttpClient c, String path, Object body, boolean csrf) throws Exception {
    var b =
        HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/v1" + path))
            .header("Content-Type", "application/json");
    if (csrf) {
      var token = json.tree(get(c, "/auth/csrf").body());
      b.header(token.path("headerName").asString(), token.path("token").asString());
    }
    return c.send(
        b.POST(HttpRequest.BodyPublishers.ofString(json.write(body))).build(),
        HttpResponse.BodyHandlers.ofString());
  }

  GuestHistoricalRequest.Item item(String district, int second) {
    var event = disasters.catalog().events().getFirst();
    var region =
        event.regions().stream()
            .filter(r -> r.districtId().equals(district))
            .findFirst()
            .orElseThrow();
    var site =
        NativeSiteFixtures.sites(sites, district).values().stream()
            .filter(
                s ->
                    s.allowedTypes().contains("GREEN_ROOF")
                        && s.existingInfrastructure() == null
                        && s.maxAreaFor(FacilityType.GREEN_ROOF).compareTo(BigDecimal.TEN) >= 0)
            .findFirst()
            .orElseThrow();
    return new GuestHistoricalRequest.Item(
        district,
        new HistoricalRequest.Item(
            site.cellId(),
            FacilityType.GREEN_ROOF,
            BigDecimal.TEN,
            Instant.parse(region.start()).plusSeconds(second),
            site.modelHash()));
  }

  GuestHistoricalRequest request(UUID key, List<GuestHistoricalRequest.Item> items) {
    return new GuestHistoricalRequest(
        key, disasters.catalog().events().getFirst().id(), "11200", items);
  }

  @Test
  void anonymousStreetPavementQueuesWithServerGeometryAndRejectsForgedArea() throws Exception {
    var browser = client();
    var template = item("11200", 137);
    var site =
        NativeSiteFixtures.sites(sites, "11200").values().stream()
            .filter(
                s ->
                    s.sourceRole().equals("ROAD_AREA")
                        && s.maxAreaM2().compareTo(BigDecimal.TEN) >= 0)
            .findFirst()
            .orElseThrow();
    var placement =
        new HistoricalRequest.Item(
            site.cellId(),
            FacilityType.PERMEABLE_PAVEMENT,
            BigDecimal.TEN,
            template.placement().installedAt(),
            site.modelHash());
    var dto =
        request(UUID.randomUUID(), List.of(new GuestHistoricalRequest.Item("11200", placement)));
    assertThat(post(browser, "/guest-historical", dto, true).statusCode()).isEqualTo(202);
    var bad =
        new HistoricalRequest.Item(
            site.cellId(),
            FacilityType.PERMEABLE_PAVEMENT,
            site.maxAreaM2().add(new BigDecimal("0.01")),
            template.placement().installedAt(),
            site.modelHash());
    assertThat(
            post(
                    browser,
                    "/guest-historical",
                    request(
                        UUID.randomUUID(), List.of(new GuestHistoricalRequest.Item("11200", bad))),
                    true)
                .statusCode())
        .isEqualTo(422);
    assertThat(
            post(
                    browser,
                    "/installations",
                    Map.of(
                        "districtId",
                        site.districtId(),
                        "cellId",
                        site.cellId(),
                        "facilityType",
                        "PERMEABLE_PAVEMENT",
                        "areaM2",
                        10),
                    true)
                .statusCode())
        .isEqualTo(401);
  }

  @Test
  void anonymousCalculationIsSessionOwnedCsrfProtectedAndNeverSubmitted() throws Exception {
    int accounts = db.queryForObject("SELECT count(*) FROM accounts", Integer.class);
    var a = client();
    var b = client();
    var dto = request(UUID.randomUUID(), List.of(item("11200", 137)));
    assertThat(post(a, "/guest-historical", dto, false).statusCode()).isEqualTo(403);
    var created = post(a, "/guest-historical", dto, true);
    assertThat(created.statusCode()).isEqualTo(202);
    assertThat(created.headers().firstValue("Cache-Control").orElse("")).contains("no-store");
    var id = json.tree(created.body()).path("id").asString();
    assertThat(get(a, "/guest-historical/" + id).statusCode()).isEqualTo(200);
    assertThat(get(b, "/guest-historical/" + id).statusCode()).isEqualTo(404);
    assertThat(get(b, "/guest-historical").body()).isEqualTo("[]");
    assertThat(get(a, "/historical/" + id).statusCode()).isEqualTo(401);
    assertThat(get(a, "/historical/leaderboard/" + dto.eventId()).statusCode()).isEqualTo(401);
    assertThat(post(a, "/historical/submissions", Map.of(), true).statusCode()).isEqualTo(401);
    assertThat(post(a, "/installations", Map.of(), true).statusCode()).isEqualTo(401);
    assertThat(get(a, "/guest-historical/" + id + "/bundle").statusCode()).isEqualTo(401);
    assertThat(db.queryForObject("SELECT count(*) FROM historical_submissions", Integer.class))
        .isZero();
    assertThat(db.queryForObject("SELECT count(*) FROM accounts", Integer.class))
        .isEqualTo(accounts);
    assertThat(
            db.queryForObject(
                "SELECT owner_id IS NULL AND guest_key IS NOT NULL FROM historical_experiments"
                    + " WHERE id=?",
                Boolean.class,
                UUID.fromString(id)))
        .isTrue();
  }

  @Test
  void wholeDesignIdempotencyAndQueueLimitSurviveMultipleRequests() throws Exception {
    var client = client();
    var items = List.of(item("11200", 137), item("11680", 377));
    var dto = request(UUID.randomUUID(), items);
    var first = post(client, "/guest-historical", dto, true);
    assertThat(first.statusCode()).isEqualTo(202);
    assertThat(post(client, "/guest-historical", dto, true).body()).isEqualTo(first.body());
    var changed = request(dto.requestKey(), List.of(items.getFirst(), item("11680", 378)));
    assertThat(post(client, "/guest-historical", changed, true).statusCode()).isEqualTo(409);
    assertThat(
            post(client, "/guest-historical", request(UUID.randomUUID(), items), true).statusCode())
        .isEqualTo(202);
    assertThat(
            post(client, "/guest-historical", request(UUID.randomUUID(), items), true).statusCode())
        .isEqualTo(429);
    assertThat(db.queryForObject("SELECT count(*) FROM historical_experiments", Integer.class))
        .isEqualTo(2);
  }

  @Test
  void guestReadListAndIdempotentResponsesExcludeFinalScore() throws Exception {
    var browser = client();
    var dto = request(UUID.randomUUID(), List.of(item("11200", 137)));
    var created = post(browser, "/guest-historical", dto, true);
    var id = json.tree(created.body()).path("id").asString();
    String result =
        """
        {"engineVersion":"test-only-987","validationLevel":"EXPLORATORY","start":"2022-08-08T09:00:00Z","end":"2022-08-08T09:03:00Z",
        "differenceM3":987,"baselineAccountedM3":999,"designAccountedM3":12,
        "frames":[{"at":"2022-08-08T09:01:00Z","differenceM3":1},{"at":"2022-08-08T09:02:00Z","differenceM3":2},{"at":"2022-08-08T09:03:00Z","differenceM3":987}],
        "facilities":[{"cellId":"TEST","runoffComparison":{"final":987},"frames":[{"at":"2022-08-08T09:01:00Z","differenceM3":1},{"at":"2022-08-08T09:03:00Z","differenceM3":987}]}]}
        """;
    db.update(
        "UPDATE historical_experiments SET state='SUCCEEDED',result=?,finished_at=CURRENT_TIMESTAMP"
            + " WHERE id=?",
        result,
        UUID.fromString(id));
    for (var response :
        List.of(
            get(browser, "/guest-historical/" + id),
            get(browser, "/guest-historical"),
            post(browser, "/guest-historical", dto, true))) {
      assertThat(response.statusCode()).isIn(200, 202);
      var value = json.tree(response.body());
      var records = new ArrayList<tools.jackson.databind.JsonNode>();
      if (value.isArray()) value.forEach(records::add);
      else records.add(value);
      assertThat(records).hasSize(1);
      for (var record : records) {
        var previewResult = record.path("result");
        assertThat(previewResult.path("engineVersion").asString()).isEqualTo("test-only-987");
        for (String field : List.of("differenceM3", "baselineAccountedM3", "designAccountedM3"))
          assertThat(previewResult.has(field)).isFalse();
        assertThat(previewResult.path("frames").size()).isEqualTo(2);
        for (var frame : previewResult.path("frames"))
          assertThat(frame.path("differenceM3").asDouble()).isNotEqualTo(987);
        for (var facility : previewResult.path("facilities")) {
          assertThat(facility.has("runoffComparison")).isFalse();
          assertThat(facility.path("frames").size()).isEqualTo(1);
          for (var frame : facility.path("frames"))
            assertThat(frame.path("differenceM3").asDouble()).isNotEqualTo(987);
        }
      }
    }
    var preview = json.tree(get(browser, "/guest-historical/" + id).body()).path("result");
    assertThat(preview.has("differenceM3")).isFalse();
    assertThat(preview.path("frames").size()).isEqualTo(2);
    assertThat(preview.path("facilities").get(0).path("frames").size()).isEqualTo(1);
  }

  @Test
  void rejectsUnknownSiteFutureTimeAndDuplicateWholeDesign() throws Exception {
    var client = client();
    var item = item("11200", 137);
    var p = item.placement();
    var bad =
        new GuestHistoricalRequest.Item(
            item.districtId(),
            new HistoricalRequest.Item(
                p.cellId(), p.facilityType(), p.areaM2(), p.installedAt(), "0".repeat(64)));
    assertThat(
            post(client, "/guest-historical", request(UUID.randomUUID(), List.of(bad)), true)
                .statusCode())
        .isEqualTo(409);
    var future =
        new GuestHistoricalRequest.Item(
            item.districtId(),
            new HistoricalRequest.Item(
                p.cellId(),
                p.facilityType(),
                p.areaM2(),
                p.installedAt().plusSeconds(864000),
                p.siteModelHash()));
    assertThat(
            post(client, "/guest-historical", request(UUID.randomUUID(), List.of(future)), true)
                .statusCode())
        .isEqualTo(422);
    assertThat(
            post(client, "/guest-historical", request(UUID.randomUUID(), List.of(item, item)), true)
                .statusCode())
        .isEqualTo(422);
    assertThat(db.queryForObject("SELECT count(*) FROM historical_experiments", Integer.class))
        .isZero();
  }

  @Test
  void concurrentGuestRequestsCannotExceedAdmissionLimit() throws Exception {
    var start = new java.util.concurrent.CountDownLatch(1);
    try (var pool = java.util.concurrent.Executors.newFixedThreadPool(3)) {
      var futures = new ArrayList<java.util.concurrent.Future<Boolean>>();
      for (int i = 0; i < 3; i++)
        futures.add(
            pool.submit(
                () -> {
                  start.await();
                  try {
                    service.createGuest(
                        "c".repeat(64), request(UUID.randomUUID(), List.of(item("11200", 137))));
                    return true;
                  } catch (io.waterleague.common.exception.DomainException e) {
                    return false;
                  }
                }));
      start.countDown();
      int accepted = 0;
      for (var future : futures) if (future.get()) accepted++;
      assertThat(accepted).isEqualTo(2);
      assertThat(db.queryForObject("SELECT count(*) FROM historical_experiments", Integer.class))
          .isEqualTo(2);
    }
  }

  @Test
  void wholeDesignRejectsCombinedBudgetExcessAcrossDistricts() throws Exception {
    var items = new ArrayList<GuestHistoricalRequest.Item>();
    var total = BigDecimal.ZERO;
    for (var district : List.of("11200", "11680")) {
      var at = item(district, 137).placement().installedAt();
      var candidates =
          NativeSiteFixtures.sites(sites, district).values().stream()
              .filter(
                  s ->
                      s.allowedTypes().contains("GREEN_ROOF") && s.existingInfrastructure() == null)
              .sorted(
                  Comparator.comparing(
                          (io.waterleague.installation.view.SiteView s) ->
                              s.maxAreaFor(FacilityType.GREEN_ROOF))
                      .reversed())
              .limit(25)
              .toList();
      for (var site : candidates) {
        var amount =
            site.maxAreaFor(FacilityType.GREEN_ROOF)
                .min(new BigDecimal("2500"))
                .setScale(2, java.math.RoundingMode.DOWN);
        items.add(
            new GuestHistoricalRequest.Item(
                district,
                new HistoricalRequest.Item(
                    site.cellId(), FacilityType.GREEN_ROOF, amount, at, site.modelHash())));
        total = total.add(amount.multiply(site.unitCosts().get("GREEN_ROOF")));
      }
    }
    assertThat(total).isGreaterThan(new BigDecimal("2000000000"));
    assertThat(
            post(client(), "/guest-historical", request(UUID.randomUUID(), items), true)
                .statusCode())
        .isEqualTo(422);
    assertThat(db.queryForObject("SELECT count(*) FROM historical_experiments", Integer.class))
        .isZero();
  }

  @Test
  void freezesServerValidatedGuestInputForNativeWorker() throws Exception {
    var dto = request(UUID.randomUUID(), List.of(item("11200", 137), item("11680", 377)));
    var job = service.createGuest("a".repeat(64), dto);
    var row =
        db.queryForMap(
            "SELECT model_hash,input_hash,placements FROM historical_experiments WHERE id=?",
            job.id());
    var path = System.getProperty("waterleague.integration.guest.fixture");
    if (path != null)
      Files.writeString(
          Path.of(path),
          json.write(
              Map.of(
                  "modelHash",
                  row.get("model_hash"),
                  "inputHash",
                  row.get("input_hash"),
                  "placements",
                  row.get("placements"))));
    assertThat(
            json.tree(row.get("placements").toString())
                .get(0)
                .path("guestDesignSnapshotRaw")
                .asString())
        .contains("11680", "11200");
  }
}
