package io.waterleague.installation.service;

import io.waterleague.account.repository.AccountRepository;
import io.waterleague.account.service.AccountService;
import io.waterleague.common.exception.ErrorCode;
import io.waterleague.common.service.JsonService;
import io.waterleague.facility.repository.CisternSpecificationRepository;
import io.waterleague.installation.dto.CisternPlanRequest;
import io.waterleague.installation.entity.CisternPlan;
import io.waterleague.installation.exception.CisternPlanException;
import io.waterleague.installation.mapper.CisternPlanMapper;
import io.waterleague.installation.repository.*;
import io.waterleague.installation.view.CisternPlanView;
import io.waterleague.watershed.repository.WatershedCostRepository;
import io.waterleague.watershed.service.CisternReferenceService;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CisternPlanService {
  private final CisternPlanRepository plans;
  private final SiteCatalogRepository sites;
  private final AccountRepository accounts;
  private final AccountService auth;
  private final JsonService json;
  private final WatershedCostRepository costs;
  private final CisternSpecificationRepository specifications;

  public CisternPlanService(
      CisternPlanRepository plans,
      SiteCatalogRepository sites,
      AccountRepository accounts,
      AccountService auth,
      JsonService json,
      WatershedCostRepository costs,
      CisternSpecificationRepository specifications) {
    this.plans = plans;
    this.sites = sites;
    this.accounts = accounts;
    this.auth = auth;
    this.json = json;
    this.costs = costs;
    this.specifications = specifications;
  }

  private io.waterleague.account.entity.Account member(String username) {
    var account = auth.current(username);
    if (!account.usable() || !account.role().equals("MEMBER"))
      throw new CisternPlanException(ErrorCode.ACCESS_DENIED);
    return account;
  }

  public List<CisternPlanView> list(String username) {
    return plans.owned(member(username).id()).stream()
        .map(p -> CisternPlanMapper.view(p, json))
        .toList();
  }

  @Transactional
  public CisternPlanView save(String username, CisternPlanRequest request) {
    var account = accounts.lock(member(username).id());
    if (!account.usable() || !account.role().equals("MEMBER"))
      throw new CisternPlanException(ErrorCode.ACCESS_DENIED);
    if (request.mode() != null && !Set.of("WEEKLY", "HISTORICAL").contains(request.mode()))
      throw new CisternPlanException(ErrorCode.PLACEMENT_INVALID);
    boolean historical = "HISTORICAL".equals(request.mode());
    if (!historical) {
      if (account.districtId() == null) throw new CisternPlanException(ErrorCode.DISTRICT_REQUIRED);
      if (!account.districtId().equals(request.districtId()))
        throw new CisternPlanException(ErrorCode.DISTRICT_ACCESS_DENIED);
    }
    var roof = sites.requireInstallable(request.districtId(), request.roofCellId());
    var ground = sites.requireInstallable(request.districtId(), request.groundCellId());
    if (!roof.modelHash().equals(request.roofModelHash())
        || !ground.modelHash().equals(request.groundModelHash()))
      throw new CisternPlanException(ErrorCode.CONFLICT);
    if (!"ROOF".equals(roof.kind())
        || !"GROUND".equals(ground.kind())
        || roof.cellId().equals(ground.cellId())
        || request.captureAreaM2().signum() <= 0
        || request.captureAreaM2().compareTo(roof.maxAreaM2()) > 0)
      throw new CisternPlanException(ErrorCode.PLACEMENT_INVALID);
    boolean equipment = request.equipment() != null;
    if (equipment
        ? request.tankAreaM2() != null
            || request.tankDepthM() != null
            || request.tankLayout() != null
        : request.tankAreaM2() == null
            || request.tankDepthM() == null
            || request.tankAreaM2().signum() <= 0
            || request.tankDepthM().signum() <= 0
            || request.tankAreaM2().compareTo(ground.maxAreaM2()) > 0)
      throw new CisternPlanException(ErrorCode.PLACEMENT_INVALID);
    // 재해 공간 초안은 현재 주간 설치의 점유와 독립적으로 비교한다.
    if (!historical
        && plans.occupied(request.districtId(), request.roofCellId(), request.groundCellId()))
      throw new CisternPlanException(ErrorCode.SITE_OCCUPIED);
    var snapshot = new TreeMap<String, Object>();
    snapshot.put("schemaVersion", equipment ? 3 : request.tankLayout() == null ? 1 : 2);
    snapshot.put("status", "SPATIAL_DRAFT_NOT_INSTALLED");
    snapshot.put("request", request);
    snapshot.put("roof", roof);
    snapshot.put("ground", ground);
    java.math.BigDecimal capacity;
    if (equipment) {
      var specification =
          specifications.require(
              request.equipment().specificationId(), request.equipment().catalogSha256());
      var geometry =
          CisternLayoutService.equipment(
              ground.polygons(),
              ground.center(),
              ground.modelHash(),
              specification,
              request.equipment());
      if (java.math.BigDecimal.valueOf(geometry.widthM())
              .multiply(java.math.BigDecimal.valueOf(geometry.lengthM()))
              .compareTo(ground.maxAreaM2())
          > 0) throw new CisternPlanException(ErrorCode.PLACEMENT_INVALID);
      capacity = specification.path("nominalCapacityM3").decimalValue();
      snapshot.put("equipmentSpecification", specification);
      snapshot.put("equipmentGeometry", geometry);
      snapshot.put("capacityBasis", specification.path("capacityBasis").asString());
    } else {
      capacity = request.tankAreaM2().multiply(request.tankDepthM());
    }
    snapshot.put("capacityM3", capacity);
    if (request.tankLayout() != null)
      snapshot.put(
          "tankGeometry",
          CisternLayoutService.build(
              ground.polygons(),
              ground.center(),
              ground.modelHash(),
              request.tankAreaM2().doubleValue(),
              request.tankDepthM().doubleValue(),
              request.tankLayout()));
    snapshot.put(
        "horizontalSeparationM",
        Math.hypot(
            roof.center().get(0) - ground.center().get(0),
            roof.center().get(1) - ground.center().get(1)));
    snapshot.put(
        "referenceCosts",
        CisternReferenceService.snapshot(
            WatershedCostRepository.CISTERN_HASH,
            List.of(
                Map.of(
                    "id",
                    "CisternPlan",
                    "facilityType",
                    "RAINWATER_CISTERN",
                    "capacityM3",
                    capacity)),
            costs.cistern()));
    snapshot.put("installationReady", false);
    snapshot.put("positionReserved", false);
    snapshot.put(
        "limitations",
        List.of(
            "지붕·지상 후보의 원 경계이며 실제 홈통·배수관 경로 미확인",
            equipment
                ? "공개 장비 외형의 공간 검토이며 내부 수리 단면·월류/배수 경로·설치 공사비 미확정"
                : request.tankLayout() == null
                    ? "단면적·깊이는 설계값이며 지상 후보 안의 실제 탱크 형상 배치·바닥 높이 미확인"
                    : "탱크 외곽의 공개 도형 포함만 확인한 설계이며 기초·여유고·구조·지장물·실제 바닥 높이 미확인",
            "직선 중심 간 거리는 수평 참고 거리이며 실제 배관 길이·낙차가 아님",
            "설계 초안 저장은 위치 예약·설치·예산 차감·점수 부여가 아님"));
    String raw = json.write(snapshot), hash = json.hash(raw);
    var owned = plans.owned(account.id());
    // 같은 입력의 재시도는 같은 초안을 반환하며 회원 잠금으로 보관 개수 제한을 유지한다.
    for (var old : owned)
      if (old.inputHash().equals(hash)) return CisternPlanMapper.view(old, json);
    if (owned.size() >= 20) throw new CisternPlanException(ErrorCode.CONFLICT);
    var plan = new CisternPlan(UUID.randomUUID(), account.id(), hash, raw, Instant.now());
    plans.add(plan);
    return CisternPlanMapper.view(plan, json);
  }

  @Transactional
  public void remove(String username, UUID id) {
    var account = accounts.lock(member(username).id());
    if (!account.usable() || !plans.remove(account.id(), id))
      throw new CisternPlanException(ErrorCode.RESOURCE_NOT_FOUND);
  }
}
