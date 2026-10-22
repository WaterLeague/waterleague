import type { LabelBounds } from '../../catalog/service/sceneLabelService';

export function districtLabelBounds(
  stage: HTMLElement | null | undefined,
  width: number,
  height: number
): LabelBounds {
  const toolbar = stage?.querySelector('.city-map-top')?.getBoundingClientRect();
  return {
    left: 12,
    top:
      toolbar && stage
        ? Math.max(80, toolbar.bottom - stage.getBoundingClientRect().top + 12)
        : 130,
    right: width - 12,
    bottom: height - 100,
  };
}

export function overviewCamera(
  bounds: number[],
  width: number,
  height: number,
  fov: number,
  area: LabelBounds
) {
  const cx = (bounds[0] + bounds[2]) / 2;
  const cy = (bounds[1] + bounds[3]) / 2;
  const focal = height / (2 * Math.tan((fov * Math.PI) / 360));
  const centerY = (height / 2 - (area.top + area.bottom) / 2) / focal;
  const northOffset = (distance: number) => (centerY * distance) / (0.8 - 0.6 * centerY);
  const fits = (distance: number) => {
    for (const x of [bounds[0], bounds[2]])
      for (const y of [bounds[1], bounds[3]]) {
        const dy = y - cy + northOffset(distance);
        const depth = distance + 0.6 * dy;
        const px = width / 2 + (focal * (x - cx)) / depth;
        const py = height / 2 - (focal * 0.8 * dy) / depth;
        if (depth <= 0 || px < area.left || px > area.right || py < area.top || py > area.bottom)
          return false;
      }
    return true;
  };
  let low = 800,
    high = 350000;
  for (let i = 0; i < 40; i++) {
    const middle = (low + high) / 2;
    if (fits(middle)) high = middle;
    else low = middle;
  }
  return { center: [cx, cy - northOffset(high)] as [number, number], distance: high };
}
