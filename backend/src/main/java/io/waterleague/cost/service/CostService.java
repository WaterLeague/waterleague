package io.waterleague.cost.service;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.exception.ErrorCode;
import io.waterleague.common.service.JsonService;
import io.waterleague.cost.entity.CostSnapshot;
import io.waterleague.cost.exception.CostException;
import io.waterleague.cost.repository.CostRepository;
import io.waterleague.cost.view.CostRecordView;
import io.waterleague.installation.view.SiteView;
import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.stereotype.Service;

@Service
public class CostService {
  private static final tools.jackson.databind.ObjectReader EXACT_JSON =
      new tools.jackson.databind.ObjectMapper()
          .reader()
          .with(tools.jackson.databind.DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS);
  private final JsonService json;
  private final CostRepository repository;
  private final io.waterleague.cost.repository.GamePriceCatalog prices;

  public CostService(
      JsonService json,
      CostRepository repository,
      io.waterleague.cost.repository.GamePriceCatalog prices) {
    this.json = json;
    this.repository = repository;
    this.prices = prices;
  }

  public CostSnapshot snapshot(
      SiteView site, FacilityType type, BigDecimal area, BigDecimal charge) {
    try {
      var source = site.costModel().path("facilities").path(type.name());
      var unit = site.unitCosts().get(type.name());
      if (!site.allowedTypes().contains(type.name())
          || area.signum() <= 0
          || area.scale() > 2
          || area.compareTo(site.maxAreaFor(type)) > 0
          || !source.isObject()
          || unit == null
          || unit.compareTo(source.path("unitCost").decimalValue()) != 0
          || charge.compareTo(unit.multiply(area)) != 0
          || !source.path("sourceSha256").asString().matches("[a-f0-9]{64}"))
        throw new CostException();
      var value = new LinkedHashMap<String, Object>();
      boolean indexed = source.has("priceAdjustment");
      value.put(
          "version", indexed ? "PUBLIC_REFERENCE_QUANTITY_V2" : "PUBLIC_REFERENCE_QUANTITY_V1");
      value.put("currency", "KRW");
      value.put("districtId", site.districtId());
      value.put("cellId", site.cellId());
      value.put("siteModelHash", site.modelHash());
      value.put("facilityType", type);
      value.put("quantityM2", area);
      value.put("unitCostKrw", unit);
      value.put("referenceSubtotalKrw", charge);
      value.put("budgetChargeKrw", charge);
      value.put("completeInstalledCostKrw", null);
      value.put("priceBaseYear", null);
      value.put("vat", "UNCONFIRMED");
      value.put(
          "priceAdjustment",
          indexed ? source.path("priceAdjustment").path("method").asString() : "NONE");
      value.put("currentPriceVerified", false);
      value.put("historicalPriceEligible", false);
      value.put("costSourceSha256", site.costSourceSha256());
      value.put("source", source.deepCopy());
      // 공개 단가는 묶음 금액이므로 원문에 없는 자재·노무비 비율을 만들지 않는다.
      value.put(
          "lines",
          List.of(
              Map.of(
                  "id",
                  "REFERENCE_INSTALLATION",
                  "label",
                  source.path("scope").asString(),
                  "quantity",
                  area,
                  "quantityUnit",
                  "M2",
                  "unitCostKrw",
                  unit,
                  "amountKrw",
                  charge)));
      var unresolved = new ArrayList<Map<String, Object>>();
      for (var item : source.path("excludes")) {
        var row = new LinkedHashMap<String, Object>();
        row.put("label", item.asString());
        row.put("amountKrw", null);
        row.put("status", "UNPRICED");
        unresolved.add(row);
      }
      value.put("unpricedItems", unresolved);
      var raw = json.write(value);
      return new CostSnapshot(raw, json.hash(raw));
    } catch (RuntimeException e) {
      throw new CostException();
    }
  }

  public CostRecordView active(UUID id) {
    var row =
        repository.active(id).orElseThrow(() -> new DomainException(ErrorCode.RESOURCE_NOT_FOUND));
    if (row.raw() == null && row.sha256() == null)
      return new CostRecordView("NOT_RECORDED", null, null);
    try {
      if (row.raw() == null || !json.hash(row.raw()).equals(row.sha256()))
        throw new CostException();
      var value = json.tree(row.raw());
      if (!Set.of("PUBLIC_REFERENCE_QUANTITY_V1", "PUBLIC_REFERENCE_QUANTITY_V2")
              .contains(value.path("version").asString())
          || !value.path("districtId").asString().equals(row.districtId())
          || !value.path("cellId").asString().equals(row.cellId())
          || !value.path("siteModelHash").asString().equals(row.modelHash())
          || !value.path("facilityType").asString().equals(row.facilityType())
          || value.path("quantityM2").decimalValue().compareTo(row.areaM2()) != 0
          || value.path("budgetChargeKrw").decimalValue().compareTo(row.cost()) != 0)
        throw new CostException();
      return new CostRecordView("RECORDED", row.sha256(), value);
    } catch (RuntimeException e) {
      throw new CostException();
    }
  }

  public SiteView recordedSite(
      SiteView current, FacilityType type, BigDecimal area, String raw, String sha) {
    try {
      if (raw == null || raw.length() > 65536 || !json.hash(raw).equals(sha))
        throw new CostException();
      var record = json.tree(raw);
      var site = prices.site(current, record.path("costSourceSha256").asString());
      var expected = snapshot(site, type, area, site.unitCosts().get(type.name()).multiply(area));
      if (!same(EXACT_JSON.readTree(expected.raw()), EXACT_JSON.readTree(raw)))
        throw new CostException();
      return site;
    } catch (RuntimeException e) {
      throw new CostException();
    }
  }

  private static boolean same(
      tools.jackson.databind.JsonNode a, tools.jackson.databind.JsonNode b) {
    if (a == null || b == null) return a == b;
    // 10과 10.00의 표기 차이는 허용하되 금액은 십진수 원값으로 비교한다.
    if (a.isNumber() && b.isNumber()) return a.decimalValue().compareTo(b.decimalValue()) == 0;
    if (a.isObject() && b.isObject()) {
      if (a.size() != b.size()) return false;
      for (var entry : a.properties())
        if (!same(entry.getValue(), b.get(entry.getKey()))) return false;
      return true;
    }
    if (a.isArray() && b.isArray()) {
      if (a.size() != b.size()) return false;
      for (int i = 0; i < a.size(); i++) if (!same(a.get(i), b.get(i))) return false;
      return true;
    }
    return a.equals(b);
  }
}
