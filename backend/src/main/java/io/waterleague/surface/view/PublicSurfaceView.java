package io.waterleague.surface.view;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public final class PublicSurfaceView {
  private PublicSurfaceView() {}

  public record Run(
      UUID id,
      String basinId,
      String name,
      String inputBundleSha256,
      String numericalPolicySha256,
      Instant lastFrameAt,
      SurfaceView.Catalog catalog) {}

  public record Current(Instant serverNow, List<Run> runs) {}
}
