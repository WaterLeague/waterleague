package io.waterleague.watershed.service;

import io.waterleague.common.exception.*;
import io.waterleague.watershed.dto.WatershedRequest;
import io.waterleague.watershed.repository.WatershedCostRepository;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.*;
import org.springframework.stereotype.Service;

@Service
public class WatershedCostService {
  private final WatershedCostRepository catalog;

  public WatershedCostService(WatershedCostRepository catalog) {
    this.catalog = catalog;
  }

  public Map<String, Object> snapshot(String hash, List<WatershedRequest.Item> placements) {
    if (!WatershedCostRepository.HASH.equals(hash)) throw new DomainException(ErrorCode.CONFLICT);
    var data = catalog.value();
    var items = new ArrayList<Map<String, Object>>();
    var unpriced = new ArrayList<String>();
    BigDecimal subtotal = BigDecimal.ZERO;
    for (var p :
        placements.stream().sorted(Comparator.comparing(WatershedRequest.Item::id)).toList()) {
      var quote = data.path("entries").path(p.facilityType());
      if (quote.isMissingNode()) throw new DomainException(ErrorCode.PLACEMENT_INVALID);
      BigDecimal amount = null;
      // 규격이 다른 선형 시설의 단가를 면적 단가로 전용하지 않는다.
      if (quote.path("status").asString().equals("AREA_REFERENCE_ONLY")) {
        amount =
            p.areaM2()
                .multiply(quote.path("unitPriceKrw").decimalValue())
                .setScale(0, RoundingMode.HALF_UP);
        subtotal = subtotal.add(amount);
      } else unpriced.add(p.id());
      var item = new TreeMap<String, Object>();
      item.put("placementId", p.id());
      item.put("facilityType", p.facilityType());
      item.put("areaM2", p.areaM2().setScale(2));
      item.put("status", quote.path("status").asString());
      item.put("referenceAmountKrw", amount);
      item.put("notes", quote.path("notes"));
      items.add(item);
    }
    var result = new TreeMap<String, Object>();
    result.put("schemaVersion", 1);
    result.put("catalogHash", hash);
    result.put("classification", data.path("classification").asString());
    result.put("source", data.path("source"));
    result.put("limitations", data.path("limitations"));
    result.put("items", items);
    result.put("knownReferenceSubtotalKrw", items.size() == unpriced.size() ? null : subtotal);
    result.put("unpricedPlacementIds", unpriced);
    result.put("completeInstalledCostKrw", null);
    result.put("budgetChargedKrw", null);
    return result;
  }
}
