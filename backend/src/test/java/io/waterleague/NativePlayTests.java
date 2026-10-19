package io.waterleague;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import io.waterleague.common.exception.*;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.common.service.JsonService;
import io.waterleague.spatial.controller.NativePlayController;
import io.waterleague.spatial.repository.*;
import io.waterleague.spatial.service.NativeGeometry;
import java.nio.file.*;
import java.nio.file.attribute.FileTime;
import java.sql.SQLException;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.core.io.*;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

class NativePlayTests {
  private static final String FIXTURE_HASH =
      "2d8bf50af215afd6bb0274125d15d92801344160934c48ce2febff4a62f4f44c";
  private final JsonService json = new JsonService(new ObjectMapper());
  @TempDir Path temporary;

  private NativePlayBundle bundle(Path cache) {
    return new NativePlayBundle(json, cache, new ClassPathResource("native-play-fixture/manifest.json"),
        FIXTURE_HASH, name -> new ClassPathResource("native-play-fixture/" + name));
  }

  @Test
  void sharesThePythonFixtureGeometryConditionsAndReadOnlyDatabase() throws Exception {
    var source = bundle(temporary);
    var repository = new NativePlayRepository(source, json);
    assertThat(repository.bounds(2.5, 2.5, 3.5, 3.5, null, null, 100, false)).isEmpty();
    var values = repository.bounds(0, 0, 100, 100, "11110", null, 100, false);
    assertThat(values).hasSize(3);
    var roof = repository.bounds(0, 0, 1, 1, "11110", "ROOF", 100, false).getFirst();
    assertThat(roof.path("areaM2").asDouble()).isEqualTo(96);
    assertThat(roof.path("geometry").path("coordinates")).hasSize(2);
    assertThat(repository.require("11110", roof.path("id").asString())).isEqualTo(roof);
    var crop = repository.bounds(40, 0, 50, 10, "11110", "GROUND", 100, false).getFirst();
    assertThat(crop.path("physicalInputs").path("imperviousPercent").asDouble()).isZero();
    assertThat(crop.path("physicalInputs").path("nPervious").asDouble()).isEqualTo(.06);
    assertThat(repository.bounds(60, 0, 70, 10, null, null, 100, false)).isEmpty();
    assertThat(repository.bounds(60, 0, 70, 10, null, null, 100, true)).hasSize(1);
    try (var connection = repository.connection(); var statement = connection.createStatement()) {
      assertThatThrownBy(() -> statement.executeUpdate("DELETE FROM sites")).isInstanceOf(SQLException.class);
    }
    assertThat(Files.getPosixFilePermissions(source.database()))
        .isEqualTo(java.nio.file.attribute.PosixFilePermissions.fromString("r--------"));
  }

  @Test
  void refusesTruncatedViewsWrongDistrictsAndChangedFiles() throws Exception {
    var source = bundle(temporary);
    var repository = new NativePlayRepository(source, json);
    assertThatThrownBy(() -> repository.bounds(0, 0, 100, 100, null, null, 1, false))
        .isInstanceOfSatisfying(DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.SPATIAL_VIEW_TOO_DENSE));
    assertThatThrownBy(() -> repository.bounds(0, 0, 2001, 1, null, null, 2000, false))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> repository.bounds(0, 0, Double.NaN, 1, null, null, 2000, false))
        .isInstanceOf(DomainException.class);
    var id = repository.bounds(0, 0, 1, 1, "11110", null, 100, false).getFirst().path("id").asString();
    assertThatThrownBy(() -> repository.require("11140", id)).isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> repository.require("11110", "C" + "0".repeat(24)))
        .isInstanceOfSatisfying(DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.RESOURCE_NOT_FOUND));
    Files.setLastModifiedTime(source.database(), FileTime.fromMillis(System.currentTimeMillis() + 10000));
    assertThatThrownBy(() -> repository.require("11110", id)).isInstanceOf(DomainException.class);
  }

  @Test
  void rejectsCorruptArchivesTraversalLinksAndPartialCacheWithoutLeakingPaths() throws Exception {
    var original = json.tree(new String(new ClassPathResource("native-play-fixture/manifest.json")
        .getContentAsByteArray(), java.nio.charset.StandardCharsets.UTF_8));
    var raw = json.write(original);
    var corrupt = new NativePlayBundle(json, temporary.resolve("corrupt"),
        new ByteArrayResource(raw.getBytes(java.nio.charset.StandardCharsets.UTF_8)), json.hash(raw),
        ignored -> new ByteArrayResource(new byte[16]));
    assertThatThrownBy(corrupt::database).isInstanceOf(DomainException.class).hasMessageNotContaining("corrupt");
    try (var files = Files.walk(temporary)) { assertThat(files.noneMatch(p -> p.toString().endsWith(".part"))).isTrue(); }
    ((ObjectNode) original.path("chunks").get(0)).put("file", "../private.gz");
    var invalid = json.write(original);
    assertThatThrownBy(() -> new NativePlayBundle(json, temporary,
        new ByteArrayResource(invalid.getBytes(java.nio.charset.StandardCharsets.UTF_8)), json.hash(invalid),
        ignored -> { throw new AssertionError("거부한 경로 읽기 금지"); }))
        .isInstanceOf(DomainException.class).hasMessageNotContaining("private.gz");
    var source = bundle(temporary.resolve("link-cache"));
    var directory = temporary.resolve("link-cache").resolve(source.manifest().path("databaseSha256").asString());
    Files.createDirectories(directory);
    Files.setPosixFilePermissions(directory, java.nio.file.attribute.PosixFilePermissions.fromString("rwx------"));
    var sentinel = temporary.resolve("sentinel");
    Files.writeString(sentinel, "unchanged");
    Files.createSymbolicLink(directory.resolve("play.sqlite"), sentinel);
    assertThatThrownBy(source::database).isInstanceOf(DomainException.class);
    assertThat(Files.readString(sentinel)).isEqualTo("unchanged");
  }

  @Test
  void concurrentContextsRestoreOnceAndReuseTheSameInode() throws Exception {
    var directory = temporary.resolve(bundle(temporary).manifest().path("databaseSha256").asString());
    Files.createDirectory(directory, java.nio.file.attribute.PosixFilePermissions.asFileAttribute(
        java.nio.file.attribute.PosixFilePermissions.fromString("rwx------")));
    Files.writeString(directory.resolve("play-interrupted.part"), "partial");
    Files.writeString(directory.resolve("notes.txt"), "keep");
    try (var executor = Executors.newFixedThreadPool(2)) {
      var one = executor.submit(() -> bundle(temporary).database());
      var two = executor.submit(() -> bundle(temporary).database());
      var first = one.get(10, TimeUnit.SECONDS);
      assertThat(two.get(10, TimeUnit.SECONDS)).isEqualTo(first);
      var key = Files.readAttributes(first, java.nio.file.attribute.BasicFileAttributes.class).fileKey();
      assertThat(Files.readAttributes(bundle(temporary).database(), java.nio.file.attribute.BasicFileAttributes.class).fileKey())
          .isEqualTo(key);
      assertThat(Files.exists(directory.resolve("play-interrupted.part"))).isFalse();
      assertThat(Files.readString(directory.resolve("notes.txt"))).isEqualTo("keep");
    }
  }

  @Test
  void waitsForTheWorkersPosixLockBeforeRestoringTheSameArtifact() throws Exception {
    var source = bundle(temporary);
    var directory = temporary.resolve(source.manifest().path("databaseSha256").asString());
    Files.createDirectory(directory, java.nio.file.attribute.PosixFilePermissions.asFileAttribute(
        java.nio.file.attribute.PosixFilePermissions.fromString("rwx------")));
    var child = new ProcessBuilder("python3", "-c", """
        import fcntl, sys
        with open(sys.argv[1], 'a') as stream:
            fcntl.lockf(stream, fcntl.LOCK_EX)
            print('LOCKED', flush=True)
            sys.stdin.read(1)
        """, directory.resolve(".lock").toString()).start();
    try (var output = child.outputWriter(); var input = child.inputReader();
        var executor = Executors.newSingleThreadExecutor()) {
      assertThat(input.readLine()).isEqualTo("LOCKED");
      var restoring = executor.submit(source::database);
      assertThatThrownBy(() -> restoring.get(200, TimeUnit.MILLISECONDS)).isInstanceOf(TimeoutException.class);
      output.write("r"); output.flush();
      assertThat(child.waitFor(5, TimeUnit.SECONDS)).isTrue();
      assertThat(child.exitValue()).isZero();
      assertThat(Files.isRegularFile(restoring.get(5, TimeUnit.SECONDS))).isTrue();
    } finally { child.destroyForcibly(); }
  }

  @Test
  void retainsHolesAndMultipartAndRejectsBrokenOrFalseAreaGeometry() {
    var shape = json.tree("""
        {"type":"MultiPolygon","coordinates":[
        [[[0,0],[10,0],[10,10],[0,10],[0,0]],[[2,2],[4,2],[4,4],[2,4],[2,2]]],
        [[[20,0],[21,0],[21,1],[20,1],[20,0]]]]}
        """);
    var geometry = NativeGeometry.polygon(shape, 97);
    assertThat(geometry.getNumGeometries()).isEqualTo(2);
    assertThat(geometry.intersects(NativeGeometry.box(2.5, 2.5, 3.5, 3.5))).isFalse();
    assertThatThrownBy(() -> NativeGeometry.polygon(shape, 101)).isInstanceOf(DomainException.class);
    var invalid = json.write(shape).replace("[0,0]", "[0,0,1]");
    assertThatThrownBy(() -> NativeGeometry.polygon(json.tree(invalid), 97)).isInstanceOf(DomainException.class);
  }

  @Test
  void exposesBoundedVersionedReadApiAndCommonErrors() throws Exception {
    var limits = mock(RateLimitService.class);
    var controller = new NativePlayController(new NativePlayRepository(bundle(temporary), json), limits, json);
    var client = MockMvcBuilders.standaloneSetup(controller).setControllerAdvice(new GlobalExceptionHandler()).build();
    client.perform(get("/api/v1/spatial/play")).andExpect(status().isOk())
        .andExpect(jsonPath("$.coordinateSystem").value("EPSG:5186"))
        .andExpect(jsonPath("$.catalog.referenceScenario.id").value("EPA_REFERENCE_SURFACES_2026_V1"));
    client.perform(get("/api/v1/spatial/play/sites?minx=0&miny=0&maxx=100&maxy=100&limit=1"))
        .andExpect(status().isUnprocessableContent()).andExpect(jsonPath("$.code").value("SPATIAL_VIEW_TOO_DENSE"));
    verify(limits, times(2)).check(anyString(), eq(300), eq(60));
  }
}
