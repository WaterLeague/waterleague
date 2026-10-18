package io.waterleague.surface.view;

import java.util.List;

public final class SurfaceView {
  private SurfaceView() {}

  public record Catalog(
      int schemaVersion,
      String catalogSha256,
      String surfaceResultSha256,
      String classification,
      String startUtc,
      String coordinateSystem,
      double[] originProjected,
      String verticalPlacement,
      int triangleCount,
      List<Double> timesSeconds,
      List<String> limitations) {}

  public record Cell(int triangleId, double[][] vertices, double depthM, double speedMps) {}

  public record Frame(
      String catalogSha256,
      String sourceSha256,
      int index,
      double timeSeconds,
      double wholeDomainStorageM3,
      List<Cell> cells) {}
}
