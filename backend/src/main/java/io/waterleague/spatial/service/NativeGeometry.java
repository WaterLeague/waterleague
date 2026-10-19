package io.waterleague.spatial.service;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.exception.ErrorCode;
import java.util.ArrayList;
import org.locationtech.jts.geom.*;
import tools.jackson.databind.JsonNode;

public final class NativeGeometry {
  private static final GeometryFactory FACTORY = new GeometryFactory(new PrecisionModel(), 5186);

  private NativeGeometry() {}

  public static Geometry polygon(JsonNode value, double expectedArea) {
    try {
      String type = value.path("type").asString();
      JsonNode coordinates = value.path("coordinates");
      var polygons = new ArrayList<Polygon>();
      int[] count = {0};
      if (type.equals("Polygon")) polygons.add(part(coordinates, count));
      else if (type.equals("MultiPolygon") && coordinates.isArray()
          && coordinates.size() > 0 && coordinates.size() <= 1000) {
        for (var part : coordinates) polygons.add(part(part, count));
      } else invalid();
      Geometry result = polygons.size() == 1 ? polygons.getFirst()
          : FACTORY.createMultiPolygon(polygons.toArray(Polygon[]::new));
      if (!result.isValid() || result.isEmpty() || result.getArea() <= 0
          || !Double.isFinite(expectedArea) || expectedArea <= 0
          || Math.abs(result.getArea() - expectedArea) > Math.max(1e-6, expectedArea * 1e-10)) invalid();
      return result;
    } catch (DomainException e) { throw e; }
    catch (Exception e) { throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID); }
  }

  private static Polygon part(JsonNode rings, int[] count) {
    if (!rings.isArray() || rings.isEmpty() || rings.size() > 500) invalid();
    var shell = ring(rings.get(0), count);
    var holes = new LinearRing[rings.size() - 1];
    for (int i = 1; i < rings.size(); i++) holes[i - 1] = ring(rings.get(i), count);
    return FACTORY.createPolygon(shell, holes);
  }

  private static LinearRing ring(JsonNode points, int[] count) {
    if (!points.isArray() || points.size() < 4 || points.size() > 20000) invalid();
    var coordinates = new Coordinate[points.size()];
    for (int i = 0; i < points.size(); i++) {
      var point = points.get(i);
      if (!point.isArray() || point.size() != 2 || ++count[0] > 1_000_000) invalid();
      double[] values = new double[2];
      for (int j = 0; j < 2; j++) {
        if (!point.get(j).isNumber()) invalid();
        values[j] = point.get(j).asDouble();
        if (!Double.isFinite(values[j]) || Math.abs(values[j]) > 10_000_000) invalid();
      }
      coordinates[i] = new Coordinate(values[0], values[1]);
    }
    if (!coordinates[0].equals2D(coordinates[coordinates.length - 1])) invalid();
    return FACTORY.createLinearRing(coordinates);
  }

  public static Geometry box(double minx, double miny, double maxx, double maxy) {
    return FACTORY.toGeometry(new Envelope(minx, maxx, miny, maxy));
  }

  private static void invalid() { throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID); }
}
