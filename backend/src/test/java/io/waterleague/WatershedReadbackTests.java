package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.common.service.JsonService;
import java.net.*;
import java.net.http.*;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("local")
@EnabledIfSystemProperty(named = "waterleague.integration.watershed.fixtures", matches = ".+")
class WatershedReadbackTests extends PostgresIntegrationTest {
  @org.springframework.test.context.DynamicPropertySource
  static void integrationDatabase(
      org.springframework.test.context.DynamicPropertyRegistry registry) {
    SharedInstallationTests.integrationDatabase(registry);
  }

  @Autowired JsonService json;
  @Autowired AccountRepository accounts;
  @Autowired JdbcTemplate database;
  @Autowired PasswordEncoder passwords;

  @Value("${local.server.port}")
  int port;

  HttpResponse<String> get(HttpClient client, String path) throws Exception {
    return client.send(
        HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/v1" + path))
            .timeout(Duration.ofSeconds(20))
            .GET()
            .build(),
        HttpResponse.BodyHandlers.ofString());
  }

  HttpClient login(String username, String password) throws Exception {
    var client =
        HttpClient.newBuilder()
            .cookieHandler(new CookieManager(null, CookiePolicy.ACCEPT_ALL))
            .connectTimeout(Duration.ofSeconds(10))
            .build();
    var csrf = get(client, "/auth/csrf");
    assertThat(csrf.statusCode()).isEqualTo(200);
    var response =
        client.send(
            HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/v1/auth/login"))
                .timeout(Duration.ofSeconds(20))
                .header("Content-Type", "application/json")
                .header("X-CSRF-TOKEN", json.tree(csrf.body()).path("token").asString())
                .POST(
                    HttpRequest.BodyPublishers.ofString(
                        json.write(Map.of("username", username, "password", password))))
                .build(),
            HttpResponse.BodyHandlers.ofString());
    assertThat(response.statusCode()).isEqualTo(200);
    return client;
  }

  @Test
  void readsActualWorkerResultThroughOwnerHttpProjectionAndDeniesAnotherMember() throws Exception {
    var directory = Path.of(System.getProperty("waterleague.integration.watershed.fixtures"));
    var expected = json.tree(Files.readString(directory.resolve("watershed-readback.json")));
    var ownerId = UUID.fromString(expected.path("ownerId").asString());
    assertThat(accounts.byUsername("queue_test").orElseThrow().id()).isEqualTo(ownerId);
    String password = UUID.randomUUID() + "Aa9!";
    // 전용 임시 DB의 워커 시험 계정만 실제 세션 로그인에 사용할 수 있게 한다.
    assertThat(
            database.update(
                "UPDATE accounts SET password_hash=? WHERE id=? AND username='queue_test'",
                passwords.encode(password),
                ownerId))
        .isEqualTo(1);
    var owner = login("queue_test", password);
    var other = UUID.randomUUID();
    String username = "readback_" + other.toString().substring(0, 8);
    accounts.add(
        new Account(
            other,
            username,
            "관망 조회 시험",
            passwords.encode(password),
            "MEMBER",
            "PLAYER",
            "APPROVED",
            null,
            "",
            "",
            true));
    var stranger = login(username, password);
    var anonymous = HttpClient.newHttpClient();
    for (var job : expected.path("jobs")) {
      String id = job.path("id").asString();
      var raw =
          Files.readString(
              Path.of(job.path("artifactDirectory").asString()).resolve("result.json"));
      assertThat(json.hash(raw)).isEqualTo(job.path("resultSha256").asString());
      var response = get(owner, "/watersheds/" + id);
      assertThat(response.statusCode()).isEqualTo(200);
      assertThat(response.headers().firstValue("Cache-Control")).contains("no-store");
      var value = json.tree(response.body());
      assertThat(value.path("state").asString()).isEqualTo("SUCCEEDED");
      assertThat(value.path("result")).isEqualTo(json.tree(raw));
      assertThat(value.path("design").path("cistern").path("schemaVersion").asInt()).isEqualTo(3);
      String scenario = job.path("host").asString().replace("-reused", "");
      if (job.path("host").asString().endsWith("-reused")) {
        assertThat(
                value.path("result").path("cases").get(0).path("execution").path("mode").asString())
            .isEqualTo("REUSED");
      }
      if (scenario.endsWith("-pipe") || scenario.endsWith("-narrow")) {
        assertThat(
                value
                    .path("design")
                    .path("cistern")
                    .path("inletPipe")
                    .path("lengthM")
                    .decimalValue())
            .isEqualByComparingTo("10");
        var inlet =
            value
                .path("result")
                .path("cases")
                .get(1)
                .path("networkCistern")
                .path("wholeRunLedger")
                .path("inletPipe");
        assertThat(inlet.path("nodeId").asString()).isEqualTo("WLCT_Cistern1_U");
        boolean flooded = scenario.endsWith("-narrow");
        assertThat(inlet.path("numericalStatus").asString())
            .isEqualTo(flooded ? "FAILED" : "PASSED");
        if (flooded) {
          assertThat(value.path("result").path("signedReductionM3").isNull()).isTrue();
          assertThat(inlet.path("floodingM3").decimalValue()).isPositive();
        }
      }
      if (scenario.endsWith("-outlets") || scenario.endsWith("-outletflood")) {
        var outlets =
            value
                .path("result")
                .path("cases")
                .get(1)
                .path("networkCistern")
                .path("wholeRunLedger")
                .path("outletPipes");
        for (String kind : List.of("drain", "overflow")) {
          assertThat(
                  value
                      .path("design")
                      .path("cistern")
                      .path(kind + "Pipe")
                      .path("lengthM")
                      .decimalValue())
              .isEqualByComparingTo("10");
          assertThat(outlets.path(kind).path("receiverNodeId").asString()).isEqualTo("J22");
        }
        if (scenario.endsWith("-outletflood")) {
          assertThat(outlets.path("drain").path("floodingM3").decimalValue()).isPositive();
          assertThat(value.path("result").path("signedReductionM3").isNull()).isTrue();
        }
      }
      if (scenario.endsWith("-closed")) {
        assertThat(value.path("design").path("cistern").path("drain").path("mode").asString())
            .isEqualTo("CLOSED_NO_WITHDRAWAL");
        assertThat(
                value
                    .path("result")
                    .path("cases")
                    .get(1)
                    .path("networkCistern")
                    .path("wholeRunLedger")
                    .path("facilities")
                    .get(0)
                    .path("drainOperation")
                    .asString())
            .isEqualTo("CLOSED_NO_WITHDRAWAL");
      }
      Files.writeString(
          directory.resolve("api-view-" + job.path("host").asString() + ".json"),
          response.body(),
          StandardOpenOption.CREATE_NEW);
      assertThat(get(stranger, "/watersheds/" + id).statusCode()).isEqualTo(404);
      assertThat(get(anonymous, "/watersheds/" + id).statusCode()).isEqualTo(401);
    }
  }
}
