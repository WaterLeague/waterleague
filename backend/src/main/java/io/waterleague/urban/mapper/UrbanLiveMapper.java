package io.waterleague.urban.mapper;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.urban.view.UrbanLiveView;
import java.time.*;
import java.time.format.*;
import java.util.*;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;

@Component
public class UrbanLiveMapper {
  private static final ZoneId KST = ZoneId.of("Asia/Seoul");
  private static final DateTimeFormatter TIME =
      DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm").withResolverStyle(ResolverStyle.STRICT);
  private static final Pattern RANGE = Pattern.compile("([0-9/,]+)~([0-9/,]+)명");
  private static final Pattern HOUR = Pattern.compile("(?:\\d{1,2}/\\d{1,2} )?(\\d{1,2})시");
  private final JsonService json;

  public UrbanLiveMapper(JsonService json) {
    this.json = json;
  }

  public UrbanLiveView.Population population(String raw, String name, Instant now) {
    try {
      var root = json.tree(raw);
      if (!root.isArray() || root.size() != 1) throw invalid();
      var row = root.get(0);
      if (!name.equals(row.path("hotspot_nm").asString())) throw invalid();
      String[] times = parts(row, "time_cd"),
          ranges = parts(row, "people_interval"),
          values = parts(row, "people_value"),
          kinds = parts(row, "people_text_list"),
          congestion = parts(row, "congestion_label_list");
      if (times.length < 2
          || times.length > 49
          || ranges.length != times.length
          || values.length != times.length
          || kinds.length != times.length
          || congestion.length != times.length) throw invalid();
      int current = -1;
      for (int i = 0; i < times.length; i++)
        if (times[i].equals("현재")) {
          if (current != -1) throw invalid();
          current = i;
        }
      if (current < 0 || current + 1 >= times.length || !kinds[current].equals("인구수"))
        throw invalid();
      var range = RANGE.matcher(ranges[current]);
      var hour = HOUR.matcher(times[current + 1]);
      if (!range.matches() || !hour.matches()) throw invalid();
      long low = Long.parseLong(range.group(1).replace("/", "").replace(",", ""));
      long high = Long.parseLong(range.group(2).replace("/", "").replace(",", ""));
      double middle = Double.parseDouble(values[current]);
      int next = Integer.parseInt(hour.group(1));
      int sourceHour = (next + 23) % 24;
      int ageHours = (now.atZone(KST).getHour() - sourceHour + 24) % 24;
      if (next > 24
          || ageHours > 1
          || low < 0
          || high < low
          || high > 5_000_000
          || !Double.isFinite(middle)
          || middle < low
          || middle > high) throw invalid();
      if (!Set.of("여유", "보통", "약간 붐빔", "붐빔").contains(congestion[current])) throw invalid();
      var sourceDateHour =
          now.atZone(KST).minusHours(ageHours).withMinute(0).withSecond(0).withNano(0);
      boolean dated = false;
      for (int i = 0; i < times.length; i++) {
        if (i == current) continue;
        var expected = sourceDateHour.plusHours(i - current);
        var label = HOUR.matcher(times[i]);
        if (!label.matches() || Integer.parseInt(label.group(1)) % 24 != expected.getHour())
          throw invalid();
        if (times[i].contains("/")) {
          dated = true;
          if (!times[i].startsWith(expected.getMonthValue() + "/" + expected.getDayOfMonth() + " "))
            throw invalid();
        }
      }
      if (!dated) throw invalid();
      // 공개 화면은 시간대만 제공하므로 조회 시각을 관측 시각으로 만들지 않는다.
      return new UrbanLiveView.Population(
          low, high, sourceHour, congestion[current], now, now.plusSeconds(300), json.hash(raw));
    } catch (DomainException e) {
      throw e;
    } catch (Exception e) {
      throw invalid();
    }
  }

  public UrbanLiveView.Traffic traffic(String raw, String name, Instant now) {
    try {
      var rows = json.tree(raw).path("row");
      if (!rows.isArray() || rows.size() == 0 || rows.size() > 5000) throw invalid();
      Double speed = null;
      Instant at = null;
      for (var row : rows) {
        if (!name.equals(row.path("HOTSPOTNM").asString())) throw invalid();
        double value = row.path("ROAD_TRAFFIC_SPD").asDouble(Double.NaN);
        Instant time =
            LocalDateTime.parse(row.path("ROAD_TRAFFIC_TIME").asString(), TIME)
                .atZone(KST)
                .toInstant();
        if (!Double.isFinite(value)
            || value < 0
            || value > 180
            || time.isAfter(now.plusSeconds(120))
            || !time.isAfter(now.minusSeconds(900))) throw invalid();
        if (speed != null && (Double.compare(speed, value) != 0 || !at.equals(time)))
          throw invalid();
        speed = value;
        at = time;
      }
      return new UrbanLiveView.Traffic(
          speed,
          at,
          now,
          at.plusSeconds(900).isBefore(now.plusSeconds(300))
              ? at.plusSeconds(900)
              : now.plusSeconds(300),
          json.hash(raw));
    } catch (DomainException e) {
      throw e;
    } catch (Exception e) {
      throw invalid();
    }
  }

  private String[] parts(JsonNode row, String field) {
    var value = row.path(field);
    if (!value.isString() || value.asString().length() > 10000) throw invalid();
    return value.asString().split("\\|", -1);
  }

  private DomainException invalid() {
    return new DomainException(ErrorCode.URBAN_DATA_INVALID);
  }
}
