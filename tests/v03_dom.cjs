// Synthetic DOM fixture rendering, NOT a real provider/browser-login acceptance test.
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const {JSDOM, VirtualConsole} = require(path.resolve('.cache/life-dom/node_modules/jsdom'));
const fixture = JSON.parse(fs.readFileSync(0,'utf8'));
const acknowledgements = [], errors = [];
let rendered;
const completion = new Promise(resolve => { rendered=resolve });
const vc = new VirtualConsole(); vc.on('jsdomError', e => errors.push(e.message));
const dom = new JSDOM(fixture.html, {url:'http://localhost/', runScripts:'dangerously', virtualConsole:vc, beforeParse(w){
 w.fetch = async (url, options={}) => {
  const parsed=new URL(url,'http://localhost'); let data;
  if(parsed.pathname==='/api/life/state') data=fixture.state;
  else if(parsed.pathname==='/api/life/graph') data=fixture.graph;
  else if(parsed.pathname==='/api/life/discovery-reports') data=[];
  else if(parsed.pathname==='/api/life/comparison') data=fixture.comparison;
  else if(parsed.pathname.endsWith('/rendered')){
   assert(w.document.querySelector('#recommendations').textContent.includes('May add:'));
   acknowledgements.push(parsed.pathname.split('/')[4]); data={acknowledged:true}; rendered();
  } else throw Error('Unexpected fixture request '+url);
  return {ok:true,json:async()=>structuredClone(data)};
 };
}});
(async()=>{
 dom.window.eval(fs.readFileSync('src/par/static/life.js','utf8'));
 let timer; await Promise.race([completion,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('No recommendation DOM acknowledgement')),3000)})]); clearTimeout(timer);
 assert.match(dom.window.document.querySelector('#recommendations').textContent,/Composition/);
 assert.match(dom.window.document.querySelector('#recommendations').textContent,/Functors/);
 assert.match(dom.window.document.querySelector('#recommendations').textContent,/manually supplied, unverified URL/);
 const form=dom.window.document.querySelector('#comparison-form');
 await form.onsubmit({preventDefault(){},target:form});
 assert.match(dom.window.document.querySelector('#comparison-result').textContent,/Additional represented in candidate: Functors/);
 assert.match(dom.window.document.querySelector('#analyses').textContent,/7a. Recommendation generated — observed/);
 assert.match(dom.window.document.querySelector('#analyses').textContent,/7b. UI acknowledged rendering — not reached/);
 await new Promise(setImmediate); // Drain the initial refresh/discovery promise chain before closing the DOM.
 assert.equal(errors.length,0,errors.join('\n'));
 console.log(JSON.stringify({acknowledgements,errors}));
 dom.window.close();
})().catch(e=>{console.error(e);dom.window.close();process.exit(1)});
