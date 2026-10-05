// Synthetic DOM / real UI code. NOT a browser account or native Windows test.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {JSDOM,VirtualConsole}=require(path.resolve('.cache/life-dom/node_modules/jsdom'));
const fixture=JSON.parse(fs.readFileSync(0,'utf8')),posts=[],errors=[];
let planned=false,approved=false;
const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
const dom=new JSDOM(fixture.html,{url:'http://localhost/',runScripts:'dangerously',virtualConsole:vc,beforeParse(w){
 w.fetch=async(url,options={})=>{
  let data;
  if(options.method==='POST')posts.push({url,body:JSON.parse(options.body)});
  if(url==='/api/assistant/state')data={config:fixture.config,operations:planned?[approved?fixture.result.job:fixture.plan.job]:[]};
  else if(url==='/api/assistant/commands'){planned=true;data=fixture.plan.job}
  else if(url.endsWith('/approve')){approved=true;data=fixture.result.job}
  else if(url==='/api/assistant/operations/'+fixture.result.job.id)data=approved?fixture.result:fixture.plan;
  else throw Error('Unexpected request '+url);
  return {ok:true,json:async()=>structuredClone(data)};
 };
}});
(async()=>{
 const w=dom.window,d=w.document;
 w.eval(fs.readFileSync('src/par/static/assistant.js','utf8'));await new Promise(setImmediate);
 assert.equal(d.querySelector('#advanced-controls').open,false);
 d.querySelector('#collection-text').value=fixture.plan.job.command;
 const form=d.querySelector('#collection-command');await form.onsubmit({preventDefault(){},target:form});
 assert.equal(posts.length,1);assert.equal(posts[0].body.text,fixture.plan.job.command);
 assert.match(d.querySelector('#collection-result').textContent,/One approval for this collection/);
 assert.equal(d.querySelectorAll('#collection-result input').length,0);
 const consent=[...d.querySelectorAll('#collection-result button')].find(b=>b.textContent==='Approve chatgpt and begin');
 assert(consent);await consent.onclick();
 assert.equal(posts.length,2);assert.deepEqual(posts[1].body,{provider:'chatgpt'});
 assert.match(d.querySelector('#collection-result').textContent,/Collection analysis finished/);
 assert.match(d.querySelector('#collection-result').textContent,/No relationship was silently confirmed/);
 const progress=d.querySelector('#collection-result progress');assert.equal(progress.value,progress.max);
 assert(d.querySelector('#collection-result svg'));
 const theme=[...d.querySelectorAll('#collection-result button')].find(b=>b.textContent.startsWith('Composition ·'));
 assert(theme);await theme.onclick();
 const evidence=d.querySelector('#collection-evidence');
 assert.match(evidence.textContent,/covers · proposed/);assert.match(evidence.textContent,/covers · confirmed/);
 assert.match(evidence.textContent,/Composition is associative/);
 assert([...evidence.querySelectorAll('a')].every(a=>a.getAttribute('href').startsWith('/api/artifacts/')));
 assert(evidence.querySelectorAll('a').length>0);
 assert.equal(d.querySelector('[data-injected]'),null);
 assert.equal(d.querySelector('#advanced-controls').open,false);
 assert.equal(errors.length,0,errors.join('\n'));
 console.log(JSON.stringify({posts:posts.length,evidenceLinks:evidence.querySelectorAll('a').length,errors}));
 dom.window.close();
})().catch(e=>{console.error(e);dom.window.close();process.exit(1)});
