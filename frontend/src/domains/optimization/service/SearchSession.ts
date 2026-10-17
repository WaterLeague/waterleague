import type { ResearchSearch, SearchInput, SearchSummary } from '../entity/search';
import { searchFingerprint } from './searchService';
import { errorMessage } from '../../../shared/exception/ApiError';
export interface SearchState {
  items: SearchSummary[];
  detail: ResearchSearch | null;
  selectedId: string;
  busy: boolean;
  error: string;
}
export interface SearchPort {
  list(): Promise<SearchSummary[]>;
  get(id: string): Promise<ResearchSearch>;
  create(input: SearchInput, key: string): Promise<ResearchSearch>;
}
export const emptySearchState = (): SearchState => ({
  items: [],
  detail: null,
  selectedId: '',
  busy: false,
  error: '',
});
export class SearchSession {
  state = emptySearchState();
  lastRefresh = 0;
  private epoch = 0;
  private alive = true;
  private inFlight = false;
  private pending: { fingerprint: string; key: string } | null = null;
  constructor(
    private port: SearchPort,
    private publish: (s: SearchState) => void,
    private key: () => string = () => crypto.randomUUID()
  ) {}
  private update(p: Partial<SearchState>) {
    this.state = { ...this.state, ...p };
    if (this.alive) this.publish(this.state);
  }
  private current(token: number) {
    return this.alive && this.epoch === token;
  }
  dispose() {
    this.alive = false;
    this.epoch++;
  }
  invalidate() {
    this.epoch++;
    this.inFlight = false;
    this.update({ detail: null, selectedId: '', busy: false, error: '' });
  }
  conceal() {
    this.epoch++;
    this.inFlight = false;
    this.update({ items: [], detail: null, busy: false });
  }
  async refresh(hide = false) {
    if (!this.alive || (this.inFlight && !hide)) return;
    if (hide) this.conceal();
    const token = ++this.epoch,
      id = this.state.selectedId;
    this.inFlight = true;
    this.lastRefresh = Date.now();
    try {
      const [items, detail] = await Promise.all([
        this.port.list(),
        id ? this.port.get(id) : Promise.resolve(null),
      ]);
      if (this.current(token)) this.update({ items, detail, error: '' });
    } catch (e) {
      if (this.current(token))
        this.update({ items: [], detail: null, selectedId: '', error: errorMessage(e) });
    } finally {
      if (this.current(token)) this.inFlight = false;
    }
  }
  async open(id: string) {
    if (!id) {
      this.invalidate();
      return;
    }
    const token = ++this.epoch;
    this.inFlight = true;
    this.update({ detail: null, selectedId: id, busy: true, error: '' });
    try {
      const value = await this.port.get(id);
      if (this.current(token)) this.update({ detail: value });
    } catch (e) {
      if (this.current(token))
        this.update({ items: [], detail: null, selectedId: '', error: errorMessage(e) });
    } finally {
      if (this.current(token)) {
        this.inFlight = false;
        this.lastRefresh = Date.now();
        this.update({ busy: false });
      }
    }
  }
  async create(input: SearchInput) {
    if (!this.alive || this.state.busy) return;
    const fingerprint = searchFingerprint(input);
    if (this.pending?.fingerprint !== fingerprint) this.pending = { fingerprint, key: this.key() };
    const key = this.pending.key,
      token = ++this.epoch;
    this.inFlight = true;
    this.update({ detail: null, selectedId: '', busy: true, error: '' });
    try {
      const detail = await this.port.create(input, key);
      if (!this.current(token)) return;
      this.update({ detail, selectedId: detail.id });
      const items = await this.port.list();
      if (this.current(token)) {
        this.pending = null;
        this.update({ items });
      }
    } catch (e) {
      if (this.current(token))
        this.update({ items: [], detail: null, selectedId: '', error: errorMessage(e) });
    } finally {
      if (this.current(token)) {
        this.inFlight = false;
        this.lastRefresh = Date.now();
        this.update({ busy: false });
      }
    }
  }
}
