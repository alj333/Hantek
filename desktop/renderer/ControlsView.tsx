import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  Activity, Camera, Check, ChevronDown, Clock3, FileText, Info, Menu, Minus,
  MousePointer2, Play, Plus, RefreshCw, SlidersHorizontal, Square,
} from 'lucide-react';
import type { InstrumentControl, ScopeMode } from '../shared/contracts';
import './controls.css';

// Matches the catalog supplied by the isolated desktop backend. No keycodes or
// default control entries live in the renderer; only advertised controls render.
export type FrontPanelControl = InstrumentControl;

export interface LastControlRequest {
  label: string;
  count: number;
  rotary: boolean;
  at: string;
  source: ScopeMode;
  status: 'sending' | 'replied' | 'unconfirmed';
  message: string;
}

interface Props {
  catalog: FrontPanelControl[];
  connected: boolean;
  busy: boolean;
  mode: ScopeMode;
  model: string;
  screen: ReactNode;
  lastRequest: LastControlRequest | null;
  onAction: (control: FrontPanelControl, count: number) => void;
  onRefresh: () => void;
  onSave: () => void;
  onAcquisition: (action: 'start' | 'stop') => void;
  onReadSettings: () => void;
}

function isSoftkey(control: FrontPanelControl) {
  return control.kind === 'button' && /(?:^|[\s_-])f[1-5](?:$|[\s_-])/i.test(`${control.id} ${control.label}`);
}

function ControlIcon({ control }: { control: FrontPanelControl }) {
  if (control.kind === 'rotary') {
    if (/[+↑]|\b(?:increase|increment|up|right)\b/i.test(control.label)) return <Plus size={14} />;
    if (/[−–↓]|\b(?:decrease|decrement|down|left)\b| -/.test(control.label)) return <Minus size={14} />;
    return <SlidersHorizontal size={14} />;
  }
  if (/menu/i.test(control.label)) return <Menu size={14} />;
  return <MousePointer2 size={14} />;
}

export default function ControlsView({
  catalog, connected, busy, mode, model, screen, lastRequest,
  onAction, onRefresh, onSave, onAcquisition, onReadSettings,
}: Props) {
  const [stepsText, setStepsText] = useState('1');
  const deck = useRef<HTMLElement>(null);
  const [deckHeight, setDeckHeight] = useState<number>();
  const fitDeck = useCallback(() => {
    const element = deck.current;
    if (!element) return;
    const top = element.getBoundingClientRect().top + window.scrollY;
    const height = Math.floor(Math.max(260, window.innerHeight - top - 20));
    setDeckHeight((previous) => previous !== undefined && Math.abs(previous - height) < 2 ? previous : height);
  }, []);
  useLayoutEffect(() => { fitDeck(); });
  useEffect(() => {
    window.addEventListener('resize', fitDeck);
    return () => window.removeEventListener('resize', fitDeck);
  }, [fitDeck]);
  const count = Number(stepsText);
  const validCount = stepsText.trim() !== '' && Number.isInteger(count) && count >= 1 && count <= 5;
  const enabled = connected && !busy;
  const demo = mode === 'demo';
  const softkeys = catalog.filter(isSoftkey);
  const groups = useMemo(() => {
    const result = new Map<string, FrontPanelControl[]>();
    for (const control of catalog) {
      if (isSoftkey(control)) continue;
      const group = control.group || 'Instrument';
      result.set(group, [...(result.get(group) ?? []), control]);
    }
    const order = ['Channel 1', 'Channel 2', 'Horizontal', 'Trigger', 'Acquisition', 'Menus', 'Soft keys'];
    const rank = (group: string) => { const index = order.indexOf(group); return index === -1 ? order.length : index; };
    return [...result.entries()].sort(([a], [b]) => rank(a) - rank(b));
  }, [catalog]);
  const pending = catalog.filter((control) => control.validation === 'bench-pending').length;

  const apply = (control: FrontPanelControl) => {
    if (!enabled || (control.kind === 'rotary' && (!validCount || count > Math.min(5, control.maxCount)))) return;
    onAction(control, control.kind === 'rotary' ? count : 1);
  };

  const renderControl = (control: FrontPanelControl, softkey = false) => <div className={softkey ? 'softkey-wrap' : 'panel-key-wrap'} key={control.id}>
    <button
      className={`${softkey ? 'scope-softkey' : 'panel-key'} ${control.kind === 'rotary' ? 'rotary-key' : 'push-key'}`}
      aria-label={control.label}
      aria-describedby={`control-help-${control.id}`}
      title={`${control.description}${demo ? ' · Simulated in demo mode.' : control.validation === 'bench-pending' ? ' · Bench validation pending.' : ' · Previously verified on screen.'}`}
      disabled={!enabled || (control.kind === 'rotary' && (!validCount || count > Math.min(5, control.maxCount)))}
      data-control-id={control.id}
      data-validation={control.validation}
      onClick={() => apply(control)}
    >
      {!softkey && <ControlIcon control={control} />}
      <span>{softkey ? /f[1-5]/i.exec(`${control.id} ${control.label}`)?.[0].toUpperCase() ?? control.label : control.label}</span>
      {!demo && control.validation === 'bench-pending' && <Clock3 className="pending-key-dot" size={10} aria-hidden="true" />}
    </button>
    <span className="visually-hidden" id={`control-help-${control.id}`}>
      {control.description} {demo ? 'Simulated control.' : control.validation === 'bench-pending' ? 'Bench validation pending.' : 'Previously verified on screen.'}
      {control.kind === 'rotary' ? ` Requests ${validCount ? count : 'an invalid number of'} steps per click.` : 'One press per click.'}
    </span>
  </div>;

  return <>
    <div className="page-heading controls-heading">
      <div><h1>Front-panel controls</h1><p>Instrument menus and adjustments, with the screen in view.</p></div>
      <span className={`controls-validation-badge ${demo ? 'demo' : !catalog.length ? 'unavailable' : pending ? 'pending' : 'verified'}`}>
        {demo ? <MonitorLabel /> : !catalog.length ? <Info size={13} /> : pending ? <Clock3 size={13} /> : <Check size={13} />}
        {demo ? 'Simulated controls' : !catalog.length ? 'Controls unavailable' : pending ? 'Bench validation pending' : 'Screen-verified controls'}
      </span>
    </div>

    <div className={`controls-notice ${demo ? 'demo' : ''}`}>
      <Info size={15} />
      <p>{demo ? 'Demo actions are simulated. They do not validate real hardware behavior.' : `${pending ? 'Some controls await bench validation. ' : ''}Check the captured screen after each adjustment.`}</p>
    </div>

    <div className="controls-layout">
      <section className="controls-monitor instrument-panel" aria-label="Control screen and acquisition">
        <div className="instrument-heading"><span className="instrument-icon"><Activity size={21} /></span>
          <div><h2>{demo ? 'Demo oscilloscope' : model}</h2><p>{demo ? 'Simulated front panel' : 'Observe the screen after each adjustment'}</p></div>
          <span className={`connection-pill ${connected ? 'connected' : ''}`}><span />{connected ? 'Connected' : 'Disconnected'}</span>
        </div>
        <div className="controls-screen-toolbar">
          <button className="button primary" disabled={!enabled} onClick={onSave}><Camera size={14} />Save capture</button>
          <div className="controls-acquisition"><button className="button secondary" disabled={!enabled} onClick={() => onAcquisition('start')}><Play size={13} />Run</button><button className="button secondary" disabled={!enabled} onClick={() => onAcquisition('stop')}><Square size={12} />Stop</button></div>
          <button className="button quiet controls-refresh" aria-label="Refresh preview" title="Refresh preview" disabled={!enabled} onClick={onRefresh}><RefreshCw size={14} /><span>Refresh preview</span></button>
        </div>
        <div className={`control-screen-row ${softkeys.length ? 'with-softkeys' : ''}`}>
          {screen}
          {softkeys.length > 0 && <div className="softkey-rail" role="group" aria-label="Right-screen softkeys"><span>SOFT<br />KEYS</span>{softkeys.map((control) => renderControl(control, true))}<small>Follow the<br />screen</small></div>}
        </div>
        <div className="controls-screen-caption"><MousePointer2 size={13} /><p>One gesture per request. Soft keys follow the displayed menu. Auto-refresh pauses before a control action.</p></div>
        <details className="panel-menu-help"><summary>Coupling, probes and trigger options<ChevronDown size={13} /></summary><ul>
          <li>Open <strong>CH1 menu</strong> or <strong>CH2 menu</strong> for channel coupling, probe factor and other channel options.</li>
          <li>Open <strong>Trigger menu</strong> for source, edge and other trigger options.</li>
          <li>Use <strong>F1–F5</strong> for the choices shown on the right of the screen. <strong>Select left</strong>, <strong>Select right</strong> and <strong>Select press</strong> navigate the current menu.</li>
          <li>Read the displayed values after each action. Rotary buttons request relative steps, not an absolute voltage or timebase.</li>
        </ul></details>
        <section className={`last-control-request ${lastRequest?.status ?? 'empty'}`} aria-label="Last control request" aria-live="polite">
          <div className="last-control-title"><span>{lastRequest?.status === 'sending' ? 'REQUESTING' : 'LAST PANEL REQUEST'}</span>{lastRequest && <time dateTime={lastRequest.at}>{new Date(lastRequest.at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time>}</div>
          {lastRequest ? <><strong>{lastRequest.label}{lastRequest.rotary ? ` · ${lastRequest.count} ${lastRequest.count === 1 ? 'step' : 'steps'}` : ''}<span>{lastRequest.source === 'demo' ? 'DEMO' : 'HARDWARE'}</span></strong><p>{lastRequest.message}</p>{lastRequest.status === 'replied' && <small>Reply received · requested state is not independently verified.</small>}</> : <p>No panel request in this session. Verify settings on the captured instrument screen.</p>}
        </section>
        <div className="settings-record-action"><button className="button quiet" disabled={!enabled} onClick={onReadSettings}><FileText size={14} />Save settings record</button><span>Preserve a read-only diagnostic record.</span></div>
      </section>

      <aside className="control-deck" aria-label="Instrument front panel" ref={deck} style={deckHeight === undefined ? undefined : { height: deckHeight }}>
        <div className="control-deck-settings"><div><strong>Instrument controls</strong><span>{catalog.length ? `${catalog.length} controls` : 'Waiting for supported controls'}</span></div>
          <label>Steps per click<input aria-label="Rotary steps per click" type="number" min={1} max={5} step={1} inputMode="numeric" value={stepsText} disabled={busy} onChange={(event) => setStepsText(event.target.value)} aria-invalid={!validCount} aria-describedby={!validCount ? 'rotary-count-error' : 'rotary-count-help'} /></label>
        </div>
        <p className={`rotary-count-help ${!validCount ? 'invalid' : ''}`} id={!validCount ? 'rotary-count-error' : 'rotary-count-help'}>{validCount ? 'Rotary adjustments: 1–5 steps. Menu buttons: one press.' : 'Use 1–5 whole steps.'}</p>
        <div className="control-groups">
          {groups.length ? groups.map(([group, controls]) => <section className={`control-group ${/ch(?:annel)?\s*1/i.test(group) ? 'channel-one' : /ch(?:annel)?\s*2/i.test(group) ? 'channel-two' : ''}`} key={group} aria-label={`${group} controls`}>
            <div className="control-group-heading"><h2>{group}</h2>{!demo && controls.some((control) => control.validation === 'bench-pending') && <span><Clock3 size={10} />Bench pending</span>}</div>
            <div className="panel-key-grid">{controls.map((control) => renderControl(control))}</div>
          </section>) : <div className="controls-empty"><SlidersHorizontal size={25} /><h2>Controls unavailable</h2><p>The desktop app has not supplied its supported instrument controls.</p></div>}
          {groups.length > 0 && <div className="control-deck-end"><ChevronDown size={13} />Supported instrument controls</div>}
        </div>
      </aside>
    </div>
  </>;
}

function MonitorLabel() { return <SlidersHorizontal size={13} />; }
