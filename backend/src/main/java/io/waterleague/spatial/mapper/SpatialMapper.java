package io.waterleague.spatial.mapper;

import io.waterleague.common.exception.*;
import io.waterleague.spatial.entity.ReferenceBuilding;
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

  public SpatialView map(String raw) {
    try {
      var response = json.readTree(raw).path("response");
      if (!response.path("status").asString().equals("OK")) {
        var code = response.path("error").path("code").asString();
        if (Set.of("INCORRECT_KEY", "INVALID_KEY", "UNAVAILABLE_KEY").contains(code))
          throw new DomainException(ErrorCode.SPATIAL_ACCESS_UNAVAILABLE);
        throw new DomainException(ErrorCode.SPATIAL_UNAVAILABLE);
      }
      var features = response.path("result").path("featureCollection").path("features");
      int count = features.size();
      if (!features.isArray()
          || count < 1
          || count > 1000
          || response.path("record").path("total").asInt(-1) != count
          || response.path("record").path("current").asInt(-1) != count) invalid();
      var result = new ArrayList<ReferenceBuilding>();
      var ids = new HashSet<String>();
      int points = 0;
      for (var feature : features) {
        String id = feature.path("id").asString();
        if (id.isBlank() || id.length() > 100 || !ids.add(id)) invalid();
        var properties = feature.path("properties");
        String name = properties.path("buld_nm").asString("");
        if (name.length() > 200) invalid();
        String floors = properties.path("gro_flo_co").asString("");
        Integer floorCount = null;
        if (floors.matches("[0-9]{1,3}")) {
          int value = Integer.parseInt(floors);
          if (value > 0 && value <= 200) floorCount = value;
        }
        var geometry = feature.path("geometry");
        if (!geometry.path("type").asString().equals("MultiPolygon")) invalid();
        var coordinates = geometry.path("coordinates");
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
          "행정안전부 · 브이월드",
          "LT_C_SPBD",
          "EPSG:4326",
          "https://www.vworld.kr/dev/v4dv_2ddataguide2_s002.do?svcIde=spbd&apiVer=2",
          Instant.now(),
          "DISPLAY_COMPARISON_ONLY",
          false,
          List.of(127.0525, 37.5430, 127.0555, 37.5455),
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
