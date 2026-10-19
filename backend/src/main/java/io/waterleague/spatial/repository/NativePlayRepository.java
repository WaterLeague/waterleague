package io.waterleague.spatial.repository;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.exception.ErrorCode;
import io.waterleague.common.service.JsonService;
import io.waterleague.spatial.service.NativeGeometry;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.sql.*;
import java.util.*;
import java.util.concurrent.Semaphore;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;

@Repository
public class NativePlayRepository {
  private final NativePlayBundle bundle;
  private final JsonService json;
  private record State(Path database, BasicFileAttributes identity, JsonNode metadata) {}
  private volatile State state;
  private final Set<String> districts;
  private final Semaphore queries = new Semaphore(4);

  public NativePlayRepository(NativePlayBundle bundle, JsonService json) {
    this.bundle = bundle;
    this.json = json;
    var values = new HashSet<String>();
    bundle.manifest().path("districtKindCounts").properties().forEach(entry -> values.add(entry.getKey().split(":")[0]));
    districts = Set.copyOf(values);
  }

  private synchronized State state() {
    if (state != null) return state;
    try {
      Path database = bundle.database();
      var identity = Files.readAttributes(database, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
      JsonNode metadata;
      try (var connection = open(database); var statement = connection.createStatement()) {
        try (var rows = statement.executeQuery("PRAGMA user_version")) {
          if (!rows.next() || rows.getInt(1) != 1) invalid();
        }
        try (var rows = statement.executeQuery("SELECT value FROM metadata WHERE key='catalog'")) {
          if (!rows.next()) invalid();
          metadata = json.tree(rows.getString(1));
        }
      }
      var manifest = bundle.manifest();
      if (!metadata.path("id").asString().equals(manifest.path("id").asString())
          || !metadata.path("coordinateSystem").asString().equals("EPSG:5186")
          || !metadata.path("referenceScenario").equals(manifest.path("referenceScenario"))
          || !metadata.path("sourceSitesSha256").asString().equals(manifest.path("sourceSitesSha256").asString())
          || !metadata.path("sourceObjectsSha256").asString().equals(manifest.path("sourceObjectsSha256").asString())
          || !metadata.path("policy").path("externalInflowConnected").isBoolean()
          || metadata.path("policy").path("externalInflowConnected").asBoolean()) invalid();
      state = new State(database, identity, metadata);
      return state;
    } catch (Exception e) { throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID); }
  }

  public Connection connection() throws Exception {
    var value = state();
    var database = value.database();
    var identity = value.identity();
    var current = Files.readAttributes(database, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
    if (current.isSymbolicLink() || !current.isRegularFile() || current.size() != identity.size()
        || !Objects.equals(current.fileKey(), identity.fileKey())
        || !current.lastModifiedTime().equals(identity.lastModifiedTime())) invalid();
    return open(database);
  }

  private static Connection open(Path database) throws Exception {
    var connection = DriverManager.getConnection("jdbc:sqlite:" + database.toUri().toASCIIString() + "?mode=ro&immutable=1");
    try (var statement = connection.createStatement()) {
      statement.execute("PRAGMA trusted_schema=OFF");
      statement.execute("PRAGMA query_only=ON");
      statement.execute("PRAGMA cache_size=-8192");
    } catch (Exception e) { connection.close(); throw e; }
    return connection;
  }

  public JsonNode metadata() { return state().metadata().deepCopy(); }
  public JsonNode envelope() { return bundle.manifest(); }
  public String sha256() { return bundle.manifest().path("databaseSha256").asString(); }

  public JsonNode require(String district, String candidate) {
    district(district);
    if (candidate == null || !candidate.matches("C[a-f0-9]{24}")) requestInvalid();
    try (var connection = connection(); var query = connection.prepareStatement(
        "SELECT body FROM sites WHERE district_id=? AND id=?")) {
      query.setString(1, district);
      query.setString(2, candidate);
      try (var rows = query.executeQuery()) {
        if (!rows.next()) throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
        return json.tree(rows.getString(1));
      }
    } catch (DomainException e) { throw e; }
    catch (Exception e) { throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID); }
  }

  public JsonNode building(String district, String objectId) {
    district(district);
    if (objectId == null || !objectId.matches("ngii:N1A_B0010000:[a-f0-9]{64}")) requestInvalid();
    try (var connection = connection(); var query = connection.prepareStatement(
        "SELECT body FROM sites WHERE district_id=? AND object_id=? AND kind='ROOF' AND allowed_mask<>0")) {
      query.setString(1, district); query.setString(2, objectId);
      try (var rows = query.executeQuery()) {
        if (!rows.next()) throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
        return json.tree(rows.getString(1));
      }
    } catch (DomainException e) { throw e; }
    catch (Exception e) { throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID); }
  }

  public JsonNode atPoint(double x, double y, String kind) {
    var point = NativeGeometry.box(x, y, x, y);
    return bounds(x - 1e-7, y - 1e-7, x + 1e-7, y + 1e-7, null, kind, 2000, false)
        .stream().filter(cell -> NativeGeometry.polygon(cell.path("geometry"), cell.path("areaM2").asDouble()).covers(point))
        .min(Comparator.comparing(cell -> cell.path("id").asString()))
        .orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
  }

  public record Page(List<JsonNode> cells, int count) {}
  public Page nearest(String district, double x, double y, int offset, Integer mask, String role) {
    district(district);
    if (!Double.isFinite(x) || !Double.isFinite(y) || Math.abs(x) > 10_000_000 || Math.abs(y) > 10_000_000
        || offset < 0 || offset > 300000
        || mask != null && !Set.of(1, 2, 4, 8, 16, 32).contains(mask)
        || role != null && !Set.of("ROAD_AREA", "SIDEWALK_AREA", "OTHER").contains(role)) requestInvalid();
    String filter = "district_id=? AND allowed_mask<>0" + (mask == null ? "" : " AND allowed_mask & ? <> 0")
        + (role == null ? "" : role.equals("OTHER") ? " AND role NOT IN ('ROAD_AREA','SIDEWALK_AREA')" : " AND role=?");
    if (!queries.tryAcquire()) throw new DomainException(ErrorCode.RATE_LIMITED);
    try (var connection = connection(); var count = connection.prepareStatement("SELECT COUNT(*) FROM sites WHERE " + filter);
        var query = connection.prepareStatement("SELECT body FROM sites WHERE " + filter
            + " ORDER BY (cx-?)*(cx-?)+(cy-?)*(cy-?),id LIMIT 200 OFFSET ?")) {
      int index = 1;
      for (var statement : List.of(count, query)) {
        index = 1; statement.setString(index++, district);
        if (mask != null) statement.setInt(index++, mask);
        if (role != null && !role.equals("OTHER")) statement.setString(index++, role);
      }
      query.setDouble(index++, x); query.setDouble(index++, x);
      query.setDouble(index++, y); query.setDouble(index++, y); query.setInt(index, offset);
      int total;
      try (var row = count.executeQuery()) {
        if (!row.next()) invalid();
        total = row.getInt(1);
      }
      var cells = new ArrayList<JsonNode>();
      try (var rows = query.executeQuery()) { while (rows.next()) cells.add(json.tree(rows.getString(1))); }
      return new Page(List.copyOf(cells), total);
    } catch (DomainException e) { throw e; }
    catch (Exception e) { throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID); }
    finally { queries.release(); }
  }

  public List<JsonNode> bounds(double minx, double miny, double maxx, double maxy,
      String district, String kind, int limit, boolean unsupported) {
    if (Arrays.stream(new double[]{minx, miny, maxx, maxy})
            .anyMatch(value -> !Double.isFinite(value) || Math.abs(value) > 10_000_000)
        || maxx <= minx || maxy <= miny || maxx - minx > 2000 || maxy - miny > 2000
        || limit < 1 || limit > 2000) requestInvalid();
    if (district != null) district(district);
    if (kind != null && !Set.of("ROOF", "GROUND").contains(kind)) requestInvalid();
    String sql = "SELECT s.body FROM site_bounds b CROSS JOIN sites s ON s.fid=b.fid "
        + "WHERE b.maxx>=? AND b.minx<=? AND b.maxy>=? AND b.miny<=?"
        + (district == null ? "" : " AND s.district_id=?")
        + (kind == null ? "" : " AND s.kind=?")
        + (unsupported ? "" : " AND s.allowed_mask<>0") + " ORDER BY b.fid LIMIT 20001";
    var result = new ArrayList<JsonNode>();
    var viewport = NativeGeometry.box(minx, miny, maxx, maxy);
    if (!queries.tryAcquire()) throw new DomainException(ErrorCode.RATE_LIMITED);
    try (var connection = connection(); var query = connection.prepareStatement(sql)) {
      query.setDouble(1, minx); query.setDouble(2, maxx);
      query.setDouble(3, miny); query.setDouble(4, maxy);
      int parameter = 5;
      if (district != null) query.setString(parameter++, district);
      if (kind != null) query.setString(parameter, kind);
      int scanned = 0, bytes = 0;
      try (var rows = query.executeQuery()) {
        while (rows.next()) {
          if (++scanned > 20000) dense();
          String body = rows.getString(1);
          if (body.length() > 16 * 1024 * 1024) dense();
          bytes += body.getBytes(java.nio.charset.StandardCharsets.UTF_8).length;
          if (bytes > 16 * 1024 * 1024) dense();
          var cell = json.tree(body);
          if (NativeGeometry.polygon(cell.path("geometry"), cell.path("areaM2").asDouble()).intersects(viewport)) {
            if (result.size() >= limit) dense();
            result.add(cell);
          }
        }
      }
      return List.copyOf(result);
    } catch (DomainException e) { throw e; }
    catch (Exception e) { throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID); }
    finally { queries.release(); }
  }

  private void district(String value) {
    if (value == null || !districts.contains(value)) requestInvalid();
  }
  private static void dense() { throw new DomainException(ErrorCode.SPATIAL_VIEW_TOO_DENSE); }
  private static void requestInvalid() { throw new DomainException(ErrorCode.REQUEST_INVALID); }
  private static void invalid() { throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID); }
}
