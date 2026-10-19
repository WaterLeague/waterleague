package io.waterleague.rainfall.mapper;

import io.waterleague.common.exception.ErrorCode;
import io.waterleague.rainfall.entity.LiveObservation;
import io.waterleague.rainfall.exception.RainfallException;
import java.math.BigDecimal;
import java.time.*;
import java.time.format.*;
import java.util.*;

public final class KmaObservationMapper {
  public static final ZoneId KST = ZoneId.of("Asia/Seoul");
  public static final DateTimeFormatter TIME =
      DateTimeFormatter.ofPattern("uuuuMMddHHmm").withResolverStyle(ResolverStyle.STRICT);

  private KmaObservationMapper() {}

  public static Map<String, LiveObservation> parse(String text, Instant requested) {
    try {
      if (!text.startsWith("#START7777")
          || !text.stripTrailing().endsWith("#7777END")
          || !text.contains("RN-15m RN-60m RN-12H RN-DAY")) throw new IllegalArgumentException();
      var observations = new HashMap<String, NavigableMap<Instant, LiveObservation>>();
      for (String line : text.split("\n")) {
        if (line.isBlank() || line.startsWith("#")) continue;
        String[] f = line.strip().split("\\s+");
        if (f.length != 18 || !f[1].matches("[0-9]{1,5}")) throw new IllegalArgumentException();
        Instant time = LocalDateTime.parse(f[0], TIME).atZone(KST).toInstant();
        if (time.isAfter(requested) || time.isBefore(requested.minusSeconds(240)))
          throw new IllegalArgumentException();
        var value =
            new LiveObservation(
                f[1],
                time,
                depth(f[10]),
                depth(f[11]),
                depth(f[13]),
                detection(f[9]),
                null,
                weather(f[8], -90, 60),
                weather(f[14], 0, 100),
                weather(f[7], 0, 150),
                weather(f[15], 300, 1100),
                weather(f[6], 0, 360));
        var target = observations.computeIfAbsent(f[1], id -> new TreeMap<>());
        if (target.put(time, value) != null) throw new IllegalArgumentException();
      }
      var rows = new HashMap<String, LiveObservation>();
      observations.forEach(
          (id, series) -> {
            // 같은 직접 응답 안에서 최근 유효 관측을 선택하고 원 시각을 보존한다.
            var current =
                series.descendingMap().values().stream()
                    .filter(LiveObservation::hasRainObservation)
                    .findFirst()
                    .orElse(series.lastEntry().getValue());
            var before = series.get(current.observedAt().minusSeconds(60));
            BigDecimal minute = null;
            // 자정 초기화나 관측 역전을 실제 분 강우로 만들지 않는다.
            if (before != null
                && before.dayMm() != null
                && current.dayMm() != null
                && before
                    .observedAt()
                    .atZone(KST)
                    .toLocalDate()
                    .equals(current.observedAt().atZone(KST).toLocalDate())) {
              var delta = current.dayMm().subtract(before.dayMm());
              if (delta.signum() >= 0) minute = delta;
            }
            rows.put(
                id,
                new LiveObservation(
                    id,
                    current.observedAt(),
                    current.fifteenMinuteMm(),
                    current.sixtyMinuteMm(),
                    current.dayMm(),
                    current.rainDetected(),
                    minute,
                    current.temperatureC(),
                    current.humidityPercent(),
                    current.windSpeedMs(),
                    current.pressureHpa(),
                    current.windDirectionDeg()));
          });
      return Map.copyOf(rows);
    } catch (RuntimeException e) {
      throw new RainfallException(ErrorCode.RAINFALL_DATA_INVALID);
    }
  }

  private static Boolean detection(String s) {
    var n = new BigDecimal(s);
    if (n.signum() < 0) return null;
    if (n.signum() == 0) return false;
    if (n.compareTo(BigDecimal.ONE) == 0) return true;
    throw new IllegalArgumentException();
  }

  private static BigDecimal weather(String s, int minimum, int maximum) {
    var n = new BigDecimal(s);
    if (n.compareTo(BigDecimal.valueOf(-99)) <= 0) return null;
    if (n.compareTo(BigDecimal.valueOf(minimum)) < 0
        || n.compareTo(BigDecimal.valueOf(maximum)) > 0
        || n.scale() > 3) throw new IllegalArgumentException();
    return n;
  }

  private static BigDecimal depth(String s) {
    var n = new BigDecimal(s);
    if (n.compareTo(BigDecimal.valueOf(-50)) <= 0) return null;
    if (n.signum() < 0 || n.compareTo(BigDecimal.valueOf(5000)) > 0 || n.scale() > 3)
      throw new IllegalArgumentException();
    return n;
  }
}
