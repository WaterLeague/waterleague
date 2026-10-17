import { api } from '../../../shared/repository/apiClient';
import type { District } from '../entity/district';
export const loadDistricts = () => api<District[]>('/districts');
