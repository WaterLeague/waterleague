package io.waterleague.installation.service;

import io.waterleague.account.repository.AccountRepository;
import io.waterleague.account.service.AccountService;
import io.waterleague.common.exception.*;
import io.waterleague.district.repository.DistrictRepository;
import io.waterleague.installation.dto.InstallRequest;
import io.waterleague.installation.entity.SharedInstallation;
import io.waterleague.installation.exception.InstallationException;
import io.waterleague.installation.repository.InstallationRepository;
import io.waterleague.model.service.LabModelService;
import io.waterleague.strategy.entity.Placement;
import java.time.Instant;
import java.util.*;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InstallationService {
  private final InstallationRepository installations;
  private final DistrictRepository districts;
  private final AccountRepository accounts;
  private final AccountService auth;
  private final LabModelService models;
  private final io.waterleague.model.repository.LabModelRepository registry;

  public InstallationService(
      InstallationRepository i,
      DistrictRepository d,
      AccountRepository a,
      AccountService auth,
      LabModelService m,
      io.waterleague.model.repository.LabModelRepository registry) {
    installations = i;
    districts = d;
    accounts = a;
    this.auth = auth;
    models = m;
    this.registry = registry;
  }

  public List<SharedInstallation> active() {
    return installations.active();
  }

  public List<io.waterleague.installation.view.SiteView> sites() {
    var sites = new ArrayList<io.waterleague.installation.view.SiteView>();
    for (var district : districts.all()) {
      var model = registry.require(district.modelHash()).model();
      var costs = new LinkedHashMap<String, java.math.BigDecimal>();
      for (var f : io.waterleague.strategy.entity.FacilityType.values())
        costs.put(f.name(), model.path("unitCosts").path(f.name()).decimalValue());
      for (var cell : model.path("cells")) {
        var coordinates = new ArrayList<List<Double>>();
        for (var p : cell.path("coordinates"))
          coordinates.add(
              List.of(
                  p.get(0).asDouble() + district.center().get(0),
                  p.get(1).asDouble() + district.center().get(1)));
        var types = new ArrayList<String>();
        for (var t : cell.path("allowedTypes")) types.add(t.asString());
        sites.add(
            new io.waterleague.installation.view.SiteView(
                district.id(),
                cell.path("id").asString(),
                cell.path("name").asString(),
                cell.path("kind").asString(),
                coordinates,
                List.of(
                    cell.path("center").get(0).asDouble() + district.center().get(0),
                    cell.path("center").get(1).asDouble() + district.center().get(1)),
                cell.path("heightM").asDouble(),
                cell.path("maxAreaM2").decimalValue(),
                types,
                costs,
                model.path("budget").decimalValue(),
                district.modelHash()));
      }
    }
    return List.copyOf(sites);
  }

  @Transactional
  public SharedInstallation install(String username, InstallRequest request) {
    var account = accounts.lock(auth.current(username).id());
    if (!account.usable() || !account.role().equals("MEMBER"))
      throw new InstallationException(ErrorCode.ACCESS_DENIED);
    if (account.districtId() == null) throw new InstallationException(ErrorCode.DISTRICT_REQUIRED);
    if (!account.districtId().equals(request.districtId()))
      throw new InstallationException(ErrorCode.DISTRICT_ACCESS_DENIED);
    var district = districts.require(account.districtId());
    var placement = new Placement(request.cellId(), request.facilityType(), request.areaM2());
    var own = installations.owned(account.id());
    if (own.stream().anyMatch(i -> i.cellId().equals(request.cellId())))
      throw new InstallationException(ErrorCode.SITE_OCCUPIED);
    var all = new ArrayList<Placement>();
    for (var i : own) all.add(new Placement(i.cellId(), i.facilityType(), i.areaM2()));
    all.add(placement);
    models.validate(district.modelHash(), all);
    var cost = models.validate(district.modelHash(), List.of(placement));
    var value =
        new SharedInstallation(
            UUID.randomUUID(),
            district.id(),
            request.cellId(),
            account.id(),
            account.displayName(),
            district.modelHash(),
            request.facilityType(),
            request.areaM2(),
            cost,
            Instant.now(),
            null);
    // 사용자별 예산 잠금과 별개로 위치 고유 제약이 서로 다른 회원의 동시 설치를 직렬화한다.
    try {
      installations.add(value);
    } catch (DuplicateKeyException e) {
      throw new InstallationException(ErrorCode.SITE_OCCUPIED);
    }
    return value;
  }

  @Transactional
  public void remove(String username, UUID id) {
    var account = accounts.lock(auth.current(username).id());
    var value =
        installations
            .find(id)
            .orElseThrow(() -> new InstallationException(ErrorCode.RESOURCE_NOT_FOUND));
    if (!account.usable()
        || !value.ownerId().equals(account.id())
        || !value.districtId().equals(account.districtId()))
      throw new InstallationException(ErrorCode.ACCESS_DENIED);
    if (!installations.remove(id, account.id(), Instant.now()))
      throw new InstallationException(ErrorCode.CONFLICT);
  }
}
