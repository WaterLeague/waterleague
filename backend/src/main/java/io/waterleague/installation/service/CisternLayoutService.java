package io.waterleague.installation.service;

import io.waterleague.common.exception.ErrorCode;
import io.waterleague.installation.dto.CisternLayoutRequest;
import io.waterleague.installation.exception.CisternPlanException;
import io.waterleague.installation.view.CisternLayoutView;
import java.awt.geom.*;
import java.util.*;

public final class CisternLayoutService {
  private CisternLayoutService() {}

  public static CisternLayoutView build(
      List<List<Double>> ring,
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
        || ring.size() < 4
        || ring.size() > 500) throw new CisternPlanException(ErrorCode.PLACEMENT_INVALID);
    double length = areaM2 / width, outerWidth = width + 2 * wall, outerLength = length + 2 * wall;
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
    var relative = ring.stream().map(p -> List.of(p.get(0) - x, p.get(1) - y)).toList();
    Area outside = new Area(path(local));
    outside.subtract(new Area(path(relative)));
    // 큰 투영 좌표의 상쇄 오차를 줄여 외곽 전체와 오목한 경계의 교차 면적을 검사한다.
    if (area(outside) > Math.max(1e-8, outerWidth * outerLength * 1e-9))
      throw new CisternPlanException(ErrorCode.PLACEMENT_INVALID);
    return new CisternLayoutView(
        "RECTANGULAR_INTERNAL_SECTION_WITH_WALL_V1",
        sourceHash,
        List.of(x, y),
        width,
        length,
        wall,
        outerWidth,
        outerLength,
        depthM,
        rotation,
        points,
        true);
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
