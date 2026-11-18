// Uses workspace Playwright and installed Chrome; serves the unmodified production build.
const fs = require('fs'); const path = require('path'); const {spawn} = require('child_process');
const root = path.resolve(__dirname, '../..');
const {chromium} = require(path.join(root,'.tools/browser-check/node_modules/playwright-core'));
const dash = process.env.QA_DASH_ROOT || path.join(root,'.parts-snapshots-20261118-check/2026-Agent_Scope-8f56930af9f2b9b8491b0df6c26ba6c4a4dc8cc5/dashboard');
const out = process.env.QA_BROWSER_OUT || path.join(root,'QA/evidence/RUN-20261118-LINK-01');
const dataRoot = process.env.QA_DATA_ROOT || path.join(dash,'public/data');
fs.mkdirSync(out,{recursive:true});
const server=spawn(path.join(root,'.pr5-review/asset-scanner/.venv/Scripts/python.exe'),
 ['-m','http.server','18173','--bind','127.0.0.1','--directory',path.join(dash,'dist')],{windowsHide:true,stdio:'ignore'});
const checks=[];let browser;
(async()=>{
 try{
  for(let i=0;i<60;i++){try{if((await fetch('http://127.0.0.1:18173/')).ok)break;}catch{} await new Promise(r=>setTimeout(r,100));}
  browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  if(process.env.QA_DATA_ROOT)await context.route('**/data/**',async route=>{
   const pathname=new URL(route.request().url()).pathname;
   const file=path.resolve(dataRoot,decodeURIComponent(pathname.split('/data/')[1]));
   if(!file.startsWith(path.resolve(dataRoot)+path.sep))return route.abort();
   if(fs.existsSync(file))return route.fulfill({path:file,contentType:'application/json'});
   return route.fulfill({status:404,body:'Missing QA data'});
  });
  for(const profile of ['P0','P1','P2','S1','S1-T5','S2','S3','S4','S5-T1','S5-T2','S5-T3']){
   const page=await context.newPage();const errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.goto('http://127.0.0.1:18173/#'+profile);await page.waitForSelector('.page .empty',{state:'hidden'});
   for(const label of ['자산 현황','자산 지도','위협과 조치']){
    await page.getByRole('navigation').getByRole('button',{name:label}).click();
    const body=await page.locator('main').innerText();
    checks.push({profile,page:label,pass:body.length>100&&!body.includes('파일의 형식이 맞지')&&errors.length===0,js_errors:[...errors]});
    if(['P2','S3'].includes(profile))await page.screenshot({path:path.join(out,profile+'-'+(['자산 현황','자산 지도','위협과 조치'].indexOf(label))+'.png'),fullPage:true});
   }
   await page.close();
  }
  for(const [name,mutate] of [
   ['old_version',s=>s.schema_version='0.6.0-draft'],
   ['duplicate_id',s=>s.assets.push(s.assets[0])],
   ['missing_gateway',s=>s.context.gateway_ref='qa-missing-gateway'],
   ['invalid_target',s=>s.relations[0].target={kind:'qa-invalid'}]]){
   const page=await context.newPage();
   await page.route('**/data/snapshots/P2/snapshot.json',async route=>{
    const s=JSON.parse(fs.readFileSync(path.join(dataRoot,'snapshots/P2/snapshot.json'),'utf8'));mutate(s);
    await route.fulfill({json:s});
   });
   await page.goto('http://127.0.0.1:18173/#P2');
   await page.getByRole('heading',{name:'점검 결과 파일의 형식이 맞지 않아요'}).waitFor();
   checks.push({case:name,pass:true,scope:'browser rejected controlled invalid input'});await page.close();
  }
 }catch(e){checks.push({case:'harness',pass:false,error:String(e)});process.exitCode=1;}
 finally{if(browser)await browser.close();server.kill();fs.writeFileSync(path.join(out,'browser-checks.json'),JSON.stringify(checks,null,2));
 console.log(JSON.stringify({passed:checks.filter(c=>c.pass).length,failed:checks.filter(c=>!c.pass).length}));
 if(checks.some(c=>!c.pass))process.exitCode=1;}
})();
