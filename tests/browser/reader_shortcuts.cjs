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
  const server=await startServer(), context=await contextFor(server.url), page=await context.newPage();
  await page.addInitScript(()=>Object.defineProperty(navigator,'platform',{get:()=> 'MacIntel'}));
  const paper=(await read(context,server.url+'api/library')).documents.find(d=>d.filename==='paper.pdf').id;
  await page.goto(server.url+'reader?id='+paper);
  await page.waitForFunction(()=>window.paperdesk?.view?.analysis && window.paperdesk.view.pages[0].map,null,{timeout:60000});
  const results=[];
  async function check(name, fn) { try { await fn(); results.push({name,ok:true}); } catch(e) { results.push({name,ok:false,error:e.message}); } }
  async function count() {return (await read(context,server.url+'api/documents/'+paper+'/annotations')).annotations.length;}
  async function select(event) {
    return page.evaluate(event=>{
      const reader=window.paperdesk.view; reader.pagesEl.focus(); reader.hideMenu();
      const span=[...document.querySelectorAll('.page[data-page="1"] .textLayer span')].find(s=>s.textContent.length>40);
      const range=document.createRange(); range.selectNodeContents(span);
      const selection=getSelection(); selection.removeAllRanges(); selection.addRange(range);
      if(event) {const e=new KeyboardEvent('keydown',{bubbles:true,cancelable:true,...event});reader.pagesEl.dispatchEvent(e);return e.defaultPrevented;}
      return reader.selectionInfo().text;
    },event);
  }
  async function waitMenu(){await page.waitForSelector('.selection-menu');}
  await check('English H saves highlight',async()=>{
    const before=await count(); await select(); await waitMenu(); await page.keyboard.press('h'); await waitFor(async()=>await count()===before+1);
  });
  await check('H works before selection toolbar appears',async()=>{
    const before=await count(); assert(await select({key:'h',code:'KeyH'}),'shortcut was ignored'); await waitFor(async()=>await count()===before+1);
  });
  await check('Korean-layout H saves highlight',async()=>{
    const before=await count(); await select(); await waitMenu();
    await page.dispatchEvent('.pages','keydown',{key:'ㅗ',code:'KeyH'}); await waitFor(async()=>await count()===before+1);
  });
  await check('Korean-layout C opens and saves a note',async()=>{
    const before=await count(); await select(); await waitMenu(); await page.dispatchEvent('.pages','keydown',{key:'ㅊ',code:'KeyC'});
    await page.waitForSelector('.note-input',{timeout:1500}); await page.locator('.note-input').fill('Shortcut regression note');
    await page.locator('.note-input').press('Meta+Enter'); await waitFor(async()=>await count()===before+1);
    assert((await read(context,server.url+'api/documents/'+paper+'/annotations')).annotations.some(a=>a.note==='Shortcut regression note'));
  });
  await check('Typing and IME confirmation never trigger reader commands or save a note',async()=>{
    const before=await count(); await select(); await waitMenu(); await page.keyboard.press('c');
    await page.waitForSelector('.note-input');
    await page.locator('.note-input').fill('Draft: '); await page.locator('.note-input').press('End'); await page.keyboard.type('hct');
    assert.equal(await page.locator('.note-input').inputValue(),'Draft: hct');
    for(const event of [{key:'Enter',code:'Enter',metaKey:true,isComposing:true},
                        {key:'Enter',code:'Enter',metaKey:true,keyCode:229},
                        {key:'Escape',code:'Escape',isComposing:true},
                        {key:'ㄹ',code:'KeyF',metaKey:true},
                        {key:'ㅓ',code:'KeyJ',metaKey:true}]) {
      await page.dispatchEvent('.note-input','keydown',event);
      assert.equal(await page.locator('.note-input').count(),1,'IME or a global shortcut closed the note');
    }
    assert.equal(await page.evaluate(()=>window.paperdesk.view.find.bar.hidden),true);
    assert.equal(await count(),before);
    await page.locator('.note-input').press('Escape');
    await page.waitForSelector('.note-input',{state:'detached'});
    assert.equal(await count(),before);
    assert.equal(await page.evaluate(()=>document.activeElement===window.paperdesk.view.pagesEl),true);
  });
  await check('Collapsed selection cannot reuse a stale toolbar selection',async()=>{
    const before=await count(); await select(); await waitMenu();
    const prevented=await page.evaluate(()=>{
      getSelection().removeAllRanges();
      const e=new KeyboardEvent('keydown',{key:'h',code:'KeyH',bubbles:true,cancelable:true});
      window.paperdesk.view.pagesEl.dispatchEvent(e);return e.defaultPrevented;
    });
    assert.equal(prevented,false); await page.waitForTimeout(220); assert.equal(await count(),before);
  });
  await check('Command+C, Option+H and repeated keys preserve native keyboard behavior',async()=>{
    const before=await count(); await select(); await waitMenu();
    const prevented=await page.evaluate(()=>{
      const el=window.paperdesk.view.pagesEl;
      return [{key:'c',code:'KeyC',metaKey:true},{key:'h',code:'KeyH',altKey:true},{key:'h',code:'KeyH',repeat:true}].map(data=>{
        const e=new KeyboardEvent('keydown',{bubbles:true,cancelable:true,...data});el.dispatchEvent(e);return e.defaultPrevented;
      });
    });
    assert.deepEqual(prevented,[false,false,false]); assert.equal(await count(),before); assert.equal(await page.locator('.note-input').count(),0);
  });
  await check('Korean-layout Command+F opens PDF find',async()=>{
    await page.dispatchEvent('.pages','keydown',{key:'ㄹ',code:'KeyF',metaKey:true});
    assert.equal(await page.evaluate(()=>window.paperdesk.view.find.bar.hidden),false);
    await page.locator('.find-input').press('Escape');
  });
  await check('All selection actions use physical keys for non-Latin input',async()=>{
    await page.evaluate(()=>{
      const a=window.paperdesk.assistant;
      window.shortcutActions=[];
      window.oldRun=a.runOnSelection;window.oldQuote=a.quote;
      a.runOnSelection=(action,info)=>window.shortcutActions.push({action,text:info.text});
      a.quote=info=>window.shortcutActions.push({action:'ask',text:info.text});
    });
    for(const [key,code] of [['ㅅ','KeyT'],['ㄷ','KeyE'],['ㅈ','KeyW'],['ㅂ','KeyQ']]) {
      const selected=await select(); await waitMenu(); await page.dispatchEvent('.pages','keydown',{key,code});
      const actions=await page.evaluate(()=>window.shortcutActions); assert.equal(actions.at(-1).text,selected);
    }
    const actions=await page.evaluate(()=>window.shortcutActions.map(a=>a.action));
    assert.deepEqual(actions,['translate','explain','define','ask']);
    await page.evaluate(()=>{const a=window.paperdesk.assistant;a.runOnSelection=window.oldRun;a.quote=window.oldQuote;});
  });
  await check('Note editing can delete a saved annotation',async()=>{
    const before=await count();
    await page.evaluate(()=>{
      const a=window.paperdesk.view.annotations; const note=a.items.find(n=>n.note==='Shortcut regression note');
      window.pendingEdit=a.editNote(note);
    });
    await page.waitForSelector('.note-input');
    await page.locator('.floating-note .btn.danger').click();
    await waitFor(async()=>await count()===before-1);
    await page.evaluate(()=>window.pendingEdit);
  });
  await check('Dragging PDF text after using the AI composer restores shortcut focus',async()=>{
    const before=await count();
    await page.evaluate(()=>window.paperdesk.assistant.showTab('chat'));
    await page.locator('.composer textarea').fill('Draft kept while reading');
    const points=await page.evaluate(()=>{
      const span=[...document.querySelectorAll('.page[data-page="1"] .textLayer span')].find(s=>s.textContent.length>40);
      const range=document.createRange();range.setStart(span.firstChild,0);range.setEnd(span.firstChild,20);
      const r=range.getBoundingClientRect();return {x:r.left+1,y:r.top+r.height/2,end:r.right-1};
    });
    await page.mouse.move(points.x,points.y);await page.mouse.down();
    await page.mouse.move(points.end,points.y,{steps:12});await page.mouse.up();
    await waitMenu();assert(await page.evaluate(()=>getSelection().toString().trim().length>3));
    await page.keyboard.press('h');await waitFor(async()=>await count()===before+1);
    assert.equal(await page.locator('.composer textarea').inputValue(),'Draft kept while reading');
  });
  await check('Highlights persist after reload',async()=>{
    const before=await count(); await page.reload();
    await page.waitForFunction(()=>window.paperdesk?.view?.pages[0]?.map,null,{timeout:60000});
    await page.waitForFunction(()=>window.paperdesk.view.annotations.items.some(a=>a.kind==='highlight'));
    assert.equal(await count(),before);
    assert(await page.locator('.layer.marks .hl').count()>0);
  });
  console.log(JSON.stringify({root,results,errors,external},null,2));
  assert(results.every(r=>r.ok),'Some reader shortcuts failed'); assert.deepEqual(errors,[]); assert.deepEqual(external,[]);
  await context.close();
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{
  if(browser)await browser.close();for(const child of processes)await stopServer(child);
});
