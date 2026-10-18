package io.waterleague;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import io.waterleague.account.entity.Account;
import io.waterleague.account.service.AccountService;
import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.watershed.entity.WatershedExperiment;
import io.waterleague.watershed.repository.WatershedPlaybackRepository;
import io.waterleague.watershed.service.*;
import io.waterleague.watershed.view.WatershedPlaybackView;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.ObjectMapper;

class WatershedPlaybackTests {
  @TempDir Path root;
  final JsonService json = new JsonService(new ObjectMapper());

  @BeforeEach
  void canonicalTemporaryPath() throws Exception {
    root = root.toRealPath();
  }

  String hash(byte[] raw) throws Exception {
    return HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(raw));
  }

  Map<String, Object> state(double time, double flow) {
    return Map.of(
        "totals",
        Map.of("timeSeconds", time),
        "nodes",
        Map.of(
            "J1",
            Map.of("type", 0, "headM", 12., "depthM", 2., "storageM3", 1., "overflowM3s", 0.)),
        "links",
        Map.of("C1", Map.of("flowM3s", flow, "depthM", .2, "setting", 1.)));
  }

  Path directory(WatershedExperiment job) {
    return root.resolve("watersheds")
        .resolve(job.id().toString())
        .resolve(job.leaseToken().toString());
  }

  WatershedExperiment fixture() throws Exception {
    UUID id = UUID.randomUUID(), token = UUID.randomUUID();
    Path target = root.resolve("watersheds").resolve(id.toString()).resolve(token.toString());
    var files = new TreeMap<String, String>();
    var cases = new ArrayList<Object>();
    String input = "a".repeat(64);
    for (String name : List.of("baseline", "strategy")) {
      Path d = target.resolve(name);
      Files.createDirectories(d);
      var initial = state(0, 0);
      var last = state(10, 3);
      byte[] frames =
          (json.write(state(name.equals("baseline") ? 5 : 6, -2)) + "\n" + json.write(last) + "\n")
              .getBytes(java.nio.charset.StandardCharsets.UTF_8);
      Files.write(d.resolve("network-frames.jsonl"), frames);
      String frameHash = hash(frames);
      String status = name.equals("strategy") ? "FAILED" : "PASSED";
      byte[] result =
          json.write(
                  Map.of(
                      "initial",
                      initial,
                      "final",
                      last,
                      "complete",
                      true,
                      "numericalStatus",
                      status,
                      "files",
                      Map.of("network-frames.jsonl", frameHash, "network.inp", input)))
              .getBytes(java.nio.charset.StandardCharsets.UTF_8);
      Files.write(d.resolve("network-result.json"), result);
      files.put(name + "/network-frames.jsonl", frameHash);
      files.put(name + "/network-result.json", hash(result));
      files.put(name + "/network.inp", input);
      cases.add(Map.of("id", name, "inputSha256", input, "numericalStatus", status));
    }
    return new WatershedExperiment(
        id,
        UUID.randomUUID(),
        "b".repeat(64),
        "c".repeat(64),
        "{}",
        "SUCCEEDED",
        token,
        Instant.now(),
        json.write(
            Map.of(
                "catalogHash",
                "b".repeat(64),
                "inputHash",
                "c".repeat(64),
                "artifactFiles",
                files,
                "cases",
                cases)));
  }

  @Test
  void keepsRecordedClocksAndSignedFlowWithoutInterpolationOrExtrapolation() throws Exception {
    var job = fixture();
    var repository = new WatershedPlaybackRepository(root.toString(), json);
    var catalog = repository.catalog(job);
    assertThat(catalog.timesSeconds()).containsExactly(0., 5., 6., 10.);
    var frame = repository.frame(job, 5.5);
    assertThat(frame.cases().getFirst().state().timeSeconds()).isEqualTo(5);
    assertThat(frame.cases().getFirst().ageSeconds()).isEqualTo(.5);
    assertThat(frame.cases().getFirst().state().links().getFirst().flowM3s()).isEqualTo(-2);
    assertThat(frame.cases().getLast().state().timeSeconds()).isZero();
    assertThat(frame.cases().getLast().numericalStatus()).isEqualTo("FAILED");
    assertThat(repository.frame(job, 10).cases().getFirst().ageSeconds()).isZero();
    for (double time : new double[] {-1, 10.01, Double.NaN, Double.POSITIVE_INFINITY})
      assertThatThrownBy(() -> repository.frame(job, time)).isInstanceOf(DomainException.class);
  }

  @Test
  void rejectsChangedSourceEvenAfterCacheAndSymlinks() throws Exception {
    var job = fixture();
    var repository = new WatershedPlaybackRepository(root.toString(), json);
    repository.catalog(job);
    Path file = directory(job).resolve("baseline/network-frames.jsonl");
    byte[] original = Files.readAllBytes(file);
    Files.writeString(file, "{}\n");
    assertThatThrownBy(() -> repository.frame(job, 5)).isInstanceOf(DomainException.class);
    Files.write(file, original);
    Path target = root.resolve("original-frames.jsonl");
    Files.move(file, target);
    Files.createSymbolicLink(file, target);
    assertThatThrownBy(() -> repository.catalog(job)).isInstanceOf(DomainException.class);
  }

  @Test
  void preservesDesignFailureEvenWhenNetworkRoutingPassed() throws Exception {
    var job = fixture();
    Path file = directory(job).resolve("strategy/network-result.json");
    byte[] before = Files.readAllBytes(file);
    var detail = (tools.jackson.databind.node.ObjectNode) json.tree(Files.readString(file));
    detail.put("numericalStatus", "PASSED");
    byte[] after = json.write(detail).getBytes(java.nio.charset.StandardCharsets.UTF_8);
    Files.write(file, after);
    var changed =
        new WatershedExperiment(
            job.id(),
            job.ownerId(),
            job.modelHash(),
            job.inputHash(),
            job.placements(),
            job.state(),
            job.leaseToken(),
            job.createdAt(),
            job.result().replace(hash(before), hash(after)));
    var catalog = new WatershedPlaybackRepository(root.toString(), json).catalog(changed);
    assertThat(catalog.sources().getLast().numericalStatus()).isEqualTo("FAILED");
  }

  @Test
  void checksOwnerBeforeReadAndAccountAfterRead() throws Exception {
    var job = fixture();
    var accounts = mock(AccountService.class);
    var jobs = mock(WatershedService.class);
    var repository = mock(WatershedPlaybackRepository.class);
    var account = mock(Account.class);
    when(account.id()).thenReturn(job.ownerId());
    when(accounts.current("member")).thenReturn(account);
    when(jobs.require(job.ownerId(), job.id()))
        .thenThrow(new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    var service = new WatershedPlaybackService(accounts, jobs, repository);
    assertThatThrownBy(() -> service.catalog("member", job.id()))
        .isInstanceOf(DomainException.class);
    verifyNoInteractions(repository);
    reset(jobs, accounts);
    when(jobs.require(job.ownerId(), job.id())).thenReturn(job);
    when(accounts.current("member"))
        .thenReturn(account)
        .thenThrow(new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    assertThatThrownBy(() -> service.frame("member", job.id(), 5))
        .isInstanceOf(DomainException.class);
    verify(repository).frame(job, 5);
  }

  @Test
  @EnabledIfEnvironmentVariable(named = "WATERSHED_PLAYBACK_SOURCE", matches = ".+")
  void readsPublicNativeFramesAndExportsSelectedDisplayEvidence() throws Exception {
    Path source = Path.of(System.getenv("WATERSHED_PLAYBACK_SOURCE"));
    var result = json.tree(Files.readString(source.resolve("result.json")));
    var job =
        new WatershedExperiment(
            UUID.fromString("00000000-0000-4000-8000-000000000001"),
            UUID.randomUUID(),
            result.path("catalogHash").asString(),
            result.path("inputHash").asString(),
            "{}",
            "SUCCEEDED",
            UUID.randomUUID(),
            Instant.now(),
            json.write(result));
    for (var name : List.of("baseline", "strategy")) {
      Path target = directory(job).resolve(name);
      Files.createDirectories(target);
      for (var file : List.of("network-frames.jsonl", "network-result.json"))
        Files.copy(source.resolve(name).resolve(file), target.resolve(file));
    }
    var repository = new WatershedPlaybackRepository(root.toString(), json);
    var catalog = repository.catalog(job);
    assertThat(catalog.timesSeconds().size()).isGreaterThan(289);
    assertThat(catalog.timesSeconds().getLast()).isEqualTo(86339);
    var selected = new TreeSet<Double>();
    for (int i :
        new int[] {
          0,
          catalog.timesSeconds().size() / 4,
          catalog.timesSeconds().size() / 2,
          catalog.timesSeconds().size() * 3 / 4,
          catalog.timesSeconds().size() - 1
        }) selected.add(catalog.timesSeconds().get(i));
    var frames = new ArrayList<WatershedPlaybackView.Frame>();
    for (double at : selected) {
      var frame = repository.frame(job, at);
      frames.add(frame);
      for (var c : frame.cases()) {
        var original =
            json.tree(Files.readString(source.resolve(c.id() + "/network-result.json")))
                .path("initial");
        for (var line : Files.readAllLines(source.resolve(c.id() + "/network-frames.jsonl"))) {
          var candidate = json.tree(line);
          if (candidate.path("totals").path("timeSeconds").doubleValue() <= at)
            original = candidate;
          else break;
        }
        assertThat(c.state().timeSeconds())
            .isEqualTo(original.path("totals").path("timeSeconds").doubleValue());
        for (var n : c.state().nodes())
          assertThat(n.depthM())
              .isEqualTo(original.path("nodes").path(n.id()).path("depthM").doubleValue());
        for (var l : c.state().links())
          assertThat(l.flowM3s())
              .isEqualTo(original.path("links").path(l.id()).path("flowM3s").doubleValue());
      }
    }
    String output = System.getenv("WATERSHED_PLAYBACK_QA");
    if (output != null) {
      var subset =
          new WatershedPlaybackView.Catalog(
              catalog.jobId(),
              catalog.inputHash(),
              catalog.method(),
              catalog.depthScaleM(),
              List.copyOf(selected),
              catalog.sources());
      Files.writeString(
          Path.of(output),
          json.write(
              Map.of(
                  "catalog",
                  subset,
                  "frames",
                  frames,
                  "layout",
                  result.path("networkLayout").path("layout"),
                  "scope",
                  "PUBLIC_NETWORK_SELECTED_RECORDED_FRAMES_ONLY")));
    }
  }
}
