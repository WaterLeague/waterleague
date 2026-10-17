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
      for (String line : text.split("\n")) {
        if (line.isBlank() || line.startsWith("#")) continue;
        String[] f = line.strip().split("\s+");
        if (f.length != 18 || !f[1].matches("[0-9]{1,5}")) throw new IllegalArgumentException();
        Instant time = LocalDateTime.parse(f[0], TIME).atZone(KST).toInstant();
        if (!time.equals(requested)) throw new IllegalArgumentException();
        var value = new LiveObservation(f[1], time, depth(f[10]), depth(f[11]), depth(f[13]));
        if (rows.put(f[1], value) != null) throw new IllegalArgumentException();
      }
      return Map.copyOf(rows);
    } catch (RuntimeException e) {
      throw new RainfallException(ErrorCode.RAINFALL_DATA_INVALID);
    }
  }

  private static BigDecimal depth(String s) {
    var n = new BigDecimal(s);
    if (n.compareTo(BigDecimal.valueOf(-50)) <= 0) return null;
    if (n.signum() < 0 || n.compareTo(BigDecimal.valueOf(5000)) > 0 || n.scale() > 3)
      throw new IllegalArgumentException();
    return n;
  }
}
