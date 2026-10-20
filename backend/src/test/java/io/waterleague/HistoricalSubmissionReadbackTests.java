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
import org.springframework.beans.factory.annotation.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("local")
@EnabledIfSystemProperty(named = "waterleague.integration.submission.evidence", matches = ".+")
class HistoricalSubmissionReadbackTests extends PostgresIntegrationTest {
  @org.springframework.test.context.DynamicPropertySource
  static void integrationDatabase(
      org.springframework.test.context.DynamicPropertyRegistry registry) {
    SharedInstallationTests.integrationDatabase(registry);
  }

  @Autowired JdbcTemplate database;
  @Autowired JsonService json;
  @Autowired AccountRepository accounts;
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
            .build();
    var csrf = get(client, "/auth/csrf");
    var response =
        client.send(
            HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/v1/auth/login"))
                .header("Content-Type", "application/json")
                .header("X-CSRF-TOKEN", json.tree(csrf.body()).path("token").asString())
                .POST(
                    HttpRequest.BodyPublishers.ofString(
                        json.write(Map.of("username", username, "password", password))))
                .timeout(Duration.ofSeconds(20))
                .build(),
            HttpResponse.BodyHandlers.ofString());
    assertThat(response.statusCode()).isEqualTo(200);
    return client;
  }

  @Test
  void servesPostedDecimalAndFrozenContextThroughAuthenticatedHttp() throws Exception {
    var directory = Path.of(System.getProperty("waterleague.integration.submission.evidence"));
    var owner = accounts.byUsername("queue_test").orElseThrow();
    var rows =
        database.query(
            "SELECT"
                + " j.id,j.result,s.event_id,s.difference_m3,s.rules_hash,s.comparison_group_hash,s.score_policy_sha256"
                + " FROM historical_submissions s JOIN historical_experiments j ON j.id=s.job_id"
                + " WHERE j.owner_id=? AND j.state='SUCCEEDED' ORDER BY j.created_at,j.id",
            (r, n) ->
                Map.<String, Object>of(
                    "id",
                    r.getObject("id", UUID.class),
                    "result",
                    r.getString("result"),
                    "event",
                    r.getString("event_id"),
                    "score",
                    r.getBigDecimal("difference_m3"),
                    "rules",
                    r.getString("rules_hash"),
                    "context",
                    r.getString("comparison_group_hash"),
                    "policy",
                    r.getString("score_policy_sha256")),
            owner.id());
    assertThat(rows).hasSize(3);
    String password = UUID.randomUUID() + "Aa9!";
    database.update(
        "UPDATE accounts SET password_hash=? WHERE id=?", passwords.encode(password), owner.id());
    var client = login(owner.username(), password);
    var anonymous = HttpClient.newHttpClient();
    var otherId = UUID.randomUUID();
    String otherName = "score_http_" + otherId.toString().substring(0, 8);
    accounts.add(
        new Account(
            otherId,
            otherName,
            "시험 다른 회원",
            passwords.encode(password),
            "MEMBER",
            "PLAYER",
            "APPROVED",
            null,
            "",
            "",
            true,
            "11680",
            "AFFILIATED"));
    var other = login(otherName, password);
    for (var row : rows) {
      String path = "/historical/submissions/" + row.get("id");
      assertThat(get(anonymous, path).statusCode()).isEqualTo(401);
      assertThat(get(other, path).statusCode()).isEqualTo(404);
      var response = get(client, path);
      assertThat(response.statusCode()).isEqualTo(200);
      assertThat(response.headers().firstValue("Cache-Control")).contains("no-store");
      var result = json.tree(response.body()).path("result");
      assertThat(result.path("rankingStatus").asString()).isEqualTo("COMPARABLE");
      assertThat(result.path("scoreContext"))
          .isEqualTo(json.tree((String) row.get("result")).path("scoreContext"));
      assertThat(result.path("scoreContext").path("sha256").asString())
          .isEqualTo(row.get("context"));
      assertThat(new java.math.BigDecimal(result.path("rankingScoreM3Exact").asString()))
          .isEqualByComparingTo((java.math.BigDecimal) row.get("score"));
      Files.writeString(
          directory.resolve("submission-http-" + row.get("id") + ".json"),
          response.body(),
          StandardOpenOption.CREATE_NEW);
    }
    String boardPath = "/historical/leaderboard/" + rows.getFirst().get("event");
    assertThat(get(anonymous, boardPath).statusCode()).isEqualTo(401);
    var response = get(client, boardPath);
    assertThat(response.statusCode()).isEqualTo(200);
    assertThat(response.headers().firstValue("Cache-Control")).contains("no-store");
    var board = json.tree(response.body());
    assertThat(board.path("groups").size()).isEqualTo(1);
    var entries = board.path("groups").get(0).path("entries");
    assertThat(entries.size()).isEqualTo(1);
    var best =
        rows.stream()
            .map(r -> (java.math.BigDecimal) r.get("score"))
            .max(java.math.BigDecimal::compareTo)
            .orElseThrow();
    assertThat(new java.math.BigDecimal(entries.get(0).path("differenceM3Exact").asString()))
        .isEqualByComparingTo(best);
    assertThat(entries.get(0).path("rank").asInt()).isEqualTo(1);
    assertThat(board.path("withheldSubmissionCount").asInt()).isZero();
    assertThat(response.body())
        .doesNotContain("password", "lease_token", "costSnapshotRaw", "submissionRequestRaw");
    Files.writeString(
        directory.resolve("board-http.json"), response.body(), StandardOpenOption.CREATE_NEW);
  }
}
