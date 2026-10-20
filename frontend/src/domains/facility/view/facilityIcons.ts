import {
  Leaf,
  Grid2X2,
  House,
  Waves,
  Route,
  Droplets,
  Container,
  Warehouse,
  CircleDot,
  Network,
  Factory,
} from 'lucide-react';

export const facilityIcons = {
  RAIN_GARDEN: Leaf,
  PERMEABLE_PAVEMENT: Grid2X2,
  GREEN_ROOF: House,
  BIORETENTION: Waves,
  VEGETATIVE_SWALE: Route,
  INFILTRATION_TRENCH: Droplets,
  RAINWATER_CISTERN: Container,
  UNDERGROUND_STORAGE: Warehouse,
  DETENTION: Waves,
  INLET: CircleDot,
  CONDUIT: Network,
  PUMP_STATION: Factory,
} as const;
