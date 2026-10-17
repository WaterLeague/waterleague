package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.model.entity.LabModel;
import io.waterleague.model.repository.LabModelRepository;
import io.waterleague.model.service.LabModelService;
import io.waterleague.optimization.entity.*;
import io.waterleague.optimization.service.CandidateGenerationService;
import io.waterleague.strategy.entity.*;
import io.waterleague.strategy.service.PlacementIdentityService;
import io.waterleague.strategy.service.PlacementValidationService;
import java.math.BigDecimal;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class CandidateGenerationTests {
  final JsonService json = new JsonService(new ObjectMapper());
  final PlacementValidationService validation = new PlacementValidationService();
  final CandidateGenerationService generator =
      new CandidateGenerationService(json, validation, new PlacementIdentityService(json));
  final LabModelRepository repository;
  final LabModelService models;
  final LabModel model;

  CandidateGenerationTests() throws Exception {
    repository = new LabModelRepository(json);
    models = new LabModelService(repository, validation);
    model = repository.require(LegacyModelFixtures.HASH);
  }

  SearchSample sample(int id, String cell, String area, String score) {
    List<Placement> placements =
        cell == null
            ? List.of()
            : List.of(new Placement(cell, FacilityType.RAIN_GARDEN, new BigDecimal(area)));
    String source = json.write(placements);
    return new SearchSample(
        new UUID(0, id),
        new UUID(0, id + 100),
        json.hash(model.hash() + "\n" + source),
        source,
        new BigDecimal(score),
        models.validate(model.hash(), placements));
  }

  List<SearchSample> sources() {
    return List.of(
        sample(1, "G1", "20", "10"),
        sample(2, "G1", "20.00", "10"),
        sample(3, "G2", "30", "7"),
        sample(4, "G1", "40", "7"),
        sample(5, null, null, "-2"));
  }

  SearchSettings settings(long seed) {
    return new SearchSettings(2, new BigDecimal("40000000"), seed, 4);
  }

  @Test
  void estimatesSmoothedFrequenciesFromDistinctPhysicalInputsAndIncludesAllBoundaryTies() {
    var report = generator.generate(model, sources(), settings(42));
    assertThat(report.requestedCount()).isEqualTo(5);
    assertThat(report.uniquePhysicalCount()).isEqualTo(4);
    assertThat(report.trainingCount()).isEqualTo(3);
    assertThat(report.cutoffScore()).isEqualByComparingTo("7");
    assertThat(report.sources().get(0).physicalHash())
        .isEqualTo(report.sources().get(1).physicalHash());
    assertThat(report.sources().get(0).sample().inputHash())
        .isNotEqualTo(report.sources().get(1).sample().inputHash());
    assertThat(report.sources())
        .filteredOn(SearchGeneration.Source::selected)
        .extracting(s -> s.sample().jobId())
        .containsExactly(new UUID(0, 1), new UUID(0, 3), new UUID(0, 4));
    var g1 =
        report.distributions().stream()
            .filter(d -> d.cellId().equals("G1"))
            .findFirst()
            .orElseThrow();
    assertThat(g1.options())
        .filteredOn(o -> List.of("NONE", "RAIN_GARDEN:25", "RAIN_GARDEN:50").contains(o.key()))
        .allSatisfy(
            o -> {
              assertThat(o.observedCount()).isEqualTo(1);
              assertThat(o.patternWeight()).isEqualTo(2);
            });
    assertThat(report.distributions())
        .allSatisfy(
            d -> {
              assertThat(
                      d.options().stream().mapToInt(SearchGeneration.Option::observedCount).sum())
                  .isEqualTo(3);
              assertThat(d.options())
                  .allSatisfy(o -> assertThat(o.patternWeight()).isEqualTo(o.observedCount() + 1));
            });
    assertThat(generator.generate(model, sources().reversed(), settings(42))).isEqualTo(report);
  }

  @Test
  void createsNovelFeasibleCandidatesWithEqualBudgetsAndExplicitRejectionCounts() {
    for (long seed : List.of(0L, 1L, 42L, 2147483647L)) {
      var report = generator.generate(model, sources(), settings(seed));
      var originals = report.sources().stream().map(SearchGeneration.Source::physicalHash).toList();
      for (var arm : SearchArm.values()) {
        var selected = report.candidates().stream().filter(c -> c.arm() == arm).toList();
        assertThat(selected).hasSize(4);
        assertThat(selected)
            .extracting(SearchGeneration.Candidate::inputHash)
            .doesNotHaveDuplicates();
        var summary = report.arms().stream().filter(a -> a.arm() == arm).findFirst().orElseThrow();
        assertThat(summary.attempts()).isBetween(4, 128);
        assertThat(
                summary.emptyRejected()
                    + summary.sourceRejected()
                    + summary.duplicateRejected()
                    + 4)
            .isEqualTo(summary.attempts());
        assertThat(selected)
            .allSatisfy(
                c -> {
                  assertThat(c.placements()).isNotEmpty();
                  assertThat(c.inputHash()).isNotIn(originals);
                  assertThat(json.hash(model.hash() + "\n" + c.placementsSource()))
                      .isEqualTo(c.inputHash());
                  assertThat(models.validate(model.hash(), c.placements()))
                      .isEqualByComparingTo(c.costKrw())
                      .isLessThanOrEqualTo(report.settings().budgetKrw());
                  assertThat(c.placements())
                      .extracting(Placement::cellId)
                      .isSorted()
                      .doesNotHaveDuplicates();
                });
      }
    }
  }

  @Test
  void changesLearnedModelWhenCitizenPlacementsChange() {
    var a = generator.generate(model, sources(), settings(42));
    var updated = new ArrayList<>(sources());
    updated.set(0, sample(1, "G3", "20", "10"));
    updated.set(1, sample(2, "G3", "20.00", "10"));
    var b = generator.generate(model, updated, settings(42));
    assertThat(b.distributions()).isNotEqualTo(a.distributions());
    assertThat(b.candidates().stream().filter(c -> c.arm() == SearchArm.PATTERN).toList())
        .isNotEqualTo(a.candidates().stream().filter(c -> c.arm() == SearchArm.PATTERN).toList());
  }

  @Test
  void rejectsSourceCorruptionDuplicateJobsInsufficientPopulationAndUnfairBudget() {
    var s = sources().getFirst();
    assertThatThrownBy(() -> generator.generate(model, List.of(s, s), settings(1)))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(() -> generator.generate(model, sources().subList(0, 2), settings(1)))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.SEARCH_SAMPLE_INSUFFICIENT));
    var conflict = sample(2, "G1", "20.00", "11");
    assertThatThrownBy(() -> generator.generate(model, List.of(s, conflict), settings(1)))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.RESULT_QUALITY_FAILED));
    var bad =
        new SearchSample(
            s.jobId(), s.versionId(), "0".repeat(64), s.placementsSource(), s.score(), s.costKrw());
    assertThatThrownBy(() -> generator.generate(model, List.of(bad, sources().get(2)), settings(1)))
        .isInstanceOf(DomainException.class);
    var wrongCost =
        new SearchSample(
            s.jobId(),
            s.versionId(),
            s.inputHash(),
            s.placementsSource(),
            s.score(),
            BigDecimal.ZERO);
    assertThatThrownBy(
            () -> generator.generate(model, List.of(wrongCost, sources().get(2)), settings(1)))
        .isInstanceOf(DomainException.class);
    assertThatThrownBy(
            () ->
                generator.generate(
                    model, sources(), new SearchSettings(2, new BigDecimal("10000000"), 1, 1)))
        .isInstanceOfSatisfying(
            DomainException.class, e -> assertThat(e.code()).isEqualTo(ErrorCode.BUDGET_EXCEEDED));
    for (var setting :
        List.of(
            new SearchSettings(1, BigDecimal.TEN, 1, 1),
            new SearchSettings(2, BigDecimal.TEN, -1, 1),
            new SearchSettings(2, BigDecimal.TEN, 2147483648L, 1),
            new SearchSettings(2, BigDecimal.TEN, 1, 5),
            new SearchSettings(2, new BigDecimal("1.1"), 1, 1))) {
      assertThatThrownBy(() -> generator.generate(model, sources(), setting))
          .isInstanceOf(DomainException.class);
    }
  }

  @Test
  void refusesToInventCandidatesWhenEveryFeasibleChoiceWasAlreadySubmitted() {
    var node =
        json.tree(
            """
            {"budget":1,"maxPlacements":1,"unitCosts":{"RAIN_GARDEN":1,"GREEN_ROOF":1,"PERMEABLE_PAVEMENT":1},
             "cells":[{"id":"G1","maxAreaM2":1,"allowedTypes":["RAIN_GARDEN"]}]}
            """);
    String source = json.write(node), hash = json.hash(source);
    var tiny = new LabModel(hash, source, node);
    List<SearchSample> samples = new ArrayList<>();
    for (int i = 1; i <= 4; i++) {
      var area = BigDecimal.valueOf(i).divide(BigDecimal.valueOf(4));
      String raw = json.write(List.of(new Placement("G1", FacilityType.RAIN_GARDEN, area)));
      samples.add(
          new SearchSample(
              new UUID(0, i), new UUID(0, i + 100), json.hash(hash + "\n" + raw), raw, area, area));
    }
    assertThatThrownBy(
            () -> generator.generate(tiny, samples, new SearchSettings(2, BigDecimal.ONE, 0, 1)))
        .isInstanceOfSatisfying(
            DomainException.class,
            e -> assertThat(e.code()).isEqualTo(ErrorCode.CANDIDATE_SPACE_EXHAUSTED));
  }

  @Test
  void matchesPortableGenerationFixture() throws Exception {
    var report = generator.generate(model, sources(), settings(42));
    String export = System.getProperty("waterleague.search.fixture.path");
    if (export != null) Files.writeString(Path.of(export), json.write(report) + "\n");
    else {
      var path = Path.of("../simulation/tests/fixtures/pattern-search-v1.json");
      assertThat(json.tree(Files.readString(path))).isEqualTo(json.tree(json.write(report)));
    }
  }
}
