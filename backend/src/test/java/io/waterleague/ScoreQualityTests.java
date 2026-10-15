package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.model.entity.*;
import io.waterleague.model.service.*;
import io.waterleague.ranking.service.*;
import io.waterleague.simulation.entity.*;
import io.waterleague.simulation.exception.*;
import io.waterleague.simulation.service.*;
import java.math.BigDecimal;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class ScoreQualityTests {
  private final ResultQualityService quality = new ResultQualityService();
  private final ScoreService service = new ScoreService(new ModelEligibilityService(), quality);
  private final String hash = "a".repeat(64);
  private final ModelEvidence evidence =
      new ModelEvidence(ValidationLevel.BENCHMARKED, false, hash, Set.of(hash), true);

  private RunMetrics metrics(double volume, double peak) {
    return new RunMetrics(volume, peak, 0, 0.1, null, false);
  }

  private BigDecimal score(RunMetrics baseline, RunMetrics strategy) {
    return service.calculate(
        evidence, hash, baseline, strategy, new BigDecimal("0.7"), new BigDecimal("0.3"));
  }

  @Test
  void calculatesWeightedReductionAndPreservesDeterioration() {
    assertThat(score(metrics(100, 10), metrics(80, 9))).isEqualByComparingTo("17");
    assertThat(score(metrics(100, 10), metrics(110, 11))).isEqualByComparingTo("-10");
  }

  @Test
  void rejectsZeroBaselineAndNonFiniteValues() {
    assertThatThrownBy(() -> score(metrics(0, 10), metrics(0, 5)))
        .isInstanceOf(ResultQualityException.class);
    assertThatThrownBy(() -> score(metrics(100, 10), metrics(Double.NaN, 5)))
        .isInstanceOf(ResultQualityException.class);
    assertThatThrownBy(() -> score(metrics(100, 10), metrics(Double.POSITIVE_INFINITY, 5)))
        .isInstanceOf(ResultQualityException.class);
  }

  @ParameterizedTest
  @ValueSource(doubles = {-1.01, 1.01})
  void rejectsContinuityErrorInEitherDirection(double error) {
    assertThatThrownBy(() -> quality.validate(new RunMetrics(1, 1, 0, error, null, false), 1))
        .isInstanceOf(ResultQualityException.class);
  }

  @Test
  void requiresRoutingEvidenceWhenRouted() {
    assertThatThrownBy(() -> quality.validate(new RunMetrics(1, 1, 0, 0, null, true), 1))
        .isInstanceOf(ResultQualityException.class);
  }

  @Test
  void allowsVolumeOnlyWithoutDividingByZeroPeak() {
    var volumeEvidence =
        new ModelEvidence(ValidationLevel.BENCHMARKED, false, hash, Set.of(hash), false);
    assertThat(
            service.calculate(
                volumeEvidence,
                hash,
                metrics(100, 0),
                metrics(80, 0),
                BigDecimal.ONE,
                BigDecimal.ZERO))
        .isEqualByComparingTo("20");
  }
}
