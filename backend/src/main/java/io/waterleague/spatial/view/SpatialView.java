package io.waterleague.spatial.view;

import io.waterleague.spatial.entity.ReferenceBuilding;
import java.time.Instant;
import java.util.List;

public record SpatialView(
    String provider,
    String layer,
    String requestedCrs,
    String sourceUrl,
    Instant retrievedAt,
    int dataYear,
    String snapshotHash,
    String use,
    boolean rawRetained,
    List<Double> bounds,
    List<ReferenceBuilding> buildings) {}
