package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.analysis.entity.PatternSample;
import io.waterleague.analysis.service.PatternAnalysisService;
import io.waterleague.common.exception.DomainException;
import io.waterleague.common.service.JsonService;
import io.waterleague.strategy.entity.*;
import io.waterleague.strategy.service.PlacementIdentityService;
import java.math.BigDecimal;
import java.util.*;
import org.junit.jupiter.api.Test;

class PatternAnalysisTests {
  final PatternAnalysisService service =
      new PatternAnalysisService(
          new PlacementIdentityService(new JsonService(new tools.jackson.databind.ObjectMapper())));

  Placement p(String cell, FacilityType type, String area) {
    return new Placement(cell, type, new BigDecimal(area));
  }

  PatternSample sample(int id, String hash, String score, String cost, Placement... p) {
    return new PatternSample(
        new UUID(0, id), hash, new BigDecimal(score), new BigDecimal(cost), List.of(p));
  }

  @Test
  void deduplicatesPhysicalInputsIncludesBoundaryTiesAndUsesCorrectDenominators() {
    var a = sample(1, "a", "10.00000000", "100", p("G1", FacilityType.RAIN_GARDEN, "10"));
    var duplicate = sample(2, "a", "10", "100", p("G1", FacilityType.RAIN_GARDEN, "10"));
    var b =
        sample(
            3,
            "b",
            "5",
            "200",
            p("G1", FacilityType.RAIN_GARDEN, "20"),
            p("R1", FacilityType.GREEN_ROOF, "30"));
    var c = sample(4, "c", "5", "300", p("G2", FacilityType.PERMEABLE_PAVEMENT, "40"));
    var excluded = sample(5, "d", "-2", "400", p("G1", FacilityType.RAIN_GARDEN, "70"));
    var inputs = List.of(a, duplicate, b, c, excluded);
    var result = service.analyze("model", inputs, 2);
    assertThat(result.requestedCount()).isEqualTo(5);
    assertThat(result.uniqueInputCount()).isEqualTo(4);
    assertThat(result.duplicateInputCount()).isEqualTo(1);
    assertThat(result.includedCount()).isEqualTo(3);
    assertThat(result.designs())
        .extracting(d -> d.jobId())
        .containsExactlyInAnyOrder(a.jobId(), b.jobId(), c.jobId());
    var garden = result.placements().get(0);
    assertThat(garden.designCount()).isEqualTo(2);
    assertThat(garden.frequencyPercent()).isEqualByComparingTo("66.67");
    assertThat(garden.meanInstalledAreaM2()).isEqualByComparingTo("15");
    assertThat(garden.meanAllDesignAreaM2()).isEqualByComparingTo("10");
    assertThat(garden.minimumAreaM2()).isEqualByComparingTo("10");
    assertThat(garden.maximumAreaM2()).isEqualByComparingTo("20");
    assertThat(result.facilityPairs())
        .filteredOn(pair -> pair.designCount() == 1)
        .singleElement()
        .satisfies(pair -> assertThat(pair.frequencyPercent()).isEqualByComparingTo("33.33"));
    assertThat(result.minimumCostKrw()).isEqualByComparingTo("100");
    assertThat(result.maximumCostKrw()).isEqualByComparingTo("300");
    assertThat(service.analyze("model", inputs.reversed(), 2)).isEqualTo(result);
  }

  @Test
  void preservesNegativeScoresZeroPlacementAndInsufficientPopulation() {
    var r =
        service.analyze(
            "m",
            List.of(
                sample(1, "a", "-3", "0"),
                sample(2, "b", "-2", "100", p("G1", FacilityType.RAIN_GARDEN, "10"))),
            20);
    assertThat(r.includedCount()).isEqualTo(2);
    assertThat(r.minimumScore()).isEqualByComparingTo("-3");
    assertThat(r.maximumScore()).isEqualByComparingTo("-2");
    assertThat(r.placements())
        .singleElement()
        .satisfies(p -> assertThat(p.frequencyPercent()).isEqualByComparingTo("50"));
    assertThat(r.facilityPairs()).allSatisfy(p -> assertThat(p.designCount()).isZero());
  }

  @Test
  void rejectsConflictingOutcomesForSamePhysicalInput() {
    assertThatThrownBy(
            () ->
                service.analyze(
                    "m", List.of(sample(1, "a", "1", "0"), sample(2, "a", "2", "0")), 2))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () ->
                service.analyze(
                    "m", List.of(sample(1, "a", "1", "0"), sample(2, "a", "1", "1")), 2))
        .isInstanceOf(DomainException.class);
  }

  @Test
  void deduplicatesNumericNotationAndCellOrderWithoutReplacingOriginalHashes() {
    var a =
        sample(
            1,
            "original-a",
            "10",
            "100",
            p("G1", FacilityType.RAIN_GARDEN, "20"),
            p("R1", FacilityType.GREEN_ROOF, "10"));
    var duplicate =
        sample(
            2,
            "original-b",
            "10",
            "100",
            p("R1", FacilityType.GREEN_ROOF, "10.00"),
            p("G1", FacilityType.RAIN_GARDEN, "20.0"));
    var result = service.analyze("model", List.of(duplicate, a), 2);
    assertThat(result.method()).isEqualTo("SELECTED_UNIQUE_PHYSICAL_TOP_K_WITH_TIES_V2");
    assertThat(result.uniqueInputCount()).isEqualTo(1);
    assertThat(result.includedCount()).isEqualTo(1);
    assertThat(result.duplicateInputCount()).isEqualTo(1);
    assertThat(result.designs())
        .singleElement()
        .satisfies(
            d -> {
              assertThat(d.inputHash()).isEqualTo("original-a");
              assertThat(d.physicalHash()).matches("[a-f0-9]{64}");
            });
    assertThat(result.placements()).allSatisfy(p -> assertThat(p.designCount()).isEqualTo(1));
    var conflict =
        sample(
            2,
            "original-b",
            "11",
            "100",
            p("R1", FacilityType.GREEN_ROOF, "10.00"),
            p("G1", FacilityType.RAIN_GARDEN, "20.0"));
    assertThatThrownBy(() -> service.analyze("model", List.of(a, conflict), 2))
        .isInstanceOf(DomainException.class);
    assertThat(
            service
                .analyze("other-model", List.of(a, duplicate), 2)
                .designs()
                .getFirst()
                .physicalHash())
        .isNotEqualTo(result.designs().getFirst().physicalHash());
  }
}
