import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity, ArrowDownRight, ArrowLeft, ArrowRight, ArrowUpRight, Bell, BookOpen, BrainCircuit,
  CalendarDays, Check, CheckCheck, ChevronDown, ChevronRight, CircleAlert, CircleCheck,
  Clock3, Command, Database, ExternalLink, FileCheck2, FileText, Filter, Fingerprint, GitBranch,
  Globe2, Layers3, LayoutDashboard, LockKeyhole, MessageSquareText, MoreHorizontal, Play,
  RotateCcw, Search, Send, ShieldCheck, ShieldOff, Sparkles, Terminal, Trash2, WandSparkles,
  X, Zap
} from 'lucide-react'
import { request, withQuery, fmtDate, fmtTime } from './api'
import OrbitScene from './components/OrbitScene'

const nav = [
  {id:'overview',name:'Overview',icon:LayoutDashboard},
  {id:'ask',name:'Ask TraceMind',icon:Sparkles},
  {id:'briefs',name:'Meeting studio',icon:CalendarDays},
  {id:'evidence',name:'Evidence explorer',icon:Database},
  {id:'memory',name:'Memory timeline',icon:GitBranch},
  {id:'evaluation',name:'Evaluation lab',icon:Activity},
]
const colorByType = {chat:'mint',mail:'blue',task:'amber',doc:'purple',event:'blue',note:'pink',sheet:'amber',notification:'muted'}
const promptSamples = [
  'Who owns billing for Northbeam now?',
  'When is the homepage redesign for NB due?',
  'Send the NB deck to Arjun. Which Arjun is that?',
  'Is the Friday thing done?'
]
const meetingTopics = ['Delivery changes','Promises & owners','Evidence sources','Open questions']

function useRemote(path, deps=[]) {
  const [data,setData] = useState(null)
  const [loading,setLoading] = useState(true)
  const [error,setError] = useState(null)
  useEffect(()=>{
    let active=true
    setLoading(true);setError(null)
    request(path).then(value=>{if(active){setData(value);setLoading(false)}}).catch(e=>{if(active){setError(e.message);setLoading(false)}})
    return ()=>{active=false}
  },deps)
  return {data,loading,error}
}

function Logo(){return <div className="brand-symbol"><div className="brand-inner"><BrainCircuit size={19} strokeWidth={1.7}/></div></div>}
function Tag({children,tone='mint',dot=false}){return <span className={`tag tag-${tone}`}>{dot&&<i className="tag-dot"/>}{children}</span>}
function SourceTag({id,onOpen}){return <button className="source-tag" onClick={()=>onOpen(id)} title={`Inspect source ${id}`}><FileCheck2 size={12}/>{id}<ArrowUpRight size={12}/></button>}
function Empty({icon:Icon=Database,title='Nothing to show yet',sub='Try another day or client.'}){return <div className="empty"><div className="empty-icon"><Icon size={22}/></div><strong>{title}</strong><p>{sub}</p></div>}
function Spinner({label='Loading intelligence'}){return <div className="wait"><div className="wait-ring"/><span>{label}</span></div>}
function SectionTitle({eyebrow,title,subtitle,action}){return <div className="section-heading"><div><div className="eyebrow">{eyebrow}</div><h2>{title}</h2>{subtitle&&<p>{subtitle}</p>}</div>{action}</div>}
function StatusPill({value}){const tone={done:'mint',blocked:'danger',in_progress:'blue',todo:'muted',brief:'mint',nothing_new:'muted'}[value]||'muted';return <Tag tone={tone} dot>{(value||'unknown').replaceAll('_',' ')}</Tag>}
function Card({children,className='',...other}){return <div className={'surface-card '+className} {...other}>{children}</div>}
function StatCard({icon:Icon,label,value,hint,accent}){return <div className={'stat-card accent-'+accent}><div className="stat-icon"><Icon size={18}/></div><div className="stat-value">{value}</div><div className="stat-label">{label}</div><div className="stat-hint">{hint}</div></div>}

function Sidebar({view,setView,score}) {
  return <aside className="sidebar">
    <button className="sidebar-brand" onClick={()=>setView('overview')}>
      <Logo/><div className="brand-label"><span>tracemind<span className="brand-period">.</span></span><small>INTELLIGENCE STUDIO</small></div>
    </button>
    <div className="side-scroll">
      <div className="side-label">WORKSPACE</div>
      <nav className="side-nav">{nav.map(({id,name,icon:Icon})=><button key={id} className={'nav-item '+(view===id?'active':'')} onClick={()=>setView(id)}><Icon size={18} strokeWidth={1.9}/><span>{name}</span>{view===id&&<div className="active-indicator"/>}</button>)}</nav>
      <div className="side-label side-label-space">THE ENGINE</div>
      <div className="side-engine"><div className="engine-row"><span className="engine-led"/><span>Evidence-first reasoning</span><Check size={14}/></div><div className="engine-row"><span className="engine-led purple-led"/><span>Persistent fact memory</span><Check size={14}/></div><div className="engine-row"><span className="engine-led blue-led"/><span>Scope-aware privacy</span><Check size={14}/></div></div>
      <div className="side-tip"><div className="side-tip-icon"><Fingerprint size={20}/></div><strong>Every answer has a trail.</strong><p>Open a citation to inspect the source behind the claim.</p></div>
    </div>
    <div className="sidebar-bottom"><div className="sidebar-score"><span className="score-icon"><ShieldCheck size={18}/></span><div><span>Public benchmark</span><strong>{score?.available?`${score.score.total} / ${score.score.max_scored}`:'Run evaluator'}</strong></div><ArrowUpRight size={15}/></div><div className="sidebar-foot"><span>BUILDSprint R3</span><span>•</span><span>Local demo</span></div></div>
  </aside>
}

function Topbar({view,person,setPerson,day,setDay,bootstrap,onOpenMenu}){
 const today=new Date(`2026-11-${String(day+1).padStart(2,'0')}T12:00:00Z`)
 return <header className="topbar"><div className="bread"><span>WORKSPACE</span><ChevronRight size={14}/><strong>{nav.find(n=>n.id===view)?.name}</strong></div><div className="topbar-controls"><div className="day-picker"><Clock3 size={14}/><span>Day</span><select value={day} onChange={e=>setDay(Number(e.target.value))}>{bootstrap?.days?.map(d=><option key={d} value={d}>{d}</option>)}</select></div><div className="control-divider"/><div className="persona-picker"><span className="avatar-small">{(bootstrap?.persons?.find(p=>p.id===person)?.name||'M').slice(0,1)}</span><div className="persona-names"><strong>{bootstrap?.persons?.find(p=>p.id===person)?.name||'Select persona'}</strong><small>Demo identity · no authentication</small></div><select className="persona-select" value={person} onChange={e=>setPerson(e.target.value)} aria-label="Choose demo persona">{bootstrap?.persons?.map(p=><option key={p.id} value={p.id}>{p.name} — {p.org}</option>)}</select><ChevronDown size={15}/></div></div></header>
}

function Overview({ctx,goAsk,openSource,goView}){
 const {data,loading,error}=useRemote(withQuery('/dashboard',ctx),[ctx.person,ctx.day])
 if(loading)return <Spinner/>
 if(error)return <Empty title="Dashboard unavailable" sub={error}/>
 const s=data.stats
 return <div className="view-enter">
   <div className="welcome-line"><span className="eyebrow"><span className="live-pulse"/> LIVE WORKSPACE INTELLIGENCE</span><span className="date-stamp">AS OF {new Date(data.as_of).toLocaleDateString('en-GB',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'}).toUpperCase()}</span></div>
   <div className="hero"><div className="hero-left"><Tag tone="mint" dot>Source-grounded workspace</Tag><h1>Clarity, in a world<br/>of <span className="headline-gradient">constant change.</span></h1><p>Ask better questions. Walk into every meeting prepared. See exactly where every answer came from.</p><div className="hero-actions"><button className="button button-primary" onClick={()=>goAsk()}>Ask TraceMind <ArrowUpRight size={17}/></button><button className="button button-subtle" onClick={()=>goView('briefs')}>Open meeting briefs <ArrowRight size={17}/></button></div><div className="hero-verification"><ShieldCheck size={16}/><span>Privacy filtered</span><span className="bullet-sep">·</span><span>Evidence cited</span><span className="bullet-sep">·</span><span>Time aware</span></div></div><div className="hero-visual"><OrbitScene counts={data.record_types}/><div className="orbit-label orbit-label-top"><span className="tiny-orbit-dot mint-dot"/> EVIDENCE NETWORK</div><div className="orbit-label orbit-label-bottom"><span className="tiny-orbit-dot purple-dot"/> {s.records} ACCESSIBLE NODES</div><div className="orbit-centered"><BrainCircuit size={25}/></div></div></div>
   <div className="stats-grid"><StatCard icon={Database} label="Accessible records" value={s.records.toLocaleString()} hint="Privacy-scoped sources" accent="mint"/><StatCard icon={FileCheck2} label="Active tasks" value={s.tasks} hint={`${s.done} complete · ${s.blocked} blocked`} accent="purple"/><StatCard icon={CalendarDays} label="Upcoming meetings" value={s.meetings} hint="From calendar evidence" accent="blue"/><StatCard icon={LockKeyhole} label="Private records" value={s.private} hint="Only visible to this persona" accent="amber"/></div>
   <div className="overview-grid"><Card className="activity-panel"><div className="panel-head"><div><div className="eyebrow">SIGNAL FEED</div><h3>What changed</h3></div><button className="icon-text-button" onClick={()=>goView('evidence')}>All evidence <ArrowUpRight size={16}/></button></div><div className="activity-feed">{data.signals.length?data.signals.slice(0,6).map((ev,i)=><div className="activity-entry" key={ev.source+i}><div className={'activity-bubble bubble-'+(i%3===0?'mint':i%3===1?'purple':'amber')}><Activity size={15}/></div><div className="activity-copy"><p>{ev.text}</p><div className="activity-meta"><span>{ev.client||'Internal'}</span><span>·</span><span>{fmtDate(ev.at)}</span></div></div><SourceTag id={ev.source} onOpen={openSource}/></div>):<Empty title="No notable changes"/>}</div></Card>
    <div className="overview-right"><Card className="client-panel"><div className="panel-head"><div><div className="eyebrow">WORKSTREAM DISTRIBUTION</div><h3>Client pulse</h3></div><Layers3 size={18} className="muted-icon"/></div><div className="client-bars">{Object.entries(data.client_counts).map(([client,count],i)=>{const max=Math.max(...Object.values(data.client_counts),1);return <div className="client-bar" key={client}><div className="bar-caption"><span><i className={'legend-dot ld-'+i}/>{client==='northbeam'?'Northbeam Retail':client==='cobaltline'?'Cobaltline Logistics':client==='alderpoint'?'Alderpoint Foods':client}</span><b>{count}</b></div><div className="bar-track"><div className={'bar-fill bar-'+i} style={{width:(count/max*100)+'%'}}/></div></div>})}</div><div className="panel-footnote"><CircleCheck size={15}/> Counts reflect this persona's authorized evidence.</div></Card>
    <Card className="meeting-mini"><div className="panel-head"><div><div className="eyebrow">UP NEXT</div><h3>Meeting prep</h3></div><CalendarDays size={18} className="muted-icon"/></div>{data.meetings.length?data.meetings.map(m=><div key={m.id} className="mini-meeting"><span className="meeting-mini-date"><b>{fmtDate(m.start).split(' ')[0]}</b><small>{fmtDate(m.start).split(' ')[1]}</small></span><div><strong>{m.title}</strong><small>{m.client} · {fmtTime(m.start)}</small></div></div>):<p className="muted-description">No meetings scheduled for this persona on the following day.</p>}<button className="inline-action" onClick={()=>goView('briefs')}>Prepare for meetings <ArrowRight size={16}/></button></Card></div></div>
   <div className="bottom-note"><LockKeyhole size={14}/><span>Demo personas are simulated identities, not secure login accounts. The backend checks record visibility for every request.</span></div>
 </div>
}

function AskStudio({ctx,openSource,initialQuestion,setInitialQuestion,modelReady}){
 const [question,setQuestion]=useState(initialQuestion||'')
 const [mode,setMode]=useState('baseline')
 const [loading,setLoading]=useState(false)
 const [response,setResponse]=useState(null)
 const [error,setError]=useState('')
 useEffect(()=>{if(initialQuestion)setQuestion(initialQuestion)},[initialQuestion])
 const ask=async(q)=>{
   const text=(q??question).trim();if(!text)return
   setQuestion(text);setLoading(true);setError('');setResponse(null);setInitialQuestion('')
   try{setResponse(await request('/ask',{method:'POST',body:JSON.stringify({person:ctx.person,day:ctx.day,question:text,mode})}))}
   catch(e){setError(e.message)}finally{setLoading(false)}
 }
 return <div className="view-enter"><SectionTitle eyebrow="ASK THE WORKSPACE" title="Intelligence, with receipts." subtitle="Ask a natural-language question. Verify each answer against its underlying records." action={<Tag tone="mint" dot>Grounded response engine</Tag>}/>
  <div className="ask-grid"><div className="ask-main"><Card className="query-composer"><div className="composer-header"><div className="composer-star"><Sparkles size={19}/></div><div><strong>Ask anything about your workspace</strong><p>Answers are based only on your accessible records.</p></div></div><form onSubmit={e=>{e.preventDefault();ask()}}><textarea value={question} onChange={e=>setQuestion(e.target.value)} placeholder="e.g. Who is responsible for the Northbeam launch?" rows={3} maxLength={600}/><div className="composer-bottom"><div className="mode-toggle"><button type="button" className={mode==='baseline'?'selected':''} onClick={()=>setMode('baseline')}><Zap size={13}/> Fast</button><button type="button" className={mode==='lexical'?'selected':''} onClick={()=>setMode('lexical')}><Search size={13}/> Evidence</button><button type="button" className={mode==='vector'?'selected':''} onClick={()=>setMode('vector')} title="Persistent Qdrant vector search; uses local MiniLM and needs no API key"><Database size={13}/> Vector DB</button><button type="button" disabled={!modelReady} title={modelReady?'Send authorized team evidence to configured external LLM':'External model disabled in local demo'} className={mode==='model'?'selected':''} onClick={()=>setMode('model')}><WandSparkles size={13}/> Model</button></div><button className="button button-primary" type="submit" disabled={loading||!question.trim()}>{loading?'Reasoning…':'Ask TraceMind'}<ArrowUpRight size={17}/></button></div></form></Card>
  {!response&&!loading&&!error&&<div className="suggestions"><span>TRY ASKING</span><div className="suggestion-grid">{promptSamples.map(q=><button className="suggestion" key={q} onClick={()=>ask(q)}><MessageSquareText size={16}/><span>{q}</span><ArrowUpRight size={15}/></button>)}</div></div>}
  {loading&&<Card className="answer-card"><Spinner label={mode==='hybrid'||mode==='vector'?'Loading local MiniLM and retrieving evidence…':'Inspecting your authorized records…'}/></Card>}
  {error&&<div className="error-banner"><CircleAlert size={16}/>{error}</div>}
  {response&&<Card className="answer-card"><div className="answer-top"><div><div className="eyebrow">TRACEMIND RESPONSE</div><h3>Evidence-grounded result</h3></div><Tag tone={response.result.refused?'danger':'mint'} dot>{response.result.refused?'Access restricted':response.result.clarify?'Clarification needed':response.result.answer?.sources?.length?'Verified sources':'Conservative response'}</Tag></div>{response.result.refused?<div className="answer-body"><ShieldOff size={24} className="danger-ink"/><p>This request was refused: <strong>{response.result.refused.reason}</strong>.</p></div>:response.result.clarify?<div className="answer-body"><CircleAlert size={24} className="purple-ink"/><p>{response.result.clarify.question}</p><div className="clarify-options">{response.result.clarify.options?.map((o,i)=><span key={i}>{typeof o==='string'?o:o.text||o.id}</span>)}</div></div>:<div className="answer-body"><div className="answer-icon"><Sparkles size={22}/></div><p>{response.result.answer?.text||'No verified answer available.'}</p></div>}
  {!!response.result.answer?.sources?.length&&<div className="answer-sources"><span className="eyebrow">CITATIONS</span><div className="source-tags">{response.result.answer.sources.map(id=><SourceTag id={id} key={id} onOpen={openSource}/>)}</div></div>}
  <div className="answer-footer"><span><Clock3 size={14}/> {response.elapsed_ms} ms total</span><span><Database size={14}/> {response.retrieval.evidence.length} suggested sources</span><span><BrainCircuit size={14}/> {response.retrieval.neural_used?'Local neural retrieval':'Deterministic / lexical'}</span></div></Card>}
 </div><div className="ask-right"><Card className="side-help"><div className="eyebrow">HOW IT THINKS</div><h3>A clear chain of evidence</h3><div className="how-steps"><div><span>01</span><strong>Scope</strong><p>Restrict records to your organization, visibility, and requested time.</p></div><div><span>02</span><strong>Retrieve</strong><p>Search by keywords or local MiniLM embeddings when you choose neural mode.</p></div><div><span>03</span><strong>Verify</strong><p>Only return claims supported by permitted source IDs.</p></div></div><div className="help-foot"><ShieldCheck size={16}/> Private and restricted records are never sent to an external model. Model mode requires explicit opt-in.</div></Card>
 {response&&<Card className="evidence-suggestion-panel"><div className="panel-head"><div><div className="eyebrow">RETRIEVAL TRACE</div><h3>Candidate sources</h3></div><Tag tone={response.retrieval.neural_used?'purple':'muted'}>{response.retrieval.mode}</Tag></div>{response.retrieval.error&&<div className="warning-small">{response.retrieval.error}</div>}{response.retrieval.evidence.length?response.retrieval.evidence.map((r,i)=><button className="evidence-suggestion" key={r.id} onClick={()=>openSource(r.id)}><span className="result-number">{String(i+1).padStart(2,'0')}</span><div><strong>{r.title}</strong><p>{r.excerpt}</p><small>{r.id} · {r.semantic_similarity!=null?`similarity ${Math.round(r.semantic_similarity*100)}%`:r.type}</small></div><ArrowUpRight size={15}/></button>):<Empty title="No ranked evidence" sub="Select Evidence or Neural to inspect candidate records."/>}<div className="help-foot">Suggested sources are not automatically verified answers.</div></Card>}</div></div></div>
}

function MeetingStudio({ctx,openSource}){
 const {data,loading,error}=useRemote(withQuery('/briefs',ctx),[ctx.person,ctx.day])
 if(loading)return <Spinner/>
 if(error)return <Empty title="Unable to load meetings" sub={error}/>
 return <div className="view-enter"><SectionTitle eyebrow="MEETING INTELLIGENCE" title="Walk in knowing everything." subtitle="TraceMind finds meaningful changes, outstanding promises, and questions worth asking." action={<Tag tone="blue"><CalendarDays size={12}/> {fmtDate(data.date)}</Tag>}/>
  {data.briefs.length?<div className="meeting-cards">{data.briefs.map(b=><Card className="meeting-detail" key={b.meeting_id}><div className="meeting-detail-head"><div><div className="eyebrow">{b.client||'WORKSPACE'} · {b.meeting_id}</div><h3>{b.title}</h3></div><StatusPill value={b.status}/></div>{b.status==='nothing_new'?<Empty title="Nothing meaningful changed" sub="TraceMind chose accuracy over filler for this meeting." icon={CheckCheck}/>:<><div className="meeting-columns"><section><h4><Activity size={16}/> Meaningful changes</h4>{b.changed.length?b.changed.map((c,i)=><div className="brief-bullet" key={i}><span className="bullet-glyph"/><div><p>{c.text}</p><div className="source-tags">{c.sources?.map(id=><SourceTag key={id} id={id} onOpen={openSource}/>)}</div></div></div>):<p className="muted-description">No significant changes.</p>}</section><section><h4><CheckCheck size={16}/> Open commitments</h4>{b.promises?.length?b.promises.slice(0,8).map((p,i)=><div className="promise-item" key={i}><div className="promise-date"><Clock3 size={13}/>{fmtDate(p.due)}</div><p>{p.what}</p><small>Owner: {p.owner}</small><div className="source-tags">{p.sources?.map(id=><SourceTag id={id} key={id} onOpen={openSource}/>)}</div></div>):<p className="muted-description">No confirmed outstanding commitments.</p>}</section></div><div className="meeting-detail-foot"><div className="meeting-question"><Sparkles size={18}/><div><small>QUESTION TO ASK</small><p>{b.question_to_ask?.text||'No question required.'}</p></div></div><div className="open-these"><small>OPEN BEFORE MEETING</small><div className="source-tags">{b.open_these?.map((r,i)=><SourceTag id={r.record} key={i} onOpen={openSource}/>)}</div></div></div></>}</Card>)}</div>:<Card><Empty icon={CalendarDays} title="No meetings scheduled for this day" sub="Switch to Day 3 with Meera Iyer or Day 4 with Rohan Kapoor to see generated briefs."/></Card>}
 </div>
}

function EvidenceExplorer({ctx,openSource}){
 const [q,setQ]=useState(''),[type,setType]=useState('all'),[client,setClient]=useState('')
 const {data,loading,error}=useRemote(withQuery('/records',{...ctx,q,type,client,limit:60}),[ctx.person,ctx.day,q,type,client])
 return <div className="view-enter"><SectionTitle eyebrow="EVIDENCE EXPLORER" title="Nothing claimed. Everything traceable." subtitle="Browse the exact authorized records behind TraceMind's responses." action={<Tag tone="mint"><ShieldCheck size={12}/> Access filtered</Tag>}/>
  <Card className="explorer-card"><div className="explorer-toolbar"><div className="search-box"><Search size={18}/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search evidence, task titles, source IDs…"/><kbd>⌘ K</kbd></div><select className="filter-select" value={type} onChange={e=>setType(e.target.value)}><option value="all">All types</option>{['chat','mail','task','doc','note','sheet','event','notification'].map(s=><option key={s} value={s}>{s}</option>)}</select><select className="filter-select" value={client} onChange={e=>setClient(e.target.value)}><option value="">All clients</option><option value="northbeam">Northbeam</option><option value="cobaltline">Cobaltline</option><option value="alderpoint">Alderpoint</option></select></div><div className="results-subhead"><span>{data?`${data.total.toLocaleString()} authorized records`:'Searching records…'}</span><span>Showing latest {data?.items?.length||0}</span></div>{loading?<Spinner/>:error?<Empty title="Unable to search" sub={error}/>:!data?.items.length?<Empty title="No matching records" sub="Change the search or filters."/>:<div className="record-list">{data.items.map(r=><button className="record-row" key={r.id} onClick={()=>openSource(r.id)}><span className={'record-icon type-'+(colorByType[r.type]||'muted')}><FileText size={17}/></span><div className="record-content"><div className="record-head"><strong>{r.title}</strong><Tag tone={colorByType[r.type]||'muted'}>{r.type}</Tag></div><p>{r.body||'No body text'}</p><div className="record-meta"><span>{r.author}</span><span>·</span><span>{r.client||'Internal'}</span><span>·</span><span>{fmtTime(r.at)}</span>{r.visibility!=='team'&&<span className="privacy-indicator"><LockKeyhole size={11}/>{r.visibility}</span>}</div></div><div className="record-end"><code>{r.id}</code><ArrowUpRight size={17}/></div></button>)}</div>}</Card>
  <div className="bottom-note"><ShieldCheck size={15}/> Records outside the current persona, day, or permission scope do not appear in this view.</div></div>
}

function MemoryStudio({ctx,openSource,onReset}){
 const {data,loading,error}=useRemote(withQuery('/memory',ctx),[ctx.person,ctx.day])
 const [topic,setTopic]=useState(''),[running,setRunning]=useState(false),[notice,setNotice]=useState('')
 const resetDemo=async()=>{
  if(!window.confirm('Reset ALL Studio demo memory and reload public days 1–5? This does not touch the official CLI database.')) return
  setRunning(true)
  try { await request('/demo-reset',{method:'POST'});setNotice('Demo state reset to the original public records.');onReset() }
  catch(e){setNotice(e.message)}finally{setRunning(false)}
 }
 const forget=async()=>{
  if(!topic.trim()||!window.confirm(`Forget “${topic}” for this demo persona? This changes the Studio demo memory.`))return
  setRunning(true)
  try{await request('/forget',{method:'POST',body:JSON.stringify({person:ctx.person,what:topic})});setNotice('Forget request applied. Refresh the memory view to see updated state.');setTopic('');onReset()}
  catch(e){setNotice(e.message)}finally{setRunning(false)}
 }
 if(loading)return <Spinner/>
 if(error)return <Empty title="Memory unavailable" sub={error}/>
 return <div className="view-enter"><SectionTitle eyebrow="PERSISTENT MEMORY" title="A memory with boundaries." subtitle="Explore corrections, preferences, expired facts, and user-initiated forgetting." action={<Tag tone="purple"><BrainCircuit size={12}/> Per-person scope</Tag>}/>
 <div className="memory-grid"><Card className="memory-main"><div className="panel-head"><div><div className="eyebrow">YOUR MEMORY TIMELINE</div><h3>Learned across days</h3></div><span className="small-counter">{data.feedback.length} feedback items</span></div>{data.feedback.length?<div className="timeline">{data.feedback.map((f,i)=><div className="timeline-item" key={i}><div className="timeline-marker"><GitBranch size={15}/></div><div className="timeline-copy"><div className="timeline-meta"><span>DAY {f.day} FEEDBACK</span><Tag tone={f.type==='preference'?'purple':'blue'}>{f.type||f.verdict||'feedback'}</Tag></div><p>{f.words||f.verdict||'Feedback recorded'}</p><small>Scoped to this person's memory</small></div></div>)}</div>:<Empty icon={BrainCircuit} title="No feedback memory yet" sub="Choose a later day or another persona to see learned preferences."/>}
 <div className="memory-subtitle"><span>DEADLINE FACT LEDGER</span><span>{data.facts.length} visible entries</span></div>{data.facts.length?<div className="fact-list">{data.facts.map((f,i)=><div className="fact-row" key={i}><span><Clock3 size={15}/>{f.subject||'Deadline fact'} — {f.value||f.due||'updated'}</span><SourceTag id={f.source_id} onOpen={openSource}/></div>)}</div>:<p className="muted-description">No extracted deadline facts visible for this persona and selected day. This section is connected to the persistent ledger.</p>}</Card>
 <div className="memory-side"><Card><div className="panel-head"><div><div className="eyebrow">PRIVACY BY DESIGN</div><h3>Forget a topic</h3></div><LockKeyhole size={18} className="muted-icon"/></div><p className="small-intro">Suppress matching memory for this demo identity. Other people's workspace evidence is not deleted.</p><label className="field-label" htmlFor="forget-topic">Topic to forget</label><input id="forget-topic" className="full-input" placeholder="e.g. Dubai trip" value={topic} onChange={e=>setTopic(e.target.value)}/><button className="button button-danger" disabled={running||!topic.trim()} onClick={forget}><Trash2 size={16}/> Apply forget request</button>{notice&&<div className="inline-notice">{notice}</div>}<p className="field-help">Demo-only change. The official CLI database stays separate.</p><button className="reset-demo" disabled={running} onClick={resetDemo}><RotateCcw size={14}/> Reset demo to public records</button></Card><Card><div className="panel-head"><div><div className="eyebrow">SUPPRESSION LOG</div><h3>Forgotten topics</h3></div><ShieldCheck size={17} className="muted-icon"/></div>{data.forget_topics.length?data.forget_topics.map(x=><div className="forgotten-entry" key={x}><LockKeyhole size={15}/>{x}</div>):<div className="muted-description">No forget requests have been made for this persona.</div>}</Card></div></div></div>
}

function EvaluationStudio(){
 const {data,loading,error}=useRemote('/evaluation',[])
 const neuralReport=useRemote('/neural-benchmark',[])
 if(loading)return <Spinner/>
 if(error)return <Empty title="Evaluation unavailable" sub={error}/>
 const s=data?.score
 return <div className="view-enter"><SectionTitle eyebrow="ENGINEERING EVIDENCE" title="Measured. Not imagined." subtitle="Public results are taken from the official scorer output—not from a fabricated dashboard." action={<Tag tone="amber"><Activity size={12}/> Public data only</Tag>}/>
 {data.available?<><Card className="score-showcase"><div><div className="eyebrow">OFFICIAL PUBLIC REPLAY</div><div className="score-main"><strong>{s.total}<span>/{s.max_scored}</span></strong><Tag tone="mint" dot>Public days verified</Tag></div><p>All available machine-scored points on public days 1–5. Hidden-day performance remains unknown.</p><small>Source: {data.source}</small></div><div className="score-rings"><div className="big-score-ring"><ShieldCheck size={40}/><span>PASS</span></div></div></Card><div className="eval-grid">{Object.entries(s.areas||{}).filter(([,a])=>a.points!=null).map(([key,a])=><Card key={key} className="eval-tile"><div className="eval-title"><span>{key.replaceAll('_',' ')}</span><strong>{a.points}/{a.weight}</strong></div><div className="eval-progress"><span style={{width:((a.points/a.weight)*100)+'%'}}/></div><small>{a.checks} checks</small></Card>)}</div><Card className="eval-note"><CircleAlert size={20}/><p><strong>Scope matters.</strong> These scores measure only the official public cases. The hidden 6–15 days, manual design review, and independent model-assisted answer quality are not represented.</p></Card></>:<Card><Empty icon={Activity} title="Run the official public evaluator" sub={data.message}/><div className="cmd-block"><code>python tools/run_days.py --cmd "python tracemind.py" --days 1-5 --out runs/studio-score</code><code>python tools/score.py --run runs/studio-score --days 1-5</code></div></Card>}
 {neuralReport.data?.available&&neuralReport.data?.neural&&<Card className="neural-comparison"><div className="panel-head"><div><div className="eyebrow">LOCAL MODEL BENCHMARK</div><h3>Semantic retrieval, measured.</h3></div><Tag tone="purple"><BrainCircuit size={12}/> MiniLM</Tag></div><p className="muted-description">{neuralReport.data.dataset} · {neuralReport.data.source}</p><div className="compare-row"><span>Lexical Recall@3</span><strong>{Math.round((neuralReport.data.lexical?.recall_at_3||0)*100)}%</strong><div className="compare-track"><div style={{width:((neuralReport.data.lexical?.recall_at_3||0)*100)+'%'}}/></div></div><div className="compare-row neural-row"><span>Hybrid Neural Recall@3</span><strong>{Math.round((neuralReport.data.neural?.recall_at_3||0)*100)}%</strong><div className="compare-track"><div style={{width:((neuralReport.data.neural?.recall_at_3||0)*100)+'%'}}/></div></div><div className="benchmark-footer"><span>MRR@3: {neuralReport.data.lexical?.mrr_at_3} → {neuralReport.data.neural?.mrr_at_3}</span><span>Neural latency: {neuralReport.data.neural?.avg_ms_per_query} ms/query</span></div><div className="panel-footnote"><CircleAlert size={15}/> Retrieval accuracy only; not hidden-day or final answer accuracy.</div></Card>}
 <div className="eval-bottom"><div><div className="eyebrow">EXPERIMENTAL RETRIEVAL</div><h3>Local MiniLM, not a magic answer.</h3><p>Use Neural mode in Ask TraceMind to inspect candidate sources. Retrieval ranks evidence; it does not certify every generated claim. Model weights remain on your machine after installation.</p></div><BrainCircuit size={44}/></div></div>
}

function SourceDrawer({source,close,person,day}){
 const {data,loading,error}=useRemote(withQuery(`/sources/${encodeURIComponent(source)}`,{person,day}),[source,person,day])
 useEffect(()=>{const key=e=>{if(e.key==='Escape')close()};window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key)},[close])
 return <div className="drawer-overlay" onClick={close}><aside className="source-drawer" onClick={e=>e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Source record"><div className="drawer-top"><div><div className="eyebrow">PROVENANCE EXPLORER</div><h3>Source inspection</h3></div><button className="icon-button" onClick={close} aria-label="Close"><X size={19}/></button></div>{loading?<Spinner/>:error?<Empty title="Source unavailable" sub={error}/>:data&&<div className="drawer-scroll"><div className="source-identity"><Tag tone={colorByType[data.record.type]||'muted'} dot>{data.record.type}</Tag><span>{data.record.visibility}</span></div><h2>{data.record.title||data.record.subject||'Workplace record'}</h2><p className="drawer-id"><Fingerprint size={14}/>{data.record.id}</p><div className="source-fields"><div><span>AUTHORED BY</span><strong>{data.author_name}</strong></div><div><span>CLIENT</span><strong>{data.record.client||'Internal'}</strong></div><div><span>RECORDED AT</span><strong>{fmtTime(data.record.at)}</strong></div><div><span>VISIBILITY</span><strong>{data.record.visibility}</strong></div></div><div className="source-body-head">ORIGINAL EVIDENCE <ShieldCheck size={15}/></div><div className="source-body">{data.record.body||'No free-text body.'}</div><div className="drawer-footer"><ShieldCheck size={16}/><p>This record passed the current persona, time, and forget filters before being displayed.</p></div></div>}</aside></div>
}

export default function App(){
 const [view,setView]=useState('overview')
 const [person,setPerson]=useState('p02')
 const [day,setDay]=useState(3)
 const [source,setSource]=useState(null)
 const [initialQuestion,setInitialQuestion]=useState('')
 const [refresh,setRefresh]=useState(0)
 const {data:bootstrap,loading,error}=useRemote('/bootstrap',[])
 const evaluation=useRemote('/evaluation',[])
 const selected=bootstrap?.persons?.find(x=>x.id===person)
 const ctx=useMemo(()=>({person,day}),[person,day,refresh])
 const handleView=(next)=>{setView(next);window.scrollTo({top:0,behavior:'smooth'})}
 const goAsk=(q='')=>{setInitialQuestion(q);handleView('ask')}
 const openSource=useCallback((id)=>setSource(id),[])
 useEffect(()=>{function key(e){if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();handleView('evidence')}}window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key)},[])
 if(loading)return <div className="boot-screen"><Logo/><div className="wait-ring"/><strong>Preparing your intelligence workspace…</strong></div>
 if(error)return <div className="boot-screen"><Logo/><CircleAlert size={30}/><h2>Cannot connect to TraceMind</h2><p>{error}. Start the Python API with <code>uvicorn studio_api:app --host 127.0.0.1 --port 8765</code>.</p></div>
 return <div className="app-shell"><Sidebar view={view} setView={handleView} score={evaluation.data}/><div className="app-body"><Topbar view={view} person={person} setPerson={setPerson} day={day} setDay={setDay} bootstrap={bootstrap}/><main className="main-content">
 {view==='overview'&&<Overview ctx={ctx} goAsk={goAsk} openSource={openSource} goView={handleView}/>}
 {view==='ask'&&<AskStudio ctx={ctx} initialQuestion={initialQuestion} setInitialQuestion={setInitialQuestion} openSource={openSource} modelReady={Boolean(bootstrap.model_configured&&bootstrap.remote_allowed)}/>}
 {view==='briefs'&&<MeetingStudio ctx={ctx} openSource={openSource}/>}
 {view==='evidence'&&<EvidenceExplorer ctx={ctx} openSource={openSource}/>}
 {view==='memory'&&<MemoryStudio key={refresh+person+day} ctx={ctx} openSource={openSource} onReset={()=>setRefresh(x=>x+1)}/>}
 {view==='evaluation'&&<EvaluationStudio/>}
 </main><footer className="app-footer"><span><Logo/> TRACEMIND INTELLIGENCE STUDIO</span><span>Grounded in evidence. Designed for clarity.</span><span>BUILDSPRINT R3 · LOCAL DEMO</span></footer></div>
 {source&&<SourceDrawer key={source+person+day} source={source} close={()=>setSource(null)} person={person} day={day}/>}</div>
}
