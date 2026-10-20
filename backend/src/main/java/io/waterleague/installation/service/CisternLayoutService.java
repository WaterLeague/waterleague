package io.waterleague.installation.service;

import io.waterleague.common.exception.ErrorCode;
import io.waterleague.installation.dto.CisternEquipmentRequest;
import io.waterleague.installation.dto.CisternLayoutRequest;
import io.waterleague.installation.exception.CisternPlanException;
import io.waterleague.installation.view.CisternEquipmentView;
import io.waterleague.installation.view.CisternLayoutView;
import java.awt.geom.*;
import java.util.*;
import tools.jackson.databind.JsonNode;

public final class CisternLayoutService {
  private CisternLayoutService() {}

  public static CisternLayoutView build(
      List<List<List<List<Double>>>> polygons,
      List<Double> origin,
      String sourceHash,
      double areaM2,
      double depthM,
      CisternLayoutRequest request) {
    double width = request.widthM().doubleValue(), wall = request.wallThicknessM().doubleValue();
    double x = origin.get(0) + request.offsetXM().doubleValue(),
        y = origin.get(1) + request.offsetYM().doubleValue();
    double rotation = request.rotationDeg().doubleValue();
    if (!Double.isFinite(areaM2)
        || areaM2 <= 0
        || !Double.isFinite(depthM)
        || depthM <= 0
        || !Double.isFinite(width)
        || width <= 0
        || !Double.isFinite(wall)
        || wall <= 0
        || !Double.isFinite(x)
        || !Double.isFinite(y)
        || !Double.isFinite(rotation)
        || rotation < 0
        || rotation >= 360
        || polygons.isEmpty()
        || polygons.size() > 1000) throw new CisternPlanException(ErrorCode.PLACEMENT_INVALID);
    double length = areaM2 / width, outerWidth = width + 2 * wall, outerLength = length + 2 * wall;
    var rectangle = rectangle(polygons, x, y, outerWidth, outerLength, rotation);
    return new CisternLayoutView(
        "RECTANGULAR_INTERNAL_SECTION_WITH_WALL_V1",
        sourceHash,
        rectangle.center(),
        width,
        length,
        wall,
        outerWidth,
        outerLength,
        depthM,
        rotation,
        rectangle.coordinates(),
        true);
  }

  public static CisternEquipmentView equipment(
      List<List<List<List<Double>>>> polygons,
      List<Double> origin,
      String sourceHash,
      JsonNode specification,
      CisternEquipmentRequest request) {
    var dimensions = specification.path("equipmentDimensionsM");
    double width = dimensions.path("width").asDouble(),
        length = dimensions.path("length").asDouble(),
        height = dimensions.path("height").asDouble();
    double x = origin.get(0) + request.offsetXM().doubleValue(),
        y = origin.get(1) + request.offsetYM().doubleValue(),
        rotation = request.rotationDeg().doubleValue();
    if (!Double.isFinite(height) || height <= 0)
      throw new CisternPlanException(ErrorCode.PLACEMENT_INVALID);
    var rectangle = rectangle(polygons, x, y, width, length, rotation);
    // 외형만 검사하며 장비 공간을 내부 저류 단면으로 바꾸지 않는다.
    return new CisternEquipmentView(
        "PUBLIC_EQUIPMENT_ENVELOPE_V1",
        sourceHash,
        request.specificationId(),
        request.catalogSha256(),
        rectangle.center(),
        width,
        length,
        height,
        rotation,
        rectangle.coordinates(),
        true);
  }

  private record Rectangle(List<Double> center, List<List<Double>> coordinates) {}

  private static Rectangle rectangle(
      List<List<List<List<Double>>>> polygons,
      double x,
      double y,
      double outerWidth,
      double outerLength,
      double rotation) {
    if (!Double.isFinite(x)
        || !Double.isFinite(y)
        || !Double.isFinite(outerWidth)
        || !Double.isFinite(outerLength)
        || outerWidth <= 0
        || outerLength <= 0
        || !Double.isFinite(rotation)
        || rotation < 0
        || rotation >= 360
        || polygons.isEmpty()
        || polygons.size() > 1000) throw new CisternPlanException(ErrorCode.PLACEMENT_INVALID);
    double angle = Math.toRadians(rotation), c = Math.cos(angle), s = Math.sin(angle);
    var points = new ArrayList<List<Double>>();
    var local = new ArrayList<List<Double>>();
    for (int[] signs : new int[][] {{-1, -1}, {1, -1}, {1, 1}, {-1, 1}}) {
      double dx = signs[0] * outerWidth / 2, dy = signs[1] * outerLength / 2;
      double px = c * dx - s * dy, py = s * dx + c * dy;
      local.add(List.of(px, py));
      points.add(List.of(x + px, y + py));
    }
    points.add(points.getFirst());
    Area permitted = new Area();
    int count = 0;
    for (var rings : polygons) {
      if (rings.isEmpty() || rings.size() > 500)
        throw new CisternPlanException(ErrorCode.PLACEMENT_INVALID);
      Area component = null;
      for (var ring : rings) {
        if (ring.size() < 4
            || (count += ring.size()) > 1000000
            || !ring.getFirst().equals(ring.getLast()))
          throw new CisternPlanException(ErrorCode.PLACEMENT_INVALID);
        var relative = ring.stream().map(p -> List.of(p.get(0) - x, p.get(1) - y)).toList();
        var shape = new Area(path(relative));
        if (component == null) component = shape;
        else component.subtract(shape);
      }
      permitted.add(component);
    }
    Area outside = new Area(path(local));
    outside.subtract(permitted);
    // 큰 투영 좌표의 상쇄 오차를 줄여 외곽 전체와 오목한 경계의 교차 면적을 검사한다.
    if (area(outside) > Math.max(1e-8, outerWidth * outerLength * 1e-9))
      throw new CisternPlanException(ErrorCode.PLACEMENT_INVALID);
    return new Rectangle(List.of(x, y), points);
  }

  private static Path2D.Double path(List<List<Double>> ring) {
    Path2D.Double p = new Path2D.Double();
    for (int i = 0; i < ring.size(); i++) {
      var point = ring.get(i);
      if (point.size() != 2 || point.stream().anyMatch(v -> !Double.isFinite(v)))
        throw new CisternPlanException(ErrorCode.PLACEMENT_INVALID);
      if (i == 0) p.moveTo(point.get(0), point.get(1));
      else p.lineTo(point.get(0), point.get(1));
    }
    p.closePath();
    return p;
  }

  private static double area(Area shape) {
    var iterator = shape.getPathIterator(null);
    double[] p = new double[6];
    double sum = 0, x = 0, y = 0, startX = 0, startY = 0;
    while (!iterator.isDone()) {
      int type = iterator.currentSegment(p);
      if (type == PathIterator.SEG_MOVETO) {
        x = startX = p[0];
        y = startY = p[1];
      } else if (type == PathIterator.SEG_LINETO) {
        sum += x * p[1] - p[0] * y;
        x = p[0];
        y = p[1];
      } else if (type == PathIterator.SEG_CLOSE) sum += x * startY - startX * y;
      else throw new CisternPlanException(ErrorCode.PLACEMENT_INVALID);
      iterator.next();
    }
    return Math.abs(sum) / 2;
  }
}
