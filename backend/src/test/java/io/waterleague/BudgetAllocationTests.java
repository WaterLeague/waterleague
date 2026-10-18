package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.budget.entity.BudgetAllocationPolicy;
import io.waterleague.budget.service.BudgetAllocationService;
import io.waterleague.common.exception.*;
import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.util.*;
import org.junit.jupiter.api.Test;

class BudgetAllocationTests {
  BudgetAllocationPolicy plan() {
    return new BudgetAllocationPolicy(
        "TEST",
        "TEST",
        List.of(
            new BudgetAllocationPolicy.Program(
                "SHARED", "시험 공동 사업", new BigDecimal("100"), "a".repeat(64))),
        List.of(
            new BudgetAllocationPolicy.Facility(
                FacilityType.RAIN_GARDEN, "SHARED", new BigDecimal("80")),
            new BudgetAllocationPolicy.Facility(
                FacilityType.GREEN_ROOF, "SHARED", new BigDecimal("80"))));
  }

  @Test
  void parentLimitCannotBeMultipliedByFacilityWallets() {
    var plan = plan();
    BudgetAllocationService.validate(plan);
    var spent =
        Map.of(
            FacilityType.RAIN_GARDEN,
            new BigDecimal("70"),
            FacilityType.GREEN_ROOF,
            new BigDecimal("20"));
    var view = BudgetAllocationService.calculate(plan, spent);
    assertThat(view.programs().getFirst().remainingKrw()).isEqualByComparingTo("10");
    assertThat(view.facilities())
        .allSatisfy(f -> assertThat(f.availableKrw()).isEqualByComparingTo("10"));
    var over =
        BudgetAllocationService.calculate(
            plan,
            Map.of(
                FacilityType.RAIN_GARDEN,
                new BigDecimal("70"),
                FacilityType.GREEN_ROOF,
                new BigDecimal("31")));
    assertThatThrownBy(() -> BudgetAllocationService.requireWithinLimits(over))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.BUDGET_EXCEEDED));
  }

  @Test
  void facilityCapAndInvalidMappingFailWithoutMovingMoney() {
    var view =
        BudgetAllocationService.calculate(
            plan(), Map.of(FacilityType.GREEN_ROOF, new BigDecimal("81")));
    assertThat(view.programs().getFirst().remainingKrw()).isEqualByComparingTo("19");
    assertThatThrownBy(() -> BudgetAllocationService.requireWithinLimits(view))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () ->
                BudgetAllocationService.calculate(
                    plan(), Map.of(FacilityType.PERMEABLE_PAVEMENT, BigDecimal.ONE)))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () ->
                BudgetAllocationService.calculate(
                    plan(), Map.of(FacilityType.RAIN_GARDEN, new BigDecimal("-1"))))
        .isInstanceOf(DomainException.class);
    var duplicate =
        new BudgetAllocationPolicy(
            "TEST",
            "TEST",
            plan().programs(),
            List.of(plan().facilities().getFirst(), plan().facilities().getFirst()));
    assertThatThrownBy(() -> BudgetAllocationService.validate(duplicate))
        .isInstanceOf(DomainException.class);
  }
}
