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
      var rows = new HashMap<String, LiveObservation>();
      var previous = new HashMap<String, LiveObservation>();
      for (String line : text.split("\n")) {
        if (line.isBlank() || line.startsWith("#")) continue;
        String[] f = line.strip().split("\\s+");
        if (f.length != 18 || !f[1].matches("[0-9]{1,5}")) throw new IllegalArgumentException();
        Instant time = LocalDateTime.parse(f[0], TIME).atZone(KST).toInstant();
        if (!time.equals(requested) && !time.equals(requested.minusSeconds(60)))
          throw new IllegalArgumentException();
        var value =
            new LiveObservation(
                f[1], time, depth(f[10]), depth(f[11]), depth(f[13]), detection(f[9]), null);
        var target = time.equals(requested) ? rows : previous;
        if (target.put(f[1], value) != null) throw new IllegalArgumentException();
      }
      rows.replaceAll(
          (id, current) -> {
            var before = previous.get(id);
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
            return new LiveObservation(
                id,
                current.observedAt(),
                current.fifteenMinuteMm(),
                current.sixtyMinuteMm(),
                current.dayMm(),
                current.rainDetected(),
                minute);
          });
      return Map.copyOf(rows);
    } catch (RuntimeException e) {
      throw new RainfallException(ErrorCode.RAINFALL_DATA_INVALID);
    }
  }

  private static Boolean detection(String s) {
    var n = new BigDecimal(s);
    if (n.compareTo(BigDecimal.valueOf(-50)) <= 0) return null;
    if (n.signum() == 0) return false;
    if (n.compareTo(BigDecimal.ONE) == 0) return true;
    throw new IllegalArgumentException();
  }

  private static BigDecimal depth(String s) {
    var n = new BigDecimal(s);
    if (n.compareTo(BigDecimal.valueOf(-50)) <= 0) return null;
    if (n.signum() < 0 || n.compareTo(BigDecimal.valueOf(5000)) > 0 || n.scale() > 3)
      throw new IllegalArgumentException();
    return n;
  }
}
