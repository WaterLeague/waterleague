export interface HistoricalSubmission {
  id: string;
  state: 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'REJECTED';
  createdAt: string;
  placementCount: number;
  message: string;
  result: null | {
    submissionPolicy: 'FULL_EVENT_INDEPENDENT_SURFACES_V1';
    rulesHash: string;
    start: string;
    end: string;
    differenceM3: number;
    baselineAccountedM3: number;
    designAccountedM3: number;
    totalScoreStatus: string;
    assumptions: string[];
  };
}
export interface HistoricalBoard {
  eventId: string;
  title: string;
  officialTotalScore: false;
  groups: {
    rulesHash: string;
    entries: {
      id: string;
      displayName: string;
      rank: number;
      differenceM3: number;
      costKrw: number;
      submittedAt: string;
    }[];
  }[];
}
