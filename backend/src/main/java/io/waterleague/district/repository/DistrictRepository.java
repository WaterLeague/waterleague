package io.waterleague.district.repository;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.district.entity.District;
import io.waterleague.rainfall.repository.ObservedGameRepository;
import java.util.*;
import org.springframework.stereotype.Repository;

@Repository
public class DistrictRepository {
  private final Map<String, District> districts;

  public DistrictRepository(JsonService json, ObservedGameRepository models) {
    {
      var entries = new LinkedHashMap<String, District>();
      for (var d : models.catalog().path("regions")) {
        var rain = d.path("defaultRainfall");
        String id = d.path("districtId").asString(),
            hash = d.path("defaultModelHash").asString(),
            map = d.path("mapId").asString();
        if (!models.require(hash).model().path("mapId").asString().equals(map))
          throw new IllegalStateException("구별 모델 연결 불일치");
        var value =
            new District(
                id,
                d.path("districtName").asString(),
                map,
                hash,
                List.of(d.path("center").get(0).asDouble(), d.path("center").get(1).asDouble()),
                rain.path("stationId").asString(),
                rain.path("stationName").asString());
        if (entries.put(id, value) != null) throw new IllegalStateException("구 중복");
      }
      if (entries.size() != 25) throw new IllegalStateException("서울 25개 구 필요");
      districts = Collections.unmodifiableMap(entries);
    }
  }

  public List<District> all() {
    return List.copyOf(districts.values());
  }

  public District require(String id) {
    var d = districts.get(id);
    if (d == null) throw new DomainException(ErrorCode.REQUEST_INVALID);
    return d;
  }
}
