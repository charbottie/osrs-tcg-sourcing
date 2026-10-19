// Headless Chrome check via the DevTools protocol (no npm deps; Node ≥ 22 has WebSocket + fetch).
// Usage: node scripts/dev/cdp_check.mjs <url> <out.png> '<js to run after load; may await; return a value>' [waitMs]
// Prints console messages / exceptions from the page, then "[result] <value>", and saves a screenshot.
import { spawn } from 'node:child_process';
import { writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const [url, out, script = '', waitMs = '2500'] = process.argv.slice(2);
const port = 9333 + Math.floor(Math.random() * 500);
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', `--remote-debugging-port=${port}`, '--window-size=1400,1000',
  `--user-data-dir=${mkdtempSync(join(tmpdir(), 'cdp-'))}`, 'about:blank',
], { stdio: 'ignore' });

const sleep = ms => new Promise(r => setTimeout(r, ms));
let target;
for (let i = 0; i < 40 && !target; i++) {
  await sleep(250);
  try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find(t => t.type === 'page'); } catch {}
}
if (!target) { console.error('could not reach headless Chrome'); chrome.kill(); process.exit(1); }
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise(r => ws.addEventListener('open', r));
let id = 0; const pending = new Map(); const logs = [];
ws.addEventListener('message', ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  if (m.method === 'Runtime.consoleAPICalled')
    logs.push(`[${m.params.type}] ` + m.params.args.map(a => a.value ?? a.description ?? '').join(' '));
  if (m.method === 'Runtime.exceptionThrown')
    logs.push('[exception] ' + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
});
const send = (method, params = {}) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });

await send('Runtime.enable');
await send('Page.enable');
await send('Page.navigate', { url });
await sleep(Number(waitMs));
let result;
if (script) {
  const r = await send('Runtime.evaluate', { expression: `(async()=>{${script}})()`, awaitPromise: true, returnByValue: true });
  if (r.result?.exceptionDetails) logs.push('[script error] ' + (r.result.exceptionDetails.exception?.description || r.result.exceptionDetails.text));
  else result = r.result?.result?.value;
}
await sleep(300);
const shot = await send('Page.captureScreenshot', { format: 'png' });
if (out && shot.result?.data) writeFileSync(out, Buffer.from(shot.result.data, 'base64'));
for (const l of logs) console.log(l);
if (result !== undefined) console.log('[result] ' + (typeof result === 'string' ? result : JSON.stringify(result)));
ws.close(); chrome.kill();
process.exit(0);
