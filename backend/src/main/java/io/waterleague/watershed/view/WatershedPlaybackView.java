package io.waterleague.watershed.view;

import java.util.List;
import java.util.UUID;

public final class WatershedPlaybackView {
  private WatershedPlaybackView() {}

  public record Node(
      String id, int type, double headM, double depthM, double storageM3, double overflowM3s) {}

  public record Link(String id, double flowM3s, double depthM, double setting) {}

  public record State(double timeSeconds, List<Node> nodes, List<Link> links) {}

  public record Source(
      String id, String framesSha256, String resultSha256, String numericalStatus) {}

  public record Catalog(
      UUID jobId,
      String inputHash,
      String method,
      double depthScaleM,
      List<Double> timesSeconds,
      List<Source> sources) {}

  public record Case(
      String id,
      String framesSha256,
      String resultSha256,
      String numericalStatus,
      double ageSeconds,
      State state) {}

  public record Frame(
      UUID jobId, String inputHash, double requestedTimeSeconds, List<Case> cases) {}
}
