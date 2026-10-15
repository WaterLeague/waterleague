package io.waterleague;
import io.waterleague.strategy.entity.*;
import io.waterleague.strategy.service.*;
import io.waterleague.strategy.exception.*;
import io.waterleague.common.exception.ErrorCode;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import java.math.BigDecimal;
import java.util.*;
import static org.assertj.core.api.Assertions.*;

class PlacementValidationTests {
    private final PlacementValidationService service = new PlacementValidationService();
    private final Map<String, PlacementCell> cells = Map.of("test-cell", new PlacementCell("test-cell", Set.of(FacilityType.RAIN_GARDEN), new BigDecimal("40"), true));
    private final Map<FacilityType, BigDecimal> costs = Map.of(FacilityType.RAIN_GARDEN, new BigDecimal("2.5"));
    private Placement placement(String area) { return new Placement("test-cell", FacilityType.RAIN_GARDEN, new BigDecimal(area)); }
    private BigDecimal validate(List<Placement> placements) { return service.validate(placements, cells, costs, new BigDecimal("100"), 3); }
    @Test void acceptsExactAreaAndBudgetBoundary() { assertThat(validate(List.of(placement("40.00")))).isEqualByComparingTo("100"); }
    @ParameterizedTest @ValueSource(strings = {"0", "-1", "40.01", "0.001"})
    void rejectsInvalidArea(String area) { assertThatThrownBy(() -> validate(List.of(placement(area)))).isInstanceOf(PlacementException.class); }
    @Test void rejectsDuplicateCell() { assertThatThrownBy(() -> validate(List.of(placement("10"), placement("10")))).isInstanceOf(PlacementException.class); }
    @Test void rejectsWrongFacilityAndUnknownCell() {
        assertThatThrownBy(() -> validate(List.of(new Placement("test-cell", FacilityType.GREEN_ROOF, BigDecimal.ONE)))).isInstanceOf(PlacementException.class);
        assertThatThrownBy(() -> validate(List.of(new Placement("other", FacilityType.RAIN_GARDEN, BigDecimal.ONE)))).isInstanceOf(PlacementException.class);
    }
    @Test void calculatesCostOnServerAndBlocksBudgetExcess() {
        assertThatThrownBy(() -> service.validate(List.of(placement("40")), cells, costs, new BigDecimal("99"), 3))
            .isInstanceOfSatisfying(PlacementException.class, error -> assertThat(error.code()).isEqualTo(ErrorCode.BUDGET_EXCEEDED));
    }
    @Test void rejectsUnapprovedCell() {
        var draft = Map.of("test-cell", new PlacementCell("test-cell", Set.of(FacilityType.RAIN_GARDEN), new BigDecimal("40"), false));
        assertThatThrownBy(() -> service.validate(List.of(placement("10")), draft, costs, new BigDecimal("100"), 3)).isInstanceOf(PlacementException.class);
    }
}
