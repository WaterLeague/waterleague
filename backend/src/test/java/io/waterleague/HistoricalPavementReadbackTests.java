package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.account.entity.Account;
import io.waterleague.account.repository.AccountRepository;
import io.waterleague.common.service.JsonService;
import java.io.ByteArrayInputStream;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.*;
import java.util.zip.ZipInputStream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.springframework.beans.factory.annotation.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("local")
@EnabledIfSystemProperty(named = "waterleague.integration.pavement.evidence", matches = ".+")
class HistoricalPavementReadbackTests extends PostgresIntegrationTest {
  @org.springframework.test.context.DynamicPropertySource
  static void integrationDatabase(
      org.springframework.test.context.DynamicPropertyRegistry registry) {
    SharedInstallationTests.integrationDatabase(registry);
    registry.add(
        "waterleague.artifacts",
        () ->
            Path.of(System.getProperty("waterleague.integration.pavement.evidence"))
                .resolve("artifacts")
                .toString());
  }

  @Autowired JdbcTemplate database;
  @Autowired JsonService json;
  @Autowired AccountRepository accounts;
  @Autowired PasswordEncoder passwords;

  @Value("${local.server.port}")
  int port;

  HttpResponse<byte[]> get(HttpClient client, String path) throws Exception {
    return client.send(
        HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/v1" + path))
            .timeout(Duration.ofSeconds(20))
            .GET()
            .build(),
        HttpResponse.BodyHandlers.ofByteArray());
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
                .header(
                    "X-CSRF-TOKEN",
                    json.tree(new String(csrf.body(), StandardCharsets.UTF_8))
                        .path("token")
                        .asString())
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
  void servesActualComparisonAndVerifiedBundleOnlyToOwner() throws Exception {
    var directory = Path.of(System.getProperty("waterleague.integration.pavement.evidence"));
    var owner = accounts.byUsername("queue_test").orElseThrow();
    var row =
        database.queryForMap(
            "SELECT id,result FROM historical_experiments WHERE owner_id=? AND state='SUCCEEDED'"
                + " AND jsonb_exists(result::jsonb, 'pavementMaintenanceComparison')",
            owner.id());
    String path = "/historical/" + row.get("id");
    String password = UUID.randomUUID() + "Aa9!";
    database.update(
        "UPDATE accounts SET password_hash=? WHERE id=?", passwords.encode(password), owner.id());
    var client = login(owner.username(), password);
    var otherId = UUID.randomUUID();
    String otherName = "pavement_" + otherId.toString().substring(0, 8);
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
    var anonymous = HttpClient.newHttpClient();
    for (String endpoint : List.of(path, path + "/bundle")) {
      assertThat(get(anonymous, endpoint).statusCode()).isEqualTo(401);
      assertThat(get(other, endpoint).statusCode()).isEqualTo(404);
    }
    var response = get(client, path);
    assertThat(response.statusCode()).isEqualTo(200);
    assertThat(response.headers().firstValue("Cache-Control")).contains("no-store");
    var body = json.tree(new String(response.body(), StandardCharsets.UTF_8));
    assertThat(body.path("result")).isEqualTo(json.tree((String) row.get("result")));
    var comparison = body.path("result").path("pavementMaintenanceComparison");
    assertThat(comparison)
        .isEqualTo(json.tree(Files.readString(directory.resolve("comparison.json"))));
    var bundle = get(client, path + "/bundle");
    assertThat(bundle.statusCode()).isEqualTo(200);
    assertThat(bundle.headers().firstValue("Cache-Control")).contains("no-store");
    var files = new TreeMap<String, byte[]>();
    try (var zip = new ZipInputStream(new ByteArrayInputStream(bundle.body()))) {
      java.util.zip.ZipEntry entry;
      while ((entry = zip.getNextEntry()) != null)
        assertThat(files.put(entry.getName(), zip.readAllBytes())).isNull();
    }
    var manifest = json.tree(new String(files.get("manifest.json"), StandardCharsets.UTF_8));
    assertThat(files.size()).isEqualTo(manifest.size() + 1);
    for (String name : manifest.propertyNames())
      assertThat(
              HexFormat.of()
                  .formatHex(MessageDigest.getInstance("SHA-256").digest(files.get(name))))
          .isEqualTo(manifest.path(name).asString());
    assertThat(
            json.tree(
                new String(
                    files.get("pavement-comparison/comparison.json"), StandardCharsets.UTF_8)))
        .isEqualTo(comparison);
    assertThat(files)
        .containsKeys(
            "pavement-comparison/FRESH.out",
            "pavement-comparison/DUST_96_G.out",
            "pavement-comparison/DUST_192_G.out",
            "pavement-comparison/code/engine/pavement_maintenance.py");
    Files.write(
        directory.resolve("http-result.json"), response.body(), StandardOpenOption.CREATE_NEW);
    Files.write(directory.resolve("http-bundle.zip"), bundle.body(), StandardOpenOption.CREATE_NEW);
  }
}
