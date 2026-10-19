package io.waterleague.urban.repository;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.urban.entity.UrbanArea;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;

@Repository
public class UrbanAreaRepository {
  public static final String HASH =
      "a7612f567007844dba44f1334784314748f6dd19819e3c320f9ea63df832ee40";
  private final Map<String, UrbanArea> areas;

  public UrbanAreaRepository(JsonService json) throws IOException {
    try (var in = new ClassPathResource("urban/city-live-areas-v1.json").getInputStream()) {
      String raw = new String(in.readNBytes(600000), StandardCharsets.UTF_8);
      if (!json.hash(raw).equals(HASH)) throw new DomainException(ErrorCode.URBAN_DATA_INVALID);
      var found = new LinkedHashMap<String, UrbanArea>();
      for (var row : json.tree(raw).path("areas")) {
        var value =
            new UrbanArea(
                row.path("id").asString(),
                row.path("name").asString(),
                row.path("areaKm2").asDouble());
        if (found.put(value.id(), value) != null)
          throw new DomainException(ErrorCode.URBAN_DATA_INVALID);
      }
      if (found.size() != 121) throw new DomainException(ErrorCode.URBAN_DATA_INVALID);
      areas = Map.copyOf(found);
    }
  }

  public UrbanArea require(String id) {
    var area = areas.get(id);
    if (area == null) throw new DomainException(ErrorCode.REQUEST_INVALID);
    return area;
  }
}
