package io.waterleague.watershed.service;

import io.waterleague.common.exception.*;
import io.waterleague.watershed.dto.WatershedRequest;
import io.waterleague.watershed.repository.WatershedCatalogRepository;
import java.math.BigDecimal;
import java.util.*;
import tools.jackson.databind.JsonNode;

public final class CisternDesignService {
  private CisternDesignService() {}

  public static Map<String, Object> compile(
      WatershedRequest.CisternRequest request,
      WatershedCatalogRepository catalog,
      Set<String> ids,
      List<WatershedRequest.Item> lids) {
    if (!WatershedCatalogRepository.STORAGE_HASH.equals(request.catalogHash()))
      throw new DomainException(ErrorCode.CONFLICT);
    var p = request.placement();
    if (!p.isDrainConfigurationValid()) throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    boolean closed = Boolean.TRUE.equals(p.drainClosed());
    JsonNode host = null, receiver = null;
    for (var c : catalog.value().path("catchments"))
      if (c.path("id").asString().equals(p.catchmentId())) host = c;
    var shared = lids.stream().filter(l -> l.catchmentId().equals(p.catchmentId())).toList();
    if (host == null
        || host.path("imperviousM2").decimalValue().signum() <= 0
        || host.path("imperviousM2").decimalValue().compareTo(host.path("areaM2").decimalValue())
            > 0
        || shared.stream().anyMatch(l -> l.facilityType().equals("RAINWATER_CISTERN"))
        || !ids.add(p.id().toUpperCase(Locale.ROOT))
        || !p.id().matches("[A-Za-z][A-Za-z0-9_-]{0,23}"))
      throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    var allocated = p.captureAreaM2().add(p.areaM2());
    var lidArea = BigDecimal.ZERO;
    for (var lid : shared) {
      allocated = allocated.add(lid.areaM2()).add(lid.treatedImperviousM2());
      lidArea = lidArea.add(lid.areaM2());
    }
    var free =
        host.path("imperviousM2").decimalValue().subtract(p.captureAreaM2()).subtract(p.areaM2());
    if (allocated.compareTo(host.path("imperviousM2").decimalValue()) > 0
        || (!shared.isEmpty() && lidArea.compareTo(free.multiply(new BigDecimal("0.999"))) > 0))
      throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    for (var c : catalog.storage().path("connections"))
      for (String side : List.of("inlet", "receiver"))
        if (c.path(side).path("id").asString().equals(host.path("outletNodeId").asString()))
          receiver = c.path(side);
    if (receiver == null
        || p.captureAreaM2().signum() <= 0
        || p.areaM2().signum() <= 0
        || p.captureAreaM2().add(p.areaM2()).compareTo(host.path("imperviousM2").decimalValue()) > 0
        || p.depthM().signum() <= 0
        || p.initialDepthM().signum() < 0
        || p.initialDepthM().compareTo(p.depthM()) > 0
        || (!closed && p.overflow().crestM().compareTo(p.drain().crestM()) <= 0))
      throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    var result = new TreeMap<String, Object>();
    result.put(
        "schemaVersion",
        !shared.isEmpty()
            ? 3
            : host.path("imperviousM2").decimalValue().compareTo(host.path("areaM2").decimalValue())
                    == 0
                ? 1
                : 2);
    result.put("catalogHash", request.catalogHash());
    result.put("sourceNetworkSha256", catalog.storage().path("baseNetworkSha256").asString());
    result.put("id", p.id());
    result.put("subcatchmentId", p.catchmentId());
    result.put("captureAreaM2", number(p.captureAreaM2()));
    result.put("footprintM2", number(p.areaM2()));
    result.put("invertM", number(p.invertM()));
    result.put("initialDepthM", number(p.initialDepthM()));
    result.put(
        "depthAreaCurve",
        List.of(
            Map.of("depthM", BigDecimal.ZERO, "areaM2", number(p.areaM2())),
            Map.of("depthM", number(p.depthM()), "areaM2", number(p.areaM2()))));
    result.put(
        "drain", closed ? Map.of("mode", "CLOSED_NO_WITHDRAWAL") : port(p.drain(), receiver, p));
    result.put("overflow", port(p.overflow(), receiver, p));
    result.put("evidence", "회원 지정 집수·밀폐 이용조 설계; 실제 지붕·홈통·설치 높이 측정값 아님");
    return result;
  }

  private static BigDecimal number(BigDecimal value) {
    return new BigDecimal(value.stripTrailingZeros().toPlainString());
  }

  private static Map<String, Object> port(
      WatershedRequest.Port port, JsonNode node, WatershedRequest.CisternItem tank) {
    var floor = node.path("invertM").decimalValue();
    var top = floor.add(node.path("maxDepthM").decimalValue());
    if (port.crestM().compareTo(floor.max(tank.invertM())) < 0
        || port.diameterM().signum() <= 0
        || port.dischargeCoefficient().signum() <= 0
        || port.dischargeCoefficient().compareTo(BigDecimal.ONE) > 0
        || port.crestM().add(port.diameterM()).compareTo(top.min(tank.invertM().add(tank.depthM())))
            > 0) throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    return new TreeMap<>(
        Map.of(
            "crestM",
            number(port.crestM()),
            "diameterM",
            number(port.diameterM()),
            "dischargeCoefficient",
            number(port.dischargeCoefficient()),
            "flapGate",
            port.flapGate()));
  }
}
