package io.waterleague.surface.repository;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.surface.dto.SurfaceFrameRequest;
import io.waterleague.surface.entity.SurfacePublication;
import io.waterleague.surface.exception.SurfaceResultException;
import io.waterleague.surface.view.SurfaceView;
import java.nio.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;

@Repository
public class SurfacePlaybackRepository {
  private static final String DIRECTION_METHOD = "SOURCE_MOMENTUM_LOCAL_PROJECTION_JACOBIAN_V1";
  private final Path root;
  private final JsonService json;

  public SurfacePlaybackRepository(
      @Value("${waterleague.artifacts}") String path, JsonService json) {
    root = Path.of(path).toAbsolutePath().normalize();
    this.json = json;
  }

  private void require(boolean condition) {
    if (!condition) throw new SurfaceResultException();
  }

  private Path directory(SurfacePublication p) {
    return root.resolve(p.scope().directory)
        .resolve(p.jobId().toString())
        .resolve(p.token().toString())
        .resolve("surface-playback");
  }

  private byte[] read(Path path, String hash, int max) {
    try {
      require(
          hash != null
              && hash.matches("[a-f0-9]{64}")
              && Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
              && path.toRealPath().equals(path)
              && Files.size(path) <= max);
      try (var in = Files.newInputStream(path, LinkOption.NOFOLLOW_LINKS)) {
        var bytes = in.readNBytes(max + 1);
        require(
            bytes.length <= max
                && HexFormat.of()
                    .formatHex(MessageDigest.getInstance("SHA-256").digest(bytes))
                    .equals(hash));
        return bytes;
      }
    } catch (SurfaceResultException e) {
      throw e;
    } catch (Exception e) {
      throw new SurfaceResultException();
    }
  }

  private JsonNode tree(byte[] bytes) {
    try {
      return json.tree(new String(bytes, StandardCharsets.UTF_8));
    } catch (Exception e) {
      throw new SurfaceResultException();
    }
  }

  private double number(JsonNode n) {
    require(n.isNumber() && Double.isFinite(n.doubleValue()));
    return n.doubleValue();
  }

  private int integer(JsonNode n, int min, int max) {
    require(
        n.isIntegralNumber() && n.canConvertToInt() && n.intValue() >= min && n.intValue() <= max);
    return n.intValue();
  }

  private JsonNode catalog(SurfacePublication p) {
    var c = tree(read(directory(p).resolve("catalog.json"), p.catalogHash(), 8 * 1024 * 1024));
    int version = integer(c.path("schemaVersion"), 1, 2);
    require(
        c.path("type").asString().equals("SURFACE_PLAYBACK")
            && c.path("rankingEligible").isBoolean()
            && !c.path("rankingEligible").asBoolean()
            && c.path("coordinateSystem").asString().equals("EPSG:5186")
            && c.path("verticalPlacement")
                .asString()
                .equals("TERRAIN_DRAPED_SCALAR_NOT_WATER_ELEVATION")
            && p.resultHash().matches("[a-f0-9]{64}")
            && c.path("surfaceResultSha256").asString().equals(p.resultHash())
            && c.path("originProjected").isArray()
            && c.path("originProjected").size() == 2
            && c.path("classification").isString()
            && c.path("classification").asString().length() <= 120
            && number(c.path("velocityDepthThresholdM")) == 1e-6);
    if (version == 2) {
      var projection = c.path("directionProjection");
      require(
          c.path("flowDirectionMethod").asString().equals(DIRECTION_METHOD)
              && projection.path("method").asString().equals(DIRECTION_METHOD)
              && projection.path("coordinateSystem").asString().equals("EPSG:5186")
              && projection.path("axisOrder").asString().equals("EASTING_NORTHING")
              && projection.path("matrixOrder").isArray()
              && projection.path("matrixOrder").size() == 4
              && number(projection.path("differenceStepM")) == .25
              && number(projection.path("comparisonStepM")) == .5
              && number(projection.path("relativeDifferenceLimit")) == 1e-6
              && projection.path("sourceFramesUnchanged").isBoolean()
              && projection.path("sourceFramesUnchanged").asBoolean()
              && c.path("directionCodeSha256").asString().matches("[a-f0-9]{64}"));
      var order = List.of("dXdx", "dXdy", "dYdx", "dYdy");
      for (int i = 0; i < 4; i++)
        require(projection.path("matrixOrder").get(i).asString().equals(order.get(i)));
      double error = number(projection.path("maximumRelativeDifference"));
      require(error >= 0 && error <= 1e-6);
    } else require(!c.has("flowDirectionMethod") && !c.has("directionProjection"));
    number(c.path("originProjected").get(0));
    number(c.path("originProjected").get(1));
    try {
      Instant.parse(c.path("startUtc").asString());
    } catch (Exception e) {
      throw new SurfaceResultException();
    }
    int count = integer(c.path("triangleCount"), 1, 200000);
    var frames = c.path("frames");
    require(frames.isArray() && frames.size() >= 1 && frames.size() <= 10000);
    double last = -1;
    for (int i = 0; i < frames.size(); i++) {
      var f = frames.get(i);
      double at = number(f.path("timeSeconds"));
      require(
          integer(f.path("index"), 0, 9999) == i
              && (i == 0 ? at == 0 : at > last)
              && f.path("file").asString().equals("frame-%05d.bin".formatted(i))
              && integer(f.path("bytes"), 1, 32 * 1024 * 1024) == count * 24
              && f.path("sha256").asString().matches("[a-f0-9]{64}")
              && f.path("sha256").asString().equals(f.path("sourceSha256").asString()));
      number(f.path("storageM3"));
      last = at;
    }
    require(c.path("limitations").isArray() && c.path("limitations").size() <= 50);
    for (var item : c.path("limitations"))
      require(item.isString() && item.asString().length() <= 1000);
    return c;
  }

  public SurfaceView.Catalog catalogView(SurfacePublication p) {
    return io.waterleague.surface.mapper.SurfaceMapper.catalog(p, catalog(p));
  }

  public SurfaceView.Frame frame(SurfacePublication p, SurfaceFrameRequest request) {
    request.validate();
    var c = catalog(p);
    if (request.index() >= c.path("frames").size())
      throw new DomainException(ErrorCode.REQUEST_INVALID);
    var meshRef = c.path("mesh");
    require(meshRef.path("file").asString().equals("mesh.json"));
    int meshSize = integer(meshRef.path("bytes"), 1, 64 * 1024 * 1024);
    var meshRaw =
        read(directory(p).resolve("mesh.json"), meshRef.path("sha256").asString(), meshSize);
    require(meshRaw.length == meshSize);
    var mesh = tree(meshRaw);
    var vertices = mesh.path("vertices");
    var triangles = mesh.path("triangles");
    var areas = mesh.path("areasM2");
    var basis = mesh.path("directionBasis");
    boolean directions = c.path("schemaVersion").asInt() == 2;
    int count = c.path("triangleCount").asInt();
    require(!directions || (basis.isArray() && basis.size() == count));
    require(
        vertices.isArray()
            && vertices.size() >= 3
            && vertices.size() <= 500000
            && triangles.isArray()
            && triangles.size() == count
            && areas.isArray()
            && areas.size() == count);
    var row = c.path("frames").get(request.index());
    var bytes =
        read(
            directory(p).resolve(row.path("file").asString()),
            row.path("sha256").asString(),
            count * 24);
    require(bytes.length == count * 24);
    var buffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN);
    var selected = new ArrayList<SurfaceView.Cell>();
    double storage = 0, compensation = 0;
    for (int i = 0; i < count; i++) {
      double depth = buffer.getDouble(), mx = buffer.getDouble(), my = buffer.getDouble();
      double area = number(areas.get(i));
      require(
          Double.isFinite(depth)
              && depth >= -1e-10
              && Double.isFinite(mx)
              && Double.isFinite(my)
              && area > 0);
      double value = depth * area - compensation, next = storage + value;
      compensation = (next - storage) - value;
      storage = next;
      double[] jacobian = null;
      if (directions) {
        var matrix = basis.get(i);
        require(matrix.isArray() && matrix.size() == 4);
        jacobian = new double[4];
        for (int k = 0; k < 4; k++) {
          jacobian[k] = number(matrix.get(k));
          require(Math.abs(jacobian[k]) <= 1000);
        }
        require(Math.abs(jacobian[0] * jacobian[3] - jacobian[1] * jacobian[2]) > 1e-12);
      }
      var triangle = triangles.get(i);
      require(triangle.isArray() && triangle.size() == 3);
      double[][] xy = new double[3][2];
      double xmin = Double.POSITIVE_INFINITY, ymin = xmin, xmax = -xmin, ymax = -xmin;
      for (int j = 0; j < 3; j++) {
        var point = vertices.get(integer(triangle.get(j), 0, vertices.size() - 1));
        require(point.isArray() && point.size() == 2);
        double x = number(point.get(0)), y = number(point.get(1));
        require(Math.abs(x) <= 60000 && Math.abs(y) <= 60000);
        xy[j] = new double[] {x, y};
        xmin = Math.min(xmin, x);
        xmax = Math.max(xmax, x);
        ymin = Math.min(ymin, y);
        ymax = Math.max(ymax, y);
      }
      if (xmax >= request.minX()
          && xmin <= request.maxX()
          && ymax >= request.minY()
          && ymin <= request.maxY()) {
        if (selected.size() >= 8192) throw new DomainException(ErrorCode.REQUEST_TOO_LARGE);
        double speed = depth > 1e-6 ? Math.hypot(mx / depth, my / depth) : 0;
        require(Double.isFinite(speed));
        double[] direction = null;
        if (jacobian != null && speed > 0) {
          double vx = mx / depth, vy = my / depth;
          double x = jacobian[0] * vx + jacobian[1] * vy, y = jacobian[2] * vx + jacobian[3] * vy;
          double norm = Math.hypot(x, y);
          require(Double.isFinite(norm) && norm > 0);
          direction = new double[] {x / norm, y / norm};
        }
        selected.add(new SurfaceView.Cell(i, xy, depth, speed, direction));
      }
    }
    double recorded = number(row.path("storageM3"));
    require(Math.abs(storage - recorded) <= Math.max(1e-10, Math.abs(recorded) * 1e-12));
    return new SurfaceView.Frame(
        p.catalogHash(),
        row.path("sha256").asString(),
        request.index(),
        number(row.path("timeSeconds")),
        recorded,
        selected);
  }
}
