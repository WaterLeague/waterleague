import { readPublicData } from '../../../shared/repository/publicDataCache';
import { z } from 'zod';
import type { Population } from '../entity/urban';
export const read = readPublicData;
let population: Population | null = null;
export async function loadPopulation(signal: AbortSignal) {
  if (population) return population;
  const values = z.record(z.string(), z.array(z.number().nonnegative().max(5000000)).length(24));
  const schema = z.object({
    schemaVersion: z.literal(1),
    event2022: values,
    reference2025: values,
  });
  population = schema.parse(
    await read(
      '/data/city-population-native-v1.json',
      '908f9709c331d278afe69090f7499c2de5403cc5c67d10fcb432fda60dfe05e4',
      150000,
      signal
    )
  );
  return population;
}
