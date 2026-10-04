// Optional DOM/HTTP smoke: see docs/intellectual-life.md. Use a fresh server data root.
const path=require('node:path'),fs=require('node:fs'),os=require('node:os');
const {JSDOM,CookieJar,VirtualConsole}=require(path.resolve(process.env.PAR_JSDOM_MODULE||'.cache/life-dom/node_modules/jsdom'));
const assert=require('node:assert/strict');
(async()=>{
 const base=process.env.PAR_SMOKE_BASE||'http://127.0.0.1:8765',token=process.env.PAR_ACCESS_TOKEN;
 const books=fs.mkdtempSync(path.join(os.tmpdir(),'omnibus-books-smoke-'));
 const fixture='# Synthetic reading\nAn invented section for smoke testing.\n## A musical idea\nA synthetic motif, not extracted semantic knowledge.\n';
 fs.writeFileSync(path.join(books,'fixture.md'),fixture);
 const jar=new CookieJar();if(token)jar.setCookieSync('par_access='+token,base);
 const errors=[];const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
 const dom=await JSDOM.fromURL(base+'/life',{cookieJar:jar,resources:'usable',runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){w.fetch=(url,options={})=>fetch(new URL(url,base),{...options,headers:{...options.headers,...(token?{Authorization:'Bearer '+token}:{})}});w.prompt=()=>'';w.confirm=()=>true;}});
 const w=dom.window;await new Promise(resolve=>w.addEventListener('load',resolve));
 await w.refresh();
 assert.match(w.document.title,/Intellectual Life/);
 const root=w.document.querySelector('#root-form');root.elements.path.value=books;
 await root.onsubmit({preventDefault(){},target:root});
 const scan=[...w.document.querySelectorAll('#roots button')].find(b=>b.textContent==='Scan read-only');
 await scan.onclick();
 assert.match(w.document.querySelector('#books').textContent,/Synthetic reading/);
 assert(w.document.querySelector('.member-node').options.length>=3);
 const api=(path,method='GET',body)=>w.api(path,method,body);
 const n=await api('/nodes','POST',{data:{title:'200-page smoke fixture',measure:'pages',total:200,provenance:[{kind:'user',description:'Synthetic test fixture'}]}});
 await w.refresh();await w.detail(n.id);
 for(const [start,end]of [[90,100],[100,110]]){
  const form=w.document.querySelector('#progress-form');form.elements.start.value=start;form.elements.end.value=end;
  await form.onsubmit({preventDefault(){},target:form});
 }
 const state=await api('/state');assert.equal(state.progress[n.id].fraction,.55);assert.equal(state.progress[n.id].newly_read,20);
 assert.match(w.document.querySelector('#detail').textContent,/55.0%/);
 assert(w.document.querySelector('#charts svg'));
 const concept=await api('/nodes','POST',{data:{node_type:'concept',kind:'motif',title:'Synthetic musical motif',provenance:[{kind:'user',description:'Fixture assertion, no model'}]}});
 const recording=await api('/nodes','POST',{data:{title:'Fixture recording (placeholder URL)',kind:'recording',url:'https://example.org/fixture-recording',provenance:[{kind:'user',description:'Fixture URL only'}]}});
 for(const [type,members]of [['covers',[{node_id:n.id,role:'source'},{node_id:concept.id,role:'concept'}]],['illustrates',[{node_id:recording.id,role:'resource'},{node_id:concept.id,role:'motif'}]]])await api('/edges','POST',{type,members,explanation:'Smoke fixture connection',provenance:[{kind:'user',description:'Explicit synthetic relation'}]});
 await w.refresh();assert.match(w.document.querySelector('#recommendations').textContent,/Fixture recording/);
 assert(w.document.querySelectorAll('#graph-view polygon').length===2);
 w.document.querySelector('#graph-view polygon').onclick();assert.match(w.document.querySelector('#graph-detail').textContent,/provenance/);
 const dismiss=[...w.document.querySelectorAll('#recommendations button')].find(b=>b.textContent==='dismissed');await dismiss.onclick();
 assert.match(w.document.querySelector('#recommendations').textContent,/No evidenced suggestion/);
 assert.match(w.document.querySelector('#availability').textContent,/No semantic backend configured/);
 const exported=await api('/export');assert.equal(exported.edges.length,2);
 console.log('LIVE HTTP + JSDOM PASS: authenticated page/assets, root form, scan button, populated relation selectors, library, progress form twice, 55% / 20 new pages, chart SVG, graph diamonds/evidence panel, contextual recommendation, dismissal, semantic unavailable, export.');
 console.log('JSDOM errors:',JSON.stringify(errors));assert.equal(errors.length,0);
 assert.equal(fs.readFileSync(path.join(books,'fixture.md'),'utf8'),fixture);
 console.log('Original fixture unchanged; disposable source directory:',books);
 dom.window.close();
})().catch(e=>{console.error(e);process.exit(1)});
