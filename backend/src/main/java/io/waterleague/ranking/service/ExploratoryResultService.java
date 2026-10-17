package io.waterleague.ranking.service;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.simulation.entity.SimulationJob;
import java.math.*;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class ExploratoryResultService {
  private final JsonService json;

  public ExploratoryResultService(JsonService json) {
    this.json = json;
  }

  public BigDecimal score(SimulationJob job) {
    return score(job.state(), job.modelHash(), job.inputHash(), job.result());
  }

  public BigDecimal score(String state, String modelHash, String inputHash, String rawResult) {
    if (!state.equals("SUCCEEDED")) throw new DomainException(ErrorCode.CONFLICT);
    if (rawResult == null) throw new DomainException(ErrorCode.RESULT_QUALITY_FAILED);
    var result = json.tree(rawResult);
    if (!inputHash.equals(result.path("inputHash").asString())
        || !modelHash.equals(result.path("modelHash").asString())
        || !"EXPLORATORY".equals(result.path("validationLevel").asString())
        || !result.path("official").isBoolean()
        || result.path("official").asBoolean())
      throw new DomainException(ErrorCode.RESULT_QUALITY_FAILED);
    for (var name : List.of("baseline", "strategy")) {
      var metrics = result.path(name);
      double error = metrics.path("runoffContinuityPercent").asDouble(Double.NaN);
      double volume = metrics.path("accountedDischargeM3").asDouble(Double.NaN);
      if (!metrics.path("accountedDischargeM3").isNumber()
          || !metrics.path("runoffContinuityPercent").isNumber()
          || !Double.isFinite(error)
          || Math.abs(error) > 1
          || !Double.isFinite(volume)
          || volume < 0) throw new DomainException(ErrorCode.RESULT_QUALITY_FAILED);
    }
    BigDecimal base = result.path("baseline").path("accountedDischargeM3").decimalValue();
    BigDecimal strategy = result.path("strategy").path("accountedDischargeM3").decimalValue();
    if (base.compareTo(new BigDecimal("0.000001")) <= 0)
      throw new DomainException(ErrorCode.RESULT_QUALITY_FAILED);
    BigDecimal score =
        base.subtract(strategy)
            .multiply(BigDecimal.valueOf(100))
            .divide(base, 8, RoundingMode.HALF_UP);
    if (score.abs().compareTo(new BigDecimal("99999999")) > 0)
      throw new DomainException(ErrorCode.RESULT_QUALITY_FAILED);
    return score;
  }
}
