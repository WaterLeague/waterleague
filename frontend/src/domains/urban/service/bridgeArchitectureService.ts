import { Color } from 'three';
import type { Street } from '../entity/urban';
import { bridgeAxis } from './nativeBridgeStructureService';
import { withinBridge } from './nativeBridgeService';
import { streetPath, pathPosition } from './streetLifeService';
type Point = [number, number];
type Beam = (a: number[], b: number[], width: number, depth: number, color: Color) => void;
// 구조 종류는 공개 자료에 결속하며 부재 단면·배치 보간은 화면 표시 제원이다.
export const bridgeArchitectureSources = {
  forms: 'https://hangang.seoul.go.kr/files/2013/12/korean.pdf',
  steel:
    'https://opengov.seoul.go.kr/og/com/download.php?uri=%2Ffiles%2Fdcdata%2F100001%2F20180115%2FF0000063071856.pdf&dname=bridge.pdf',
  worldCup: 'https://mediahub.seoul.go.kr/archives/2002596',
  olympic: 'https://mediahub.seoul.go.kr/news/article/newsArticlePrintPopup.do?articleNo=2002038',
  doubleDeck: 'https://news.seoul.go.kr/traffic/archives/507091?listPage=1',
  cheongdam: 'https://news.seoul.go.kr/citybuild/archives/208956',
};
export function bridgeArchitecture(road: Street, deck: number, beam: Beam, detail: boolean) {
  const polygons = road.nativePolygons;
  if (!polygons || !road.bridgeName) return;
  const name = road.bridgeName;
  const axis = bridgeAxis(polygons),
    normal: Point = [-axis[1], axis[0]];
  const points = polygons.flatMap((p) => p[0]);
  const along = points.map((p) => p[0] * axis[0] + p[1] * axis[1]);
  const start = Math.min(...along),
    end = Math.max(...along);
  const sourcePath = road.nativeStructurePath;
  const route = sourcePath ? streetPath({ ...road, coordinates: sourcePath.coordinates }) : null;
  const length = sourcePath ? sourcePath.span[1] - sourcePath.span[0] : end - start;
  if (length < 300) return;
  const across = points.map((p) => p[0] * normal[0] + p[1] * normal[1]);
  const middle = (Math.min(...across) + Math.max(...across)) / 2;
  const width = Math.min(
    40,
    Math.max(5, sourcePath?.widthM ?? Math.max(...across) - Math.min(...across))
  );
  const at = (s: number, offset = 0, h = 0): number[] => {
    if (route && sourcePath) {
      const point = pathPosition(route, sourcePath.span[0] + s, offset, 1);
      return [point.x, deck + h, point.y];
    }
    return [
      axis[0] * (start + s) + normal[0] * (middle + offset),
      deck + h,
      axis[1] * (start + s) + normal[1] * (middle + offset),
    ];
  };
  const steel = new Color(
    name === '성산대교'
      ? '#d6ad64'
      : name === '서강대교'
        ? '#bd6d55'
        : name === '한강철교'
          ? '#788e85'
          : '#b0c4bc'
  );
  const cable = new Color('#d0d9d6');
  const draw = (a: number[], b: number[], w = 0.65, color = steel) => beam(a, b, w, w, color);
  if (['월드컵대교', '올림픽대교', '행주대교'].includes(name)) {
    const world = name === '월드컵대교',
      olympic = name === '올림픽대교';
    const station = length * 0.5,
      height = world ? 100 : olympic ? 60 : 60;
    const lean = world ? (height / Math.tan((78 * Math.PI) / 180)) * (axis[1] >= 0 ? -1 : 1) : 0;
    const top = at(station + lean, 0, height);
    if (world) {
      for (const side of [-1, 1]) draw(at(station, side * 4, -1), top, 3.2, cable);
    } else {
      for (const side of [-1, 1])
        for (const delta of [-2, 2]) draw(at(station + delta, side * 4), top, 2, cable);
    }
    const count = world ? 11 : 12,
      reach = Math.min(length * 0.3, world ? 225 : 150);
    for (const side of [-1, 1])
      for (let i = 1; i <= count; i++)
        draw(
          at(station + lean * (0.55 + (i * 0.45) / count), 0, height * (0.55 + (i * 0.45) / count)),
          at(station + (side * reach * i) / count, 0, 0.3),
          detail ? 0.2 : 0.35,
          cable
        );
    return;
  }
  const arch = ['한강대교', '서강대교', '성산대교', '방화대교'].includes(name);
  const truss = ['한강철교', '성수대교'].includes(name);
  if (arch || truss) {
    const mainLength = name === '서강대교' ? Math.min(300, length * 0.5) : length * 0.68;
    const count = name === '서강대교' ? 1 : Math.max(1, Math.round(mainLength / 120));
    const span = mainLength / count,
      begin = (length - mainLength) / 2;
    const panels = detail ? 16 : 8,
      rise = Math.min(28, span * 0.16);
    for (let j = 0; j < count; j++)
      for (const side of [-1, 1]) {
        const lateral = side * (width / 2 - 0.8);
        for (let i = 0; i < panels; i++) {
          const a = i / panels,
            b = (i + 1) / panels;
          const height = (t: number) => (arch ? Math.sin(Math.PI * t) * rise : rise * 0.55);
          const p = at(begin + (j + a) * span, lateral, height(a));
          const q = at(begin + (j + b) * span, lateral, height(b));
          if (!withinBridge([p[0], p[2]], polygons) || !withinBridge([q[0], q[2]], polygons))
            continue;
          draw(p, q, 0.9);
          draw(at(begin + (j + b) * span, lateral), q, 0.35);
          if (truss || name === '성산대교' || name === '방화대교')
            draw(at(begin + (j + a) * span, lateral), q, 0.45);
          if (detail && i % 4 === 0) draw(p, at(begin + (j + a) * span, -lateral, height(a)), 0.4);
        }
      }
  } else {
    for (const side of [-1, 1])
      for (let s = 0; s < length; s += 20) {
        const a = at(s, side * width * 0.3, -1.2),
          b = at(Math.min(length, s + 20), side * width * 0.3, -1.2);
        if (withinBridge([a[0], a[2]], polygons) && withinBridge([b[0], b[2]], polygons))
          beam(a, b, 1.2, 1.8, steel);
      }
  }
}
