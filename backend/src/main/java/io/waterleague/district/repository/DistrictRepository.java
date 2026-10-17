package io.waterleague.district.repository;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.district.entity.District;
import io.waterleague.model.repository.LabModelRepository;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;

@Repository
public class DistrictRepository {
  private final Map<String, District> districts;

  public DistrictRepository(JsonService json, LabModelRepository models)
      throws java.io.IOException {
    try (var in = new ClassPathResource("districts/seoul-play-v2.json").getInputStream()) {
      var source = new String(in.readAllBytes(), StandardCharsets.UTF_8);
      if (!json.hash(source)
          .equals("4187dbcf06bbcf0cb36212ae6d983969098ab9d947afe083702487e3ec910121"))
        throw new IllegalStateException("서울 구 목록 해시 불일치");
      var entries = new LinkedHashMap<String, District>();
      for (var d : json.tree(source).path("regions")) {
        var rain = d.path("defaultRainfall");
        String id = d.path("districtId").asString(),
            hash = d.path("defaultModelHash").asString(),
            map = d.path("mapId").asString();
        if (!models.require(hash).model().path("mapId").asString().equals(map))
          throw new IllegalStateException("구별 모델 연결 불일치");
        // 강서는 과거 분자료 결측으로 기본 모델이 공통 강우지만 실시간 조회는 강서 관측소 사용.
        var value =
            new District(
                id,
                d.path("districtName").asString(),
                map,
                hash,
                List.of(d.path("center").get(0).asDouble(), d.path("center").get(1).asDouble()),
                rain.path("stationId").asString("110"),
                rain.path("stationName").asString("강서"));
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
