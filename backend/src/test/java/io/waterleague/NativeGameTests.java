package io.waterleague;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import io.waterleague.common.exception.GlobalExceptionHandler;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.common.service.JsonService;
import io.waterleague.rainfall.controller.ObservedGameController;
import io.waterleague.rainfall.repository.ObservedGameRepository;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

class NativeGameTests {
  private final JsonService json = new JsonService(new ObjectMapper());

  @Test
  void exportsAllOfficialDistrictObservationBindingsWithoutGeometryModelDependencies() throws Exception {
    var repository = new ObservedGameRepository(json);
    var catalog = repository.catalog();
    var forcing = new TreeMap<String, Object>();
    var districtIds = new TreeSet<String>();
    for (var region : catalog.path("regions")) {
      String district = region.path("districtId").asString();
      assertThat(district).matches("11[0-9]{3}");
      assertThat(districtIds.add(district)).isTrue();
      for (var hash : region.path("modelHashes")) {
        var model = repository.require(hash.asString());
        assertThat(json.hash(model.source())).isEqualTo(hash.asString());
        assertThat(model.model().path("districtId").asString()).isEqualTo(district);
        assertThat(model.model().has("cells")).isFalse();
        assertThat(model.model().path("rainfall").path("stationDistanceKm").asDouble()).isBetween(0., 10.);
        assertThat(forcing.put(hash.asString(), model.model())).isNull();
      }
    }
    assertThat(districtIds).hasSize(25);
    assertThat(forcing).hasSize(100);
    for (var event : repository.events().path("events")) {
      assertThat(event.path("models")).hasSize(25);
      for (var binding : event.path("models")) {
        var model = repository.require(binding.path("modelHash").asString()).model();
        assertThat(model.path("disasterEvent").path("id")).isEqualTo(event.path("id"));
        assertThat(model.path("districtId")).isEqualTo(binding.path("districtId"));
      }
    }
    Files.createDirectories(Path.of("target"));
    Files.writeString(Path.of("target/native-game-cross-runtime-v1.json"), json.write(Map.of(
        "catalogSha256", ObservedGameRepository.SHA256, "forcings", forcing)) + "\n");
  }

  @Test
  void returnsIndependentSnapshotsAndBoundedPublicApiErrors() throws Exception {
    var repository = new ObservedGameRepository(json);
    String hash = repository.catalog().path("regions").get(0).path("defaultModelHash").asString();
    ((ObjectNode) repository.catalog()).put("id", "changed");
    ((ObjectNode) repository.require(hash).model()).put("districtId", "changed");
    assertThat(repository.catalog().path("id").asString()).isEqualTo("SEOUL_NGII_GAME_V1");
    assertThat(repository.require(hash).model().path("districtId").asString()).isEqualTo("11110");
    var rates = mock(RateLimitService.class);
    var client = MockMvcBuilders.standaloneSetup(new ObservedGameController(repository, rates, json))
        .setControllerAdvice(new GlobalExceptionHandler()).build();
    client.perform(get("/api/v1/spatial/play/forcings")).andExpect(status().isOk())
        .andExpect(jsonPath("$.catalogSha256").value(ObservedGameRepository.SHA256));
    client.perform(get("/api/v1/spatial/play/forcings/" + hash)).andExpect(status().isOk())
        .andExpect(jsonPath("$.kind").value("OBSERVED_FORCING_BINDING"));
    client.perform(get("/api/v1/spatial/play/forcings/old-model")).andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("REQUEST_INVALID"));
    client.perform(get("/api/v1/spatial/play/forcings/" + "0".repeat(64)))
        .andExpect(status().isUnprocessableContent()).andExpect(jsonPath("$.code").value("MODEL_NOT_ELIGIBLE"));
    verify(rates, times(4)).check(anyString(), eq(300), eq(60));
  }
}
