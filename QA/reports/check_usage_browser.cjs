const fs=require('fs'),path=require('path'),{spawn}=require('child_process');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'QA/evidence/RUN-20261118-LINK-01');
const dash=path.join(root,'.parts-snapshots-20261118-check/2026-Agent_Scope-8f56930af9f2b9b8491b0df6c26ba6c4a4dc8cc5/dashboard');
const {chromium}=require(path.join(root,'.tools/browser-check/node_modules/playwright-core'));
let browser;const checks=[];const logs=fs.openSync(path.join(out,'live-browser.local.log'),'w');
const api=spawn(path.join(out,'pc/agentscope-usage-api.local.exe'),['--env','agentscope-testbed','--profile','tb-openclaw','--inventory',path.join(out,'P2.snapshot.json'),'--input',path.join(out,'controlled.traces.jsonl'),'--reference-pricing=false','--addr','127.0.0.1:18088'],{windowsHide:true,stdio:['ignore',logs,logs]});
const vite=spawn(process.execPath,[path.join(dash,'node_modules/vite/bin/vite.js'),'preview','--host','127.0.0.1','--port','18174','--strictPort'],{cwd:dash,env:{...process.env,USAGE_API_TARGET:'http://127.0.0.1:18088'},windowsHide:true,stdio:['ignore',logs,logs]});
(async()=>{try{
 for(let i=0;i<100;i++){try{if((await fetch('http://127.0.0.1:18174/api/v1/usage/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,150));}
 browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const received=page.waitForResponse(r=>r.url().includes('/api/v1/usage/summary')&&r.status()===200);
 await page.goto('http://127.0.0.1:18174/#P2');const summary=await (await received).json();
 await page.waitForSelector('.page .empty',{state:'hidden'});
 await page.getByRole('navigation').getByRole('button',{name:'자산 지도'}).click();
 await page.getByText('15,769',{exact:true}).first().waitFor();
 checks.push({case:'live_proxy_summary',pass:summary.calls===16&&summary.by_mapping.matched===2&&summary.attributed_tokens===15769});
 checks.push({case:'live_total_rendered',pass:(await page.locator('main').innerText()).includes('15,769')});
 await page.getByRole('button',{name:/로컬 MCP 서버 1/}).first().click();
 await page.getByText(/3,920 토큰/).waitFor();
 checks.push({case:'mapped_server_usage_rendered',pass:true,expected:'3,920 tokens / 2 calls'});
 checks.push({case:'no_browser_runtime_errors',pass:errors.length===0,errors});
 await page.screenshot({path:path.join(out,'P2-live-usage.png'),fullPage:true});
}catch(e){checks.push({case:'live_harness',pass:false,error:String(e)});process.exitCode=1;}
finally{if(browser)await browser.close();vite.kill();api.kill();fs.closeSync(logs);fs.writeFileSync(path.join(out,'live-browser-checks.json'),JSON.stringify(checks,null,2));console.log(JSON.stringify(checks));if(checks.some(c=>!c.pass))process.exitCode=1;}})();
