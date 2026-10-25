package io.waterleague;

import static org.assertj.core.api.Assertions.assertThat;

import io.waterleague.common.service.JsonService;
import io.waterleague.physics.view.PhysicsView;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

class PhysicsRainfallEvidenceTests {
  @Test
  void storedRainfallRecoverySurvivesThePublicResponseBoundary() throws Exception {
    var json = new JsonService(new ObjectMapper());
    var stored = (ObjectNode) json.tree(Files.readString(Path.of(
        "../frontend/src/domains/physics/view/fixtures/rawMetrics-physics-http-v1.json")))
        .path("value").path("result");
    var evidence = json.tree("""
        {"policy":"OBSERVED_ZERO_AND_FIXED_SEOUL_ZERO_V1","observedZeroMinutes":93,
         "substituteMinutes":663,"substituteStations":[{"stationId":"202","name":"고덕2동","distanceM":1801.366}]}
        """);
    stored.set("rainfallQuality", evidence);
    var result = json.read(json.write(stored), PhysicsView.Result.class);
    assertThat(json.tree(json.write(result)).path("rainfallQuality")).isEqualTo(evidence);
    stored.remove("rainfallQuality");
    assertThat(json.read(json.write(stored), PhysicsView.Result.class).rainfallQuality()).isNull();
  }
}
