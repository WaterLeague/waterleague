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
    Files.createDirectories(directory);
    byte[] mesh =
        json.write(
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
                    List.of(0.5, 0.5)))
            .getBytes(java.nio.charset.StandardCharsets.UTF_8);
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
    catalog.put("schemaVersion", 1);
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
            "2419953",
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
