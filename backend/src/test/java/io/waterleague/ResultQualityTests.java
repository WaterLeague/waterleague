package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.simulation.entity.RunMetrics;
import io.waterleague.simulation.exception.ResultQualityException;
import io.waterleague.simulation.service.ResultQualityService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class ResultQualityTests {
  private final ResultQualityService quality = new ResultQualityService();

  @Test
  void rejectsNonFiniteValues() {
    assertThatThrownBy(() -> quality.validate(new RunMetrics(Double.NaN, 1, 0, 0, null, false), 1))
        .isInstanceOf(ResultQualityException.class);
    assertThatThrownBy(
            () -> quality.validate(new RunMetrics(Double.POSITIVE_INFINITY, 1, 0, 0, null, false), 1))
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
}
