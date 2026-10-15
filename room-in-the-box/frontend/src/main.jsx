import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowUpRight, Copy, Download, Menu, Minus, Plus, Settings2, ShieldCheck, Sparkles, Square, X } from 'lucide-react';
import Rich, { plain } from './Rich.jsx';
import './styles.css';

const API_DEFAULT = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const HERO_VIDEO = 'https://d2ol7oe51mr4n9.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/45567745-d826-44a2-a5ce-7ef670944e60.mp4';
const CREDIT = 'CREATED BY DHRUVAN S S';
const MANUAL_MIN = 3;
const DEFAULT_TURNS = 8;

const presetFallback = [
  ['student', 'Student', 'Practicality, learning difficulty, student feasibility, implementation effort, and realistic build scope.'],
  ['professor', 'Professor', 'Technical depth, academic value, correctness, engineering quality, and academic strength.'],
  ['scientist', 'Scientist', 'Scientific reasoning, innovation, technical possibilities, research potential, and conceptual soundness.'],
  ['judge', 'Judge', 'Originality, presentation potential, relevance, technical impact, and competition-readiness.'],
  ['technical_expert', 'Technical Expert', 'Architecture, implementation problems, bugs, scalability, technical weaknesses, and improvements.'],
  ['product_manager', 'Product Manager', 'User value, market fit, scope control, prioritisation, and realistic MVP definition.'],
  ['devils_advocate', 'Devil’s Advocate', 'Hidden assumptions, failure modes, risks, and weaknesses others may overlook.'],
].map(([id, name, perspective]) => ({ id, name, perspective }));

/* ---------- storage / api helpers ---------- */
const store = {
  get token() { return localStorage.getItem('cr_token') || ''; },
  set token(v) { v ? localStorage.setItem('cr_token', v) : localStorage.removeItem('cr_token'); },
  get api() { return localStorage.getItem('cr_api') || API_DEFAULT; },
  set api(v) { localStorage.setItem('cr_api', v); },
};
// the room you are in survives a page refresh
const saved = {
  get() { try { return JSON.parse(localStorage.getItem('cr_room')); } catch { return null; } },
  set(v) { try { localStorage.setItem('cr_room', JSON.stringify(v)); } catch { /* ignore */ } },
  clear() { try { localStorage.removeItem('cr_room'); } catch { /* ignore */ } },
};
const api = (path, opts = {}) => fetch(store.api.replace(/\/$/, '') + path, {
  ...opts,
  headers: { 'Content-Type': 'application/json', ...(store.token ? { 'X-Access-Token': store.token } : {}), ...(opts.headers || {}) },
});
const eventData = (e) => { try { return JSON.parse(e.data); } catch { return {}; } };
const roomIdFromHash = () => { const m = location.hash.match(/^#\/room\/([A-Za-z0-9_-]{8,64})$/); return m ? m[1] : null; };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const errText = (e, fallback) => {
  if (!e) return fallback;
  if (typeof e === 'string') return e;
  if (Array.isArray(e)) return e.map((x) => x.msg || '').filter(Boolean).join('; ') || fallback;
  return fallback;
};

function App() {
  const initialId = roomIdFromHash();
  const [screen, setScreen] = useState(initialId ? 'studio' : 'home');
  const [roles, setRoles] = useState(presetFallback);
  const [limits, setLimits] = useState({ min_roles: 2, max_roles: 5, min_queries: 10, max_queries: 24 });
  const [selected, setSelected] = useState(['student', 'technical_expert', 'judge']);
  const [customs, setCustoms] = useState([]);
  const [turnMode, setTurnMode] = useState('auto');
  const [turns, setTurns] = useState(DEFAULT_TURNS);
  const [task, setTask] = useState('');
  const [session, setSession] = useState(() => {
    const s = saved.get();
    if (initialId) return { id: initialId, roles: s?.id === initialId ? s.roles || [] : [], task: s?.task, mode: s?.mode, turns: s?.turns };
    return s;
  });
  const [events, setEvents] = useState([]);
  const [final, setFinal] = useState('');
  const [status, setStatus] = useState('');
  const [typing, setTyping] = useState([]);
  const [connected, setConnected] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');
  const [apiOpen, setApiOpen] = useState(false);
  const [apiDraft, setApiDraft] = useState(store.api);
  const [tokenDraft, setTokenDraft] = useState(store.token);
  const esRef = useRef(null);
  const connectedRef = useRef(null); // id of the room the live stream belongs to
  const bottomRef = useRef(null);

  const manualMax = limits.max_queries || 24;
  const clampTurns = (v) => Math.max(MANUAL_MIN, Math.min(manualMax, parseInt(v, 10) || DEFAULT_TURNS));
  const totalRoles = selected.length + customs.length;

  useEffect(() => {
    api('/api/roles').then(async (r) => {
      if (r.ok) { const d = await r.json(); setRoles(d.presets || presetFallback); setLimits((l) => ({ ...l, ...d })); }
    }).catch(() => {});
  }, []);

  // refresh / back / forward: the URL hash decides which window you are in
  useEffect(() => {
    const onHash = () => { const id = roomIdFromHash(); if (id) enterRoom(id); else setScreen('home'); };
    window.addEventListener('hashchange', onHash);
    if (initialId) enterRoom(initialId);
    return () => { window.removeEventListener('hashchange', onHash); esRef.current?.close(); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [events, typing, final]);

  const activeStep = useMemo(() => {
    const m = events.filter((e) => e.type === 'message' && e.data.step);
    return m.length ? Math.max(...m.map((e) => e.data.step || 0)) : 0;
  }, [events]);
  const plannedTurns = session?.mode === 'manual' && session?.turns ? session.turns : null;
  const progressTotal = plannedTurns || limits.max_queries || 24;
  const progress = done && final ? 100 : Math.min(100, Math.round((activeStep / progressTotal) * 100));

  /* ---------- role selection ---------- */
  function toggleRole(id) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : totalRoles < limits.max_roles ? [...s, id] : s));
  }
  const addCustom = () => { if (totalRoles < limits.max_roles) setCustoms((c) => [...c, { key: Math.random().toString(36).slice(2), name: '', perspective: '' }]); };
  const editCustom = (key, patch) => setCustoms((c) => c.map((x) => (x.key === key ? { ...x, ...patch } : x)));
  const removeCustom = (key) => setCustoms((c) => c.filter((x) => x.key !== key));

  function saveSettings() { store.api = apiDraft.trim() || API_DEFAULT; store.token = tokenDraft.trim(); setApiOpen(false); }

  /* ---------- starting / resuming ---------- */
  function resetRoomState() {
    setEvents([]); setFinal(''); setTyping([]); setDone(false); setConnected(false); setError('');
  }

  async function start() {
    setError('');
    const filled = customs.filter((c) => c.name.trim() || c.perspective.trim());
    if (filled.some((c) => !c.name.trim() || !c.perspective.trim())) { setError('Every custom specialist needs both a name and a perspective.'); return; }
    const chosen = [...selected, ...filled.map((c) => ({ name: c.name.trim(), perspective: c.perspective.trim() }))];
    if (chosen.length < limits.min_roles || chosen.length > limits.max_roles) { setError(`Choose ${limits.min_roles}–${limits.max_roles} specialists in total.`); return; }
    const turnCount = turnMode === 'manual' ? clampTurns(turns) : null;
    setStatus('Opening the studio…');
    if (session && connectedRef.current && !done) api(`/api/discussions/${session.id}/stop`, { method: 'POST' }).catch(() => {});
    try {
      const r = await api('/api/discussions', { method: 'POST', body: JSON.stringify({ task: task.trim(), roles: chosen, turn_mode: turnMode, turns: turnCount }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw Error(errText(d.detail, 'Could not start the discussion.'));
      const info = { id: d.id, task: task.trim(), roles: d.roles || [], mode: turnMode, turns: turnCount };
      esRef.current?.close();
      connectedRef.current = d.id;
      resetRoomState();
      setSession(info); saved.set(info);
      setScreen('studio');
      location.hash = `#/room/${d.id}`;
      openStream(d.id);
    } catch (e) {
      setError(e.message === 'Failed to fetch' ? 'Could not reach the server. Check the API URL in settings.' : e.message);
      setStatus('');
    }
  }

  function dropRoom(message) {
    esRef.current?.close(); connectedRef.current = null; saved.clear();
    setSession(null); resetRoomState(); setStatus(''); setError(message || '');
    history.replaceState(null, '', location.pathname + location.search);
    setScreen('home');
  }

  // (re)attach to a room by id — used after a refresh, or when pressing back/forward
  async function enterRoom(id) {
    setScreen('studio');
    if (connectedRef.current === id) return;
    esRef.current?.close();
    connectedRef.current = id;
    const s = saved.get();
    setSession({ id, roles: s?.id === id ? s.roles || [] : [], task: s?.id === id ? s.task : undefined, mode: s?.id === id ? s.mode : undefined, turns: s?.id === id ? s.turns : undefined });
    resetRoomState();
    setStatus('Reconnecting to your room…');
    for (let attempt = 0; attempt < 10; attempt++) {
      if (connectedRef.current !== id) return;
      let r = null;
      try { r = await api(`/api/discussions/${id}`); } catch { r = null; }
      if (connectedRef.current !== id) return;
      if (r && r.ok) {
        const d = await r.json();
        const prev = saved.get();
        const meta = prev?.id === id ? prev : {};
        const info = { id, task: d.task, roles: d.roles || [], mode: meta.mode || 'auto', turns: meta.turns || null };
        setSession(info); saved.set(info);
        if (d.status && d.status !== 'running') { // already finished: just show it, no stream needed
          const evs = (d.events || []).map((e) => ({ seq: e.seq, type: e.type, data: { ...e.data, seq: e.seq } }));
          setEvents(evs);
          setFinal(evs.filter((e) => e.type === 'final').at(-1)?.data.text || d.final || '');
          setDone(true);
          setStatus(d.status === 'completed' ? 'Discussion completed.' : `Discussion ${d.status}.`);
        } else openStream(id);
        return;
      }
      if (r && r.status === 404) { dropRoom('That discussion is no longer available on the server.'); return; }
      if (r && (r.status === 401 || r.status === 403)) { dropRoom('The server rejected your access token — check Studio settings.'); return; }
      setStatus('Waking the server — this can take up to a minute…');
      await sleep(5000);
    }
    setStatus(''); setError('Could not reach the server. Check the API URL in settings, then reload.');
  }

  function openStream(id) {
    esRef.current?.close(); setConnected(false);
    let url = store.api.replace(/\/$/, '') + `/api/discussions/${id}/stream`;
    if (store.token) url += `?token=${encodeURIComponent(store.token)}`;
    const es = new EventSource(url); esRef.current = es;
    const handle = (type) => (e) => {
      const d = eventData(e);
      setEvents((prev) => (prev.some((x) => x.seq === d.seq && x.type === type) ? prev : [...prev, { seq: d.seq, type, data: d }]));
      if (type === 'status') setStatus(d.text || '');
      if (type === 'typing') setTyping((t) => [...t.filter((x) => x !== d.role_id), d.role_id]);
      if (type === 'message') setTyping((t) => (d.role_id ? t.filter((x) => x !== d.role_id) : t));
      if (type === 'final') { setFinal(d.text || ''); setStatus('Final answer ready.'); }
      if (type === 'error') setError(d.message || 'Discussion error.');
      if (type === 'done') { setConnected(false); setDone(true); setStatus(d.status === 'completed' ? 'Discussion completed.' : `Discussion ${d.status}.`); setTyping([]); es.close(); }
    };
    ['session', 'status', 'typing', 'message', 'final', 'error', 'done'].forEach((t) => es.addEventListener(t, handle(t)));
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
  }

  async function stop() { if (!session) return; try { await api(`/api/discussions/${session.id}/stop`, { method: 'POST' }); } catch (e) { setError(e.message); } }

  /* ---------- navigation ---------- */
  function goHome() { // keeps your room alive in the background so you can come back
    if (location.hash) history.pushState(null, '', location.pathname + location.search);
    setScreen('home');
    window.scrollTo({ top: 0 });
  }
  function resumeRoom() { if (session) location.hash = `#/room/${session.id}`; }
  async function endRoom() { // X button: close this room for good
    if (session && !done) {
      if (!window.confirm('Stop this discussion and return home?')) return;
      try { await api(`/api/discussions/${session.id}/stop`, { method: 'POST' }); } catch { /* ignore */ }
    }
    esRef.current?.close(); connectedRef.current = null; saved.clear();
    setSession(null); resetRoomState(); setStatus('');
    goHome();
  }

  async function copyFinal() { try { await navigator.clipboard.writeText(plain(final)); } catch { /* ignore */ } }
  function downloadTranscript() {
    if (!session) return;
    const text = events.filter((e) => e.type === 'message' || e.type === 'final')
      .map((e) => `${e.data.speaker || (e.type === 'final' ? 'FINAL ANSWER' : e.type)}\n${plain(e.data.text || e.data.message || '')}`).join('\n\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type: 'text/plain' }));
    a.download = `discussion-${session.id}.txt`; a.click(); URL.revokeObjectURL(a.href);
  }

  return (
    <div className="app">
      <Noise />
      <Header overlay={screen === 'home'} onHome={goHome} onSettings={() => setApiOpen(true)} onMenu={() => setApiOpen(true)} />
      <AnimatePresence mode="wait">
        {screen === 'home' && (
          <Home key="home" task={task} setTask={setTask} roles={roles} selected={selected} toggleRole={toggleRole}
            customs={customs} addCustom={addCustom} editCustom={editCustom} removeCustom={removeCustom} totalRoles={totalRoles}
            turnMode={turnMode} setTurnMode={setTurnMode} turns={turns} setTurns={setTurns} clampTurns={clampTurns} manualMax={manualMax}
            limits={limits} start={start} error={error} session={session} resumeRoom={resumeRoom} endRoom={endRoom} />
        )}
        {screen === 'studio' && (
          <Studio key="studio" session={session} events={events} final={final} status={status} typing={typing} connected={connected}
            done={done} progress={progress} activeStep={activeStep} progressTotal={progressTotal} plannedTurns={plannedTurns}
            stop={stop} endRoom={endRoom} copyFinal={copyFinal} downloadTranscript={downloadTranscript} bottomRef={bottomRef} error={error} />
        )}
      </AnimatePresence>
      <AnimatePresence>
        {apiOpen && <SettingsModal apiDraft={apiDraft} setApiDraft={setApiDraft} tokenDraft={tokenDraft} setTokenDraft={setTokenDraft} save={saveSettings} close={() => setApiOpen(false)} />}
      </AnimatePresence>
    </div>
  );
}

function Noise() { return <div className="noise" />; }

function Header({ overlay, onHome, onSettings, onMenu }) {
  return (
    <header className={overlay ? 'overlay' : ''}>
      <button className="brand" onClick={onHome} title="Back to home"><span>ROOM</span><i>in the</i><span>BOX</span></button>
      <nav>
        <button onClick={onHome}>Studio</button>
        <button onClick={() => { onHome(); setTimeout(() => document.getElementById('how')?.scrollIntoView({ behavior: 'smooth' }), 60); }}>How it works</button>
      </nav>
      <div className="header-right">
        <span className="live-dot"><b /> SYSTEM READY</span>
        <button className="icon-btn desktop-settings" onClick={onSettings} title="Connection settings"><Settings2 size={17} /></button>
        <button className="icon-btn mobile-menu" onClick={onMenu}><Menu size={19} /></button>
      </div>
    </header>
  );
}

function Home({ task, setTask, roles, selected, toggleRole, customs, addCustom, editCustom, removeCustom, totalRoles, turnMode, setTurnMode, turns, setTurns, clampTurns, manualMax, limits, start, error, session, resumeRoom, endRoom }) {
  const videoRef = useRef(null);
  useEffect(() => { // respect "reduce motion"
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) videoRef.current?.pause();
  }, []);
  const turnCount = clampTurns(turns);
  const canLaunch = task.trim() && totalRoles >= limits.min_roles;
  return (
    <main className="home">
      <section className="hero">
        <video ref={videoRef} className="hero-video" src={HERO_VIDEO} autoPlay muted loop playsInline preload="auto" disablePictureInPicture />
        <div className="hero-shade" />
        <div className="hero-inner">
          <div className="eyebrow"><span>01</span><em /> MULTI-AGENT DISCUSSION STUDIO</div>
          <h1>Put the question<br /><i>in the room.</i></h1>
          <p className="dek">One Master. One Manager. A panel of specialists. They challenge, refine and converge before a Concluder hands you the answer.</p>
          <div className="hero-meta"><span>LIVE ORCHESTRATION</span><span>UP TO {limits.max_roles} SPECIALISTS</span><span>SHARED MEMORY</span></div>
        </div>
        <span className="credit">{CREDIT}</span>
      </section>

      <section className="workspace">
        {session && (
          <div className="resume">
            <div><span className="micro">YOUR ROOM IS STILL OPEN</span><p>{session.task ? (session.task.length > 110 ? session.task.slice(0, 110) + '…' : session.task) : 'Previous discussion'}</p></div>
            <div className="resume-actions"><button onClick={resumeRoom}>Return to room <ArrowUpRight size={15} /></button><button className="ghost" onClick={endRoom}>Discard</button></div>
          </div>
        )}

        <div className="task-card">
          <div className="card-top"><span>THE BRIEF</span><span>{task.length}/4000</span></div>
          <textarea value={task} onChange={(e) => setTask(e.target.value)} placeholder="What do you want the room to figure out?" maxLength="4000" />
          <div className="examples">
            <button onClick={() => setTask('Design a genuinely original software product for a 16-hour college hackathon. Challenge the idea from technical, user, and judging perspectives.')}>Hackathon concept</button>
            <button onClick={() => setTask('Review this architecture and find the most important technical risks, then propose a practical fix for each.')}>Architecture review</button>
          </div>
        </div>

        <div className="roles-panel">
          <div className="panel-heading"><div><span className="micro">THE PANEL</span><h2>Choose your voices</h2></div><span className="count">{totalRoles}/{limits.max_roles}</span></div>
          <div className="role-grid">
            {roles.map((r) => <RoleCard key={r.id} role={r} active={selected.includes(r.id)} disabled={!selected.includes(r.id) && totalRoles >= limits.max_roles} toggle={() => toggleRole(r.id)} />)}
          </div>
          <div className="custom-wrap">
            <AnimatePresence initial={false}>
              {customs.map((c, i) => (
                <motion.div key={c.key} className="custom-card" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}>
                  <div className="custom-card-head"><span className="micro">CUSTOM SPECIALIST {i + 1}</span><button className="mini-x" onClick={() => removeCustom(c.key)} aria-label="Remove specialist"><X size={14} /></button></div>
                  <div className="custom-form">
                    <input value={c.name} onChange={(e) => editCustom(c.key, { name: e.target.value })} placeholder="Role name — e.g. Security Architect" maxLength="40" />
                    <textarea value={c.perspective} onChange={(e) => editCustom(c.key, { perspective: e.target.value })} placeholder="What should this specialist care about?" maxLength="800" />
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
            <button className="custom-toggle" onClick={addCustom} disabled={totalRoles >= limits.max_roles}><Sparkles size={14} /> Add a custom specialist</button>
          </div>
        </div>

        <div className="roles-panel length-panel">
          <div className="panel-heading">
            <div><span className="micro">THE PACE</span><h2>How long should it run?</h2></div>
            <div className="seg" role="tablist">
              <button className={turnMode === 'auto' ? 'on' : ''} onClick={() => setTurnMode('auto')}>Auto</button>
              <button className={turnMode === 'manual' ? 'on' : ''} onClick={() => setTurnMode('manual')}>Manual</button>
            </div>
          </div>
          <div className="length-body">
            {turnMode === 'auto' ? (
              <p>The room decides when it has enough. Short replies and long ones are both fine, and the <b>Concluder</b> steps in only when the discussion is ready to close.</p>
            ) : (
              <div className="stepper-row">
                <div className="stepper">
                  <button onClick={() => setTurns(clampTurns(turnCount - 1))} disabled={turnCount <= MANUAL_MIN} aria-label="Fewer turns"><Minus size={15} /></button>
                  <input type="number" min={MANUAL_MIN} max={manualMax} value={turns} onChange={(e) => setTurns(e.target.value)} onBlur={() => setTurns(clampTurns(turns))} aria-label="Number of conversations" />
                  <button onClick={() => setTurns(clampTurns(turnCount + 1))} disabled={turnCount >= manualMax} aria-label="More turns"><Plus size={15} /></button>
                </div>
                <p><b>{turnCount} conversations.</b> Everyone starts wrapping up from turn {Math.max(1, turnCount - 1)}; turn {turnCount} is the Concluder, who closes with the decision.</p>
              </div>
            )}
          </div>
        </div>

        {error && <div className="error-banner"><X size={15} />{error}</div>}
        <button className="launch" disabled={!canLaunch} onClick={start}><span>Open the room</span><ArrowUpRight size={20} /></button>
      </section>

      <section id="how" className="how">
        <div className="how-title"><span>02</span><h2>Not a queue.<br /><i>A conversation.</i></h2></div>
        <div className="flow">
          <FlowItem n="01" title="MASTER" text="Frames the problem and seeds the first answer." /><div className="flow-line" />
          <FlowItem n="02" title="MANAGER" text="Reads the whole transcript and chooses what deserves scrutiny next." /><div className="flow-line" />
          <FlowItem n="03" title="SPECIALISTS" text="Respond one after another. The next voice sees what the previous one said." /><div className="flow-line" />
          <FlowItem n="04" title="CONCLUDER" text="Appears only at the end and turns the whole discussion into a decision." />
        </div>
      </section>
      <footer><span>ROOM IN THE BOX / MULTI-AGENT STUDIO</span><span>{CREDIT}</span></footer>
    </main>
  );
}

function RoleCard({ role, active, disabled, toggle }) {
  return (
    <button className={'role-card ' + (active ? 'selected ' : '') + (disabled ? 'disabled' : '')} onClick={toggle} disabled={disabled}>
      <span className="role-mark">{role.name.slice(0, 1)}</span>
      <span className="role-copy"><b>{role.name}</b><small>{role.perspective}</small></span>
      <span className="check">{active ? '●' : '○'}</span>
    </button>
  );
}
function FlowItem({ n, title, text }) { return <div className="flow-item"><span>{n}</span><b>{title}</b><p>{text}</p></div>; }

function Studio({ session, events, final, status, typing, connected, done, progress, activeStep, progressTotal, plannedTurns, stop, endRoom, copyFinal, downloadTranscript, bottomRef, error }) {
  const msgs = events.filter((e) => e.type === 'message');
  const roles = session?.roles || [];
  const last = msgs.at(-1)?.data.kind;
  const concluderSpoke = msgs.some((m) => m.data.kind === 'concluder');
  const stepLabel = !activeStep ? 'INITIALISING' : plannedTurns ? `TURN ${activeStep} / ${plannedTurns}` : `TURN ${activeStep} · AUTO`;
  return (
    <main className="studio">
      <div className="studio-head">
        <div>
          <div className="eyebrow"><span>03</span><em /> LIVE ROOM</div>
          <h1>{done ? <>Discussion <i>closed.</i></> : <>The room is <i>thinking.</i></>}</h1>
        </div>
        <div className="room-actions">
          <span className={'connection ' + (connected ? 'on' : '')}>{done ? 'FINISHED' : connected ? 'STREAM LIVE' : 'RECONNECTING'}</span>
          {!done && !final && <button className="stop" onClick={stop}><Square size={13} fill="currentColor" /> Stop</button>}
          <button className="icon-btn" onClick={endRoom} title="Close this room"><X size={17} /></button>
        </div>
      </div>
      <div className="progress-wrap">
        <div className="progress-label"><span>{status || 'Waiting for the next move…'}</span><b>{stepLabel}</b></div>
        <div className="progress"><i style={{ width: `${Math.max(2, progress)}%` }} /></div>
      </div>
      <div className="room-grid">
        <aside className="cast">
          <div className="section-label">THE CAST <span>{roles.length}</span></div>
          <div className="cast-list">
            <CastRow name="Master AI" sub="Lead synthesis" type="master" active={last === 'master'} />
            <CastRow name="Manager" sub="Orchestrator" type="manager" active={last === 'manager'} />
            {roles.map((r) => <CastRow key={r.id} name={r.name} sub={r.perspective} type="role" active={typing.includes(r.id)} count={msgs.filter((m) => m.data.role_id === r.id).length} />)}
            <CastRow name="Concluder" sub="Speaks only at the end" type="concluder" active={last === 'concluder'} pending={!concluderSpoke} />
          </div>
          <div className="architecture">
            <div className="section-label">ORCHESTRATION</div>
            <div className="mini-map"><span>MASTER</span><i>↓</i><span>MANAGER</span><i>↕</i><div>{roles.map((r) => <b key={r.id} className={typing.includes(r.id) ? 'hot' : ''}>{r.name}</b>)}</div><i>↓</i><span className={last === 'concluder' ? 'hot-text' : ''}>CONCLUDER</span></div>
          </div>
        </aside>
        <section className="transcript">
          <div className="transcript-top"><span>SHARED TRANSCRIPT</span><div><button onClick={downloadTranscript}><Download size={14} /> Export</button></div></div>
          <div className="messages">
            {msgs.map((e, i) => <Message key={(e.seq ?? i) + '-' + e.type} e={e} />)}
            {typing.map((id) => { const r = roles.find((x) => x.id === id); return r ? <Typing key={id} name={r.name} /> : null; })}
            <div ref={bottomRef} />
          </div>
        </section>
      </div>
      {error && <div className="error-banner studio-error"><X size={15} />{error}</div>}
      <AnimatePresence>{final && <FinalAnswer text={final} copy={copyFinal} />}</AnimatePresence>
      <footer><span>SESSION {session?.id?.slice(0, 12).toUpperCase()}</span><span>{connected ? 'EVENT STREAM CONNECTED' : 'SESSION PRESERVED ON SERVER'}</span><span>{CREDIT}</span></footer>
    </main>
  );
}

function CastRow({ name, sub, type, active, count, pending }) {
  const mark = type === 'master' ? 'M' : type === 'manager' ? '↯' : type === 'concluder' ? '✓' : name.slice(0, 1);
  return (
    <div className={'cast-row ' + (active ? 'active ' : '') + (pending ? 'pending' : '')}>
      <span className={'avatar ' + type}>{mark}</span>
      <div><b>{name}</b><small>{sub}</small></div>
      {count > 0 && <em>{count}</em>}
    </div>
  );
}

function Message({ e }) {
  const d = e.data;
  const kind = d.kind || 'system';
  return (
    <motion.article initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className={'message ' + kind}>
      <div className="message-meta"><span>{d.speaker}</span>{d.step && <i>TURN {d.step}</i>}{kind === 'concluder' && <i className="tag">FINAL VOICE</i>}</div>
      <div className="message-body">
        <Rich text={d.text || d.message} />
        {d.query && <blockquote><Rich text={d.query} /></blockquote>}
      </div>
    </motion.article>
  );
}

function Typing({ name }) { return <div className="typing"><span>{name} is thinking</span><i /><i /><i /></div>; }

function FinalAnswer({ text, copy }) {
  return (
    <motion.section initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} className="final">
      <div className="final-head">
        <div><span className="micro">04 / FINAL ANSWER</span><h2>The room has <i>converged.</i></h2></div>
        <button onClick={copy}><Copy size={15} /> Copy</button>
      </div>
      <div className="final-text"><Rich text={text} /></div>
    </motion.section>
  );
}

function SettingsModal({ apiDraft, setApiDraft, tokenDraft, setTokenDraft, save, close }) {
  return (
    <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <motion.div className="modal" initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }}>
        <div className="modal-head"><div><span className="micro">CONNECTION</span><h2>Studio settings</h2></div><button className="icon-btn" onClick={close}><X size={17} /></button></div>
        <label>API base URL<input value={apiDraft} onChange={(e) => setApiDraft(e.target.value)} placeholder="http://localhost:8000" /></label>
        <label>Access token <span>optional</span><input type="password" value={tokenDraft} onChange={(e) => setTokenDraft(e.target.value)} placeholder="Only if ACCESS_TOKEN is enabled" /></label>
        <div className="secure"><ShieldCheck size={16} /><span>API keys never belong in this frontend. The backend owns Groq credentials.</span></div>
        <button className="launch" onClick={save}>Save connection <ArrowUpRight size={18} /></button>
      </motion.div>
    </motion.div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
