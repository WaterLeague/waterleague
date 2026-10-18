package io.waterleague.installation.service;

import io.waterleague.account.repository.AccountRepository;
import io.waterleague.account.service.AccountService;
import io.waterleague.common.exception.*;
import io.waterleague.district.repository.DistrictRepository;
import io.waterleague.installation.dto.InstallRequest;
import io.waterleague.installation.entity.SharedInstallation;
import io.waterleague.installation.exception.InstallationException;
import io.waterleague.installation.repository.InstallationRepository;
import io.waterleague.strategy.entity.Placement;
import java.time.Instant;
import java.util.*;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InstallationService {
  private final InstallationRepository installations;
  private final io.waterleague.budget.service.BudgetService budget;
  private final DistrictRepository districts;
  private final AccountRepository accounts;
  private final AccountService auth;
  private final io.waterleague.common.service.JsonService json;
  private final io.waterleague.installation.repository.SiteCatalogRepository sites;
  private final io.waterleague.strategy.service.PlacementValidationService validation;

  public InstallationService(
      InstallationRepository i,
      io.waterleague.budget.service.BudgetService budget,
      DistrictRepository d,
      AccountRepository a,
      AccountService auth,
      io.waterleague.common.service.JsonService json,
      io.waterleague.installation.repository.SiteCatalogRepository sites,
      io.waterleague.strategy.service.PlacementValidationService validation) {
    installations = i;
    this.budget = budget;
    districts = d;
    accounts = a;
    this.auth = auth;
    this.json = json;
    this.sites = sites;
    this.validation = validation;
  }

  public List<SharedInstallation> active() {
    return installations.active();
  }

  public io.waterleague.installation.view.SitePageView sites(
      String districtId,
      double x,
      double y,
      int offset,
      io.waterleague.strategy.entity.FacilityType type,
      boolean vacant) {
    if (!Double.isFinite(x)
        || !Double.isFinite(y)
        || Math.abs(x) > 100000
        || Math.abs(y) > 100000
        || offset < 0
        || offset > 300000) throw new InstallationException(ErrorCode.REQUEST_INVALID);
    if (districtId == null || districtId.isEmpty())
      return new io.waterleague.installation.view.SitePageView(
          List.of(), sites.counts(), 0, 0, 200);
    var occupied = new HashSet<String>();
    if (vacant)
      for (var i : installations.active())
        if (i.districtId().equals(districtId)) occupied.add(i.cellId());
    var matched =
        sites.district(districtId).values().stream()
            .filter(v -> type == null || v.allowedTypes().contains(type.name()))
            .filter(v -> !occupied.contains(v.cellId()))
            .filter(v -> !vacant || v.existingInfrastructure() == null)
            .sorted(
                Comparator.comparingDouble(
                        (io.waterleague.installation.view.SiteView v) ->
                            Math.hypot(v.center().get(0) - x, v.center().get(1) - y))
                    .thenComparing(v -> v.cellId()))
            .toList();
    return new io.waterleague.installation.view.SitePageView(
        matched.stream().skip(offset).limit(200).toList(),
        sites.counts(),
        matched.size(),
        offset,
        200);
  }

  public io.waterleague.installation.view.SiteView building(String districtId, String sourceId) {
    return sites.building(districtId, sourceId);
  }

  public io.waterleague.installation.view.SiteView site(String districtId, String cellId) {
    return sites.require(districtId, cellId);
  }

  public io.waterleague.installation.view.InstallationView view(SharedInstallation i) {
    return io.waterleague.installation.mapper.InstallationMapper.view(
        i, sites.require(i.districtId(), i.cellId()));
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
    var site = sites.requireInstallable(district.id(), request.cellId());
    var cells = new HashMap<String, io.waterleague.strategy.entity.PlacementCell>();
    for (var p : List.of(placement)) {
      var c = sites.require(district.id(), p.cellId());
      var types = new HashSet<io.waterleague.strategy.entity.FacilityType>();
      for (var t : c.allowedTypes())
        types.add(io.waterleague.strategy.entity.FacilityType.valueOf(t));
      cells.put(
          c.cellId(),
          new io.waterleague.strategy.entity.PlacementCell(c.cellId(), types, c.maxAreaM2(), true));
    }
    var costs =
        new EnumMap<io.waterleague.strategy.entity.FacilityType, java.math.BigDecimal>(
            io.waterleague.strategy.entity.FacilityType.class);
    site.unitCosts()
        .forEach((t, c) -> costs.put(io.waterleague.strategy.entity.FacilityType.valueOf(t), c));
    var cost = validation.validate(List.of(placement), cells, costs, budget.limit(), 1);
    budget.requireAvailable(account.id(), request.facilityType(), cost);
    var value =
        new SharedInstallation(
            UUID.randomUUID(),
            district.id(),
            request.cellId(),
            account.id(),
            account.displayName(),
            site.modelHash(),
            request.facilityType(),
            request.areaM2(),
            cost,
            Instant.now(),
            null);
    // 회원별 예산 잠금과 위치 고유 제약으로 초과 배정·중복 점유를 차단한다.
    try {
      installations.add(value, json.write(budget.policy()), json.write(sites.publicAssetPolicy()));
    } catch (DuplicateKeyException e) {
      throw new InstallationException(ErrorCode.SITE_OCCUPIED);
    }
    budget.allocate(account.id(), value.id(), value.facilityType());
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
    budget.lock(account.id());
    if (!installations.remove(id, account.id(), Instant.now()))
      throw new InstallationException(ErrorCode.CONFLICT);
    budget.release(account.id(), id);
  }
}
