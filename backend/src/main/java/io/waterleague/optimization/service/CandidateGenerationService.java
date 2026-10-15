package io.waterleague.optimization.service;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.model.entity.LabModel;
import io.waterleague.optimization.entity.*;
import io.waterleague.optimization.entity.SearchGeneration.*;
import io.waterleague.optimization.exception.SearchGenerationException;
import io.waterleague.strategy.entity.*;
import io.waterleague.strategy.service.PlacementValidationService;
import java.math.*;
import java.util.*;
import org.springframework.stereotype.Service;

@Service
public class CandidateGenerationService {
  public static final String POLICY = "ELITE_CATEGORICAL_SEARCH_V1";
  public static final List<Integer> BINS = List.of(25, 50, 75, 100);
  public static final int DRAW_LIMIT = 128;
  private final JsonService json;
  private final PlacementValidationService validation;

  public CandidateGenerationService(JsonService json, PlacementValidationService validation) {
    this.json = json;
    this.validation = validation;
  }

  public SearchGeneration generate(
      LabModel model, List<SearchSample> samples, SearchSettings settings) {
    if (samples == null
        || samples.size() < 2
        || samples.size() > 50
        || settings == null
        || settings.topK() < 2
        || settings.topK() > 20
        || settings.seed() < 0
        || settings.seed() > Integer.MAX_VALUE
        || settings.candidatesPerArm() < 1
        || settings.candidatesPerArm() > 4
        || settings.budgetKrw() == null
        || settings.budgetKrw().stripTrailingZeros().scale() > 0
        || settings.budgetKrw().compareTo(BigDecimal.ONE) < 0)
      throw new SearchGenerationException(ErrorCode.REQUEST_INVALID);
    if (settings.budgetKrw().compareTo(model.model().path("budget").decimalValue()) > 0)
      throw new SearchGenerationException(ErrorCode.BUDGET_EXCEEDED);
    if (!json.hash(model.source()).equals(model.hash()))
      throw new SearchGenerationException(ErrorCode.RESULT_QUALITY_FAILED);
    for (var s : samples) {
      if (s == null
          || s.jobId() == null
          || s.versionId() == null
          || s.score() == null
          || s.costKrw() == null
          || s.inputHash() == null
          || s.placementsSource() == null)
        throw new SearchGenerationException(ErrorCode.REQUEST_INVALID);
      if (s.score().compareTo(BigDecimal.valueOf(100)) > 0
          || s.score().compareTo(BigDecimal.valueOf(-99999999)) < 0)
        throw new SearchGenerationException(ErrorCode.RESULT_QUALITY_FAILED);
    }
    var cells = cells(model);
    var unitCosts = costs(model);
    int maxPlacements = model.model().path("maxPlacements").asInt();
    Set<UUID> ids = new HashSet<>();
    Map<String, Source> unique = new TreeMap<>();
    List<Source> originals = new ArrayList<>();
    for (var s :
        samples.stream().sorted(Comparator.comparing(v -> v.jobId().toString())).toList()) {
      if (!ids.add(s.jobId()) || s.versionId() == null || s.score() == null || s.costKrw() == null)
        throw new SearchGenerationException(ErrorCode.REQUEST_INVALID);
      if (!json.hash(model.hash() + "\n" + s.placementsSource()).equals(s.inputHash()))
        throw new SearchGenerationException(ErrorCode.RESULT_QUALITY_FAILED);
      var placements = canonical(List.of(json.read(s.placementsSource(), Placement[].class)));
      BigDecimal cost =
          validation.validate(placements, cells, unitCosts, settings.budgetKrw(), maxPlacements);
      if (cost.compareTo(s.costKrw()) != 0)
        throw new SearchGenerationException(ErrorCode.RESULT_QUALITY_FAILED);
      String physical = inputHash(model.hash(), placements);
      var source = new Source(s, physical, placements, false);
      var previous = unique.putIfAbsent(physical, source);
      if (previous != null
          && (previous.sample().score().compareTo(s.score()) != 0
              || previous.sample().costKrw().compareTo(s.costKrw()) != 0))
        throw new SearchGenerationException(ErrorCode.RESULT_QUALITY_FAILED);
      originals.add(source);
    }
    if (unique.size() < 2)
      throw new SearchGenerationException(ErrorCode.SEARCH_SAMPLE_INSUFFICIENT);
    var ranked =
        unique.values().stream()
            .sorted(
                Comparator.comparing((Source s) -> s.sample().score())
                    .reversed()
                    .thenComparing(Source::physicalHash))
            .toList();
    BigDecimal cutoff = ranked.get(Math.min(settings.topK(), ranked.size()) - 1).sample().score();
    var elite = ranked.stream().filter(s -> s.sample().score().compareTo(cutoff) >= 0).toList();
    Set<UUID> selected = new HashSet<>();
    elite.forEach(s -> selected.add(s.sample().jobId()));
    var sources =
        originals.stream()
            .map(
                s ->
                    new Source(
                        s.sample(),
                        s.physicalHash(),
                        s.placements(),
                        selected.contains(s.sample().jobId())))
            .toList();
    var distributions = distributions(cells, unitCosts, elite);
    var candidates = new ArrayList<Candidate>();
    var arms = new ArrayList<ArmSummary>();
    for (var arm : SearchArm.values()) {
      Set<String> accepted = new HashSet<>();
      int empty = 0, original = 0, duplicate = 0, attempt = 0;
      while (attempt < DRAW_LIMIT && accepted.size() < settings.candidatesPerArm()) {
        int current = attempt++;
        var order =
            distributions.stream()
                .sorted(
                    Comparator.comparing(
                            (Distribution d) ->
                                randomKey(
                                    model.hash(),
                                    settings.seed(),
                                    arm,
                                    current,
                                    "ORDER",
                                    d.cellId()))
                        .thenComparing(Distribution::cellId))
                .toList();
        var placements = new ArrayList<Placement>();
        BigDecimal remaining = settings.budgetKrw();
        for (var d : order) {
          BigDecimal available = remaining;
          var options =
              d.options().stream()
                  .filter(
                      o ->
                          o.facilityType() == null
                              || (placements.size() < maxPlacements
                                  && o.costKrw().compareTo(available) <= 0))
                  .toList();
          int weight = options.stream().mapToInt(o -> weight(arm, o)).sum();
          int ticket =
              new BigInteger(
                      randomKey(model.hash(), settings.seed(), arm, current, "CHOICE", d.cellId()),
                      16)
                  .mod(BigInteger.valueOf(weight))
                  .intValueExact();
          Option picked = options.getFirst();
          for (var option : options) {
            ticket -= weight(arm, option);
            if (ticket < 0) {
              picked = option;
              break;
            }
          }
          if (picked.facilityType() != null) {
            placements.add(new Placement(d.cellId(), picked.facilityType(), picked.areaM2()));
            remaining = remaining.subtract(picked.costKrw());
          }
        }
        var canonical = canonical(placements);
        String hash = inputHash(model.hash(), canonical);
        if (canonical.isEmpty()) {
          empty++;
          continue;
        }
        if (unique.containsKey(hash)) {
          original++;
          continue;
        }
        if (!accepted.add(hash)) {
          duplicate++;
          continue;
        }
        BigDecimal cost =
            validation.validate(canonical, cells, unitCosts, settings.budgetKrw(), maxPlacements);
        candidates.add(
            new Candidate(
                arm,
                accepted.size(),
                current,
                hash,
                json.write(canonical),
                canonical,
                normalized(cost)));
      }
      if (accepted.size() != settings.candidatesPerArm())
        throw new SearchGenerationException(ErrorCode.CANDIDATE_SPACE_EXHAUSTED);
      arms.add(new ArmSummary(arm, attempt, empty, original, duplicate));
    }
    Set<String> pattern = new HashSet<>();
    candidates.stream()
        .filter(c -> c.arm() == SearchArm.PATTERN)
        .forEach(c -> pattern.add(c.inputHash()));
    int shared =
        (int)
            candidates.stream()
                .filter(c -> c.arm() == SearchArm.UNIFORM && pattern.contains(c.inputHash()))
                .count();
    return new SearchGeneration(
        1,
        POLICY,
        model.hash(),
        settings,
        samples.size(),
        unique.size(),
        elite.size(),
        cutoff,
        1,
        BINS,
        DRAW_LIMIT,
        sources,
        distributions,
        List.copyOf(arms),
        List.copyOf(candidates),
        shared);
  }

  private List<Distribution> distributions(
      Map<String, PlacementCell> cells, Map<FacilityType, BigDecimal> costs, List<Source> elite) {
    var result = new ArrayList<Distribution>();
    for (var cell : cells.values()) {
      Map<String, Integer> counts = new HashMap<>();
      for (var source : elite) {
        var p = source.placements().stream().filter(v -> v.cellId().equals(cell.id())).findFirst();
        String key = "NONE";
        if (p.isPresent()) {
          int bin =
              BINS.stream()
                  .min(
                      Comparator.comparing(
                              (Integer b) ->
                                  p.get()
                                      .areaM2()
                                      .multiply(BigDecimal.valueOf(100))
                                      .subtract(cell.maxAreaM2().multiply(BigDecimal.valueOf(b)))
                                      .abs())
                          .thenComparingInt(Integer::intValue))
                  .orElseThrow();
          key = p.get().facilityType().name() + ":" + bin;
        }
        counts.merge(key, 1, Integer::sum);
      }
      var options = new ArrayList<Option>();
      int none = counts.getOrDefault("NONE", 0);
      options.add(new Option("NONE", null, 0, BigDecimal.ZERO, BigDecimal.ZERO, none, none + 1));
      for (var type :
          cell.allowedTypes().stream().sorted(Comparator.comparing(Enum::name)).toList())
        for (int bin : BINS) {
          var area =
              normalized(
                  cell.maxAreaM2()
                      .multiply(BigDecimal.valueOf(bin))
                      .divide(BigDecimal.valueOf(100), 2, RoundingMode.HALF_UP));
          if (area.signum() == 0) continue;
          String key = type.name() + ":" + bin;
          int count = counts.getOrDefault(key, 0);
          options.add(
              new Option(
                  key,
                  type,
                  bin,
                  area,
                  normalized(area.multiply(costs.get(type))),
                  count,
                  count + 1));
        }
      result.add(new Distribution(cell.id(), List.copyOf(options)));
    }
    return List.copyOf(result);
  }

  private Map<String, PlacementCell> cells(LabModel model) {
    Map<String, PlacementCell> cells = new TreeMap<>();
    for (var c : model.model().path("cells")) {
      Set<FacilityType> types = new HashSet<>();
      for (var t : c.path("allowedTypes")) types.add(FacilityType.valueOf(t.asString()));
      cells.put(
          c.path("id").asString(),
          new PlacementCell(
              c.path("id").asString(), types, c.path("maxAreaM2").decimalValue(), true));
    }
    return cells;
  }

  private Map<FacilityType, BigDecimal> costs(LabModel model) {
    Map<FacilityType, BigDecimal> values = new EnumMap<>(FacilityType.class);
    for (var type : FacilityType.values())
      values.put(type, model.model().path("unitCosts").path(type.name()).decimalValue());
    return values;
  }

  private List<Placement> canonical(List<Placement> input) {
    // 숫자 표기만 다른 저장본도 같은 물리 배치로 학습한다. 원본 hash는 별도로 보존한다.
    if (input.stream()
        .anyMatch(
            p -> p == null || p.cellId() == null || p.facilityType() == null || p.areaM2() == null))
      throw new SearchGenerationException(ErrorCode.RESULT_QUALITY_FAILED);
    return input.stream()
        .map(p -> new Placement(p.cellId(), p.facilityType(), normalized(p.areaM2())))
        .sorted(Comparator.comparing(Placement::cellId))
        .toList();
  }

  private BigDecimal normalized(BigDecimal value) {
    return new BigDecimal(value.stripTrailingZeros().toPlainString());
  }

  private String inputHash(String modelHash, List<Placement> placements) {
    return json.hash(modelHash + "\n" + json.write(placements));
  }

  private int weight(SearchArm arm, Option option) {
    return arm == SearchArm.PATTERN ? option.patternWeight() : 1;
  }

  private String randomKey(
      String modelHash, long seed, SearchArm arm, int attempt, String purpose, String cell) {
    return json.hash(
        String.join(
            "\n",
            POLICY,
            modelHash,
            Long.toString(seed),
            arm.name(),
            Integer.toString(attempt),
            purpose,
            cell));
  }
}
