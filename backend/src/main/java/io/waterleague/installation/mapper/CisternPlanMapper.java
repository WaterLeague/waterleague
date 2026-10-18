package io.waterleague.installation.mapper;

import io.waterleague.common.exception.ErrorCode;
import io.waterleague.common.service.JsonService;
import io.waterleague.installation.entity.CisternPlan;
import io.waterleague.installation.exception.CisternPlanException;
import io.waterleague.installation.view.CisternPlanView;

public final class CisternPlanMapper {
  private CisternPlanMapper() {}

  public static CisternPlanView view(CisternPlan value, JsonService json) {
    if (!json.hash(value.snapshot()).equals(value.inputHash()))
      throw new CisternPlanException(ErrorCode.SPATIAL_DATA_INVALID);
    return new CisternPlanView(
        value.id(), value.inputHash(), value.createdAt(), json.tree(value.snapshot()));
  }
}
