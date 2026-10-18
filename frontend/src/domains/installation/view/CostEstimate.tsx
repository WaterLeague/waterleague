import type { SharedSite } from '../entity/installation';
import type { FacilityType } from '../../game/entity/game';
import { won } from '../../game/service/gameService';
import { CostScope } from '../../cost/view/CostScope';

export function CostEstimate({
  site,
  type,
  area,
  remaining,
  onArea,
}: {
  site: SharedSite;
  type: FacilityType;
  area: number;
  remaining: number;
  onArea: (value: string) => void;
}) {
  const evidence = site.costModel.facilities[type];
  const unit = site.unitCosts[type];
  const affordable =
    Math.max(
      0,
      Math.min(Math.floor(site.maxAreaM2 * 100 + 1e-7), Math.floor((remaining * 100) / unit))
    ) / 100;
  return (
    <div className="cost-estimate">
      <div className="placement-cost">
        <span>예산 반영 참고비</span>
        <strong>{won(Math.max(0, area || 0) * unit)}</strong>
      </div>
      <p className="cost-formula">
        {(area || 0).toLocaleString('ko-KR')}m² × {won(unit)}/m²
      </p>
      <button
        type="button"
        className="cost-fit"
        disabled={affordable < 0.01}
        onClick={() => onArea(affordable.toFixed(2))}
      >
        예산 내 최대 면적 · {affordable.toLocaleString('ko-KR')}m²
      </button>
      <CostScope
        source={evidence}
        quantity={Math.max(0, area || 0)}
        unit={unit}
        subtotal={Math.max(0, area || 0) * unit}
      />
    </div>
  );
}
