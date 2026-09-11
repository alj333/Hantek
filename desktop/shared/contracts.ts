export type ScopeMode = 'hardware' | 'demo';
export interface Settings {
  mode: ScopeMode;
  storageDir: string;
  refreshIntervalMs: number;
  interfaceGuid: string;
}
export interface Capture {
  id: string;
  createdAt: string;
  label: string;
  notes: string;
  source: ScopeMode;
  imageUrl: string;
  width: number;
  height: number;
  checksumVerified: boolean;
  saved: boolean;
}
export interface Activity {
  id: string;
  at: string;
  kind: 'success' | 'info' | 'error';
  message: string;
}
export interface InstrumentControl {
  id: string;
  label: string;
  group: string;
  kind: 'button' | 'rotary';
  description: string;
  validation: 'bench-pending' | 'screen-verified';
  maxCount: number;
  contextDependent: boolean;
}
export interface ControlResult {
  message: string;
  capture: Capture | null;
}
export interface AppState {
  appVersion: string;
  settings: Settings;
  connected: boolean;
  busy: boolean;
  device: { model: string; vid: string; pid: string } | null;
  captures: Capture[];
  activity: Activity[];
  controlCatalog: InstrumentControl[];
}
export interface ScopeAppApi {
  getState(): Promise<AppState>;
  connect(): Promise<AppState>;
  disconnect(): Promise<AppState>;
  checkConnection(): Promise<{ message: string }>;
  capture(options?: { save?: boolean }): Promise<Capture>;
  setAcquisition(state: 'start' | 'stop'): Promise<{ message: string; capture: Capture | null }>;
  panelAction(input: { control: string; count?: number }): Promise<ControlResult>;
  readSettings(): Promise<{ message: string; record: Record<string, unknown> }>;
  updateSettings(patch: Partial<Pick<Settings, 'mode' | 'refreshIntervalMs' | 'interfaceGuid'>>): Promise<AppState>;
  chooseStorageDirectory(): Promise<AppState>;
  listCaptures(): Promise<Capture[]>;
  updateCapture(input: { id: string; label: string; notes: string }): Promise<Capture>;
  exportCapture(id: string): Promise<{ cancelled: boolean; path?: string }>;
  revealCapture(id: string): Promise<void>;
  openStorage(): Promise<void>;
  onStateChanged(callback: (state: AppState) => void): () => void;
}
declare global {
  interface Window { scopeApp: ScopeAppApi; }
}
