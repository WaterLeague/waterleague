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
  private final JsonService json;
  private final CostRepository repository;

  public CostService(JsonService json, CostRepository repository) {
    this.json = json;
    this.repository = repository;
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
      value.put("version", "PUBLIC_REFERENCE_QUANTITY_V1");
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
      value.put("priceAdjustment", "NONE");
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
      if (!value.path("version").asString().equals("PUBLIC_REFERENCE_QUANTITY_V1")
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
}
