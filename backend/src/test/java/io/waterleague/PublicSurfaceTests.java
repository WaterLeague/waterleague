package io.waterleague;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.surface.dto.SurfaceFrameRequest;
import io.waterleague.surface.entity.SurfacePublication;
import io.waterleague.surface.exception.SurfaceResultException;
import io.waterleague.surface.repository.*;
import io.waterleague.surface.service.PublicSurfaceService;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

class PublicSurfaceTests {
  @TempDir Path temporary;
  final JsonService json = new JsonService(new ObjectMapper());
  final Instant now = Instant.parse("2026-10-19T04:00:00Z");
  final String classification = "PUBLIC_INPUT_UNCALIBRATED_CURRENT_BASELINE";
  final SurfaceFrameRequest area = new SurfaceFrameRequest(0, -1, -1, 20, 20);
  final UUID id = UUID.randomUUID(), token = UUID.randomUUID();
  Path root, directory, index;
  SurfacePlaybackRepository results;
  PublicSurfaceModelRepository models;
  PublicSurfaceService service;
  Map<String, Object> row;

  @BeforeEach
  void setup() throws Exception {
    root = temporary.toRealPath();
    directory = root.resolve("public-surface/" + id + "/" + token + "/surface-playback");
    index = root.resolve("public-surface/current.json");
    var ref = SurfacePlaybackTests.fixture(directory, json, true);
    var catalog = (ObjectNode) json.tree(Files.readString(directory.resolve("catalog.json")));
    catalog.put("classification", classification);
    catalog.put("startUtc", now.minusSeconds(30).toString());
    var raw = json.write(catalog);
    Files.writeString(directory.resolve("catalog.json"), raw);
    row = new LinkedHashMap<>();
    row.put("basinId", "test-only");
    row.put("id", id.toString());
    row.put("token", token.toString());
    row.put("catalogSha256", json.hash(raw));
    row.put("surfaceResultSha256", ref.get("surfaceResultSha256"));
    row.put("lastFrameAt", now.minusSeconds(30).toString());
    row.put("scenario", "PUBLIC_BASELINE");
    row.put("numericalStatus", "PASSED");
    row.put("forcingSource", "OFFICIAL_OBSERVATIONS");
    row.put("inputBundleSha256", "b".repeat(64));
    row.put("numericalPolicySha256", "c".repeat(64));
    results = spy(new SurfacePlaybackRepository(root.toString(), json));
    models = mock(PublicSurfaceModelRepository.class);
    when(models.find("test-only"))
        .thenReturn(
            Optional.of(
                new PublicSurfaceModelRepository.Model(
                    "test-only",
                    "전달·권한 시험 전용",
                    "b".repeat(64),
                    "c".repeat(64),
                    classification,
                    new double[] {0, 0, 11, 11})));
    service = new PublicSurfaceService(root.toString(), json, models, results);
    writeIndex(List.of(row));
  }

  void writeIndex(List<?> rows) throws Exception {
    Files.writeString(index, json.write(Map.of("schemaVersion", 1, "runs", rows)));
  }

  void changeTime(Instant time) throws Exception {
    var catalog = (ObjectNode) json.tree(Files.readString(directory.resolve("catalog.json")));
    catalog.put("startUtc", time.toString());
    String raw = json.write(catalog);
    Files.writeString(directory.resolve("catalog.json"), raw);
    row.put("lastFrameAt", time.toString());
    row.put("catalogSha256", json.hash(raw));
    writeIndex(List.of(row));
  }

  @Test
  void productionRegistryRemainsEmptyAndUnpublishedPrivateIdsStayUnavailable() throws Exception {
    var production =
        new PublicSurfaceService(
            root.toString(), json, new PublicSurfaceModelRepository(json), results);
    assertThat(production.current(area, now).runs()).isEmpty();
    assertThatThrownBy(() -> production.frame(id, area, now))
        .isInstanceOf(DomainException.class)
        .extracting(e -> ((DomainException) e).code())
        .isEqualTo(ErrorCode.RESOURCE_NOT_FOUND);
    verifyNoInteractions(results);
    Files.delete(index);
    assertThat(service.current(area, now).runs()).isEmpty();
  }

  @Test
  void exactPublicFrameKeepsNativeValuesAndViewportFiltering() {
    var metadata = service.current(area, now);
    assertThat(metadata.serverNow()).isEqualTo(now);
    assertThat(metadata.runs()).hasSize(1);
    assertThat(metadata.runs().getFirst().id()).isEqualTo(id);
    assertThat(metadata.runs().getFirst().catalog().classification()).isEqualTo(classification);
    assertThat(json.write(metadata)).doesNotContain(token.toString(), root.toString());
    var frame = service.frame(id, area, now);
    assertThat(frame.cells()).hasSize(2);
    assertThat(frame.cells().getFirst().depthM()).isEqualTo(.1);
    assertThat(frame.cells().getFirst().speedMps()).isCloseTo(.5, within(1e-15));
    assertThat(frame.cells().getFirst().flowDirection()[0]).isCloseTo(-.8, within(1e-15));
    assertThat(frame.cells().getFirst().flowDirection()[1]).isCloseTo(.6, within(1e-15));
    assertThat(frame.wholeDomainStorageM3()).isEqualTo(.05);
    assertThat(service.current(new SurfaceFrameRequest(0, 100, 100, 200, 200), now).runs())
        .isEmpty();
    assertThatThrownBy(() -> service.frame(UUID.randomUUID(), area, now))
        .isInstanceOf(DomainException.class);
  }

  @Test
  void staleAndFutureResultsDisappearAndNeverBecomeZeroFlood() throws Exception {
    changeTime(now.minusSeconds(299));
    assertThat(service.frame(id, area, now).cells()).hasSize(2);
    for (Instant at : List.of(now.minusSeconds(300).minusNanos(1), now.plusNanos(1))) {
      changeTime(at);
      assertThat(service.current(area, now).runs()).isEmpty();
      assertThatThrownBy(() -> service.frame(id, area, now)).isInstanceOf(DomainException.class);
    }
  }

  @Test
  void privateUnvalidatedAndWrongModelInputsCannotPublish() throws Exception {
    for (String key :
        List.of(
            "scenario",
            "numericalStatus",
            "forcingSource",
            "inputBundleSha256",
            "numericalPolicySha256")) {
      Object original = row.put(key, "UNAPPROVED");
      writeIndex(List.of(row));
      assertThatThrownBy(() -> service.current(area, now))
          .isInstanceOf(SurfaceResultException.class);
      row.put(key, original);
    }
    row.put("lastFrameAt", now.minusSeconds(29).toString());
    writeIndex(List.of(row));
    assertThatThrownBy(() -> service.current(area, now)).isInstanceOf(SurfaceResultException.class);
  }

  @Test
  void duplicatesCatalogChangesAndSymlinksAreRejected() throws Exception {
    writeIndex(List.of(row, row));
    assertThatThrownBy(() -> service.current(area, now)).isInstanceOf(SurfaceResultException.class);
    writeIndex(List.of(row));
    Files.writeString(directory.resolve("catalog.json"), "changed");
    assertThatThrownBy(() -> service.current(area, now)).isInstanceOf(SurfaceResultException.class);
    Files.move(index, root.resolve("moved.json"));
    Files.createSymbolicLink(index, root.resolve("moved.json"));
    assertThatThrownBy(() -> service.current(area, now)).isInstanceOf(SurfaceResultException.class);
  }

  @Test
  void changedFrameAndPublicationRemovalDuringReadFailClosed() throws Exception {
    doAnswer(
            invocation -> {
              var frame = invocation.callRealMethod();
              writeIndex(List.of());
              return frame;
            })
        .when(results)
        .frame(any(SurfacePublication.class), any(SurfaceFrameRequest.class));
    assertThatThrownBy(() -> service.frame(id, area, now))
        .isInstanceOf(DomainException.class)
        .extracting(e -> ((DomainException) e).code())
        .isEqualTo(ErrorCode.RESOURCE_NOT_FOUND);
    reset(results);
    writeIndex(List.of(row));
    Files.writeString(directory.resolve("frame-00000.bin"), "changed");
    assertThatThrownBy(() -> service.frame(id, area, now))
        .isInstanceOf(SurfaceResultException.class);
  }

  @Test
  void registeredBoundsAreImmutableAndInvalidInputsFailDomainValidation() {
    var bounds = new double[] {0, 0, 1, 1};
    var model =
        new PublicSurfaceModelRepository.Model(
            "test", "시험", "a".repeat(64), "b".repeat(64), classification, bounds);
    bounds[0] = 10;
    model.bounds()[1] = 10;
    assertThat(model.bounds()).containsExactly(0, 0, 1, 1);
    assertThatThrownBy(
            () ->
                new PublicSurfaceModelRepository.Model(
                    "test", "시험", null, "b".repeat(64), classification, bounds))
        .isInstanceOf(SurfaceResultException.class);
  }
}
