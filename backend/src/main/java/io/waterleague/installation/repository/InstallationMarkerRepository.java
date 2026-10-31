package io.waterleague.installation.repository;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.exception.ErrorCode;
import io.waterleague.installation.entity.SharedInstallation;
import io.waterleague.spatial.repository.NativePlayRepository;
import java.util.*;
import org.springframework.stereotype.Repository;

@Repository
public class InstallationMarkerRepository {
  private final NativePlayRepository nativeSites;
  private final Set<String> districts;
  private final Map<SiteKey, Marker> markers = new LinkedHashMap<>(256, .75f, true);

  public record SiteKey(String districtId, String cellId) {}

  public record Marker(List<Double> center, double heightM) {}

  public InstallationMarkerRepository(NativePlayRepository nativeSites) {
    this.nativeSites = nativeSites;
    var values = new HashSet<String>();
    nativeSites.envelope().path("districtKindCounts").properties()
        .forEach(entry -> values.add(entry.getKey().split(":")[0]));
    districts = Set.copyOf(values);
  }

  public Map<UUID, Marker> forInstallations(Collection<SharedInstallation> installations) {
    var values = markers(installations.stream()
        .map(i -> new SiteKey(i.districtId(), i.cellId())).toList());
    var result = new HashMap<UUID, Marker>();
    for (var installation : installations)
      result.put(installation.id(), values.get(new SiteKey(installation.districtId(), installation.cellId())));
    return Map.copyOf(result);
  }

  public synchronized Map<SiteKey, Marker> markers(Collection<SiteKey> requested) {
    var keys = new LinkedHashSet<>(requested);
    for (var key : keys) {
      if (key.districtId() == null || !districts.contains(key.districtId()))
        throw new DomainException(ErrorCode.REQUEST_INVALID);
      if (key.cellId() == null || !key.cellId().matches("C[a-f0-9]{24}"))
        throw new DomainException(ErrorCode.REQUEST_INVALID);
    }
    if (keys.isEmpty()) return Map.of();
    // 캐시 적중 시에도 기존 읽기 전용 연결의 원본 무결성 검사를 거친다.
    try (var connection = nativeSites.connection()) {
      var result = new HashMap<SiteKey, Marker>();
      var missing = new ArrayList<SiteKey>();
      for (var key : keys) {
        var marker = markers.get(key);
        if (marker == null) missing.add(key);
        else result.put(key, marker);
      }
      for (int start = 0; start < missing.size(); start += 250) {
        var batch = missing.subList(start, Math.min(start + 250, missing.size()));
        var placeholders = String.join(",", Collections.nCopies(batch.size(), "?"));
        try (var query = connection.prepareStatement(
            "SELECT district_id,id,cx,cy,json_extract(body,'$.heightM'),allowed_mask"
                + " FROM sites WHERE id IN (" + placeholders + ")")) {
          int index = 1;
          for (var key : batch) {
            query.setString(index++, key.cellId());
          }
          try (var rows = query.executeQuery()) {
            while (rows.next()) {
              var key = new SiteKey(rows.getString(1), rows.getString(2));
              if (!keys.contains(key)) throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
              double x = rows.getDouble(3), y = rows.getDouble(4), height = rows.getDouble(5);
              if (rows.wasNull() || !Double.isFinite(x) || !Double.isFinite(y)
                  || Math.abs(x) > 10_000_000 || Math.abs(y) > 10_000_000
                  || !Double.isFinite(height) || height < 0) throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID);
              if (rows.getInt(6) == 0) throw new DomainException(ErrorCode.PLACEMENT_INVALID);
              result.put(key, new Marker(List.of(x - SiteCatalogRepository.ORIGIN_X, y - SiteCatalogRepository.ORIGIN_Y), height));
            }
          }
        }
      }
      if (result.size() != keys.size()) throw new DomainException(ErrorCode.RESOURCE_NOT_FOUND);
      markers.putAll(result);
      while (markers.size() > 8192) markers.remove(markers.keySet().iterator().next());
      return Map.copyOf(result);
    } catch (DomainException e) {
      throw e;
    } catch (Exception e) {
      throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID);
    }
  }
}
