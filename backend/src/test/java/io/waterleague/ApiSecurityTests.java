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
  @org.springframework.test.context.DynamicPropertySource
  static void integrationDatabase(
      org.springframework.test.context.DynamicPropertyRegistry registry) {
    String url = System.getProperty("waterleague.integration.jdbc");
    if (url != null) {
      registry.add("spring.datasource.url", () -> url);
      registry.add("spring.datasource.driver-class-name", () -> "org.postgresql.Driver");
      registry.add("spring.datasource.username", () -> System.getenv("WL_INTEGRATION_USER"));
      registry.add("spring.datasource.password", () -> System.getenv("WL_INTEGRATION_PASSWORD"));
    }
  }

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
  void publicInfrastructureVersionsStayReadableWithoutOpeningPrivateEndpoints() throws Exception {
    var current = get("/api/v1/infrastructure/seoul-public-20261019-v3");
    var old = get("/api/v1/infrastructure/seoul-public-20261018-v2");
    assertThat(current.statusCode()).isEqualTo(200);
    assertThat(old.statusCode()).isEqualTo(200);
    assertThat(current.body()).contains("PUBLIC_MAPPED_BUILDING", "W653831038");
    assertThat(old.body()).doesNotContain("PUBLIC_MAPPED_BUILDING");
    assertThat(get("/api/v1/infrastructure/unknown").statusCode()).isEqualTo(401);
  }

  @Test
  void publicCurrentSurfaceIsEmptyWithoutExposingPrivateJobs() throws Exception {
    String area = "?index=0&minX=-60000&minY=-60000&maxX=60000&maxY=60000";
    var response = get("/api/v1/surface/current" + area);
    assertThat(response.statusCode()).isEqualTo(200);
    assertThat(response.body()).contains("\"runs\":[]", "\"serverNow\"");
    assertThat(response.headers().firstValue("Cache-Control")).contains("no-store");
    var unknown = get("/api/v1/surface/current/00000000-0000-4000-8000-000000000000/frame" + area);
    assertThat(unknown.statusCode()).isEqualTo(404);
    assertThat(unknown.body()).doesNotContain("stackTrace", "artifacts", "public-surface");
    for (String path :
        new String[] {
          "/api/v1/historical/00000000-0000-4000-8000-000000000000/surface/catalog",
          "/api/v1/installations/00000000-0000-4000-8000-000000000000/surface/frame" + area,
          "/api/v1/research/installations/00000000-0000-4000-8000-000000000000/surface/catalog",
          "/api/v1/surface/current/00000000-0000-4000-8000-000000000000/catalog"
        }) {
      assertThat(get(path).statusCode()).isEqualTo(401);
    }
  }

  @Test
  void protectsInstitutionAndManagementEndpoints() throws Exception {
    for (String path :
        new String[] {
          "/api/v1/references",
          "/api/v1/organizations/private/strategies",
          "/actuator/env",
          "/api/v1/spatial/buildings"
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
}
