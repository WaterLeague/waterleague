package io.waterleague.surface.entity;

import java.util.UUID;

public record SurfacePublication(
    Scope scope, UUID jobId, UUID token, String catalogHash, String resultHash) {
  public enum Scope {
    PUBLIC_CURRENT("public-surface"),
    HISTORICAL("historical"),
    SHARED("shared-physics");
    public final String directory;

    Scope(String directory) {
      this.directory = directory;
    }
  }
}
