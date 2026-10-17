package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.model.entity.*;
import io.waterleague.model.exception.*;
import io.waterleague.model.service.*;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;

class ModelEligibilityTests {
  private final ModelEligibilityService service = new ModelEligibilityService();
  private final String hash = "a".repeat(64);

  @ParameterizedTest
  @EnumSource(
      value = ValidationLevel.class,
      names = {"DRAFT", "EXPLORATORY"})
  void blocksUnvalidatedOfficialResults(ValidationLevel level) {
    var evidence = new ModelEvidence(level, false, hash, Set.of(hash), true);
    assertThatThrownBy(() -> service.requireOfficial(evidence, hash, true, false))
        .isInstanceOf(ModelNotEligibleException.class);
  }

  @Test
  void rejectsRevokedEvidence() {
    var evidence =
        new ModelEvidence(ValidationLevel.SITE_VALIDATED, true, hash, Set.of(hash), true);
    assertThatThrownBy(() -> service.requireOfficial(evidence, hash, false, false))
        .isInstanceOf(ModelNotEligibleException.class);
  }

  @Test
  void limitsApprovalToValidatedRainfall() {
    var evidence =
        new ModelEvidence(ValidationLevel.SITE_VALIDATED, false, hash, Set.of(hash), true);
    assertThatThrownBy(() -> service.requireOfficial(evidence, "b".repeat(64), false, false))
        .isInstanceOf(ModelNotEligibleException.class);
  }

  @Test
  void rejectsPeakAndSiteClaimsWithoutEvidence() {
    var evidence = new ModelEvidence(ValidationLevel.BENCHMARKED, false, hash, Set.of(hash), false);
    assertThatCode(() -> service.requireOfficial(evidence, hash, false, false))
        .doesNotThrowAnyException();
    assertThatThrownBy(() -> service.requireOfficial(evidence, hash, true, false))
        .isInstanceOf(ModelNotEligibleException.class);
    assertThatThrownBy(() -> service.requireOfficial(evidence, hash, false, true))
        .isInstanceOf(ModelNotEligibleException.class);
  }

  @Test
  void rejectsMissingReport() {
    var evidence =
        new ModelEvidence(ValidationLevel.SITE_VALIDATED, false, null, Set.of(hash), true);
    assertThatThrownBy(() -> service.requireOfficial(evidence, hash, true, false))
        .isInstanceOf(ModelNotEligibleException.class);
  }
}
