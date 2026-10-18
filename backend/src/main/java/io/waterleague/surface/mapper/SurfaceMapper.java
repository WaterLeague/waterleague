package io.waterleague.surface.mapper;

import io.waterleague.surface.entity.SurfacePublication;
import io.waterleague.surface.view.SurfaceView;
import java.util.ArrayList;
import tools.jackson.databind.JsonNode;

public final class SurfaceMapper {
  private SurfaceMapper() {}

  public static SurfaceView.Catalog catalog(SurfacePublication publication, JsonNode validated) {
    var times = new ArrayList<Double>();
    var notes = new ArrayList<String>();
    validated.path("frames").forEach(f -> times.add(f.path("timeSeconds").doubleValue()));
    validated.path("limitations").forEach(n -> notes.add(n.asString()));
    return new SurfaceView.Catalog(
        validated.path("schemaVersion").asInt(),
        publication.catalogHash(),
        publication.resultHash(),
        validated.path("classification").asString(),
        validated.path("startUtc").asString(),
        "EPSG:5186",
        new double[] {
          validated.path("originProjected").get(0).doubleValue(),
          validated.path("originProjected").get(1).doubleValue()
        },
        validated.path("verticalPlacement").asString(),
        validated.path("triangleCount").asInt(),
        times,
        notes,
        validated.path("schemaVersion").asInt() == 2
            ? validated.path("flowDirectionMethod").asString()
            : null);
  }
}
