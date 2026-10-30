// Run with Playwright installed, or set PAPERDESK_PLAYWRIGHT_MODULE to its module path.
const {chromium} = require(process.env.PAPERDESK_PLAYWRIGHT_MODULE || 'playwright');
const path = require('path');
const {spawn} = require('child_process');
const fs = require('fs');
const assert = require('assert').strict;
const root = fs.mkdtempSync('/tmp/pd-local-'); console.error('Test data:',root);
const project = path.resolve(__dirname, '../..');
let processes = [], browser;
const serverErrors = [], errors = [], external = [];
function startServer() {
  return new Promise((resolve, reject) => {
    const child = spawn(process.env.PYTHON || 'python3', ['-m', 'tests.offline_server', root], {
      cwd: project, env: {...process.env, PYTHONPATH: 'src:.'}, stdio: ['ignore','pipe','pipe']
    });
    processes.push(child);
    child.stderr.on('data', data => serverErrors.push(data.toString()));
    let output = '';
    child.stdout.on('data', data => { output += data; if (output.includes('\n')) resolve({...JSON.parse(output.split('\n')[0]), process: child}); });
    child.on('error', reject);
    child.on('exit', code => { if (!output) reject(new Error('server failed: '+code+' '+serverErrors)); });
  });
}
async function stopServer(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  await new Promise(resolve => {
    const timer=setTimeout(()=>child.kill('SIGTERM'),5000);
    child.once('exit',()=>{clearTimeout(timer);resolve();});
    child.kill('SIGINT');
  });
}
async function contextFor(base) {
  const context = await browser.newContext({viewport:{width:1500,height:920}});
  await context.route('**/*', async route => {
    const url = route.request().url();
    if (!url.startsWith(base) && /^https?:/.test(url)) { external.push(url); return route.abort(); }
    await route.continue();
  });
  context.on('page', page => {
    page.on('pageerror', e => errors.push(e.message));
    page.on('response', async r => { if(r.status()>=400) console.error('HTTPFAIL',r.url(),await r.text(),r.request().postData()); });
    page.on('console', m => { if (m.type()==='error') errors.push(m.text()); });
  });
  return context;
}
async function read(context, url) { const response=await context.request.get(url); assert(response.ok(), await response.text()); return response.json(); }
async function waitFor(fn) { for(let i=0;i<100;i++) { if(await fn()) return; await new Promise(r=>setTimeout(r,100)); } throw new Error('poll timed out'); }
(async()=>{
  browser=await chromium.launch(process.env.PAPERDESK_CHROMIUM ? {executablePath:process.env.PAPERDESK_CHROMIUM} : {});
  const first=await startServer();
  let context=await contextFor(first.url), page=await context.newPage();
  const lib=await read(context,first.url+'api/library');
  const paper=lib.documents.find(d=>d.filename==='paper.pdf').id;
  const other=lib.documents.find(d=>d.filename==='second.pdf').id;
  await page.addInitScript(({paper})=>{
    if (!location.search.includes('seed')) return;
    localStorage.setItem('paperdesk-theme','dark');
    localStorage.setItem('paperdesk-assistant','collapsed');
    localStorage.setItem('paperdesk-expanded','[]');
    localStorage.setItem('paperdesk-thread:'+paper,JSON.stringify([{task:'ask',question:'legacy question',answer:'legacy answer',status:'done'}]));
  },{paper});
  await page.goto(first.url+'library?seed=1');
  await page.waitForFunction(()=>window.paperdesk?.view);
  assert.equal(await page.evaluate(()=>document.documentElement.dataset.theme),'dark');
  assert.equal(await page.evaluate(id=>localStorage.getItem('paperdesk-thread:'+id),paper),null);
  assert.equal((await read(context,first.url+'api/documents/'+paper+'/conversation')).turns[0].answer,'legacy answer');
  await page.goto(first.url+'reader?id='+paper);
  await page.waitForFunction(()=>window.paperdesk?.view?.analysis,null,{timeout:60000});
  await page.evaluate(()=>window.paperdesk.assistant.history.ready);
  assert.equal(await page.evaluate(()=>window.paperdesk.assistant.turns[0].answer),'legacy answer');
  assert.equal(await page.evaluate(()=>document.getElementById('app').classList.contains('assistant-collapsed')),true);
  await page.evaluate(async()=>{
    const app=window.paperdesk;
    window.paperdeskTheme.set('light');
    app.toggleSidebar();
    app.view.setTranslationMode('over');
    app.view.nav.open('pages');
    const prefs=await import('/js/prefs.js');
    await prefs.flushPrefs();
    const block=app.view.analysis.blocks.find(b=>b.translatable);
    app.view.translation.enqueue([block]);
    await app.api.post('/api/documents/'+app.view.id+'/annotations',{kind:'note',color:'green',page:1,text:'local note text',note:'persisted note',rects:[[0.1,0.1,0.3,0.15]]});
    await app.assistant.run({task:'ask',text:'Local reading test.',question:'saved question'});
  });
  await page.waitForFunction(()=>Object.keys(window.paperdesk.view.translation.store).length>0);
  // Completing an AI request after navigating must save to its original paper.
  let release, requestStarted;
  const gate=new Promise(resolve=>release=resolve), started=new Promise(resolve=>requestStarted=resolve);
  await context.route('**/api/assist',async route=>{
    if(route.request().postDataJSON().question!=='switch-paper') return route.fallback();
    requestStarted(); await gate;
    await route.fulfill({json:{text:'response for original paper',provider_id:'demo',model:'demo',cached:false}});
  });
  await page.evaluate(()=>{window.pendingRun=window.paperdesk.assistant.run({task:'ask',text:'original paper',question:'switch-paper'});});
  await started;
  await page.evaluate(id=>window.paperdesk.router.go('/reader?id='+id),other);
  await page.waitForFunction(id=>window.paperdesk.view?.id===id&&window.paperdesk.view.analysis,other,{timeout:60000});
  release(); await page.evaluate(()=>window.pendingRun);
  assert((await read(context,first.url+'api/documents/'+paper+'/conversation')).turns.some(t=>t.answer==='response for original paper'));
  assert.equal((await read(context,first.url+'api/documents/'+other+'/conversation')).turns.length,0);
  await context.close();
  await stopServer(first.process);
  // A new app process, new port and new empty browser storage use the same app data folder.
  const second=await startServer();
  assert.notEqual(second.url,first.url);
  context=await contextFor(second.url); page=await context.newPage();
  await page.goto(second.url+'reader?id='+paper);
  await page.waitForFunction(()=>window.paperdesk?.view?.analysis&&Object.keys(window.paperdesk.view.translation.store).length,null,{timeout:60000});
  await page.evaluate(()=>window.paperdesk.assistant.history.ready);
  assert.equal(await page.evaluate(()=>document.documentElement.dataset.theme),'light');
  assert.equal(await page.evaluate(()=>document.getElementById('app').classList.contains('sidebar-hidden')),true);
  assert.equal(await page.evaluate(()=>window.paperdesk.view.tmode),'over');
  assert.equal(await page.evaluate(()=>window.paperdesk.view.nav.tab),'pages');
  assert.equal(await page.evaluate(()=>window.paperdesk.view.nav.drawer.hidden),false);
  assert.equal(await page.evaluate(()=>window.paperdesk.assistant.turns.length),3);
  assert.equal(await page.evaluate(()=>localStorage.length),0);
  assert((await read(context,second.url+'api/documents/'+paper+'/annotations')).annotations.some(a=>a.note==='persisted note'));
  await page.screenshot({path:root+'/restored.png'});
  // Clearing remains empty after reloading and after an old client offers its legacy history.
  await page.evaluate(()=>window.paperdesk.assistant.clearTurns());
  await context.request.post(second.url+'api/state/import',{headers:{'X-Paperdesk':'1'},data:{conversations:{[paper]:[{answer:'must not resurrect',status:'done'}]},preferences:{theme:'dark'}}});
  await page.reload();
  await page.waitForFunction(()=>window.paperdesk?.assistant?.reader);
  await page.evaluate(()=>window.paperdesk.assistant.history.ready);
  assert.equal(await page.evaluate(()=>window.paperdesk.assistant.turns.length),0);
  assert.equal(await page.evaluate(()=>document.documentElement.dataset.theme),'light');
  // Development builds show the real unavailable state, without claiming to be up to date.
  await page.goto(second.url+'settings');
  const updates=page.getByTestId('app-updates');
  await updates.waitFor();
  assert(await updates.getByRole('button',{name:'Check for updates'}).isDisabled());
  assert(await updates.getByRole('checkbox').isDisabled());
  // Exercise the settings UI contract without loading Cocoa in Linux.
  let automatic=false, checks=0;
  await context.route('**/api/updates',route=>route.fulfill({json:{version:'0.1.0',available:true,can_check:true,automatic_checks:automatic,message:''}}));
  await context.route('**/api/updates/preferences',route=>{
    automatic=route.request().postDataJSON().automatic_checks;
    return route.fulfill({json:{version:'0.1.0',available:true,can_check:true,automatic_checks:automatic,message:''}});
  });
  await context.route('**/api/updates/check',route=>{checks++;return route.fulfill({json:{opened:true}});});
  await page.reload();
  await page.getByTestId('app-updates').getByRole('checkbox').check();
  await waitFor(()=>automatic);
  await page.getByTestId('app-updates').getByRole('button',{name:'Check for updates'}).click();
  await waitFor(()=>checks===1);
  await page.screenshot({path:root+'/settings-updates.png',fullPage:true});
  await context.close(); await stopServer(second.process);
  assert.deepEqual(errors,[]); assert.deepEqual(external,[]); assert.deepEqual(serverErrors,[]);
  console.log(JSON.stringify({root,ports:[first.url,second.url],legacyMigrated:true,restored:['PDF','translations','notes','chat','theme','panels','navigator','translation mode'],externalRequests:external,consoleErrors:errors},null,2));
})().catch(e=>{console.error(e);console.error({serverErrors,errors,external});process.exitCode=1;}).finally(async()=>{
  if(browser)await browser.close(); for(const child of processes)await stopServer(child);
});
