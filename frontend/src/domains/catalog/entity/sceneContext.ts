import type { z } from 'zod';
import type { sceneContextDto, sceneContextSourceDto } from '../dto/sceneContextDto';
export type SceneContext = z.infer<typeof sceneContextDto>;
export type SceneContextSource = z.infer<typeof sceneContextSourceDto> & { baseMapSha256: string };
