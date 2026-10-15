package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import java.net.*;
import java.net.http.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("local")
class ApiSecurityTests {
  @org.springframework.beans.factory.annotation.Autowired
  io.waterleague.common.service.JsonService json;

  @Value("${local.server.port}")
  int port;

  private final HttpClient client = HttpClient.newHttpClient();

  private HttpResponse<String> get(String path) throws Exception {
    return client.send(
        HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path)).GET().build(),
        HttpResponse.BodyHandlers.ofString());
  }

  @Test
  void publicCatalogReportsUnavailabilityWithoutInventedMaps() throws Exception {
    var catalog = get("/api/v1/catalog");
    assertThat(catalog.statusCode()).isEqualTo(200);
    assertThat(catalog.body()).contains("\"officialEvaluationAvailable\":false");
    assertThat(get("/api/v1/maps").body()).isEqualTo("[]");
    assertThat(catalog.headers().firstValue("X-Request-Id")).isPresent();
    assertThat(catalog.headers().firstValue("X-Content-Type-Options")).contains("nosniff");
  }

  @Test
  void protectsInstitutionAndManagementEndpoints() throws Exception {
    for (String path :
        new String[] {
          "/api/v1/organizations/private/strategies", "/actuator/env", "/api/v1/spatial/buildings"
        }) {
      var response = get(path);
      assertThat(response.statusCode()).isEqualTo(401);
      assertThat(response.headers().firstValue("Content-Type").orElse(""))
          .startsWith("application/problem+json");
      assertThat(response.body())
          .contains("AUTHENTICATION_REQUIRED")
          .doesNotContain("stackTrace", "password");
    }
  }

  @Test
  void rejectsWritesWithoutCsrf() throws Exception {
    var response =
        client.send(
            HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/v1/strategies"))
                .POST(HttpRequest.BodyPublishers.ofString("{}"))
                .header("Content-Type", "application/json")
                .build(),
            HttpResponse.BodyHandlers.ofString());
    assertThat(response.statusCode()).isEqualTo(403);
    assertThat(response.body()).contains("ACCESS_DENIED");
  }

  @Test
  void publishesCpuEvidenceWithoutAddingHumanRecords() throws Exception {
    var response = get("/api/v1/references");
    assertThat(response.statusCode()).isEqualTo(200);
    var view = json.tree(response.body());
    var report = view.path("report");
    var source = get("/api/v1/references/source");
    var ledger = get("/api/v1/references/ledger");
    assertThat(source.statusCode()).isEqualTo(200);
    assertThat(ledger.statusCode()).isEqualTo(200);
    assertThat(source.headers().firstValue("Content-Disposition").orElse(""))
        .contains("attachment");
    assertThat(json.hash(source.body())).isEqualTo(view.path("reportHash").asString());
    assertThat(json.hash(ledger.body())).isEqualTo(report.path("ledgerSha256").asString());
    assertThat(report.path("official").asBoolean()).isFalse();
    assertThat(report.path("validationLevel").asString()).isEqualTo("EXPLORATORY");
    assertThat(report.path("plans").size()).isEqualTo(3);
    assertThat(json.tree(ledger.body()).size())
        .isEqualTo(report.path("uniqueCandidateEvaluations").asInt());
    assertThat(get("/api/v1/leaderboard").body()).doesNotContain("cpu-", "CPU 기준안");
    assertThat(get("/api/v1/references/private").statusCode()).isEqualTo(401);
  }
}
