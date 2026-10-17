package io.waterleague.disaster.repository;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.disaster.view.DisasterView;
import io.waterleague.district.repository.DistrictRepository;
import io.waterleague.model.repository.LabModelRepository;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;

@Repository
public class DisasterRepository {
  private final DisasterView view;
  private final Map<String, String> districtsByHash;

  public DisasterRepository(
      JsonService json, LabModelRepository models, DistrictRepository districts)
      throws java.io.IOException {
    var events = new ArrayList<DisasterView.Event>();
    var hashes = new HashMap<String, String>();
    var ids = new HashSet<String>();
    try (var in = new ClassPathResource("disasters/seoul-events-v1.json").getInputStream()) {
      byte[] bytes = in.readNBytes(1024 * 1024 + 1);
      if (bytes.length > 1024 * 1024) throw new IllegalStateException("재해 목록 크기 초과");
      var catalog = json.tree(new String(bytes, StandardCharsets.UTF_8));
      if (catalog.path("schemaVersion").asInt() != 1 || !catalog.path("events").isArray())
        throw new IllegalStateException("재해 목록 형식 오류");
      for (var e : catalog.path("events")) {
        String id = e.path("id").asString();
        if (!id.matches("seoul-[0-9]{8}")
            || !ids.add(id)
            || !e.path("evidenceUrl").asString().startsWith("https://"))
          throw new IllegalStateException("재해 출처 오류");
        var regions = new ArrayList<DisasterView.Region>();
        var districtIds = new HashSet<String>();
        String start = null, end = null;
        for (var b : e.path("models")) {
          String districtId = b.path("districtId").asString(),
              hash = b.path("modelHash").asString();
          var m = models.require(hash).model();
          var r = m.path("rainfall");
          if (!districtIds.add(districtId)
              || hashes.put(hash, districtId) != null
              || !districts.require(districtId).mapId().equals(m.path("mapId").asString())
              || !id.equals(m.path("disasterEvent").path("id").asString())
              || !e.path("evidenceUrl")
                  .asString()
                  .equals(m.path("disasterEvent").path("evidenceUrl").asString()))
            throw new IllegalStateException("재해 모델 연결 오류");
          String from = r.path("start").asString(), to = r.path("end").asString();
          if (start != null && (!start.equals(from) || !end.equals(to)))
            throw new IllegalStateException("재해 재생 시간 불일치");
          start = from;
          end = to;
          var depths = new ArrayList<Double>();
          for (var n : r.path("depthsMm")) {
            double value = n.asDouble();
            if (!Double.isFinite(value) || value < 0) throw new IllegalStateException("재해 강우 오류");
            depths.add(value);
          }
          long seconds =
              OffsetDateTime.parse(to).toEpochSecond() - OffsetDateTime.parse(from).toEpochSecond();
          double total = r.path("totalDepthMm").asDouble(),
              distance = r.path("stationDistanceKm").asDouble();
          if (depths.isEmpty()
              || depths.size() > 1440
              || seconds != depths.size() * 60L
              || r.path("intervalSeconds").asInt() != 60
              || !Double.isFinite(total)
              || total <= 0
              || Math.abs(depths.stream().mapToDouble(Double::doubleValue).sum() - total) > .001
              || !Double.isFinite(distance)
              || distance < 0
              || distance > 10) throw new IllegalStateException("재해 강우 수지 오류");
          regions.add(
              new DisasterView.Region(
                  districtId,
                  hash,
                  r.path("stationName").asString(),
                  r.path("stationId").asString(),
                  distance,
                  from,
                  to,
                  total,
                  List.copyOf(depths)));
        }
        if (regions.isEmpty() || regions.size() > 25) throw new IllegalStateException("재해 지역 누락");
        events.add(
            new DisasterView.Event(
                id,
                e.path("title").asString(),
                e.path("eventDate").asString(),
                e.path("summary").asString(),
                e.path("evidenceTitle").asString(),
                e.path("evidenceUrl").asString(),
                List.copyOf(regions)));
      }
    }
    if (events.isEmpty() || events.size() > 20) throw new IllegalStateException("재해 사건 수 오류");
    view = new DisasterView(List.copyOf(events));
    districtsByHash = Map.copyOf(hashes);
  }

  public DisasterView all() {
    return view;
  }

  public void require(String districtId, String hash) {
    if (!districtId.equals(districtsByHash.get(hash)))
      throw new DomainException(ErrorCode.MODEL_NOT_ELIGIBLE);
  }
}
