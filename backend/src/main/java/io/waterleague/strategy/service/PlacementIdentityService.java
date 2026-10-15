package io.waterleague.strategy.service;

import io.waterleague.common.exception.*;
import io.waterleague.common.service.JsonService;
import io.waterleague.strategy.entity.Placement;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.stereotype.Service;

@Service
public class PlacementIdentityService {
  private final JsonService json;

  public PlacementIdentityService(JsonService json) {
    this.json = json;
  }

  public List<Placement> canonical(List<Placement> input) {
    if (input == null
        || input.stream()
            .anyMatch(
                p ->
                    p == null
                        || p.cellId() == null
                        || p.facilityType() == null
                        || p.areaM2() == null))
      throw new DomainException(ErrorCode.RESULT_QUALITY_FAILED);
    // 원본 저장 표현은 보존하고 집계·학습에 사용할 물리 배치만 정규화한다.
    return input.stream()
        .map(
            p ->
                new Placement(
                    p.cellId(),
                    p.facilityType(),
                    new BigDecimal(p.areaM2().stripTrailingZeros().toPlainString())))
        .sorted(Comparator.comparing(Placement::cellId))
        .toList();
  }

  public String physicalHash(String modelHash, List<Placement> input) {
    return json.hash(modelHash + "\n" + json.write(canonical(input)));
  }
}
