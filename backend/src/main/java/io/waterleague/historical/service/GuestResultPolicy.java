package io.waterleague.historical.service;

import io.waterleague.common.service.JsonService;
import java.time.OffsetDateTime;
import java.util.*;
import tools.jackson.databind.JsonNode;

final class GuestResultPolicy {
  private GuestResultPolicy() {}

  static JsonNode preview(JsonService json, JsonNode result) {
    if (result == null || result.isNull()) return null;
    var safe = new LinkedHashMap<String, Object>();
    for (var key : List.of("engineVersion", "validationLevel", "stationName", "start", "end", "assumptions", "temporalPolicy"))
      if (result.has(key)) safe.put(key, result.get(key));
    var end = OffsetDateTime.parse(result.path("end").asString()).toInstant();
    safe.put("frames", progressFrames(result.path("frames"), end));
    var facilities = new ArrayList<Map<String, Object>>();
    for (var facility : result.path("facilities")) {
      var value = new LinkedHashMap<String, Object>();
      for (var key : List.of("cellId", "installedAt", "initialization", "facilityDesign", "costRecord"))
        if (facility.has(key)) value.put(key, facility.get(key));
      value.put("frames", progressFrames(facility.path("frames"), end));
      facilities.add(value);
    }
    safe.put("facilities", facilities);
    return json.tree(json.write(safe));
  }

  private static List<JsonNode> progressFrames(JsonNode frames, java.time.Instant end) {
    var values = new ArrayList<JsonNode>();
    // 최종 합계·마지막 구간을 제외해 게스트 진행 응답에 최종 점수가 실리지 않게 한다.
    for (int i = 0; i + 1 < frames.size(); i++) {
      var frame = frames.get(i);
      if (OffsetDateTime.parse(frame.path("at").asString()).toInstant().isBefore(end)) values.add(frame);
    }
    return List.copyOf(values);
  }
}
