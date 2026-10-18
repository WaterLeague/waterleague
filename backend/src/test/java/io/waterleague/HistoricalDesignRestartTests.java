package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.common.service.JsonService;
import io.waterleague.historical.dto.HistoricalDesignRequest;
import io.waterleague.historical.service.HistoricalDesignService;
import java.nio.file.*;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("local")
@EnabledIfSystemProperty(named = "waterleague.integration.design.fixture", matches = ".+")
class HistoricalDesignRestartTests {
  @org.springframework.test.context.DynamicPropertySource
  static void database(org.springframework.test.context.DynamicPropertyRegistry r) {
    SharedInstallationTests.integrationDatabase(r);
  }

  @Autowired HistoricalDesignService service;
  @Autowired JdbcTemplate db;
  @Autowired JsonService json;

  @Test
  void secondJvmRestoresEmptyLatestAndReplaysOriginalRequestWithoutNewRevision() throws Exception {
    var fixture =
        json.tree(
            Files.readString(
                Path.of(System.getProperty("waterleague.integration.design.fixture"))));
    String sha = fixture.path("snapshotSha256").asString();
    var row =
        db.queryForMap(
            "SELECT owner_id,event_id,request_raw FROM historical_design_revisions WHERE"
                + " snapshot_sha256=?",
            sha);
    var owner = (UUID) row.get("owner_id");
    String event = (String) row.get("event_id");
    var request =
        json.read(
            json.write(json.tree((String) row.get("request_raw")).path("request")),
            HistoricalDesignRequest.class);
    assertThat(service.get(owner, event).revision()).isEqualTo(2);
    assertThat(service.get(owner, event).snapshot().path("placements").size()).isZero();
    assertThat(service.save(owner, event, request).snapshotSha256()).isEqualTo(sha);
    assertThat(
            db.queryForObject(
                "SELECT count(*) FROM historical_design_revisions WHERE owner_id=?",
                Integer.class,
                owner))
        .isEqualTo(2);
  }
}
