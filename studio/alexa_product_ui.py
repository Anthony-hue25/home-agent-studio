"""Self-contained Alexa+ MCP App for the complete Adaptive Stay product."""
from hashlib import sha256
import json

UI_MIME_TYPE = "text/html;profile=mcp-app"
SHELL_VERSION = "gate-i-product-5"

_TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>Adaptive Stay</title>
<style>
:root{--bg:var(--color-background-primary,#f4f7f8);--panel:var(--color-background-secondary,#fff);--panel2:var(--color-background-tertiary,#edf3f5);--text:var(--color-text-primary,#172027);--muted:var(--color-text-secondary,#61707a);--line:var(--color-border-secondary,#d9e3e8);--accent:#087ea4;--accent2:#6b58d8;--ok:#157a57;--warn:#9a6200;--danger:#a3352c;--shadow:0 18px 48px rgba(19,35,48,.10);--r:30px;--rs:20px;--sans:var(--font-sans,system-ui,-apple-system,"Segoe UI",sans-serif)}
@media(prefers-color-scheme:dark){:root{--bg:#101619;--panel:#172024;--panel2:#202a2f;--text:#f2f6f8;--muted:#b9c4cb;--line:#344047;--shadow:0 18px 48px rgba(0,0,0,.3);--accent:#5bc8ed;--accent2:#9ba5ff;--ok:#58d1a0;--warn:#f0bd63;--danger:#f0938a}}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:var(--bg);color:var(--text);font-family:var(--sans)}body{padding:env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left)}button{font:inherit;color:inherit}.shell{width:min(1120px,100%);margin:0 auto;padding:clamp(20px,3.2vw,46px);padding-bottom:calc(clamp(20px,3.2vw,46px) + 90px);min-height:100vh}.top{display:flex;justify-content:space-between;align-items:center;gap:18px;margin-bottom:clamp(24px,4vw,48px)}.brand{display:flex;align-items:center;gap:13px;font-weight:760;font-size:clamp(19px,2vw,27px);letter-spacing:-.02em}.orb{width:38px;height:38px;border-radius:50%;background:radial-gradient(circle at 35% 30%,#aaf0ff 0 14%,#4bc5e9 30%,#6b58d8 72%,#102f4d 100%);box-shadow:0 0 0 6px rgba(75,197,233,.12)}.time{color:var(--muted);font-size:clamp(16px,1.6vw,21px)}.hero{padding:clamp(28px,4vw,52px);border-radius:var(--r);background:linear-gradient(135deg,var(--panel),var(--panel2));box-shadow:var(--shadow);margin-bottom:26px}.eyebrow{font-size:14px;font-weight:800;letter-spacing:.11em;text-transform:uppercase;color:var(--accent);margin-bottom:14px}h1{font-size:clamp(38px,5.5vw,72px);line-height:1.02;letter-spacing:-.045em;margin:0 0 15px;max-width:900px}h2{font-size:clamp(27px,3.4vw,44px);line-height:1.08;letter-spacing:-.035em;margin:0 0 14px}h3{font-size:clamp(20px,2.2vw,29px);margin:0 0 10px}h4{font-size:clamp(16px,1.6vw,19px);margin:0 0 8px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;font-weight:800}.support{font-size:clamp(18px,2vw,26px);line-height:1.4;color:var(--muted);max-width:820px}.statusline{display:flex;flex-wrap:wrap;gap:10px;margin-top:22px}.pill{padding:10px 15px;border-radius:999px;background:var(--panel2);font-size:15px;font-weight:700}.pill.warn{background:color-mix(in srgb,var(--warn) 18%,var(--panel2))}.pill.ok{background:color-mix(in srgb,var(--ok) 18%,var(--panel2))}.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:18px}.card{grid-column:span 12;background:var(--panel);border:1px solid var(--line);border-radius:var(--rs);padding:clamp(22px,3vw,34px)}.guestrow,.choices,.actions{display:flex;flex-wrap:wrap;gap:12px}.guest,.choice,.primary,.secondary,.ghost,.labbtn{min-height:54px;border-radius:18px;border:1px solid var(--line);background:var(--panel);padding:13px 18px;cursor:pointer;font-weight:720;text-align:left}.guest{min-width:138px}.guest small{display:block;color:var(--muted);font-size:13px;margin-top:4px;font-weight:600}.guest.selected,.choice.selected{border-color:var(--accent);box-shadow:0 0 0 3px rgba(8,126,164,.18)}.choice{min-width:180px;flex:1 1 180px;text-align:center}.primary{background:var(--accent);color:white;border-color:transparent}.secondary{background:var(--panel2)}.ghost{background:transparent;border-style:dashed}button:disabled{opacity:.5;cursor:not-allowed}button:focus-visible{outline:4px solid rgba(8,126,164,.35);outline-offset:2px}.section{margin-top:26px}.muted{color:var(--muted)}.small{font-size:14px}.callout{border-left:6px solid var(--accent);padding-left:18px}.conflict{border-left-color:var(--warn)}.failed{border-left-color:var(--danger)}.ready{border-left-color:var(--ok)}.row{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;padding:12px 0;border-bottom:1px solid var(--line)}.row:last-child{border-bottom:0}.value{font-weight:760;text-align:right}.group{border:1px solid var(--line);border-radius:16px;padding:16px 18px;margin-top:14px}.group summary{cursor:pointer;font-weight:760;list-style:none;display:flex;justify-content:space-between;gap:12px;align-items:center}.group summary::-webkit-details-marker{display:none}.group summary .chev{transition:transform .15s ease;color:var(--muted)}.group[open] summary .chev{transform:rotate(90deg)}.evidence{margin-top:12px;padding-top:12px;border-top:1px dashed var(--line);font-size:14px;color:var(--muted);font-family:ui-monospace,Menlo,Consolas,monospace}details:not([open])>.evidence{display:none}.progress{height:10px;border-radius:999px;background:var(--panel2);overflow:hidden;margin-top:18px}.progress>i{display:block;height:100%;width:42%;background:linear-gradient(90deg,var(--accent),var(--accent2));animation:move 1.4s ease-in-out infinite alternate}@keyframes move{to{transform:translateX(130%)}}@media(prefers-reduced-motion:reduce){.progress>i{animation:none;width:70%}}.phaserow{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}.phase{padding:7px 12px;border-radius:999px;background:var(--panel2);font-size:13px;font-weight:700;color:var(--muted)}.phase.done{background:color-mix(in srgb,var(--ok) 16%,var(--panel2));color:var(--text)}.footer{padding:28px 4px;color:var(--muted);font-size:14px}.lab{position:fixed;right:18px;bottom:18px;z-index:20}.labtoggle{min-height:52px;border-radius:999px;padding:12px 20px;background:var(--text);color:var(--bg);border:none;font-weight:760;box-shadow:var(--shadow);cursor:pointer}.labpanel{position:fixed;right:18px;bottom:82px;width:min(380px,calc(100vw - 36px));max-height:min(72vh,640px);overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:22px;box-shadow:var(--shadow);padding:20px;z-index:20}.labpanel h3{font-size:18px}.labscenario{display:block;width:100%;margin-top:8px}.labscenario small{display:block;color:var(--muted);font-weight:600;margin-top:3px;white-space:normal}.field{display:flex;flex-direction:column;gap:6px;margin-top:10px}.field input,.field select{min-height:48px;border-radius:12px;border:1px solid var(--line);background:var(--bg);color:var(--text);padding:8px 12px;font:inherit}.labguestrow{border:1px solid var(--line);border-radius:14px;padding:12px 14px;margin-top:12px}.labguestrow .actions{margin-top:10px}.labguestrow .secondary{min-height:48px}body.compact .shell{padding:18px;padding-bottom:108px}body.compact h1{font-size:38px}body.compact .hero{padding:24px}body.compact .lab,.labpanel{right:12px}body.voice-only .visual-only{display:none!important}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}.propertymap{display:flex;flex-direction:column;gap:14px;margin-top:6px}.zone{border:1px solid var(--line);border-radius:18px;padding:16px 18px;background:var(--panel2);transition:border-color .15s ease,background-color .15s ease}.zone[data-status="tension"]{border-color:var(--warn);background:color-mix(in srgb,var(--warn) 12%,var(--panel2))}.zone[data-status="resolved"]{border-color:var(--ok);background:color-mix(in srgb,var(--ok) 10%,var(--panel2))}.zonehead{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px;margin-bottom:12px}.zonename{font-weight:760;font-size:15px}.zonestatus{display:inline-flex;align-items:center;gap:7px;font-size:13px;font-weight:800;color:var(--muted);white-space:nowrap}.zone[data-status="tension"] .zonestatus{color:var(--warn)}.zone[data-status="resolved"] .zonestatus{color:var(--ok)}.zonestatus svg{width:16px;height:16px;flex:none}.zonestatus.pulse svg{animation:mappulse 1.2s ease-in-out infinite}@keyframes mappulse{0%,100%{opacity:1}50%{opacity:.3}}@media(prefers-reduced-motion:reduce){.zonestatus.pulse svg{animation:none}}.zonerooms{display:flex;flex-wrap:wrap;gap:12px}.roombox{flex:1 1 160px;min-width:148px;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:12px 14px}.roomlabel{font-size:12px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);margin-bottom:8px}.roomguests{display:flex;flex-direction:column;gap:6px}.guestchip{min-height:48px;display:flex;flex-direction:column;justify-content:center;align-items:flex-start;gap:2px;border-radius:12px;border:1px solid var(--line);background:var(--panel2);padding:7px 12px;cursor:pointer;font-weight:720;text-align:left;width:100%}.guestchip.selected{border-color:var(--accent);box-shadow:0 0 0 3px rgba(8,126,164,.18)}.guestchip .chipexp{font-size:12px;color:var(--muted);font-weight:600}.roomempty{min-height:48px;display:flex;align-items:center;color:var(--muted);font-size:13px;font-style:italic;padding:7px 12px}.sharedrow{display:flex;flex-wrap:wrap;align-items:center;gap:10px;border:1px solid var(--line);border-radius:14px;padding:12px 16px;background:var(--panel2);font-size:14px;font-weight:760}.sharedrow[data-status="tension"]{border-color:var(--warn);background:color-mix(in srgb,var(--warn) 12%,var(--panel2));color:var(--warn)}.sharedrow[data-status="resolved"]{border-color:var(--ok);background:color-mix(in srgb,var(--ok) 10%,var(--panel2));color:var(--ok)}.sharedrow svg{width:16px;height:16px;flex:none}.zonedetail{margin-top:10px;font-size:14px}.zonedetail summary{cursor:pointer;font-weight:700;color:var(--muted);list-style:none}.zonedetail summary::-webkit-details-marker{display:none}.labpreview{margin-top:10px}
</style>
</head>
<body>
<main class="shell" data-shell-version="__SHELL_VERSION__">
 <div class="top"><div class="brand"><span class="orb" aria-hidden="true"></span>Adaptive Stay</div><div class="time" id="clock"></div></div>
 <section class="hero" id="hero" aria-live="polite"></section>
 <section id="content" class="grid" aria-live="polite"></section>
 <div class="footer">Alexa+ MCP-native experience · AI proposes · deterministic Dream verifies · people authorize.</div>
</main>
<div id="lab" class="visual-only"></div>
<div aria-live="assertive" class="sr-only" id="announce"></div>
<script>
(()=>{
const S={stay:null,guest:null,options:null,proposal:null,job:null,blueprint:null,hostContext:null,labOpen:false,labView:'menu',scenarios:null,activation:null,evidenceOpen:false};
let seq=0,pending=new Map(),standalone=!!window.__ADAPTIVE_STANDALONE__,mcpTransport=!!window.__ADAPTIVE_MCP__,busy=false,mcpSessionId=null,mcpInitPromise=null;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const label=s=>String(s||'').split('.').pop().replaceAll('_',' ').replaceAll('-',' ').replace(/\b\w/g,c=>c.toUpperCase());
const CATEGORY_NAMES={'pref.thermal.feel':'Temperature','pref.airflow.level':'Airflow','pref.light.blocking':'Blinds & privacy','pref.lighting.ambience':'Lighting mood'};
const categoryName=ref=>CATEGORY_NAMES[ref]||label(ref);
const post=x=>window.parent.postMessage(x,'*');
const announce=msg=>{const a=document.getElementById('announce');if(a)a.textContent=msg};
function rpc(method,params={}){if(standalone)return localRpc(method,params);return new Promise((resolve,reject)=>{const id='as-'+(++seq);pending.set(id,{resolve,reject});post({jsonrpc:'2.0',id,method,params})})}
async function localRpc(method,params){if(method==='tools/call'){if(mcpTransport)return {structuredContent:await mcpToolsCall(params.name,params.arguments||{})};const r=await fetch('/api/tool',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:params.name,arguments:params.arguments||{}})});return {structuredContent:await r.json()}}if(method==='ui/request-display-mode')return {mode:params.mode};return {}}
// ---- Real Streamable HTTP MCP transport (public Gate J1 deployment only) ----
// Speaks the exact wire protocol Alexa+ itself uses: JSON-RPC 2.0 over
// POST /mcp, capturing Mcp-Session-Id and parsing both application/json and
// SSE-framed (text/event-stream) responses. Activated only when the hosting
// page sets window.__ADAPTIVE_MCP__=true; otherwise this code never runs.
async function mcpFetch(body){const headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream'};if(mcpSessionId)headers['Mcp-Session-Id']=mcpSessionId;const r=await fetch('/mcp',{method:'POST',headers,body:JSON.stringify(body),credentials:'same-origin'});const sid=r.headers.get('Mcp-Session-Id');if(sid)mcpSessionId=sid;return r}
async function mcpParse(r){const ct=r.headers.get('Content-Type')||'';const text=await r.text();if(!text)return null;if(ct.includes('text/event-stream')){const lines=text.split('\n').filter(l=>l.startsWith('data:'));if(!lines.length)throw new Error('no data: line in SSE body');return JSON.parse(lines[lines.length-1].slice(5).trim())}return JSON.parse(text)}
function mcpEnsureInit(){if(!mcpInitPromise)mcpInitPromise=(async()=>{const r=await mcpFetch({jsonrpc:'2.0',id:'mcp-init',method:'initialize',params:{protocolVersion:'2025-06-18',capabilities:{},clientInfo:{name:'adaptive-stay-public-browser',version:'1'}}});await mcpParse(r);await mcpFetch({jsonrpc:'2.0',method:'notifications/initialized',params:{}})})();return mcpInitPromise}
async function mcpToolsCall(name,args){await mcpEnsureInit();const r=await mcpFetch({jsonrpc:'2.0',id:'as-'+(++seq),method:'tools/call',params:{name,arguments:args||{}}});const msg=await mcpParse(r);if(msg&&msg.error)throw new Error((msg.error&&msg.error.message)||('tool call failed: '+name));return (msg&&msg.result&&msg.result.structuredContent)||{}}
window.addEventListener('message',e=>{const m=e.data||{};if(m.id&&pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result);return}if(m.method==='ui/notifications/tool-result'&&m.params?.result?.structuredContent)consume(m.params.result.structuredContent);if(m.method==='ui/notifications/host-context-changed'){S.hostContext=m.params?.hostContext||m.params||{};adapt();render()}if(m.method==='ui/notifications/size-changed'){S.hostContext={...(S.hostContext||{}),containerDimensions:m.params};adapt()}});
async function init(){if(!standalone){try{await rpc('ui/initialize',{protocolVersion:'2025-11-25',capabilities:{availableDisplayModes:['inline','fullscreen']},clientInfo:{name:'adaptive-stay',version:'1'}});post({jsonrpc:'2.0',method:'ui/notifications/initialized',params:{}})}catch(_){}}adapt();await refresh();document.getElementById('clock').textContent=new Date().toLocaleTimeString([],{hour:'numeric',minute:'2-digit'})}
function adapt(){const h=S.hostContext||{},dc=(h.deviceClass||'').toLowerCase(),w=h.containerDimensions?.width||innerWidth;document.body.classList.toggle('compact',dc.includes('mobile')||w<700);document.body.classList.toggle('voice-only',dc.includes('voice'))}
async function call(name,args={}){const r=await rpc('tools/call',{name,arguments:args});const x=r.structuredContent||r;consume(x);return x}
// get_stay()'s own payload also carries a raw data.blueprint (the latest
// proposed one, for other callers) -- that is NOT the get_stay_blueprint()
// shape blueprintCard() expects (data.blueprint + data.is_current). Guarding
// on is_current too, not just the presence of .blueprint, keeps a get_stay()
// refresh from clobbering a correctly-loaded blueprint with the wrong shape.
//
// The get_stay() "stay" key is checked for PRESENCE, not truthiness: right
// after checkout, get_stay() legitimately returns {data:{...,stay:null}} with
// no shared_resources key at all (there is no stay to assess). Requiring
// shared_resources too, as this once did, meant that exact response never
// matched, S.stay kept its last (active-stay) value, and checkout appeared to
// silently do nothing until the page was reloaded -- a real stale-state bug,
// not just cosmetic, since the UI still offered an already-used checkout
// action. Checking `'stay' in x.data` matches both the with-a-stay and
// no-stay shapes and nothing else (no other tool response carries this key).
function consume(x){if(!x||!x.data)return;if('stay' in x.data)S.stay=x;if(x.data.choices)S.options=x;if(x.data.proposal_id)S.proposal=x;if(x.data.job_id){S.job=x;if(x.data.status==='READY'&&x.data.blueprint_id)loadBlueprint(x.data.blueprint_id)}if(x.data.blueprint&&x.data.is_current!==undefined)S.blueprint=x;render()}
async function refresh(){S.stay=await call('get_stay',{});if(S.guest)await loadOptions(S.guest)}
async function loadOptions(id){S.guest=id;S.options=await call('get_preference_options',{scope:'PERSON',subject_id:id});S.proposal=null;render()}
async function propose(pref,val){S.proposal=await call('propose_preference',{preference_ref:pref,value_ref:val,scope:'PERSON',subject_id:S.guest,catalog_hash:S.options.data.catalog_hash});render()}
async function localWrite(name,args){if(standalone&&!mcpTransport){const r=await fetch('/api/local-action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,arguments:args})});const x=await r.json();consume(x);return x}return call(name,args)}
async function change(){await localWrite('change_stay',{proposal_id:S.proposal.data.proposal_id});S.proposal=null;S.options=null;announce('Preference added to this stay. Dream it again before activation.');await refresh()}
async function dream(){if(busy)return;busy=true;S.activation=null;S.evidenceOpen=false;try{S.job=await call('dream_stay',{});render();await pollDream()}finally{busy=false}}
async function pollDream(){if(!S.job?.data?.job_id)return;for(let i=0;i<80;i++){await new Promise(r=>setTimeout(r,750));const x=await call('get_dream_status',{job_id:S.job.data.job_id});S.job=x;if(x.data.status==='READY'||x.data.status==='FAILED')break}await refresh();if(S.job?.data?.status==='READY')announce('A verified Stay Blueprint is ready.');if(S.job?.data?.status==='FAILED')announce('Dream could not verify a configuration for this stay.')}
async function loadBlueprint(id=''){S.blueprint=await call('get_stay_blueprint',{blueprint_id:id});render()}
// Truthful activation: exactly one real localWrite('activate_stay', ...) call.
// While it is pending we show one honest in-flight line -- never a client-
// timed "Applying... / Reading back..." sequence, since we have not actually
// observed those as separate server events over a single RPC. Only once the
// real response (success or thrown error) has come back do we reveal the
// Applied -> Read back -> Verified/Not Verified summary, built entirely from
// that response's own execution_result / error text.
async function activate(){
  if(busy)return;
  const id=S.blueprint?.data?.blueprint?.blueprint_id;
  if(!id)return;
  busy=true;
  S.activation={phase:'pending'};
  render();
  try{
    const x=await localWrite('activate_stay',{blueprint_id:id});
    if(x&&x.error){
      S.activation={phase:'done',ok:false,message:x.error};
      announce('Could not activate this stay: '+x.error);
    } else {
      S.activation={phase:'done',ok:true};
      announce('The stay is now active. The property state has been independently verified.');
    }
  } catch(e){
    S.activation={phase:'done',ok:false,message:(e&&e.message)||''};
    announce('Could not activate this stay: the property state could not be verified.');
  } finally {
    busy=false;
    await refresh();
    // Re-fetch this Blueprint through the real get_stay_blueprint tool so
    // its planner_provenance picks up the execution_result the server just
    // recorded against this blueprint_id (activate_stay mutates the same
    // provenance record get_stay_blueprint reads). Without this, the
    // "Why can I trust this?" evidence panel keeps showing the pre-
    // activation snapshot ("Property readback: Not yet activated") even
    // once Activation Verified/Not Verified is showing right above it.
    if(id)await loadBlueprint(id);
  }
}
function activationFailureStory(msg){
  const m=String(msg||'');
  if(m.includes('stale Stay Blueprint'))return 'Something changed since this configuration was verified. Dream the stay again before activating.';
  if(m.includes('unknown Stay Blueprint'))return 'This Blueprint is no longer recognized for this stay. Dream the stay again.';
  if(m.includes('Home State Gateway readback verification failed'))return 'The property did not confirm the change that was applied.';
  return m||'The property state could not be verified.';
}
// Only the case where the server message tells us the gateway actually ran
// (apply + independent readback) shows the Applied/Read back chain -- a
// rejection before that point (stale/unknown Blueprint) never claims those
// steps happened.
function activationStatusCard(){
  const a=S.activation;
  if(!a)return '';
  if(a.phase==='pending')return `<div class="card callout" role="status"><div class="eyebrow">Activation</div><h2>Activating verified stay&hellip;</h2><p class="support">Applying the verified Blueprint to the property, then independently reading its state back.</p></div>`;
  const count=S.blueprint?.data?.primitives?.length||0;
  if(a.ok){
    const rows=['Applied','Read back','Verified Active'].map(l=>`<span class="phase done">${esc(l)}</span>`).join('');
    return `<div class="card callout ready"><div class="eyebrow">Activation verified</div><h2>Verified Active.</h2><p class="support">${count?`${count} setting${count===1?' was':'s were'} applied to the property and independently read back — ${count===1?'it matched':'they matched'} exactly.`:'This stay needed no physical changes, so there was nothing to mismatch.'}</p><div class="phaserow">${rows}</div><p class="muted small">Physical device execution is simulated in this build.</p></div>`;
  }
  const gatewayRan=String(a.message||'').includes('Home State Gateway readback verification failed');
  const rows=gatewayRan?['Applied','Read back','Not Verified'].map((l,i)=>`<span class="phase ${i<2?'done':''}">${esc(l)}</span>`).join(''):'';
  return `<div class="card callout failed"><div class="eyebrow">Activation not verified</div><h2>Nothing has been activated.</h2><p class="support">${esc(activationFailureStory(a.message))}</p>${rows?`<div class="phaserow">${rows}</div>`:''}</div>`;
}
async function checkout(){if(busy)return;busy=true;try{const x=await localWrite('checkout_stay',{});if(x&&x.error){announce('Could not checkout: '+x.error);await refresh();return}resetLocal();announce('Checkout complete. The property is ready for the next stay.');await refresh()}finally{busy=false}}
async function loadNextDemoStay(){if(!standalone)return;const r=await fetch('/api/demo-next-stay',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});if(!r.ok)throw Error(await r.text());resetLocal();S.stay=await r.json();render()}
async function fullscreen(){try{await rpc('ui/request-display-mode',{mode:'fullscreen'})}catch(_){}}
function toggleEvidence(){S.evidenceOpen=!S.evidenceOpen;render()}
function resetLocal(){S.guest=null;S.options=null;S.proposal=null;S.job=null;S.blueprint=null;S.activation=null;S.evidenceOpen=false}
function assignments(){const m={};for(const a of S.stay?.data?.stay?.assignments||[])m[a.guest_id]=a.room_id;return m}
function guestById(id){return (S.stay?.data?.guests||[]).find(g=>g.guest_id===id)}
function guestName(id){return guestById(id)?.display_name||id}
function prefById(id){return (S.stay?.data?.stay?.preferences||[]).find(p=>p.preference_id===id)}
function roomForGuest(id){return assignments()[id]}
// One combined trigger card for "there's something to Dream" -- replaces the
// two near-duplicate CTA cards that used to exist (one for the no-conflict
// path, one for the conflict path). The property map above already carries
// the spatial conflict story; this card is purely the call to action.
function dreamCtaCard(){
  const d=S.stay?.data||{},prefs=d.stay?.preferences||[];
  if(!prefs.length||d.status==='ACTIVE'||S.job||S.blueprint)return '';
  const needsCoordination=(d.shared_resources||{}).status==='CONFLICT';
  return `<div class="card callout ${needsCoordination?'conflict':'ready'}"><div class="eyebrow">${needsCoordination?'Shared physical reality':'Ready to configure'}</div><h2>${needsCoordination?'This stay needs coordination':'Formulate the whole stay'}</h2><p class="support">${needsCoordination?"Each request makes sense on its own — the map above shows exactly where the property's shared systems can't grant every request independently.":"I have the saved preferences. When you're ready, I can build a complete stay configuration and Dream it against the actual property before anything is activated."}</p><div class="actions section"><button class="primary" id="dream">Formulate &amp; Dream stay</button></div><p class="muted small visual-only">I will test the combined configuration before anything is activated.</p><p class="muted small voicehint">You can also say: "Dream this stay."</p></div>`;
}
function dreamTesting(){const s=S.job?.data?.status;return s==='REQUESTED'||s==='RUNNING'}
// Whether a fetched Blueprint should be TREATED as current for display.
// Activating a Blueprint advances the stay to a new internal version (the
// BOOKED -> ACTIVE transition itself), which makes is_current's strict
// version-hash comparison read even the just-activated Blueprint as "stale"
// -- nothing about the guest configuration changed. The authoritative "did
// reality move on since activation" signal is active_blueprint_stale
// (profile/resource-hash based -- exactly what Scenario D's reality change
// flips), not raw is_current. This is purely a display heuristic: it never
// affects activation safety, since activate_stay() independently re-verifies
// is_current server-side regardless of what the UI shows.
function blueprintDisplayCurrent(b){
  if(!b)return false;
  const activeNow=S.stay?.data?.status==='ACTIVE'&&S.stay?.data?.active_blueprint_id===b.blueprint?.blueprint_id&&!S.stay?.data?.active_blueprint_stale;
  return activeNow||!!b.is_current;
}
// A conflict is only ever shown as "resolved" against a blueprint this
// display treats as current -- a genuinely stale blueprint from a prior
// configuration must never paint a live conflict as handled.
function conflictsStatus(conflicts){
  if(!conflicts.length)return 'calm';
  if(dreamTesting())return 'testing';
  const b=S.blueprint?.data;
  return (b&&blueprintDisplayCurrent(b)&&conflicts.every(c=>conflictResolvedByBlueprint(b,c)))?'resolved':'tension';
}
const STATUS_ICON={
  calm:'<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="3.2" fill="currentColor"/></svg>',
  testing:'<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 2 1 18h18z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M10 8v4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="10" cy="14.6" r=".9" fill="currentColor"/></svg>',
  tension:'<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 2 1 18h18z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M10 8v4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="10" cy="14.6" r=".9" fill="currentColor"/></svg>',
  resolved:'<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="8.2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M6.1 10.2l2.6 2.6 5.1-5.6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
};
const STATUS_LABEL={calm:'No conflict',testing:'Testing…',tension:'Needs coordination',resolved:'Coordinated'};
function statusBadge(status){return `<span class="zonestatus ${status==='testing'?'pulse':''}">${STATUS_ICON[status]}<span>${esc(STATUS_LABEL[status])}</span></span>`}
function guestChip(g){
  const prefs=S.stay?.data?.stay?.preferences||[];
  const pref=prefs.find(p=>p.subject_id===g.guest_id);
  const exp=pref?`${esc(categoryName(pref.preference_ref))}: ${esc(label(pref.value_ref))}`:'';
  return `<button class="guestchip ${S.guest===g.guest_id?'selected':''}" data-guest="${esc(g.guest_id)}" aria-pressed="${S.guest===g.guest_id}">${esc(g.display_name)}${exp?`<span class="chipexp">${exp}</span>`:''}</button>`;
}
// The spatial "whole property at a glance" view: rooms grouped by the zone
// they actually share, each guest shown inside their real room, and every
// shared system (climate zone, hot water) shown as a connector across the
// rooms/guests it touches, in tension while unresolved and calm once a
// current Blueprint covers it. This is the primary visual -- raw resource
// ids and conflict codes stay in the per-zone <details> disclosure, never
// inline, matching the same "human outcome, technical detail collapsed"
// rule the Blueprint card follows. No conflict is ever dropped to make the
// picture simpler: every entry in shared_resources.conflicts is grouped
// under its zone (or the shared hot-water row) and rendered.
function propertyMap(){
  const d=S.stay?.data;
  if(!d||!d.twin||!d.twin.room_zone_map)return '';
  const byRoom={};
  for(const g of (d.guests||[]))(byRoom[g.room_id]??=[]).push(g);
  const zoneRooms={};
  for(const [room,zone] of (d.twin.room_zone_map||[]))(zoneRooms[zone]??=[]).push(room);
  const zoneIds=(d.twin.zone_ids&&d.twin.zone_ids.length)?d.twin.zone_ids:Object.keys(zoneRooms);
  const allConflicts=(d.shared_resources?.conflicts)||[];
  const zonesHtml=zoneIds.filter(z=>zoneRooms[z]).map(zoneId=>{
    const rooms=zoneRooms[zoneId];
    const conflicts=rooms.length>1?allConflicts.filter(c=>c.resource_type==='CLIMATE_ZONE'&&c.resource_id===zoneId):[];
    const status=rooms.length>1?conflictsStatus(conflicts):null;
    const detail=conflicts.map(c=>`<details class="zonedetail"><summary>${esc(conflictStory(c))}</summary><div class="evidence">${esc(c.code)} &middot; requested: ${esc((c.requested_values||[]).map(label).join(', '))}</div></details>`).join('');
    const roomsHtml=rooms.map(roomId=>{
      const rg=byRoom[roomId]||[];
      const inner=rg.length?rg.map(g=>guestChip(g)+(S.guest===g.guest_id?inlinePreferenceChooser():'')).join(''):'<div class="roomempty">Unoccupied</div>';
      return `<div class="roombox"><div class="roomlabel">${esc(label(roomId))}</div><div class="roomguests">${inner}</div></div>`;
    }).join('');
    return `<div class="zone" data-status="${status||'none'}"><div class="zonehead"><span class="zonename">${esc(label(zoneId))}${rooms.length>1?' &middot; shared climate system':''}</span>${status?statusBadge(status):''}</div><div class="zonerooms">${roomsHtml}</div>${detail}</div>`;
  }).join('');
  const hwRequests=d.hot_water_requests||[];
  let sharedHtml='';
  if(hwRequests.length){
    const hwConflicts=allConflicts.filter(c=>c.resource_type==='HOT_WATER');
    const status=conflictsStatus(hwConflicts);
    const names=hwRequests.map(r=>guestName(r.subject_id));
    const detail=hwConflicts.map(c=>`<details class="zonedetail"><summary>${esc(conflictStory(c))}</summary><div class="evidence">${esc(c.code)} &middot; requested: ${esc((c.requested_values||[]).map(label).join(', '))}</div></details>`).join('');
    sharedHtml=`<div class="section"><div class="sharedrow" data-status="${status}">${STATUS_ICON[status]}<span>Shared hot water &mdash; ${esc(names.join(', '))} &middot; ${esc(STATUS_LABEL[status])}</span></div>${detail}</div>`;
  }
  return `<div class="card"><div class="eyebrow">The property</div><h2>${esc(d.property?.name||'This property')} at a glance</h2><div class="propertymap">${zonesHtml}</div>${sharedHtml}</div>`;
}
// Every entry in a.conflicts is rendered — grouped by the shared physical
// resource it belongs to, never truncated to the first one. Participant ids
// (preference ids, or hot-water request ids) are resolved back to the guest
// who asked for them using only data already present in this response.
function conflictParticipants(c){
  if(c.resource_type==='HOT_WATER'){
    const reqs=S.stay?.data?.hot_water_requests||[];
    return c.participants.map(pid=>{const r=reqs.find(x=>x.request_id===pid);return r?guestName(r.subject_id):pid});
  }
  return c.participants.map(pid=>{const p=prefById(pid);return p?guestName(p.subject_id):pid});
}
function conflictStory(c){
  const names=conflictParticipants(c);
  if(c.resource_type==='HOT_WATER')return `${names.join(' and ')} both want a shower around the same time, and the property's water heater can't fully deliver both at once.`;
  return `${names.join(' and ')} are in ${esc(c.resource_id)}, sharing one climate system, and asked for different temperatures at the same time.`;
}
const PHASES=['Understanding guests','Mapping shared systems','Exploring options','Verifying against the property'];
// Every reason shown here comes from a real, already-evaluated DreamEvaluation
// the server recorded (product_service.py's bounded rejected_candidates, at
// most REJECTED_CANDIDATE_LIMIT). Nothing is invented if the server has not
// evaluated it -- an empty list here just means nothing is shown.
function unresolvedStory(code){
  if(code.startsWith('THERMAL_UNRESOLVED:')){const p=prefById(code.split(':')[1]);return p?`${guestName(p.subject_id)}'s ${categoryName(p.preference_ref).toLowerCase()} request was still not met.`:'A temperature request was still not met.'}
  if(code==='HOT_WATER_CAPACITY_UNRESOLVED')return 'The shared hot-water demand could not be fully covered.';
  if(code.startsWith('CONFLICTING_ZONE_PRIMITIVES:'))return 'Two conflicting settings were proposed for the same shared zone.';
  if(code.startsWith('CAPABILITY_UNAVAILABLE:'))return 'A required device was not available to the property.';
  return 'A shared-resource constraint remained unresolved.';
}
function candidateLines(){
  const rejected=(S.job?.data?.planner_provenance?.rejected_candidates)||[];
  return rejected.map(c=>{
    const reason=unresolvedStory((c.unresolved||[])[0]||'');
    return `<div class="row"><div>Candidate rejected</div><div class="value">${esc(reason)}</div></div>`;
  }).join('');
}
function dreamCard(){
  const j=S.job?.data;
  if(!j)return '';
  const tested=candidateLines();
  if(j.status==='REQUESTED'||j.status==='RUNNING'){
    const activeIdx=j.status==='REQUESTED'?0:2;
    const rows=PHASES.map((p,i)=>`<span class="phase ${i<activeIdx?'done':''}">${esc(p)}</span>`).join('');
    return `<div class="card callout" role="status"><div class="eyebrow">Dream</div><h2>Living through this stay before the guests do…</h2><p class="support">Bounded candidate configurations are being generated and independently checked against the real property. Nothing is decided by the model itself — only deterministic Dream can pass a configuration.</p><div class="phaserow">${rows}</div><div class="progress"><i></i></div>${tested?`<div class="section">${tested}</div>`:''}</div>`;
  }
  if(j.status==='FAILED')return `<div class="card callout failed"><div class="eyebrow">Dream needs attention</div><h2>I couldn't find a verified configuration that makes every request work.</h2><p class="support">Nothing has been activated.</p>${tested?`<div class="section">${tested}</div>`:''}<div class="actions section"><button class="secondary" id="retryDream">Dream again</button></div><p class="muted small visual-only">You can also change one of the stay's preferences and Dream again.</p><p class="muted small voicehint">You can also say: "What's still unresolved?"</p></div>`;
  return '';
}
// Traceability: parse Dream's own evidence strings (already keyed by the same
// preference ids shown in the pre-Dream conflict cards) back into a per-guest
// resolution line, so the Blueprint visibly answers the conflicts above it.
function blueprintTrace(b){
  const evidence=b.blueprint?.evidence||[];
  const lines=[];
  for(const e of evidence){
    if(e.startsWith('THERMAL_SATISFIED:')){const p=prefById(e.split(':')[1]);if(p)lines.push(`${guestName(p.subject_id)}'s ${categoryName(p.preference_ref).toLowerCase()} request was honored.`)}
    else if(e==='HOT_WATER_CAPACITY_RESOLVED')lines.push('The shared hot-water demand was sequenced so every request is still met.');
  }
  return lines;
}
// shared_resources.conflicts is a standing description of the raw preference
// tension -- it does NOT clear once a Blueprint resolves it (the underlying
// requests are still, on their face, in tension; Dream found a bounded way to
// honor them anyway). So "unresolved" can never be read as conflicts.length:
// that would show "2 unresolved" forever on a fully verified, active
// Blueprint. Instead a conflict counts as resolved when THIS blueprint's own
// evidence covers it -- the same evidence blueprintTrace() already renders.
function conflictResolvedByBlueprint(b,c){
  const evidence=b.blueprint?.evidence||[];
  if(c.resource_type==='HOT_WATER')return evidence.includes('HOT_WATER_CAPACITY_RESOLVED');
  const satisfied=new Set(evidence.filter(e=>e.startsWith('THERMAL_SATISFIED:')).map(e=>e.split(':')[1]));
  return (c.participants||[]).every(pid=>satisfied.has(pid));
}
// The primary Blueprint card is the human outcome view: who is covered, in
// which room, with what they asked for, and how any shared system was
// treated -- in plain language. Raw primitive kinds (ZONE_THERMAL,
// ROOM_AIRFLOW), resource ids and value refs are real and truthful, but they
// are not the payoff a person came here for, so they live in a collapsed
// "Dream technical detail" disclosure below the outcome, never inline in it.
function blueprintCard(){
  const b=S.blueprint?.data;
  if(!b)return '';
  const guests=S.stay?.data?.guests||[],assign=assignments();
  const prefs=S.stay?.data?.stay?.preferences||[];
  const guestRows=guests.map(g=>{
    const pref=prefs.find(p=>p.subject_id===g.guest_id);
    const experience=pref?`${esc(categoryName(pref.preference_ref))}: ${esc(label(pref.value_ref))}`:'Following the property’s usual setup';
    return `<div class="row"><div>${esc(g.display_name)}<div class="muted small">${esc(assign[g.guest_id]||g.room_id||'')}</div></div><div class="value">${experience}</div></div>`;
  }).join('');
  const trace=blueprintTrace(b);
  const treatmentHtml=trace.length
    ? trace.map(t=>`<div class="row"><div>${esc(t)}</div></div>`).join('')
    : '<div class="row"><div class="muted">No shared-resource coordination was needed for this stay.</div></div>';
  // "Unresolved" counts live conflicts THIS blueprint's own evidence does not
  // cover -- never a fixed 0, and never the raw conflict count either (see
  // conflictResolvedByBlueprint above). A stale blueprint that no longer
  // matches the current stay will show this honestly, not as a leftover PASS.
  const liveConflicts=(S.stay?.data?.shared_resources?.conflicts)||[];
  const unresolvedConflicts=liveConflicts.filter(c=>!conflictResolvedByBlueprint(b,c));
  const rawRows=(b.primitives||[]).map(p=>`<div class="row"><div>${esc(label(p.kind))}<div class="muted small">${esc(p.target_id)}</div></div><div class="value">${esc(label(p.value_ref))}</div></div>`).join('');
  const rawDetail=`<details class="group section"><summary><span>Dream technical detail</span><span class="chev" aria-hidden="true">&rsaquo;</span></summary><div class="evidence">${rawRows||'No shared-resource primitives were required.'}</div></details>`;
  const pending=S.activation?.phase==='pending';
  // Once this exact Blueprint is already the active, current configuration,
  // offering "Activate stay" again is a duplicate control, not a real next
  // step -- activationStatusCard() (just after activation) or the Active
  // stay card (on a later visit) already say so.
  const activeNow=S.stay?.data?.status==='ACTIVE'&&S.stay?.data?.active_blueprint_id===b.blueprint?.blueprint_id&&!S.stay?.data?.active_blueprint_stale;
  // Activating a Blueprint advances the stay to a new internal version (the
  // BOOKED -> ACTIVE transition itself), which makes is_current's strict
  // version-hash comparison read this exact just-activated Blueprint as
  // "stale" even though nothing about the guest configuration changed. For
  // display, the authoritative "did reality move on since activation" signal
  // is active_blueprint_stale (profile/resource-hash based, exactly what
  // Scenario D's reality-change flips) -- not raw is_current. This never
  // affects activation safety: activate_stay() independently re-verifies
  // is_current server-side regardless of what the UI displays.
  const displayCurrent=activeNow||b.is_current;
  const staleActions=displayCurrent?'':'<button class="primary" id="dream">Dream again</button>';
  const activateBtn=activeNow?'':`<button class="primary" id="activate"${(b.is_current&&!pending)?'':' disabled'}>Activate stay</button>`;
  const voicehint=activeNow?'Why can I trust this?':(b.is_current?'Activate the verified stay.':'Dream this stay again.');
  return `<div class="card callout ready"><div class="eyebrow">Verified Stay Blueprint</div><h2>I found a way to make this stay work.</h2><p class="support">Every guest below is covered by a configuration that has been checked against the real property — verified, not guessed.</p><div class="section"><h4>This stay</h4>${guestRows}</div><div class="section"><h4>Shared-resource treatment</h4>${treatmentHtml}</div><div class="statusline"><span class="pill ok">Dream evidence: PASS</span><span class="pill ${unresolvedConflicts.length?'warn':'ok'}">${unresolvedConflicts.length} unresolved</span><span class="pill ${displayCurrent?'ok':'warn'}">${displayCurrent?'Current':'Stale — Dream again'}</span></div>${rawDetail}<div class="actions section">${staleActions}${activateBtn}<button class="secondary" id="full" aria-expanded="${S.evidenceOpen}">Why can I trust this?</button></div><p class="muted small voicehint">You can also say: "${esc(voicehint)}"</p>${evidencePanel(activeNow)}</div>`;
}
// Bounded, consumer-safe evidence only -- exactly the fields Gate J2's own
// anti-silent-fallback check asserts are safe to surface. Prompts, chain-of-
// thought, credentials, raw guest data and request ids never appear here.
function evidencePanel(activeNow){
  if(!S.evidenceOpen)return '';
  const prov=S.blueprint?.data?.planner_provenance||S.job?.data?.planner_provenance;
  const isCurrent=activeNow||S.blueprint?.data?.is_current;
  const rows=[
    ['MCP session', mcpSessionId?'Active':(standalone?'Local simulator':'Not yet established')],
    ['AI planner', prov?(prov.planner_backend==='strands'?'Strands':'Deterministic Fixture'):'Not yet run'],
    ['Model provider', prov?(prov.provider==='bedrock'?'Amazon Bedrock':'Deterministic'):'Not yet run'],
  ];
  if(prov&&prov.model)rows.push(['Model', prov.model]);
  rows.push(['Deterministic Dream verification', prov?.deterministic_verification?.status==='PASS'?'PASS':(prov?'Not yet verified':'Not yet run')]);
  rows.push(['Blueprint state', isCurrent===undefined?'Not yet verified':(isCurrent?'Current':'Stale')]);
  rows.push(['Property readback', prov&&prov.execution_result?(prov.execution_result==='VERIFIED_ACTIVE'?'Verified':'Not verified'):'Not yet activated']);
  return `<div class="section evidence"><h4>Runtime evidence</h4>${rows.map(([k,v])=>`<div class="row"><div>${esc(k)}</div><div class="value">${esc(v)}</div></div>`).join('')}<p class="muted small">Physical device execution is simulated in this build.</p></div>`;
}
// Personalization now lives inline, inside the selected guest's own room box
// in the property map (see propertyMap()'s roomsHtml) rather than as a
// separate stacked card below it -- guest requests appear in context with
// their room, not as a detached form.
function inlinePreferenceChooser(){
  const g=guestById(S.guest),choices=S.options?.data?.choices||[];
  if(S.proposal){
    const p=S.proposal.data;
    return `<div class="section"><p class="support small">I can make it ${esc(label(p.value_ref).toLowerCase())} for ${esc(g?.display_name||'this guest')}. Nothing has been added yet.</p><div class="actions"><button class="primary" id="change">Add to stay</button><button class="secondary" id="cancel">Cancel</button></div></div>`;
  }
  const groups={};
  for(const c of choices)(groups[c.preference_ref]??=[]).push(c);
  return `<div class="section">${Object.entries(groups).map(([k,v])=>`<h4>${esc(categoryName(k))}</h4><div class="choices">${v.map(c=>`<button class="choice" data-pref="${esc(c.preference_ref)}" data-val="${esc(c.value_ref)}">${esc(label(c.value_ref))}</button>`).join('')}</div>`).join('')}<p class="muted small voicehint">You can also say: "Personalize ${esc(g?.display_name||'their')}'s room."</p></div>`;
}
function render(){
  const root=document.getElementById('content'),hero=document.getElementById('hero'),d=S.stay?.data||{};
  if(!d.stay){
    hero.innerHTML=`<div class="eyebrow">Between stays</div><h1>Ready for the next stay.</h1><p class="support">Temporary guest state is clear. The physical property remains.</p><div class="statusline"><span class="pill ok">Guest state cleared</span><span class="pill">Property retained</span></div>`;
    root.innerHTML=standalone?`<div class="card callout ready"><div class="eyebrow">Demo lifecycle</div><h2>Load the next demo stay</h2><p class="support">In production, the next booking would arrive from the property or booking system. This local control simulates that external event without adding an Alexa-facing tool.</p><div class="actions section"><button class="primary" id="nextStay">Load next demo stay</button></div></div>`:`<div class="card"><div class="eyebrow">Waiting for booking</div><h2>The next stay will appear automatically.</h2><p class="support">Adaptive Stay is ready when the property or booking system provides the next stay.</p></div>`;
    bind();renderLab();return;
  }
  const p=d.property||{},guests=d.guests||[];
  hero.innerHTML=`<div class="eyebrow">${esc(d.status==='ACTIVE'?'Active stay':'Adaptive Stay')}</div><h1>${esc(S.stay.presentation?.headline||('Your stay at '+(p.name||'this property')+' is ready'))}</h1><p class="support">${esc(S.stay.presentation?.supporting_text||'')}</p><div class="statusline"><span class="pill">${guests.length} guests</span><span class="pill">${(d.twin?.room_ids||[]).length} bedrooms</span><span class="pill">${(d.twin?.zone_ids||[]).length} climate zones</span>${d.active_blueprint_stale?'<span class="pill warn">Blueprint needs re-Dream</span>':''}</div>`;
  // When this session just activated the stay itself, activationStatusCard()
  // already tells the richer, truthful Applied/Read back/Verified story --
  // this plain recap only appears otherwise (e.g. a fresh page load onto an
  // already-active stay, or Scenario F's server-side activation).
  const justActivated=S.activation?.phase==='done'&&S.activation.ok;
  const active=(d.status==='ACTIVE'&&!justActivated)?`<div class="card callout ready"><div class="eyebrow">Active stay</div><h2>The verified configuration is active.</h2><p class="support">${d.active_blueprint_stale?'Something changed since activation. Dream the stay again before replacing the active configuration — nothing has been silently changed.':'The active Stay Blueprint remains consistent with the current stay context.'}</p><div class="actions section">${d.active_blueprint_stale?'<button class="primary" id="dream">Dream the stay again</button>':''}<button class="secondary" id="checkout">Checkout stay</button></div>${d.active_blueprint_stale?'<p class="muted small voicehint">You can also say: "Dream this stay again."</p>':''}</div>`:'';
  root.innerHTML=propertyMap()+dreamCtaCard()+dreamCard()+blueprintCard()+activationStatusCard()+active;
  bind();renderLab();
}
function bind(){
  document.querySelectorAll('[data-guest]').forEach(b=>b.onclick=()=>loadOptions(b.dataset.guest));
  document.querySelectorAll('[data-pref]').forEach(b=>b.onclick=()=>propose(b.dataset.pref,b.dataset.val));
  const ids={change,dream,retryDream:dream,activate,checkout,full:toggleEvidence};
  for(const [id,fn] of Object.entries(ids)){const e=document.getElementById(id);if(e)e.onclick=fn}
  const c=document.getElementById('cancel');if(c)c.onclick=()=>{S.proposal=null;render()};
  const n=document.getElementById('nextStay');if(n)n.onclick=loadNextDemoStay;
  const ol2=document.getElementById('openLab2');if(ol2)ol2.onclick=()=>{S.labOpen=true;renderLab()};
}
// ---- Local Experience Lab (standalone simulator only; never an Alexa tool) ----
async function labScenarios(){if(S.scenarios)return S.scenarios;const r=await fetch('/api/lab/scenarios');S.scenarios=await r.json();return S.scenarios}
// lab_stale_blueprint_id, when a scenario sets it, is a local-simulator-only
// hint (never part of any MCP tool response) naming a specific Blueprint that
// just went stale as part of loading this scenario. Re-fetching it through
// the real get_stay_blueprint tool -- the same call the product UI always
// uses -- is what lets the property canvas honestly show it as stale rather
// than silently having no Blueprint at all. Any scenario could set this hint;
// it is not bespoke per-letter UI logic.
async function labLoad(key){const r=await fetch('/api/lab/load',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scenario:key})});if(!r.ok){announce('Could not load that scenario.');return}resetLocal();const body=await r.json();S.stay=body;S.labOpen=false;S.labView='menu';if(body.lab_stale_blueprint_id)await loadBlueprint(body.lab_stale_blueprint_id);else render()}
function labSyncGuestsFromDom(){if(!S.labCreateGuests)return;document.querySelectorAll('.labguestrow').forEach(row=>{const id=Number(row.dataset.row);const g=S.labCreateGuests.find(x=>x.id===id);if(!g)return;const n=row.querySelector('.labGuestName');const r=row.querySelector('.labGuestRoom');if(n)g.name=n.value;if(r)g.room=r.value})}
async function labCreate(ev){ev.preventDefault();labSyncGuestsFromDom();const guests=(S.labCreateGuests||[]).map(g=>({name:(g.name||'').trim(),room_id:g.room}));const r=await fetch('/api/lab/create-stay',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({guests})});if(!r.ok){announce('Could not create that stay: '+(await r.text()).slice(0,120));return}resetLocal();S.stay=await r.json();S.labOpen=false;S.labView='menu';S.labCreateGuests=null;render()}
// Live preview of the same room-map visual language used on the main
// screen, so the wizard shows guests dropping into their chosen rooms as
// they're assigned -- reads only the in-progress local draft, never writes
// anything or calls a tool.
function labPreviewHtml(rooms){
  const byRoom={};
  for(const g of (S.labCreateGuests||[]))if(g.room)(byRoom[g.room]??=[]).push((g.name||'').trim()||'Unnamed guest');
  return `<div class="propertymap"><div class="zone" data-status="none"><div class="zonerooms">${rooms.map(r=>`<div class="roombox"><div class="roomlabel">${esc(label(r))}</div><div class="roomguests">${(byRoom[r]||[]).map(n=>`<div class="guestchip" style="cursor:default">${esc(n)}</div>`).join('')||'<div class="roomempty">Unoccupied</div>'}</div></div>`).join('')}</div></div></div>`;
}
function labGuestRow(g,i,rooms,removable){
  const room=g.room||rooms[i%rooms.length]||'';
  return `<div class="labguestrow" data-row="${g.id}">
    <div class="field"><label for="labGuestName${g.id}">Guest ${i+1} name</label><input id="labGuestName${g.id}" class="labGuestName" required maxlength="60" placeholder="e.g. Alex" value="${esc(g.name||'')}"></div>
    <div class="field"><label for="labGuestRoom${g.id}">Guest ${i+1} room</label><select id="labGuestRoom${g.id}" class="labGuestRoom">${rooms.map(r=>`<option value="${esc(r)}" ${r===room?'selected':''}>${esc(label(r))}</option>`).join('')}</select></div>
    <div class="actions"><button type="button" class="secondary labGuestRemove" data-row="${g.id}" ${removable?'':'disabled'} aria-label="Remove guest ${i+1}">Remove guest</button></div>
  </div>`;
}
function renderLab(){
  const host=document.getElementById('lab');
  if(!standalone){host.innerHTML='';return}
  if(!S.labOpen){host.innerHTML='<div class="lab"><button class="labtoggle" id="labToggle" aria-expanded="false">Experience Lab</button></div>';document.getElementById('labToggle').onclick=()=>{S.labOpen=true;renderLab()};return}
  labScenarios().then(list=>{
    const rooms=(S.stay?.data?.twin?.room_ids)||list.property_rooms||[];
    let body='';
    if(S.labView==='create'){
      if(!S.labCreateGuests){S.labCreateGuests=[{id:0,name:'',room:rooms[0]||''}];S.labCreateSeq=0}
      const removable=S.labCreateGuests.length>1;
      body=`<h3>Create a stay from scratch</h3><p class="muted small">Local simulator only. Each guest gets their own existing room — no new rooms or resources can be invented here.</p>
      <form id="labCreateForm">
      <div id="labGuestRows">${S.labCreateGuests.map((g,i)=>labGuestRow(g,i,rooms,removable)).join('')}</div>
      <div class="actions section"><button class="secondary" type="button" id="labAddGuest" ${S.labCreateGuests.length>=6?'disabled':''}>Add another guest</button></div>
      <div class="section labpreview"><h4>Preview</h4><div id="labPreview">${labPreviewHtml(rooms)}</div></div>
      <div class="actions section"><button class="primary" type="submit">Create stay</button><button class="secondary" type="button" id="labBack">Back</button></div>
      </form>`;
    } else {
      body=`<h3>Experience Lab</h3><p class="muted small">Local simulator only — never available inside the real Alexa+ MCP App. Every scenario runs the actual product runtime; nothing here is faked.</p>
      ${(list.scenarios||[]).map(s=>`<button class="labscenario secondary" data-scn="${esc(s.key)}">${esc(s.label)}<small>${esc(s.description)}</small></button>`).join('')}
      <div class="actions section"><button class="ghost" id="labCreateOpen">Create a new demo stay from scratch</button></div>`;
    }
    host.innerHTML=`<div class="labpanel" role="dialog" aria-label="Experience Lab">${body}<div class="actions section"><button class="secondary" id="labClose">Close</button></div></div>`;
    const close=document.getElementById('labClose');if(close)close.onclick=()=>{S.labOpen=false;S.labView='menu';S.labCreateGuests=null;renderLab()};
    document.querySelectorAll('[data-scn]').forEach(b=>b.onclick=()=>labLoad(b.dataset.scn));
    const co=document.getElementById('labCreateOpen');if(co)co.onclick=()=>{S.labView='create';S.labCreateGuests=null;renderLab()};
    const back=document.getElementById('labBack');if(back)back.onclick=()=>{S.labView='menu';S.labCreateGuests=null;renderLab()};
    const form=document.getElementById('labCreateForm');if(form){form.onsubmit=labCreate;const updatePreview=()=>{labSyncGuestsFromDom();const prev=document.getElementById('labPreview');if(prev)prev.innerHTML=labPreviewHtml(rooms)};form.addEventListener('input',updatePreview);form.addEventListener('change',updatePreview)}
    const add=document.getElementById('labAddGuest');if(add)add.onclick=()=>{labSyncGuestsFromDom();if(S.labCreateGuests.length<6){S.labCreateGuests.push({id:++S.labCreateSeq,name:'',room:rooms[S.labCreateGuests.length%rooms.length]||''});renderLab()}};
    document.querySelectorAll('.labGuestRemove').forEach(b=>b.onclick=()=>{labSyncGuestsFromDom();if(S.labCreateGuests.length>1){const id=Number(b.dataset.row);S.labCreateGuests=S.labCreateGuests.filter(g=>g.id!==id);renderLab()}});
  });
}
init().catch(e=>{document.getElementById('hero').innerHTML='<h2>Adaptive Stay needs attention</h2><p class="support">'+esc(e.message||e)+'</p>'});
})();
</script>
</body>
</html>'''

_BUNDLE = _TEMPLATE.replace("__SHELL_VERSION__", SHELL_VERSION)
UI_URI = f"ui://adaptive-stay/product-{sha256(_BUNDLE.encode('utf-8')).hexdigest()[:12]}.html"


def mcp_app_html():
    return _BUNDLE


def standalone_html(initial=None, mcp=False):
    """Same bundle as mcp_app_html(), with one small bootstrap <script> seeded
    in front of it. mcp=False (default, unchanged) keeps the old local /api/*
    REST transport used by the standalone demo harness. mcp=True additionally
    sets window.__ADAPTIVE_MCP__=true, which switches only the tools/call and
    write paths over to the real Streamable HTTP MCP transport above -- for
    hosting this same UI on a public MCP deployment.
    """
    marker = "<script>"
    flags = "window.__ADAPTIVE_STANDALONE__=true;window.__ADAPTIVE_INITIAL__=" + json.dumps(initial or {}, separators=(",", ":")) + ";"
    if mcp:
        flags += "window.__ADAPTIVE_MCP__=true;"
    seed = "<script>" + flags + "</script>"
    return _BUNDLE.replace(marker, seed + marker, 1)
