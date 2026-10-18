package io.waterleague.watershed.mapper;

import io.waterleague.watershed.entity.WatershedExperiment;
import java.util.UUID;
import org.springframework.jdbc.core.RowMapper;

public final class WatershedMapper {
  private WatershedMapper() {}

  public static final RowMapper<WatershedExperiment> ROW =
      (r, n) ->
          new WatershedExperiment(
              r.getObject("id", UUID.class),
              r.getObject("owner_id", UUID.class),
              r.getString("model_hash"),
              r.getString("input_hash"),
              r.getString("placements"),
              r.getString("state"),
              r.getObject("lease_token", UUID.class),
              r.getTimestamp("created_at").toInstant(),
              r.getString("result"));
}
