import React,{useEffect,useMemo,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {AnimatePresence,motion} from 'framer-motion';
import {ArrowUpRight,ChevronDown,Copy,Download,ExternalLink,LoaderCircle,Menu,Pause,Play,RefreshCw,Settings2,ShieldCheck,Sparkles,Square,Users,X,Zap} from 'lucide-react';
import './styles.css';

const API_DEFAULT=(import.meta.env.VITE_API_BASE_URL||'http://localhost:8000');
const presetFallback=[
 ['student','Student','Practicality, learning difficulty, student feasibility, implementation effort, and realistic build scope.'],
 ['professor','Professor','Technical depth, academic value, correctness, engineering quality, and academic strength.'],
 ['scientist','Scientist','Scientific reasoning, innovation, technical possibilities, research potential, and conceptual soundness.'],
 ['judge','Judge','Originality, presentation potential, relevance, technical impact, and competition-readiness.'],
 ['technical_expert','Technical Expert','Architecture, implementation problems, bugs, scalability, technical weaknesses, and improvements.'],
 ['product_manager','Product Manager','User value, market fit, scope control, prioritisation, and realistic MVP definition.'],
 ['devils_advocate','Devil’s Advocate','Hidden assumptions, failure modes, risks, and weaknesses others may overlook.']
].map(([id,name,perspective])=>({id,name,perspective}));

const store={get token(){return localStorage.getItem('cr_token')||''},set token(v){v?localStorage.setItem('cr_token',v):localStorage.removeItem('cr_token')},get api(){return localStorage.getItem('cr_api')||API_DEFAULT},set api(v){localStorage.setItem('cr_api',v)}};
const api=(path,opts={})=>fetch(store.api.replace(/\/$/,'')+path,{...opts,headers:{'Content-Type':'application/json',...(store.token?{'X-Access-Token':store.token}:{}),...(opts.headers||{})}});
const eventText=(e)=>{try{return JSON.parse(e.data)}catch{return {}}};

function App(){
 const [screen,setScreen]=useState('home');
 const [roles,setRoles]=useState(presetFallback),[limits,setLimits]=useState({min_roles:2,max_roles:5,min_queries:10,max_queries:24});
 const [selected,setSelected]=useState(['student','technical_expert','judge']);
 const [custom,setCustom]=useState(false),[customName,setCustomName]=useState(''),[customPerspective,setCustomPerspective]=useState('');
 const [task,setTask]=useState(''),[session,setSession]=useState(null),[events,setEvents]=useState([]),[final,setFinal]=useState('');
 const [status,setStatus]=useState(''),[typing,setTyping]=useState([]),[connected,setConnected]=useState(false),[error,setError]=useState('');
 const [apiOpen,setApiOpen]=useState(false),[apiDraft,setApiDraft]=useState(store.api),[tokenDraft,setTokenDraft]=useState(store.token);
 const esRef=useRef(null), bottomRef=useRef(null);
 useEffect(()=>{api('/api/roles').then(async r=>{if(r.ok){const d=await r.json();setRoles(d.presets||presetFallback);setLimits(d)}}).catch(()=>{});},[]);
 useEffect(()=>{bottomRef.current?.scrollIntoView({behavior:'smooth'})},[events,typing,final]);
 const selectedRoles=useMemo(()=>roles.filter(r=>selected.includes(r.id)),[roles,selected]);
 const activeStep=useMemo(()=>{const m=events.filter(e=>e.type==='message'&&e.data.step);return m.length?Math.max(...m.map(e=>e.data.step||0)):0},[events]);
 const progress=Math.min(100,Math.round((activeStep/(limits.max_queries||24))*100));
 function toggleRole(id){setSelected(s=>s.includes(id)?s.filter(x=>x!==id):s.length<limits.max_roles?[...s,id]:s)}
 function saveSettings(){store.api=apiDraft.trim()||API_DEFAULT;store.token=tokenDraft.trim();setApiOpen(false)}
 async function start(){
  setError('');setFinal('');setEvents([]);setStatus('Opening the studio…');
  const payloadRoles=custom?[...selectedRoles,{name:customName.trim(),perspective:customPerspective.trim()}]:selected;
  if(custom&&(!customName.trim()||!customPerspective.trim())){setError('Give the custom role a name and perspective.');return}
  if(payloadRoles.length<limits.min_roles||payloadRoles.length>limits.max_roles){setError(`Choose ${limits.min_roles}–${limits.max_roles} roles.`);return}
  try{const r=await api('/api/discussions',{method:'POST',body:JSON.stringify({task:task.trim(),roles:payloadRoles})});const d=await r.json();if(!r.ok)throw Error(d.detail||'Could not start discussion.');setSession({id:d.id,roles:d.roles||[]});setScreen('studio');openStream(d.id)}catch(e){setError(e.message);setStatus('')}
 }
 function openStream(id,lastSeq=null){
  esRef.current?.close();setConnected(false);
  let url=store.api.replace(/\/$/,'')+`/api/discussions/${id}/stream`;
  if(store.token)url+=`?token=${encodeURIComponent(store.token)}`;
  const es=new EventSource(url);esRef.current=es;
  const handle=(type)=>e=>{const d=eventText(e);setEvents(prev=>prev.some(x=>x.seq===d.seq&&x.type===type)?prev:[...prev,{seq:d.seq,type,data:d}]);
    if(type==='status')setStatus(d.text||'');
    if(type==='typing')setTyping(t=>[...t.filter(x=>x!==d.role_id),d.role_id]);
    if(type==='message')setTyping(t=>d.role_id?t.filter(x=>x!==d.role_id):t);
    if(type==='final'){setFinal(d.text||'');setStatus('Final answer ready.')}
    if(type==='error')setError(d.message||'Discussion error.');
    if(type==='done'){setConnected(false);setStatus(d.status==='completed'?'Discussion completed.':`Discussion ${d.status}.`);setTyping([]);es.close()}
  };
  ['session','status','typing','message','final','error','done'].forEach(t=>es.addEventListener(t,handle(t)));
  es.onopen=()=>setConnected(true);es.onerror=()=>setConnected(false);
 }
 async function stop(){if(!session)return;try{await api(`/api/discussions/${session.id}/stop`,{method:'POST'})}catch(e){setError(e.message)}}
 async function resume(){if(session){setScreen('studio');openStream(session.id)}}
 function reset(){esRef.current?.close();setSession(null);setEvents([]);setFinal('');setStatus('');setError('');setScreen('home')}
 async function copyFinal(){try{await navigator.clipboard.writeText(final)}catch{}}
 function downloadTranscript(){if(!session)return;const text=events.map(e=>`${e.data.speaker||e.type}\n${e.data.text||e.data.message||''}`).join('\n\n');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:'text/plain'}));a.download=`discussion-${session.id}.txt`;a.click();URL.revokeObjectURL(a.href)}
 return <div className="app"><Noise/><Header onHome={reset} onSettings={()=>setApiOpen(true)} onMenu={()=>setApiOpen(true)}/>
  <AnimatePresence mode="wait">
   {screen==='home'&&<Home key="home" task={task} setTask={setTask} roles={roles} selected={selected} toggleRole={toggleRole} custom={custom} setCustom={setCustom} customName={customName} setCustomName={setCustomName} customPerspective={customPerspective} setCustomPerspective={setCustomPerspective} limits={limits} start={start} error={error} />}
   {screen==='studio'&&<Studio key="studio" session={session} events={events} final={final} status={status} typing={typing} connected={connected} progress={progress} activeStep={activeStep} limits={limits} stop={stop} reset={reset} copyFinal={copyFinal} downloadTranscript={downloadTranscript} bottomRef={bottomRef} error={error} />}
  </AnimatePresence>
  <AnimatePresence>{apiOpen&&<SettingsModal apiDraft={apiDraft} setApiDraft={setApiDraft} tokenDraft={tokenDraft} setTokenDraft={setTokenDraft} save={saveSettings} close={()=>setApiOpen(false)}/>}</AnimatePresence>
 </div>
}
function Noise(){return <div className="noise"/>}
function Header({onHome,onSettings,onMenu}){return <header><button className="brand" onClick={onHome}><span>ROOM</span><i>in the</i><span>BOX</span></button><nav><button onClick={onHome}>Studio</button><button onClick={()=>document.getElementById('how')?.scrollIntoView({behavior:'smooth'})}>How it works</button></nav><div className="header-right"><span className="live-dot"><b/> SYSTEM READY</span><button className="icon-btn desktop-settings" onClick={onSettings} title="Connection settings"><Settings2 size={17}/></button><button className="icon-btn mobile-menu" onClick={onMenu}><Menu size={19}/></button></div></header>}
function Home({task,setTask,roles,selected,toggleRole,custom,setCustom,customName,setCustomName,customPerspective,setCustomPerspective,limits,start,error}){
 return <main className="home"><section className="hero"><div className="eyebrow"><span>01</span><em/> MULTI-AGENT DISCUSSION STUDIO</div><h1>Put the question<br/><i>in the room.</i></h1><p className="dek">One Master. One Manager. A panel of specialists. They challenge, refine and converge before you get the answer.</p><div className="hero-meta"><span>LIVE ORCHESTRATION</span><span>UP TO {limits.max_roles} SPECIALISTS</span><span>SHARED MEMORY</span></div></section>
 <section className="workspace"><div className="task-card"><div className="card-top"><span>THE BRIEF</span><span>{task.length}/4000</span></div><textarea value={task} onChange={e=>setTask(e.target.value)} placeholder="What do you want the room to figure out?" maxLength="4000"/><div className="examples"><button onClick={()=>setTask('Design a genuinely original software product for a 16-hour college hackathon. Challenge the idea from technical, user, and judging perspectives.')}>Hackathon concept</button><button onClick={()=>setTask('Review this architecture and find the most important technical risks, then propose a practical fix for each.')}>Architecture review</button></div></div>
 <div className="roles-panel"><div className="panel-heading"><div><span className="micro">THE PANEL</span><h2>Choose your voices</h2></div><span className="count">{selected.length}/{limits.max_roles}</span></div><div className="role-grid">{roles.map(r=><RoleCard key={r.id} role={r} active={selected.includes(r.id)} disabled={!selected.includes(r.id)&&selected.length>=limits.max_roles} toggle={()=>toggleRole(r.id)}/>)}</div><div className="custom-wrap"><button className={'custom-toggle '+(custom?'active':'')} onClick={()=>setCustom(!custom)}><Sparkles size={14}/> Add a custom specialist <ChevronDown size={15}/></button>{custom&&<motion.div initial={{height:0,opacity:0}} animate={{height:'auto',opacity:1}} className="custom-form"><input value={customName} onChange={e=>setCustomName(e.target.value)} placeholder="Role name — e.g. Security Architect" maxLength="40"/><textarea value={customPerspective} onChange={e=>setCustomPerspective(e.target.value)} placeholder="What should this specialist care about?" maxLength="800"/></motion.div>}</div></div>
 {error&&<div className="error-banner"><X size={15}/>{error}</div>}
 <button className="launch" disabled={!task.trim()||selected.length<limits.min_roles} onClick={start}><span>Open the room</span><ArrowUpRight size={20}/></button></section>
 <section id="how" className="how"><div className="how-title"><span>02</span><h2>Not a queue.<br/><i>A conversation.</i></h2></div><div className="flow"><FlowItem n="01" title="MASTER" text="Frames the problem and seeds the first answer."/><div className="flow-line"/><FlowItem n="02" title="MANAGER" text="Reads the whole transcript and chooses what deserves scrutiny next."/><div className="flow-line"/><FlowItem n="03" title="SPECIALISTS" text="Respond one after another. The next voice sees what the previous one said."/><div className="flow-line"/><FlowItem n="04" title="MASTER" text="Synthesises the refined discussion into your final response."/></div></section>
 <footer><span>ROOM IN THE BOX / MULTI-AGENT STUDIO</span><span>SERVER-SIDE KEYS · REPLAYABLE STREAM · SHARED MEMORY</span></footer>
 </main>
}
function RoleCard({role,active,disabled,toggle}){return <button className={'role-card '+(active?'selected ':'')+(disabled?'disabled':'')} onClick={toggle} disabled={disabled}><span className="role-mark">{role.name.slice(0,1)}</span><span className="role-copy"><b>{role.name}</b><small>{role.perspective}</small></span><span className="check">{active?'●':'○'}</span></button>}
function FlowItem({n,title,text}){return <div className="flow-item"><span>{n}</span><b>{title}</b><p>{text}</p></div>}
function Studio({session,events,final,status,typing,connected,progress,activeStep,limits,stop,reset,copyFinal,downloadTranscript,bottomRef,error}){
 const msgs=events.filter(e=>e.type==='message');const roles=session?.roles||[];
 return <main className="studio"><div className="studio-head"><div><div className="eyebrow"><span>03</span><em/> LIVE ROOM</div><h1>The room is <i>thinking.</i></h1></div><div className="room-actions"><span className={'connection '+(connected?'on':'')}>{connected?'STREAM LIVE':'RECONNECTING'}</span>{!final&&<button className="stop" onClick={stop}><Square size={13} fill="currentColor"/> Stop</button>}<button className="icon-btn" onClick={reset}><X size={17}/></button></div></div>
 <div className="progress-wrap"><div className="progress-label"><span>{status||'Waiting for the next move…'}</span><b>{activeStep ? `STEP ${activeStep} / ${limits.max_queries}` : 'INITIALISING'}</b></div><div className="progress"><i style={{width:`${Math.max(2,progress)}%`}}/></div></div>
 <div className="room-grid"><aside className="cast"><div className="section-label">THE CAST <span>{roles.length}</span></div><div className="cast-list"><CastRow name="Master AI" sub="Lead synthesis" type="master" active={msgs.at(-1)?.data.kind==='master'}/><CastRow name="Manager" sub="Orchestrator" type="manager" active={msgs.at(-1)?.data.kind==='manager'}/>{roles.map(r=><CastRow key={r.id} name={r.name} sub={r.perspective} type="role" active={typing.includes(r.id)} count={msgs.filter(m=>m.data.role_id===r.id).length}/>)}</div><div className="architecture"><div className="section-label">ORCHESTRATION</div><div className="mini-map"><span>MASTER</span><i>↓</i><span>MANAGER</span><i>↕</i><div>{roles.map(r=><b key={r.id} className={typing.includes(r.id)?'hot':''}>{r.name}</b>)}</div></div></div></aside>
 <section className="transcript"><div className="transcript-top"><span>SHARED TRANSCRIPT</span><div><button onClick={downloadTranscript}><Download size={14}/> Export</button></div></div><div className="messages">{events.filter(e=>e.type==='message').map((e,i)=><Message key={(e.seq??i)+'-'+e.type} e={e}/>) }{typing.map(id=>{const r=roles.find(x=>x.id===id);return r?<Typing key={id} name={r.name}/>:null})}<div ref={bottomRef}/></div></section></div>
 {error&&<div className="error-banner studio-error"><X size={15}/>{error}</div>}
 <AnimatePresence>{final&&<FinalAnswer text={final} copy={copyFinal}/>}</AnimatePresence>
 <footer><span>SESSION {session?.id?.slice(0,12).toUpperCase()}</span><span>{connected?'EVENT STREAM CONNECTED':'SESSION PRESERVED ON SERVER'}</span></footer>
 </main>
}
function CastRow({name,sub,type,active,count}){return <div className={'cast-row '+(active?'active':'')}><span className={'avatar '+type}>{type==='master'?'M':type==='manager'?'↯':name.slice(0,1)}</span><div><b>{name}</b><small>{sub}</small></div>{count>0&&<em>{count}</em>}</div>}
function Message({e}){const d=e.data;const kind=d.kind||'system';return <motion.article initial={{opacity:0,y:12}} animate={{opacity:1,y:0}} className={'message '+kind}><div className="message-meta"><span>{d.speaker}</span>{d.step&&<i>STEP {d.step}</i>}</div><div className="message-body">{d.text||d.message}{d.query&&<blockquote>{d.query}</blockquote>}</div></motion.article>}
function Typing({name}){return <div className="typing"><span>{name} is thinking</span><i/><i/><i/></div>}
function FinalAnswer({text,copy}){return <motion.section initial={{opacity:0,y:30}} animate={{opacity:1,y:0}} className="final"><div className="final-head"><div><span className="micro">04 / FINAL ANSWER</span><h2>The room has <i>converged.</i></h2></div><button onClick={copy}><Copy size={15}/> Copy</button></div><div className="final-text">{text.split('\n').map((x,i)=><p key={i}>{x||<br/>}</p>)}</div></motion.section>}
function SettingsModal({apiDraft,setApiDraft,tokenDraft,setTokenDraft,save,close}){return <motion.div className="modal-backdrop" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}><motion.div className="modal" initial={{y:20,opacity:0}} animate={{y:0,opacity:1}}><div className="modal-head"><div><span className="micro">CONNECTION</span><h2>Studio settings</h2></div><button className="icon-btn" onClick={close}><X size={17}/></button></div><label>API base URL<input value={apiDraft} onChange={e=>setApiDraft(e.target.value)} placeholder="http://localhost:8000"/></label><label>Access token <span>optional</span><input type="password" value={tokenDraft} onChange={e=>setTokenDraft(e.target.value)} placeholder="Only if ACCESS_TOKEN is enabled"/></label><div className="secure"><ShieldCheck size={16}/><span>API keys never belong in this frontend. The backend owns Groq credentials.</span></div><button className="launch" onClick={save}>Save connection <ArrowUpRight size={18}/></button></motion.div></motion.div>}

createRoot(document.getElementById('root')).render(<App/>);
