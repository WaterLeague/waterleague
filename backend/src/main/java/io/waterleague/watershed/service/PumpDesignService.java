package io.waterleague.watershed.service;

import io.waterleague.common.exception.*;
import io.waterleague.watershed.dto.WatershedRequest;
import io.waterleague.watershed.repository.WatershedCatalogRepository;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.stereotype.Service;

@Service
public class PumpDesignService {
  private final WatershedCatalogRepository catalog;

  public PumpDesignService(WatershedCatalogRepository catalog) {
    this.catalog = catalog;
  }

  public Map<String, Object> compile(
      WatershedRequest.PumpRequest request,
      WatershedRequest.StorageRequest tanks,
      Set<String> ids) {
    if (!WatershedCatalogRepository.PUMP_HASH.equals(request.catalogHash()))
      throw new DomainException(ErrorCode.CONFLICT);
    if (request.placements() == null
        || request.placements().isEmpty()
        || request.placements().size() > 20) throw new DomainException(ErrorCode.PLACEMENT_INVALID);
    var nodes = new HashMap<String, BigDecimal>();
    var graph = new HashMap<String, Set<String>>();
    var source = catalog.storage();
    source
        .path("connections")
        .forEach(
            c -> {
              for (var key : List.of("inlet", "receiver")) {
                var n = c.path(key);
                nodes.put(n.path("id").asString(), n.path("maxDepthM").decimalValue());
              }
            });
    catalog
        .layout()
        .path("links")
        .forEach(
            l ->
                graph
                    .computeIfAbsent(l.path("fromNode").asString(), k -> new HashSet<>())
                    .add(l.path("toNode").asString()));
    var targets = Set.copyOf(nodes.keySet());
    if (tanks != null)
      for (var t : tanks.placements()) {
        var c =
            source
                .path("connections")
                .valueStream()
                .filter(v -> v.path("id").asString().equals(t.connectionId()))
                .findFirst()
                .orElseThrow(() -> new DomainException(ErrorCode.PLACEMENT_INVALID));
        String id = "WLST_" + t.id();
        nodes.put(id, t.depthM());
        graph.computeIfAbsent(c.path("inlet").path("id").asString(), k -> new HashSet<>()).add(id);
        graph
            .computeIfAbsent(id, k -> new HashSet<>())
            .add(c.path("receiver").path("id").asString());
      }
    var rows = new ArrayList<Map<String, Object>>();
    var pairs = new HashSet<String>();
    for (var p :
        request.placements().stream()
            .sorted(Comparator.comparing(WatershedRequest.PumpItem::id))
            .toList()) {
      var pipe = p.delivery();
      if (!ids.add(p.id().toUpperCase(Locale.ROOT))
          || !nodes.containsKey(p.fromNode())
          || !targets.contains(p.toNode())
          || p.fromNode().equals(p.toNode())
          || !reachable(graph, p.fromNode()).contains(p.toNode())
          || !pairs.add(p.fromNode() + "\n" + p.toNode())
          || p.stopDepthM().signum() <= 0
          || p.startDepthM().compareTo(p.stopDepthM()) <= 0
          || p.startDepthM().compareTo(nodes.get(p.fromNode())) > 0
          || pipe.pressureHeadLimitM().compareTo(pipe.diameterM()) <= 0
          || pipe.roughnessMm().compareTo(pipe.diameterM().multiply(new BigDecimal("1000"))) >= 0)
        throw new DomainException(ErrorCode.PLACEMENT_INVALID);
      var delivery = new TreeMap<String, Object>();
      delivery.put("lengthM", number(pipe.lengthM()));
      delivery.put("diameterM", number(pipe.diameterM()));
      delivery.put("roughnessMm", number(pipe.roughnessMm()));
      delivery.put("pressureHeadLimitM", number(pipe.pressureHeadLimitM()));
      delivery.put("entranceLoss", number(pipe.entranceLoss()));
      delivery.put("exitLoss", number(pipe.exitLoss()));
      delivery.put("averageLoss", number(pipe.averageLoss()));
      delivery.put("checkValve", pipe.checkValve());
      delivery.put("evidence", "회원 지정 압력관 설계; 현장 길이·재료·손실 미확인");
      var row = new TreeMap<String, Object>();
      row.put("id", p.id());
      row.put("facilityType", "PUMP_STATION");
      row.put("basis", "EXPLICIT_DESIGN_NOT_SITE_MEASURED");
      row.put("evidence", "회원 지정 펌프 연결·운전 설계; 서울 기존 펌프와 구분");
      row.put("curveId", catalog.pumps().path("id").asString());
      row.put("fromNode", p.fromNode());
      row.put("toNode", p.toNode());
      row.put("startDepthM", number(p.startDepthM()));
      row.put("stopDepthM", number(p.stopDepthM()));
      row.put("initialStatus", p.initialStatus());
      row.put("delivery", delivery);
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

  private static Set<String> reachable(Map<String, Set<String>> graph, String start) {
    var seen = new HashSet<String>();
    var queue = new ArrayDeque<String>();
    seen.add(start);
    queue.add(start);
    while (!queue.isEmpty())
      for (var n : graph.getOrDefault(queue.remove(), Set.of())) if (seen.add(n)) queue.add(n);
    return seen;
  }

  private static BigDecimal number(BigDecimal v) {
    return new BigDecimal(v.stripTrailingZeros().toPlainString());
  }
}
