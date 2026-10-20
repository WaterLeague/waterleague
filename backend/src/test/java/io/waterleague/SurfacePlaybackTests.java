package io.waterleague;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.historical.entity.HistoricalExperiment;
import io.waterleague.historical.service.HistoricalService;
import io.waterleague.sharedresearch.service.SharedResearchService;
import io.waterleague.surface.dto.SurfaceFrameRequest;
import io.waterleague.surface.entity.SurfacePublication;
import io.waterleague.surface.repository.SurfacePlaybackRepository;
import io.waterleague.surface.service.SurfacePlaybackService;
import java.nio.*;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.ObjectMapper;

class SurfacePlaybackTests {
  @TempDir Path temporary;
  final JsonService json = new JsonService(new ObjectMapper());

  static String hash(byte[] bytes) throws Exception {
    return HexFormat.of()
        .formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(bytes));
  }

  static Map<String, Object> fixture(Path directory, JsonService json) throws Exception {
    return fixture(directory, json, false);
  }

  static Map<String, Object> fixture(Path directory, JsonService json, boolean directions)
      throws Exception {
    Files.createDirectories(directory);
    var meshData =
        new LinkedHashMap<String, Object>(
            Map.of(
                "vertices",
                List.of(
                    List.of(0, 0),
                    List.of(1, 0),
                    List.of(0, 1),
                    List.of(10, 10),
                    List.of(11, 10),
                    List.of(10, 11)),
                "triangles",
                List.of(List.of(0, 1, 2), List.of(3, 4, 5)),
                "areasM2",
                List.of(0.5, 0.5)));
    if (directions)
      meshData.put("directionBasis", List.of(List.of(0, -1, 1, 0), List.of(0, -1, 1, 0)));
    byte[] mesh = json.write(meshData).getBytes(java.nio.charset.StandardCharsets.UTF_8);
    Files.write(directory.resolve("mesh.json"), mesh);
    byte[] frame =
        ByteBuffer.allocate(48)
            .order(ByteOrder.LITTLE_ENDIAN)
            .putDouble(0.1)
            .putDouble(0.03)
            .putDouble(0.04)
            .putDouble(0)
            .putDouble(0)
            .putDouble(0)
            .array();
    Files.write(directory.resolve("frame-00000.bin"), frame);
    var catalog = new LinkedHashMap<String, Object>();
    catalog.put("schemaVersion", directions ? 2 : 1);
    if (directions) {
      String method = "SOURCE_MOMENTUM_LOCAL_PROJECTION_JACOBIAN_V1";
      catalog.put("flowDirectionMethod", method);
      catalog.put("directionCodeSha256", "d".repeat(64));
      catalog.put(
          "directionProjection",
          Map.of(
              "method",
              method,
              "coordinateSystem",
              "EPSG:5186",
              "axisOrder",
              "EASTING_NORTHING",
              "matrixOrder",
              List.of("dXdx", "dXdy", "dYdx", "dYdy"),
              "differenceStepM",
              .25,
              "comparisonStepM",
              .5,
              "relativeDifferenceLimit",
              1e-6,
              "maximumRelativeDifference",
              0.,
              "sourceFramesUnchanged",
              true));
    }
    catalog.put("type", "SURFACE_PLAYBACK");
    catalog.put("rankingEligible", false);
    catalog.put("classification", "SYNTHETIC_TRANSFER_TEST_ONLY");
    catalog.put("startUtc", "2022-08-08T09:00:00Z");
    catalog.put("coordinateSystem", "EPSG:5186");
    catalog.put("originProjected", List.of(198128, 551989));
    catalog.put("verticalPlacement", "TERRAIN_DRAPED_SCALAR_NOT_WATER_ELEVATION");
    catalog.put("triangleCount", 2);
    catalog.put("mesh", Map.of("file", "mesh.json", "bytes", mesh.length, "sha256", hash(mesh)));
    catalog.put(
        "frames",
        List.of(
            Map.of(
                "index",
                0,
                "timeSeconds",
                0,
                "storageM3",
                0.05,
                "file",
                "frame-00000.bin",
                "bytes",
                48,
                "sha256",
                hash(frame),
                "sourceSha256",
                hash(frame))));
    catalog.put("surfaceResultSha256", "a".repeat(64));
    catalog.put("velocityDepthThresholdM", 1e-6);
    catalog.put("limitations", List.of("전달·권한 검사 전용 합성 자료"));
    var raw = json.write(catalog).getBytes(java.nio.charset.StandardCharsets.UTF_8);
    Files.write(directory.resolve("catalog.json"), raw);
    return Map.of(
        "schemaVersion", 1, "catalogSha256", hash(raw), "surfaceResultSha256", "a".repeat(64));
  }

  @Test
  void selectiveNativeValuesAndTamperRejection() throws Exception {
    var root = temporary.toRealPath();
    var id = UUID.randomUUID();
    var token = UUID.randomUUID();
    var dir =
        root.resolve("historical")
            .resolve(id.toString())
            .resolve(token.toString())
            .resolve("surface-playback");
    var ref = fixture(dir, json);
    var p =
        new SurfacePublication(
            SurfacePublication.Scope.HISTORICAL,
            id,
            token,
            (String) ref.get("catalogSha256"),
            "a".repeat(64));
    var repository = new SurfacePlaybackRepository(root.toString(), json);
    assertThat(repository.catalogView(p).timesSeconds()).containsExactly(0.0);
    var frame = repository.frame(p, new SurfaceFrameRequest(0, -1, -1, 2, 2));
    assertThat(frame.cells()).hasSize(1);
    assertThat(frame.cells().getFirst().depthM()).isEqualTo(0.1);
    assertThat(frame.cells().getFirst().speedMps()).isCloseTo(0.5, within(1e-15));
    assertThat(frame.cells().getFirst().flowDirection()).isNull();
    assertThat(repository.catalogView(p).flowDirectionMethod()).isNull();
    assertThat(frame.wholeDomainStorageM3()).isEqualTo(0.05);
    assertThat(repository.frame(p, new SurfaceFrameRequest(0, 20, 20, 30, 30)).cells()).isEmpty();
    assertThatThrownBy(() -> repository.frame(p, new SurfaceFrameRequest(0, Double.NaN, 0, 1, 1)))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> repository.frame(p, new SurfaceFrameRequest(1, 0, 0, 1, 1)))
        .isInstanceOf(DomainException.class);
    Files.writeString(dir.resolve("frame-00000.bin"), "changed");
    assertThatThrownBy(() -> repository.frame(p, new SurfaceFrameRequest(0, 0, 0, 1, 1)))
        .isInstanceOf(DomainException.class);
    Files.delete(dir.resolve("frame-00000.bin"));
    Files.createSymbolicLink(dir.resolve("frame-00000.bin"), dir.resolve("mesh.json"));
    assertThatThrownBy(() -> repository.frame(p, new SurfaceFrameRequest(0, 0, 0, 1, 1)))
        .isInstanceOf(DomainException.class);
  }

  @Test
  void projectedDirectionPreservesNativeSpeedAndRejectsInvalidBasis() throws Exception {
    var root = temporary.toRealPath();
    var id = UUID.randomUUID();
    var token = UUID.randomUUID();
    var dir =
        root.resolve("historical")
            .resolve(id.toString())
            .resolve(token.toString())
            .resolve("surface-playback");
    var ref = fixture(dir, json, true);
    var p =
        new SurfacePublication(
            SurfacePublication.Scope.HISTORICAL,
            id,
            token,
            (String) ref.get("catalogSha256"),
            "a".repeat(64));
    var repository = new SurfacePlaybackRepository(root.toString(), json);
    assertThat(repository.catalogView(p).schemaVersion()).isEqualTo(2);
    var frame = repository.frame(p, new SurfaceFrameRequest(0, -1, -1, 20, 20));
    assertThat(frame.cells().getFirst().speedMps()).isCloseTo(.5, within(1e-15));
    assertThat(frame.cells().getFirst().flowDirection()[0]).isCloseTo(-.8, within(1e-15));
    assertThat(frame.cells().getFirst().flowDirection()[1]).isCloseTo(.6, within(1e-15));
    assertThat(frame.cells().get(1).flowDirection()).isNull();
    var mesh =
        (tools.jackson.databind.node.ObjectNode)
            json.tree(Files.readString(dir.resolve("mesh.json")));
    mesh.set("directionBasis", json.tree("[[1,0,0,0],[1,0,0,1]]"));
    var raw = json.write(mesh).getBytes(java.nio.charset.StandardCharsets.UTF_8);
    Files.write(dir.resolve("mesh.json"), raw);
    var catalog =
        (tools.jackson.databind.node.ObjectNode)
            json.tree(Files.readString(dir.resolve("catalog.json")));
    catalog.set(
        "mesh",
        json.tree(
            json.write(Map.of("file", "mesh.json", "bytes", raw.length, "sha256", hash(raw)))));
    var updated = json.write(catalog).getBytes(java.nio.charset.StandardCharsets.UTF_8);
    Files.write(dir.resolve("catalog.json"), updated);
    var invalid =
        new SurfacePublication(
            SurfacePublication.Scope.HISTORICAL, id, token, hash(updated), "a".repeat(64));
    assertThatThrownBy(() -> repository.frame(invalid, new SurfaceFrameRequest(0, -1, -1, 20, 20)))
        .isInstanceOf(DomainException.class);
  }

  @Test
  @EnabledIfEnvironmentVariable(named = "SURFACE_DIRECTION_PLAYBACK", matches = ".+")
  void readsPublicDemExportAndMatchesPythonDirection() throws Exception {
    var source = Path.of(System.getenv("SURFACE_DIRECTION_PLAYBACK")).toRealPath();
    var root = temporary.toRealPath();
    var id = UUID.randomUUID();
    var token = UUID.randomUUID();
    var dir =
        root.resolve("historical")
            .resolve(id.toString())
            .resolve(token.toString())
            .resolve("surface-playback");
    Files.createDirectories(dir);
    try (var files = Files.list(source.resolve("surface-playback"))) {
      for (var path : files.toList()) Files.copy(path, dir.resolve(path.getFileName()));
    }
    var ref = json.tree(Files.readString(source.resolve("publication.json")));
    var p =
        new SurfacePublication(
            SurfacePublication.Scope.HISTORICAL,
            id,
            token,
            ref.path("catalogSha256").asString(),
            ref.path("surfaceResultSha256").asString());
    assertThat(p.resultHash())
        .isEqualTo("7ca65dc891fe888e9311de21d32e1432c8d72181d9356e530bed6cfc0c1cafa8");
    var expected = json.tree(Files.readString(source.resolve("preview.json"))).path("frame");
    var repository = new SurfacePlaybackRepository(root.toString(), json);
    var catalog = repository.catalogView(p);
    assertThat(catalog.triangleCount()).isEqualTo(288);
    assertThat(catalog.timesSeconds()).hasSize(31);
    var actual =
        repository.frame(
            p,
            new SurfaceFrameRequest(expected.path("index").asInt(), -60000, -60000, 60000, 60000));
    assertThat(actual.cells()).hasSize(288);
    for (int i = 0; i < actual.cells().size(); i++) {
      var a = actual.cells().get(i);
      var e = expected.path("cells").get(i);
      assertThat(a.depthM()).isEqualTo(e.path("depthM").doubleValue());
      assertThat(a.speedMps()).isCloseTo(e.path("speedMps").doubleValue(), within(1e-12));
      if (e.path("flowDirection").isNull()) assertThat(a.flowDirection()).isNull();
      else
        for (int k = 0; k < 2; k++)
          assertThat(a.flowDirection()[k])
              .isCloseTo(e.path("flowDirection").get(k).doubleValue(), within(1e-12));
    }
  }

  @Test
  void checksOwnerBeforeReadAndAfterPermissionChanges() {
    var historical = mock(HistoricalService.class);
    var shared = mock(SharedResearchService.class);
    var repository = mock(SurfacePlaybackRepository.class);
    var service =
        new SurfacePlaybackService(
            historical,
            shared,
            repository,
            json,
            mock(io.waterleague.installation.repository.InstallationRepository.class),
            mock(io.waterleague.physics.repository.PhysicsRepository.class));
    var owner = UUID.randomUUID();
    var other = UUID.randomUUID();
    var id = UUID.randomUUID();
    var job =
        new HistoricalExperiment(
            id,
            owner,
            "11200",
            "a".repeat(64),
            "b".repeat(64),
            "[]",
            "SUCCEEDED",
            UUID.randomUUID(),
            Instant.now(),
            json.write(
                Map.of(
                    "surfacePlayback",
                    Map.of(
                        "schemaVersion",
                        1,
                        "catalogSha256",
                        "c".repeat(64),
                        "surfaceResultSha256",
                        "d".repeat(64)))),
            null);
    when(historical.require(other, id))
        .thenThrow(new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    assertThatThrownBy(
            () -> service.read(other, SurfacePlaybackService.Access.HISTORICAL_OWNER, id, null))
        .isInstanceOf(DomainException.class);
    verifyNoInteractions(repository);
    when(historical.require(owner, id))
        .thenReturn(job)
        .thenThrow(new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    assertThatThrownBy(
            () -> service.read(owner, SurfacePlaybackService.Access.HISTORICAL_OWNER, id, null))
        .isInstanceOf(DomainException.class);
    verify(repository).catalogView(any());
  }
}
