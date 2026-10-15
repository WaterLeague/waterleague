package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import java.net.*;
import java.net.http.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import tools.jackson.databind.ObjectMapper;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("local")
class AccountFlowTests {
  @Value("${local.server.port}")
  int port;

  @Autowired ObjectMapper json;
  @Autowired JdbcTemplate db;
  HttpClient client =
      HttpClient.newBuilder()
          .cookieHandler(new CookieManager(null, CookiePolicy.ACCEPT_ALL))
          .build();

  HttpResponse<String> call(String path, String body, String csrf) throws Exception {
    var req = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/v1" + path));
    if (body != null)
      req.POST(HttpRequest.BodyPublishers.ofString(body))
          .header("Content-Type", "application/json");
    if (csrf != null) req.header("X-CSRF-TOKEN", csrf);
    return client.send(req.build(), HttpResponse.BodyHandlers.ofString());
  }

  String csrf() throws Exception {
    return json.readTree(call("/auth/csrf", null, null).body()).get("token").asString();
  }

  @Test
  void persistsSessionProtectsRoleAndRotatesCsrf() throws Exception {
    String name = "player_" + UUID.randomUUID().toString().substring(0, 8);
    String body =
        json.writeValueAsString(
            Map.of(
                "username",
                name,
                "password",
                "safe-test-password-142",
                "memberType",
                "PLAYER",
                "organizationName",
                "",
                "purpose",
                ""));
    var token = csrf();
    var before = call("/auth/register", body, token);
    assertThat(before.statusCode()).isEqualTo(200);
    assertThat(before.body()).contains("PLAYER").doesNotContain("passwordHash");
    assertThat(call("/auth/me", null, null).statusCode()).isEqualTo(200);
    assertThat(
            db.queryForObject(
                "SELECT COUNT(*) FROM SPRING_SESSION WHERE PRINCIPAL_NAME=?", Integer.class, name))
        .isEqualTo(1);
    assertThat(call("/auth/logout", "{}", token).statusCode()).isEqualTo(403);
    assertThat(call("/research/strategies", null, null).statusCode()).isEqualTo(403);
    assertThat(call("/auth/logout", "{}", csrf()).statusCode()).isEqualTo(200);
    assertThat(call("/auth/me", null, null).statusCode()).isEqualTo(401);
    assertThat(
            call(
                    "/auth/login",
                    json.writeValueAsString(
                        Map.of("username", name, "password", "safe-test-password-142")),
                    csrf())
                .statusCode())
        .isEqualTo(200);
  }

  @Test
  void rejectsRoleInjectionAndBadCredentials() throws Exception {
    assertThat(
            call(
                    "/auth/register",
                    "{\"username\":\"badrole\",\"password\":\"long-valid-password\",\"role\":\"INSTITUTION\"}",
                    csrf())
                .statusCode())
        .isEqualTo(400);
    assertThat(
            call(
                    "/auth/login",
                    "{\"username\":\"absent\",\"password\":\"long-valid-password\"}",
                    csrf())
                .statusCode())
        .isEqualTo(401);
  }
}
