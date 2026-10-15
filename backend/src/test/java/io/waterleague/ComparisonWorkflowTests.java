package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.model.service.LabModelService;
import java.net.*;
import java.net.http.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("local")
class ComparisonWorkflowTests {
  @Value("${local.server.port}")
  int port;

  @Autowired ObjectMapper json;
  @Autowired JdbcTemplate db;
  @Autowired AccountRepository accounts;
  @Autowired PasswordEncoder passwords;
  @Autowired LabModelService model;
  @Autowired io.waterleague.account.service.InstitutionMfaService mfa;
  @Autowired io.waterleague.common.service.JsonService documentJson;

  @Value("${waterleague.artifacts}")
  String artifactRoot;

  record Actor(UUID id, HttpClient client) {}

  Actor actor(UUID org) throws Exception {
    UUID id = UUID.randomUUID();
    String name = "qa_" + id.toString().substring(0, 8);
    accounts.add(
        new Account(
            id,
            name,
            name,
            passwords.encode("test-password-1234"),
            "MEMBER",
            org == null ? "PLAYER" : "INSTITUTION",
            "APPROVED",
            org,
            "",
            "",
            true));
    String secret = org == null ? null : mfa.provision(id);
    var a =
        new Actor(
            id,
            HttpClient.newBuilder()
                .cookieHandler(new CookieManager(null, CookiePolicy.ACCEPT_ALL))
                .build());
    var login = new HashMap<String, Object>();
    login.put("username", name);
    login.put("password", "test-password-1234");
    if (secret != null) login.put("otp", MfaTests.otp(secret));
    assertThat(call(a, "POST", "/auth/login", login).statusCode()).isEqualTo(200);
    return a;
  }

  HttpResponse<String> call(Actor a, String method, String path, Object body) throws Exception {
    var builder = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/v1" + path));
    if (!method.equals("GET")) {
      var csrf =
          a.client()
              .send(
                  HttpRequest.newBuilder(
                          URI.create("http://127.0.0.1:" + port + "/api/v1/auth/csrf"))
                      .build(),
                  HttpResponse.BodyHandlers.ofString());
      builder
          .header("X-CSRF-TOKEN", json.readTree(csrf.body()).get("token").asString())
          .header("Content-Type", "application/json")
          .method(method, HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body)));
    }
    return a.client().send(builder.build(), HttpResponse.BodyHandlers.ofString());
  }

  JsonNode ok(Actor a, String method, String path, Object body, int status) throws Exception {
    var r = call(a, method, path, body);
    assertThat(r.statusCode()).as(r.body()).isEqualTo(status);
    return json.readTree(r.body());
  }

  Map<String, Object> draft(int revision, String note) {
    return Map.of(
        "title",
        "검증 설계",
        "modelHash",
        model.hash(),
        "placements",
        List.of(Map.of("cellId", "G1", "facilityType", "RAIN_GARDEN", "areaM2", 40)),
        "designNote",
        note,
        "baseRevision",
        revision);
  }

  JsonNode create(Actor a) throws Exception {
    return ok(a, "POST", "/strategies", draft(0, "제출 이전 메모"), 200);
  }

  @Autowired io.waterleague.model.repository.LabModelRepository models;

  Map<String, Object> comparison(JsonNode source, UUID key, int count) {
    return Map.of(
        "sourceVersionId",
        source.path("id").asString(),
        "requestKey",
        key,
        "modelHashes",
        models.all().stream().map(m -> m.hash()).limit(count).toList());
  }

  int ownerVersions(Actor actor) {
    return db.queryForObject(
        "SELECT COUNT(*) FROM strategy_versions v JOIN strategies s ON s.id=v.strategy_id WHERE"
            + " s.owner_id=?",
        Integer.class,
        actor.id());
  }

  @Test
  void copiesImmutableInputsAndReplaysOnlySameRequestForOwner() throws Exception {
    var owner = actor(null);
    var other = actor(null);
    var source = create(owner);
    var key = UUID.randomUUID();
    var request = comparison(source, key, 3);
    var c = ok(owner, "POST", "/comparisons", request, 202);
    assertThat(c.path("jobs").size()).isEqualTo(3);
    assertThat(ownerVersions(owner)).isEqualTo(4);
    for (var job : c.path("jobs")) {
      var detail = ok(owner, "GET", "/strategies/" + job.path("strategyId").asString(), null, 200);
      var version = detail.path("versions").get(0);
      assertThat(version.path("placements")).isEqualTo(source.path("placements"));
      assertThat(version.path("cost").decimalValue())
          .isEqualByComparingTo(source.path("cost").decimalValue());
      assertThat(version.path("events").path("sourceVersionId").asString())
          .isEqualTo(source.path("id").asString());
    }
    var reordered = new HashMap<>(request);
    reordered.put(
        "modelHashes", models.all().stream().map(m -> m.hash()).limit(3).toList().reversed());
    assertThat(ok(owner, "POST", "/comparisons", reordered, 202).path("id"))
        .isEqualTo(c.path("id"));
    assertThat(ownerVersions(owner)).isEqualTo(4);
    assertThat(call(owner, "POST", "/comparisons", comparison(source, key, 2)).statusCode())
        .isEqualTo(409);
    assertThat(call(other, "GET", "/comparisons/" + c.path("id").asString(), null).statusCode())
        .isEqualTo(404);
    assertThat(
            call(other, "POST", "/comparisons", comparison(source, UUID.randomUUID(), 2))
                .statusCode())
        .isEqualTo(404);
    assertThat(ok(other, "GET", "/comparisons", null, 200).size()).isZero();
    assertThat(
            db.queryForObject(
                "SELECT COUNT(*) FROM submissions WHERE owner_id=?", Integer.class, owner.id()))
        .isZero();
    assertThat(
            db.queryForObject(
                "SELECT COUNT(*) FROM research_consents WHERE owner_id=?",
                Integer.class,
                owner.id()))
        .isZero();
  }

  @Test
  void rejectsInsufficientQueueCapacityWithoutOrphanVersions() throws Exception {
    var owner = actor(null);
    var source = create(owner);
    for (int i = 0; i < 2; i++)
      ok(
          owner,
          "POST",
          "/simulations",
          Map.of("versionId", source.path("id").asString(), "requestKey", UUID.randomUUID()),
          202);
    assertThat(
            call(owner, "POST", "/comparisons", comparison(source, UUID.randomUUID(), 2))
                .statusCode())
        .isEqualTo(429);
    assertThat(ownerVersions(owner)).isEqualTo(1);
    assertThat(ok(owner, "GET", "/comparisons", null, 200).size()).isZero();
    var duplicate = new HashMap<>(comparison(source, UUID.randomUUID(), 2));
    duplicate.put("modelHashes", List.of(model.hash(), model.hash()));
    assertThat(call(owner, "POST", "/comparisons", duplicate).statusCode()).isEqualTo(400);
  }

  @Test
  void rollsBackEarlierJobsWhenSecondDatabaseWriteFails() throws Exception {
    var owner = actor(null);
    var source = create(owner);
    var existing = db.queryForList("SELECT id FROM rainfall_comparisons", UUID.class);
    var allowed =
        java.util.stream.Stream.concat(
                java.util.stream.Stream.of(new UUID(0, 0)), existing.stream())
            .map(id -> "'" + id + "'")
            .collect(java.util.stream.Collectors.joining(","));
    db.execute(
        "ALTER TABLE rainfall_comparison_jobs ADD CONSTRAINT comparison_failure_probe CHECK(ordinal"
            + " <> 1 OR comparison_id IN ("
            + allowed
            + "))");
    try {
      assertThat(
              call(owner, "POST", "/comparisons", comparison(source, UUID.randomUUID(), 3))
                  .statusCode())
          .isEqualTo(500);
    } finally {
      db.execute("ALTER TABLE rainfall_comparison_jobs DROP CONSTRAINT comparison_failure_probe");
    }
    assertThat(ownerVersions(owner)).isEqualTo(1);
    assertThat(ok(owner, "GET", "/comparisons", null, 200).size()).isZero();
    assertThat(ok(owner, "GET", "/simulations", null, 200).size()).isZero();
  }

  @Test
  void serializesSimultaneousGroupsAgainstSharedQueueLimit() throws Exception {
    var owner = actor(null);
    var source = create(owner);
    var first = comparison(source, UUID.randomUUID(), 2);
    var second = comparison(source, UUID.randomUUID(), 2);
    java.util.function.Function<Map<String, Object>, Integer> submit =
        request -> {
          try {
            return call(owner, "POST", "/comparisons", request).statusCode();
          } catch (Exception e) {
            throw new IllegalStateException(e);
          }
        };
    var one = java.util.concurrent.CompletableFuture.supplyAsync(() -> submit.apply(first));
    var two = java.util.concurrent.CompletableFuture.supplyAsync(() -> submit.apply(second));
    assertThat(
            List.of(
                one.get(15, java.util.concurrent.TimeUnit.SECONDS),
                two.get(15, java.util.concurrent.TimeUnit.SECONDS)))
        .containsExactlyInAnyOrder(202, 429);
    assertThat(ownerVersions(owner)).isEqualTo(3);
    assertThat(ok(owner, "GET", "/comparisons", null, 200).size()).isEqualTo(1);
    assertThat(ok(owner, "GET", "/simulations", null, 200).size()).isEqualTo(2);
  }
}
