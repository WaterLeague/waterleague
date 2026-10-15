package io.waterleague.league.mapper;

import io.waterleague.common.service.JsonService;
import io.waterleague.league.entity.*;
import io.waterleague.league.view.LeagueView;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Component;

@Component
public class LeagueMapper {
  private final JsonService json;

  public LeagueMapper(JsonService json) {
    this.json = json;
  }

  public LeagueView view(League l, String currentHash, Instant now) {
    String phase = l.state();
    if (phase.equals("PUBLISHED"))
      phase =
          now.isBefore(l.opensAt()) ? "SCHEDULED" : !now.isBefore(l.closesAt()) ? "CLOSED" : "OPEN";
    return new LeagueView(
        l.id(),
        l.organizationId(),
        l.organizationName(),
        l.revision(),
        l.state(),
        phase,
        l.title(),
        l.question(),
        json.read(l.rules(), LeagueRules.class),
        l.rulesHash(),
        l.executionHash(),
        l.publishedAt(),
        l.cancellationReason(),
        l.modelHash().equals(currentHash));
  }

  public List<Map<String, Object>> ranks(List<Map<String, Object>> rows) {
    var out = new ArrayList<Map<String, Object>>();
    BigDecimal previous = null;
    int rank = 0;
    for (int i = 0; i < rows.size(); i++) {
      var row = new LinkedHashMap<>(rows.get(i));
      var score = (BigDecimal) row.get("score");
      if (previous == null || score.compareTo(previous) != 0) rank = i + 1;
      row.put("rank", rank);
      row.put("currency", "KRW");
      out.add(row);
      previous = score;
    }
    return out;
  }
}
