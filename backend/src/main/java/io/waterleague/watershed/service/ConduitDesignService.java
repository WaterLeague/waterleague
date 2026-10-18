package io.waterleague.watershed.service;

import io.waterleague.common.exception.*;
import io.waterleague.watershed.dto.WatershedRequest;
import io.waterleague.watershed.repository.WatershedCatalogRepository;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;

@Service
public class ConduitDesignService {
  private final WatershedCatalogRepository catalog;

  public ConduitDesignService(WatershedCatalogRepository catalog) {
    this.catalog = catalog;
  }

  public Map<String, Object> compile(WatershedRequest.ConduitRequest request, Set<String> ids) {
    if (!WatershedCatalogRepository.CONDUIT_HASH.equals(request.catalogHash()))
      throw new DomainException(ErrorCode.CONFLICT);
    var source = catalog.conduits();
    var sources = new HashMap<String, JsonNode>();
    source.path("conduits").forEach(c -> sources.put(c.path("id").asString(), c));
    if (request.placements() == null
        || request.placements().isEmpty()
        || request.placements().size() > 20) throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    var seen = new HashSet<String>();
    var rows = new ArrayList<Map<String, Object>>();
    for (var p :
        request.placements().stream()
            .sorted(Comparator.comparing(WatershedRequest.ConduitItem::id))
            .toList()) {
      var original = sources.get(p.conduitId());
      if (original == null
          || !seen.add(p.conduitId())
          || !ids.add(p.id().toUpperCase(Locale.ROOT))
          || !Set.of("CIRCULAR", "RECT_CLOSED").contains(p.shape())
          || (p.shape().equals("CIRCULAR") ? p.widthM() != null : p.widthM() == null)
          || p.fullDepthM().signum() <= 0
          || p.fullDepthM().compareTo(original.path("maxFullDepthM").decimalValue()) > 0
          || p.roughness().signum() <= 0
          || p.roughness().compareTo(BigDecimal.ONE) > 0)
        throw new DomainException(ErrorCode.PLACEMENT_INVALID);
      var row = new TreeMap<String, Object>();
      row.put("id", p.id());
      row.put("conduitId", p.conduitId());
      row.put("shape", p.shape());
      row.put("fullDepthM", number(p.fullDepthM()));
      row.put("widthM", p.widthM() == null ? null : number(p.widthM()));
      row.put("barrels", p.barrels());
      row.put("roughness", number(p.roughness()));
      row.put("basis", "EXPLICIT_DESIGN_NOT_SITE_MEASURED");
      row.put("evidence", "회원 지정 관로 개량 설계; 현장 치수·매설·시공 가능성 미확인");
      row.put("original", original.path("original"));
      rows.add(row);
    }
    return Map.of(
        "schemaVersion",
        1,
        "catalogHash",
        request.catalogHash(),
        "sourceNetworkSha256",
        source.path("baseNetworkSha256").asString(),
        "placements",
        rows);
  }

  private static BigDecimal number(BigDecimal value) {
    return new BigDecimal(value.stripTrailingZeros().toPlainString());
  }
}
