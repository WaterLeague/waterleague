package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.common.service.JsonService;
import java.net.URI;
import java.net.http.*;
import java.nio.file.*;
import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.springframework.beans.factory.annotation.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("local")
@EnabledIfSystemProperty(named = "waterleague.integration.physics.fixtures", matches = ".+")
class PhysicsReadbackTests extends PostgresIntegrationTest {
  @org.springframework.test.context.DynamicPropertySource
  static void integrationDatabase(
      org.springframework.test.context.DynamicPropertyRegistry registry) {
    SharedInstallationTests.integrationDatabase(registry);
  }

  @Autowired JdbcTemplate database;
  @Autowired JsonService json;

  @Value("${local.server.port}")
  int port;

  final HttpClient client = HttpClient.newHttpClient();

  HttpResponse<String> get(String path) throws Exception {
    return client.send(
        HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/v1" + path))
            .timeout(Duration.ofSeconds(20))
            .GET()
            .build(),
        HttpResponse.BodyHandlers.ofString());
  }

  @Test
  void servesActualWorkerComparisonAndDesignContractThroughPublicHttpWithoutPrivateFields()
      throws Exception {
    var directory = Path.of(System.getProperty("waterleague.integration.physics.fixtures"));
    assertThat(directory.toRealPath()).isEqualTo(directory);
    var rows =
        database.query(
            """
            SELECT i.id,j.result FROM shared_installations i JOIN shared_physics_jobs j ON j.installation_id=i.id
            JOIN accounts a ON a.id=i.owner_id WHERE a.username='queue_test' AND i.removed_at IS NULL
            AND j.state='SUCCEEDED' ORDER BY j.requested_through DESC,j.created_at DESC LIMIT 1
            """,
            (r, n) -> new Object[] {r.getObject("id", UUID.class), r.getString("result")});
    assertThat(rows).hasSize(1);
    var raw = json.tree((String) rows.getFirst()[1]);
    var response = get("/installations/" + rows.getFirst()[0] + "/physics");
    assertThat(response.statusCode()).isEqualTo(200);
    assertThat(response.headers().firstValue("Cache-Control")).contains("no-store");
    var result = json.tree(response.body()).path("result");
    assertThat(result.path("designContract")).isEqualTo(raw.path("designContract"));
    assertThat(result.path("designContract").path("sha256").asString()).matches("[a-f0-9]{64}");
    assertThat(result.path("runoffComparison")).isEqualTo(raw.path("runoffComparison"));
    assertThat(result.path("scoreContext")).isEqualTo(raw.path("scoreContext"));
    assertThat(result.path("scoreContext").path("sha256").asString()).matches("[a-f0-9]{64}");
    assertThat(result.path("lifeCycleCost")).isEqualTo(raw.path("lifeCycleCost"));
    assertThat(result.path("lifeCycleCost").path("status").asString()).isEqualTo("UNAVAILABLE");
    assertThat(result.path("lifeCycleCost").path("lifeCycleCost").isNull()).isTrue();
    assertThat(result.path("runoffComparison").path("schemaVersion").asInt()).isEqualTo(2);
    assertThat(response.body())
        .doesNotContain("password", "lease_token", "costSnapshotRaw", "inputHash");
    Files.writeString(
        directory.resolve("physics-response.json"), response.body(), StandardOpenOption.CREATE_NEW);
    var weekly = get("/weekly");
    assertThat(weekly.statusCode()).isEqualTo(200);
    assertThat(json.tree(weekly.body()).path("scorePolicy").path("tie").asString())
        .isEqualTo("EXACT_STORED_DECIMAL_EQUALITY");
    boolean missing = false;
    for (var district : json.tree(weekly.body()).path("current").path("districts")) {
      if (district.path("evaluatedSeconds").asLong() == 0) {
        missing = true;
        assertThat(district.path("scoreM3").isNull()).isTrue();
        assertThat(district.path("rank").isNull()).isTrue();
      }
    }
    assertThat(missing).isTrue();
    Files.writeString(
        directory.resolve("weekly-response.json"), weekly.body(), StandardOpenOption.CREATE_NEW);
  }
}
