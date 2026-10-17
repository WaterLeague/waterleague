package io.waterleague.analysis.service;

import io.waterleague.analysis.entity.PatternSample;
import io.waterleague.analysis.view.PatternAnalysisView;
import io.waterleague.analysis.view.PatternAnalysisView.*;
import io.waterleague.common.exception.*;
import io.waterleague.strategy.entity.*;
import io.waterleague.strategy.service.PlacementIdentityService;
import java.math.*;
import java.util.*;
import org.springframework.stereotype.Service;

@Service
public class PatternAnalysisService {
  private final PlacementIdentityService identity;

  public PatternAnalysisService(PlacementIdentityService identity) {
    this.identity = identity;
  }

  private record Key(String cell, FacilityType type) implements Comparable<Key> {
    public int compareTo(Key other) {
      int order = cell.compareTo(other.cell);
      return order != 0 ? order : type.name().compareTo(other.type.name());
    }
  }

  public PatternAnalysisView analyze(String modelHash, List<PatternSample> source, int topK) {
    if (source.isEmpty() || topK < 1 || topK > 20) throw new IllegalArgumentException("분석 범위 오류");
    // 같은 물리 입력은 한 번만 집계하고 요청 순서와 무관한 대표 작업을 선택한다.
    Map<String, PatternSample> unique = new TreeMap<>();
    source.stream()
        .sorted(Comparator.comparing(s -> s.jobId().toString()))
        .forEach(
            s -> {
              var previous =
                  unique.putIfAbsent(identity.physicalHash(modelHash, s.placements()), s);
              if (previous != null
                  && (previous.score().compareTo(s.score()) != 0
                      || previous.cost().compareTo(s.cost()) != 0))
                throw new DomainException(ErrorCode.RESULT_QUALITY_FAILED);
            });
    var ranked =
        unique.values().stream()
            .sorted(
                Comparator.comparing(PatternSample::score)
                    .reversed()
                    .thenComparing(s -> identity.physicalHash(modelHash, s.placements())))
            .toList();
    BigDecimal cutoff = ranked.get(Math.min(topK, ranked.size()) - 1).score();
    var selected = ranked.stream().filter(s -> s.score().compareTo(cutoff) >= 0).toList();
    Map<Key, List<BigDecimal>> cells = new TreeMap<>();
    for (var sample : selected)
      for (var placement : sample.placements())
        cells
            .computeIfAbsent(
                new Key(placement.cellId(), placement.facilityType()), k -> new ArrayList<>())
            .add(placement.areaM2());
    List<PlacementFrequency> frequencies = new ArrayList<>();
    cells.forEach(
        (key, areas) -> {
          BigDecimal sum = areas.stream().reduce(BigDecimal.ZERO, BigDecimal::add);
          frequencies.add(
              new PlacementFrequency(
                  key.cell(),
                  key.type(),
                  areas.size(),
                  percent(areas.size(), selected.size()),
                  areas.stream().min(BigDecimal::compareTo).orElseThrow(),
                  areas.stream().max(BigDecimal::compareTo).orElseThrow(),
                  mean(sum, areas.size()),
                  mean(sum, selected.size())));
        });
    var types =
        Arrays.stream(FacilityType.values()).sorted(Comparator.comparing(Enum::name)).toList();
    List<FacilityPair> pairs = new ArrayList<>();
    for (int i = 0; i < types.size(); i++)
      for (int j = i + 1; j < types.size(); j++) {
        var first = types.get(i);
        var second = types.get(j);
        int count =
            (int)
                selected.stream()
                    .filter(
                        s ->
                            s.placements().stream().anyMatch(p -> p.facilityType() == first)
                                && s.placements().stream()
                                    .anyMatch(p -> p.facilityType() == second))
                    .count();
        pairs.add(new FacilityPair(first, second, count, percent(count, selected.size())));
      }
    return new PatternAnalysisView(
        modelHash,
        "SELECTED_UNIQUE_PHYSICAL_TOP_K_WITH_TIES_V2",
        source.size(),
        unique.size(),
        source.size() - unique.size(),
        topK,
        selected.size(),
        cutoff,
        selected.stream()
            .map(
                s ->
                    new SelectedDesign(
                        s.jobId(),
                        s.inputHash(),
                        identity.physicalHash(modelHash, s.placements()),
                        s.score(),
                        s.cost()))
            .toList(),
        frequencies,
        pairs,
        selected.stream().map(PatternSample::cost).min(BigDecimal::compareTo).orElseThrow(),
        selected.stream().map(PatternSample::cost).max(BigDecimal::compareTo).orElseThrow(),
        cutoff,
        selected.get(0).score(),
        List.of(
            "선택한 동의 자료의 고유 배치 집합이며 전체 시민이나 전체 리그의 대표 표본이 아닙니다.",
            "동점 경계를 모두 포함합니다. 설계 수이며 참여자 수가 아닙니다.",
            "배치 빈도는 효과 원인·통계적 유의성·현장 추천을 뜻하지 않습니다. 비용과 리그 제약이 다를 수 있습니다.",
            "빈도는 백분율 소수 2자리, 평균 면적은 m² 소수 4자리 HALF_UP 반올림입니다.",
            "탐색 모델의 기술 통계이며 학습 모델이나 현장 효과 검증이 아닙니다."));
  }

  private static BigDecimal mean(BigDecimal total, int count) {
    return total.divide(BigDecimal.valueOf(count), 4, RoundingMode.HALF_UP);
  }

  private static BigDecimal percent(int count, int total) {
    return BigDecimal.valueOf(count * 100L)
        .divide(BigDecimal.valueOf(total), 2, RoundingMode.HALF_UP);
  }
}
