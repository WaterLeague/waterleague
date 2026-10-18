package io.waterleague.rainfall.mapper;

import io.waterleague.common.exception.ErrorCode;
import io.waterleague.rainfall.entity.PresentWeather;
import io.waterleague.rainfall.exception.RainfallException;
import java.time.*;
import java.util.*;

public final class KmaPresentWeatherMapper {
  private KmaPresentWeatherMapper() {}

  public static Map<String, PresentWeather> parse(String text, Instant requested) {
    try {
      if (!text.startsWith("#START7777")
          || !text.stripTrailing().endsWith("#7777END")
          || !text.contains("WW1")
          || !text.contains("NN1")) throw new IllegalArgumentException();
      var rows = new HashMap<String, NavigableMap<Instant, Map<Integer, PresentWeather>>>();
      for (var line : text.split("\n")) {
        if (line.isBlank() || line.startsWith("#")) continue;
        String[] f = line.strip().replaceFirst(",\\s*=\\s*$", "").split("\\s*,\\s*");
        if (f.length < 6 || !f[1].matches("[0-9]{1,5}")) throw new IllegalArgumentException();
        Instant at =
            LocalDateTime.parse(f[0], KmaObservationMapper.TIME)
                .atZone(KmaObservationMapper.KST)
                .toInstant();
        double lon = Double.parseDouble(f[2]), lat = Double.parseDouble(f[3]);
        int device = Integer.parseInt(f[4]), count = Integer.parseInt(f[5]);
        if (at.isAfter(requested)
            || at.isBefore(requested.minusSeconds(240))
            || !Double.isFinite(lon)
            || !Double.isFinite(lat)
            || Math.abs(lon) > 180
            || Math.abs(lat) > 90
            || (device != 1 && device != 2)
            || count < 0
            || count > 1
            || f.length != 6 + count * 2) throw new IllegalArgumentException();
        Integer code = null;
        if (count == 1) {
          int value = Integer.parseInt(f[6]), minutes = Integer.parseInt(f[7]);
          // 1분 창을 넘는 빈도 응답을 순간 날씨로 해석하지 않는다.
          if (minutes != 1 || value > 99) throw new IllegalArgumentException();
          if (value >= 0) code = value;
        }
        var devices =
            rows.computeIfAbsent(f[1], id -> new TreeMap<>())
                .computeIfAbsent(at, key -> new HashMap<>());
        if (devices.put(device, new PresentWeather(f[1], at, code)) != null)
          throw new IllegalArgumentException();
      }
      var result = new HashMap<String, PresentWeather>();
      rows.forEach(
          (id, times) -> {
            for (var devices : times.descendingMap().values()) {
              var known = devices.values().stream().filter(v -> v.code() != null).toList();
              if (known.isEmpty()) continue;
              var chosen = known.getFirst();
              // 같은 지점·시각의 장비가 다르면 강수 여부를 확정하지 않는다.
              if (known.stream().anyMatch(v -> !v.rainState().equals(chosen.rainState())))
                result.put(id, new PresentWeather(id, chosen.observedAt(), null));
              else result.put(id, chosen);
              break;
            }
          });
      return Map.copyOf(result);
    } catch (RuntimeException e) {
      throw new RainfallException(ErrorCode.RAINFALL_DATA_INVALID);
    }
  }
}
