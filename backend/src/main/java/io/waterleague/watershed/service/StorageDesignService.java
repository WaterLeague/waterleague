package io.waterleague.watershed.service;

import io.waterleague.common.exception.*;
import io.waterleague.watershed.dto.WatershedRequest;
import io.waterleague.watershed.repository.WatershedCatalogRepository;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;

@Service
public class StorageDesignService {
  private static final String BASIS = "EXPLICIT_DESIGN_NOT_SITE_MEASURED";
  private static final String EVIDENCE = "회원 지정 저류조 설계; 현장 치수·입지·운영 상태 미확인";
  private final WatershedCatalogRepository catalog;

  public StorageDesignService(WatershedCatalogRepository catalog) {
    this.catalog = catalog;
  }

  public Map<String, Object> compile(WatershedRequest.StorageRequest request, Set<String> ids) {
    if (!WatershedCatalogRepository.STORAGE_HASH.equals(request.catalogHash()))
      throw new DomainException(ErrorCode.CONFLICT);
    var source = catalog.storage();
    var rows = new ArrayList<Map<String, Object>>();
    var connections = new HashMap<String, JsonNode>();
    source.path("connections").forEach(c -> connections.put(c.path("id").asString(), c));
    if (request.placements() == null
        || request.placements().isEmpty()
        || request.placements().size() > 20) throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    for (var p :
        request.placements().stream()
            .sorted(Comparator.comparing(WatershedRequest.StorageItem::id))
            .toList()) {
      var connection = connections.get(p.connectionId());
      if (connection == null
          || !ids.add(p.id().toUpperCase(Locale.ROOT))
          || !p.id().matches("[A-Za-z][A-Za-z0-9_-]{0,23}")
          || p.areaM2().signum() <= 0
          || p.depthM().signum() <= 0
          || p.initialDepthM().signum() < 0
          || p.initialDepthM().compareTo(p.depthM()) > 0
          || p.overflow().crestM().compareTo(p.drain().crestM()) <= 0)
        throw new DomainException(ErrorCode.PLACEMENT_INVALID);
      var value = new TreeMap<String, Object>();
      value.put("id", p.id());
      value.put("facilityType", "UNDERGROUND_STORAGE");
      value.put("basis", BASIS);
      value.put("evidence", EVIDENCE);
      value.put("invertM", number(p.invertM()));
      value.put(
          "depthAreaCurve",
          List.of(
              Map.of("depthM", BigDecimal.ZERO, "areaM2", number(p.areaM2())),
              Map.of("depthM", number(p.depthM()), "areaM2", number(p.areaM2()))));
      value.put("initialDepthM", number(p.initialDepthM()));
      value.put("surchargeDepthM", BigDecimal.ZERO);
      value.put("cover", "COVERED");
      value.put("lining", "SEALED");
      value.put("inlet", port(p.inlet(), connection.path("inlet"), p));
      value.put("drain", port(p.drain(), connection.path("receiver"), p));
      value.put("overflow", port(p.overflow(), connection.path("receiver"), p));
      rows.add(value);
    }
    return Map.of(
        "catalogHash",
        request.catalogHash(),
        "schemaVersion",
        1,
        "sourceNetworkSha256",
        source.path("baseNetworkSha256").asString(),
        "placements",
        rows);
  }

  private static BigDecimal number(BigDecimal value) {
    return new BigDecimal(value.stripTrailingZeros().toPlainString());
  }

  private Map<String, Object> port(
      WatershedRequest.Port port, JsonNode node, WatershedRequest.StorageItem tank) {
    BigDecimal floor = node.path("invertM").decimalValue();
    BigDecimal top = floor.add(node.path("maxDepthM").decimalValue());
    // 개구부 전체가 두 절점의 유효 높이 안에 있어야 수두 연결로 취급한다.
    if (port.crestM().compareTo(floor.max(tank.invertM())) < 0
        || port.diameterM().signum() <= 0
        || port.dischargeCoefficient().signum() <= 0
        || port.dischargeCoefficient().compareTo(BigDecimal.ONE) > 0
        || port.crestM().add(port.diameterM()).compareTo(top.min(tank.invertM().add(tank.depthM())))
            > 0) throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    return new TreeMap<>(
        Map.of(
            "nodeId",
            node.path("id").asString(),
            "crestM",
            number(port.crestM()),
            "diameterM",
            number(port.diameterM()),
            "dischargeCoefficient",
            number(port.dischargeCoefficient()),
            "flapGate",
            port.flapGate(),
            "evidence",
            EVIDENCE));
  }
}
