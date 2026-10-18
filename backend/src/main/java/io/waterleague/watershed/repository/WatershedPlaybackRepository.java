package io.waterleague.watershed.repository;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.watershed.entity.WatershedExperiment;
import io.waterleague.watershed.exception.WatershedPlaybackException;
import io.waterleague.watershed.view.WatershedPlaybackView.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;

@Repository
public class WatershedPlaybackRepository {
  private final Path root;
  private final JsonService json;

  private record Run(Source source, List<State> states) {}

  private final Map<String, List<State>> cache = new LinkedHashMap<>(8, .75f, true);

  public WatershedPlaybackRepository(
      @Value("${waterleague.artifacts}") String root, JsonService json) {
    this.root = Path.of(root).toAbsolutePath().normalize();
    this.json = json;
  }

  private void require(boolean condition) {
    if (!condition) throw new WatershedPlaybackException();
  }

  private byte[] read(Path path, String hash, int max) throws Exception {
    require(
        hash.matches("[a-f0-9]{64}")
            && Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
            && path.toRealPath().equals(path)
            && Files.size(path) <= max);
    try (var stream = Files.newInputStream(path, LinkOption.NOFOLLOW_LINKS)) {
      var bytes = stream.readNBytes(max + 1);
      require(
          bytes.length <= max
              && HexFormat.of()
                  .formatHex(MessageDigest.getInstance("SHA-256").digest(bytes))
                  .equals(hash));
      return bytes;
    }
  }

  private JsonNode tree(byte[] bytes) {
    return json.tree(new String(bytes, StandardCharsets.UTF_8));
  }

  private double number(JsonNode value) {
    require(value.isNumber() && Double.isFinite(value.doubleValue()));
    return value.doubleValue();
  }

  private State state(JsonNode row) {
    double at = number(row.path("totals").path("timeSeconds"));
    require(at >= 0 && at <= 32 * 86400);
    var nodes = row.path("nodes");
    var links = row.path("links");
    require(
        nodes.isObject()
            && nodes.size() > 0
            && nodes.size() <= 512
            && links.isObject()
            && links.size() <= 1024);
    var nodeRows = new ArrayList<Node>();
    for (var id : nodes.propertyNames()) {
      require(!id.isBlank() && id.length() <= 127);
      var n = nodes.path(id);
      require(
          n.path("type").isIntegralNumber()
              && n.path("type").asInt() >= 0
              && n.path("type").asInt() <= 4);
      nodeRows.add(
          new Node(
              id,
              n.path("type").asInt(),
              number(n.path("headM")),
              number(n.path("depthM")),
              number(n.path("storageM3")),
              number(n.path("overflowM3s"))));
    }
    var linkRows = new ArrayList<Link>();
    for (var id : links.propertyNames()) {
      require(!id.isBlank() && id.length() <= 127);
      var l = links.path(id);
      linkRows.add(
          new Link(
              id, number(l.path("flowM3s")), number(l.path("depthM")), number(l.path("setting"))));
    }
    nodeRows.sort(Comparator.comparing(Node::id));
    linkRows.sort(Comparator.comparing(Link::id));
    return new State(at, List.copyOf(nodeRows), List.copyOf(linkRows));
  }

  private List<Run> load(WatershedExperiment job) {
    if (!job.state().equals("SUCCEEDED") || job.leaseToken() == null || job.result() == null)
      throw new DomainException(ErrorCode.CONFLICT);
    try {
      var result = json.tree(job.result());
      require(
          result.path("inputHash").asString().equals(job.inputHash())
              && result.path("catalogHash").asString().equals(job.modelHash()));
      var files = result.path("artifactFiles");
      var directory =
          root.resolve("watersheds")
              .resolve(job.id().toString())
              .resolve(job.leaseToken().toString());
      var runs = new ArrayList<Run>();
      for (var id : List.of("baseline", "strategy")) {
        String framesHash = files.path(id + "/network-frames.jsonl").asString();
        String resultHash = files.path(id + "/network-result.json").asString();
        byte[] raw =
            read(directory.resolve(id + "/network-frames.jsonl"), framesHash, 32 * 1024 * 1024);
        var detail =
            tree(read(directory.resolve(id + "/network-result.json"), resultHash, 4 * 1024 * 1024));
        String status = detail.path("numericalStatus").asString();
        require(
            Set.of("PASSED", "FAILED").contains(status)
                && detail.path("complete").isBoolean()
                && detail.path("complete").asBoolean());
        var cases = result.path("cases");
        require(cases.isArray() && cases.size() == 2);
        var bound = new ArrayList<JsonNode>();
        for (var c : cases) if (c.path("id").asString().equals(id)) bound.add(c);
        require(
            bound.size() == 1
                && bound.getFirst().path("inputSha256").asString().matches("[a-f0-9]{64}")
                && bound
                    .getFirst()
                    .path("inputSha256")
                    .asString()
                    .equals(files.path(id + "/network.inp").asString())
                && bound
                    .getFirst()
                    .path("inputSha256")
                    .asString()
                    .equals(detail.path("files").path("network.inp").asString())
                && framesHash.equals(detail.path("files").path("network-frames.jsonl").asString()));
        String caseStatus = bound.getFirst().path("numericalStatus").asString();
        require(
            Set.of("PASSED", "FAILED").contains(caseStatus)
                && (!status.equals("FAILED") || caseStatus.equals("FAILED")));
        String key = framesHash + ":" + resultHash;
        List<State> states;
        synchronized (cache) {
          states = cache.get(key);
        }
        if (states == null) {
          var values = new ArrayList<State>();
          values.add(state(detail.path("initial")));
          require(values.getFirst().timeSeconds() == 0);
          var nodeIds = values.getFirst().nodes().stream().map(Node::id).toList();
          var linkIds = values.getFirst().links().stream().map(Link::id).toList();
          try (var lines = new String(raw, StandardCharsets.UTF_8).lines()) {
            var iterator = lines.iterator();
            while (iterator.hasNext()) {
              String line = iterator.next();
              require(values.size() < 10000 && line.length() <= 512 * 1024 && !line.isBlank());
              State value = state(json.tree(line));
              require((long) (values.size() + 1) * (nodeIds.size() + linkIds.size()) <= 500000);
              require(
                  value.timeSeconds() > values.getLast().timeSeconds()
                      && value.nodes().stream().map(Node::id).toList().equals(nodeIds)
                      && value.links().stream().map(Link::id).toList().equals(linkIds));
              values.add(value);
            }
          }
          require(values.size() >= 2 && values.getLast().equals(state(detail.path("final"))));
          states = List.copyOf(values);
          synchronized (cache) {
            cache.put(key, states);
            while (cache.size() > 4) cache.remove(cache.keySet().iterator().next());
          }
        }
        runs.add(new Run(new Source(id, framesHash, resultHash, caseStatus), states));
      }
      return runs;
    } catch (DomainException e) {
      throw e;
    } catch (Exception e) {
      throw new WatershedPlaybackException();
    }
  }

  private double end(List<Run> runs) {
    return runs.stream().mapToDouble(r -> r.states().getLast().timeSeconds()).min().orElseThrow();
  }

  public Catalog catalog(WatershedExperiment job) {
    var runs = load(job);
    double end = end(runs);
    // 같은 요청 시각을 공유하되 원 내부 단계 기록은 보간하거나 이동하지 않는다.
    var times = new TreeSet<Double>();
    for (var r : runs)
      for (var state : r.states()) if (state.timeSeconds() <= end) times.add(state.timeSeconds());
    double scale =
        runs.stream()
            .flatMap(r -> r.states().stream())
            .flatMap(s -> s.nodes().stream())
            .mapToDouble(Node::depthM)
            .max()
            .orElse(0);
    return new Catalog(
        job.id(),
        job.inputHash(),
        "PREVIOUS_RECORDED_STATE_NO_INTERPOLATION",
        Math.max(0, scale),
        List.copyOf(times),
        runs.stream().map(Run::source).toList());
  }

  public Frame frame(WatershedExperiment job, double seconds) {
    if (!Double.isFinite(seconds) || seconds < 0)
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    var runs = load(job);
    if (seconds > end(runs)) throw new DomainException(ErrorCode.REQUEST_INVALID);
    var rows = new ArrayList<Case>();
    for (var run : runs) {
      int lo = 0, hi = run.states().size();
      while (lo + 1 < hi) {
        int mid = (lo + hi) / 2;
        if (run.states().get(mid).timeSeconds() <= seconds) lo = mid;
        else hi = mid;
      }
      State value = run.states().get(lo);
      Source source = run.source();
      rows.add(
          new Case(
              source.id(),
              source.framesSha256(),
              source.resultSha256(),
              source.numericalStatus(),
              seconds - value.timeSeconds(),
              value));
    }
    return new Frame(job.id(), job.inputHash(), seconds, rows);
  }
}
