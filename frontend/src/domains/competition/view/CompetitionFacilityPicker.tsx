import { Check } from 'lucide-react';
import { facilities } from '../../game/service/gameService';
import type { FacilityType } from '../../game/entity/game';
import { FacilityThumbnail } from '../../catalog/view/FacilityThumbnail';

export function CompetitionFacilityPicker({
  types,
  selected,
  onChange,
  disabled,
}: {
  types: FacilityType[];
  selected: FacilityType[];
  onChange: (value: FacilityType[]) => void;
  disabled: boolean;
}) {
  return (
    <div className="contest-facility-grid">
      {types.map((type) => {
        const active = selected.includes(type);
        return (
          <button
            type="button"
            key={type}
            className={`contest-facility-card${active ? ' is-selected' : ''}`}
            aria-pressed={active}
            aria-label={facilities[type].name}
            disabled={disabled}
            onClick={() =>
              onChange(active ? selected.filter((value) => value !== type) : [...selected, type])
            }
          >
            <span className="contest-facility-selection">
              <Check size={14} aria-hidden="true" />
              {active ? '선택됨' : '선택'}
            </span>
            <FacilityThumbnail type={type} />
            <strong>{facilities[type].name}</strong>
            <span className="contest-facility-intro">{facilities[type].intro}</span>
          </button>
        );
      })}
    </div>
  );
}
