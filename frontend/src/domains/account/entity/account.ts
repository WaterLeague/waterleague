export interface Account {
  id: string;
  username: string;
  displayName: string;
  role: 'PLAYER' | 'INSTITUTION';
  organizationId: string | null;
}
