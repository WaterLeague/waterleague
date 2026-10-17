package io.waterleague.spatial.mapper;

import io.waterleague.common.exception.*;
import io.waterleague.spatial.entity.ReferenceBuilding;
import io.waterleague.spatial.entity.SpatialSnapshot;
import io.waterleague.spatial.view.SpatialView;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Component;
import tools.jackson.databind.*;

@Component
public class SpatialMapper {
  private final ObjectMapper json;

  public SpatialMapper(ObjectMapper json) {
    this.json = json;
  }

  public SpatialView map(SpatialSnapshot snapshot) {
    try {
      var root = json.readTree(snapshot.json());
      if (!snapshot.sha256().matches("[a-f0-9]{64}")
          || root.path("schemaVersion").asInt(-1) != 1
          || !root.path("provider").asString().equals("국토지리정보원")
          || !root.path("layer").asString().equals("N1A_B0010000")
          || !root.path("requestedCrs").asString().equals("EPSG:4326")
          || !root.path("sourceUrl")
              .asString()
              .equals("https://www.data.go.kr/data/15059719/fileData.do")
          || root.path("dataYear").asInt(-1) != 2025
          || !root.path("use").asString().equals("DISPLAY_COMPARISON_ONLY")
          || !root.path("rawRetained").isBoolean()
          || !root.path("rawRetained").asBoolean()) invalid();
      var acquired = Instant.parse(root.path("retrievedAt").asString());
      var bounds = List.of(127.0525, 37.543, 127.0555, 37.5455);
      var extent = root.path("bounds");
      if (!extent.isArray() || extent.size() != 4) invalid();
      for (int i = 0; i < 4; i++) {
        if (!extent.get(i).isNumber() || extent.get(i).asDouble() != bounds.get(i)) invalid();
      }
      var features = root.path("buildings");
      if (!features.isArray() || features.isEmpty() || features.size() > 1000) invalid();
      var result = new ArrayList<ReferenceBuilding>();
      var ids = new HashSet<String>();
      int points = 0;
      for (var feature : features) {
        if (!feature.path("id").isString() || !feature.path("name").isString()) invalid();
        String id = feature.path("id").asString();
        if (!id.matches("[A-Za-z0-9_:-]{1,100}") || !ids.add(id)) invalid();
        String name = feature.path("name").asString();
        if (name.length() > 200 || name.contains("\ufffd")) invalid();
        var floors = feature.path("aboveGroundFloors");
        Integer floorCount = null;
        if (!floors.isNull()) {
          if (!floors.isIntegralNumber() || !floors.canConvertToInt()) invalid();
          int value = floors.asInt();
          if (value < 1 || value > 200) invalid();
          floorCount = value;
        }
        var coordinates = feature.path("polygons");
        if (!coordinates.isArray() || coordinates.isEmpty() || coordinates.size() > 100) invalid();
        var polygons = new ArrayList<List<List<List<Double>>>>();
        for (var polygon : coordinates) {
          if (!polygon.isArray() || polygon.isEmpty() || polygon.size() > 100) invalid();
          var rings = new ArrayList<List<List<Double>>>();
          for (var ring : polygon) {
            if (!ring.isArray() || ring.size() < 4 || ring.size() > 10000) invalid();
            var positions = new ArrayList<List<Double>>();
            for (var point : ring) {
              if (!point.isArray()
                  || point.size() != 2
                  || !point.get(0).isNumber()
                  || !point.get(1).isNumber()) invalid();
              double lon = point.get(0).asDouble(), lat = point.get(1).asDouble();
              if (!Double.isFinite(lon)
                  || !Double.isFinite(lat)
                  || lon < 127.04
                  || lon > 127.07
                  || lat < 37.53
                  || lat > 37.56
                  || ++points > 50000) invalid();
              positions.add(List.of(lon, lat));
            }
            if (!positions.getFirst().equals(positions.getLast())) invalid();
            rings.add(List.copyOf(positions));
          }
          polygons.add(List.copyOf(rings));
        }
        result.add(new ReferenceBuilding(id, name, floorCount, List.copyOf(polygons)));
      }
      return new SpatialView(
          "국토지리정보원",
          "N1A_B0010000",
          "EPSG:4326",
          "https://www.data.go.kr/data/15059719/fileData.do",
          acquired,
          2025,
          snapshot.sha256(),
          "DISPLAY_COMPARISON_ONLY",
          true,
          bounds,
          List.copyOf(result));
    } catch (DomainException e) {
      throw e;
    } catch (Exception e) {
      throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID);
    }
  }

  private void invalid() {
    throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID);
  }
}
