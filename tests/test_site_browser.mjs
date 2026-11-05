// Optional integration check: a running showcase on localhost:8000 and Chromium.
// Uses Node 24's native WebSocket; no browser automation dependencies.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const artifacts = await mkdtemp(join(tmpdir(), 'balance-trees-browser-'));
const browser = spawn(process.env.CHROMIUM ?? 'chromium', [
  '--headless', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage',
  '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0',
  `--user-data-dir=${join(artifacts, 'profile')}`, 'about:blank',
], { stdio: ['ignore', 'ignore', 'pipe'] });
let socket;
try {
  const endpoint = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Chromium did not start in 15 seconds')), 15000);
    browser.once('error', reject);
    browser.once('exit', code => reject(new Error(`Chromium exited: ${code}`)));
    let stderr = '';
    browser.stderr.on('data', data => {
      stderr += data;
      const match = stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) { clearTimeout(timer); resolve(match[1]); }
    });
  });
  socket = new WebSocket(endpoint);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let id = 0;
  const pending = new Map(), exceptions = [];
  socket.onmessage = event => {
    const value = JSON.parse(event.data);
    if (value.method === 'Runtime.exceptionThrown') exceptions.push(value.params.exceptionDetails);
    if (value.id) {
      const request = pending.get(value.id); pending.delete(value.id);
      clearTimeout(request.timer);
      if (value.error) request.reject(new Error(JSON.stringify(value.error)));
      else request.resolve(value.result);
    }
  };
  const call = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    const key = ++id;
    const timer = setTimeout(() => { pending.delete(key); reject(new Error(`CDP timeout: ${method}`)); }, 20000);
    pending.set(key, { resolve, reject, timer });
    socket.send(JSON.stringify({ id: key, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
  const { targetId } = await call('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await call('Target.attachToTarget', { targetId, flatten: true });
  const page = (method, params = {}) => call(method, params, sessionId);
  await page('Runtime.enable'); await page('Page.enable');
  const evaluate = async expression => {
    const response = await page('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails));
    return response.result.value;
  };
  const waitFor = async expression => {
    const until = Date.now() + 30000;
    while (Date.now() < until) {
      if (await evaluate(expression)) return;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw new Error(`Timed out waiting for ${expression}`);
  };
  const navigate = async path => {
    await page('Page.navigate', { url: `http://127.0.0.1:8000/${path}` });
    await waitFor('document.readyState === "complete"');
  };
  const screenshot = async name => {
    const { data } = await page('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
    await writeFile(join(artifacts, name), Buffer.from(data, 'base64'));
  };
  await page('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });
  await navigate('index.html');
  await waitFor('document.querySelector("#source-badge")?.textContent === "Python implementation"');
  const registeredCount = await evaluate('fetch("./api/config").then(r => r.json()).then(data => Object.keys(data.strategies).length)');
  assert.equal(await evaluate('document.querySelector("#strategy").options.length'), registeredCount + 1);
  assert.equal(await evaluate('document.querySelector("#benchmark-link").getAttribute("href")'), './benchmarks/index.html');
  await evaluate(`document.querySelector('#tutorial').close(); document.querySelector('#strategy').value='treap'; document.querySelector('#seed').value='17'; document.querySelector('#sequence').value='8,4,12,2,6,10,14,3,5,11,0,-2'; document.querySelector('#use-sequence').click();`);
  await waitFor('document.querySelector("#count").value === "12" && document.querySelector("#phase").textContent === "Ready"');
  const coloredFrame = await evaluate(`(async () => {
    const trace = await fetch('./api/trace', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sequence:[8,4,12,2,6,10,14,3,5,11,0,-2],strategy:'treap',seed:17})}).then(r=>r.json());
    const index = trace.frames.findLastIndex(frame => frame.kind === 'rotate' && frame.effects.rose.length && frame.effects.fell.length && frame.effects.compared.length > 2);
    const timeline = document.querySelector('#timeline'); timeline.value=index; timeline.dispatchEvent(new Event('input'));
    return index;
  })()`);
  assert.ok(coloredFrame > 0);
  assert.equal(await evaluate('document.querySelectorAll(".tree-node.inserted").length'), 1);
  assert.equal(await evaluate('getComputedStyle(document.querySelector(".inserted-ring")).fill'), 'none');
  assert.equal(await evaluate('getComputedStyle(document.querySelector(".inserted .inserted-ring")).display'), 'block');
  const fills = await evaluate('[".rose:not(.fell)",".fell:not(.rose)"].map(role => getComputedStyle(document.querySelector(".tree-node"+role+" > circle")).fill)');
  assert.notEqual(fills[0], fills[1]);
  assert.equal(await evaluate('document.querySelector(".tree-node.inserted .role-label").textContent.includes("★")'), true);
  const rolesBefore = await evaluate('[...document.querySelectorAll(".tree-node")].map(node=>[node.dataset.key,node.getAttribute("class")])');
  await screenshot('colored-trace-light.png');
  await evaluate('document.querySelector("#theme-toggle").click()');
  await screenshot('colored-trace-dark.png');
  await evaluate(`document.querySelector('#timeline').value=${coloredFrame + 1}; document.querySelector('#timeline').dispatchEvent(new Event('input')); document.querySelector('#timeline').value=${coloredFrame}; document.querySelector('#timeline').dispatchEvent(new Event('input'));`);
  assert.deepEqual(await evaluate('[...document.querySelectorAll(".tree-node")].map(node=>[node.dataset.key,node.getAttribute("class")])'), rolesBefore);
  await navigate('benchmarks/index.html');
  assert.equal(await evaluate('document.querySelectorAll("#workload option").length'), 8);
  assert.equal(await evaluate('document.querySelector("nav a").getAttribute("href")'), '../index.html');
  assert.equal(await evaluate('fetch("./summary.csv").then(r=>r.status)'), 200);
  await evaluate('document.querySelector("#workload").value="converging"; document.querySelector("#workload").dispatchEvent(new Event("change"))');
  assert.equal(await evaluate('[...document.querySelectorAll("[data-order]:not([hidden])")].every(element=>element.dataset.order==="converging")'), true);
  await screenshot('benchmark-report.png');
  await navigate('index.html');
  await waitFor('document.querySelector("#source-badge")?.textContent === "Python implementation"');
  await evaluate(`document.querySelector('#tutorial').close(); document.querySelector('#strategy').value='random-level'; document.querySelector('#count').value='10000'; document.querySelector('#order').value='random'; document.querySelector('#generate').click();`);
  await waitFor('document.querySelector("#source-badge").textContent === "Browser simulation"');
  await evaluate('document.querySelector("#play").click()');
  await waitFor('document.querySelector("#metric-nodes").textContent === "10000" && document.querySelector("#play-label").textContent === "Replay"');
  assert.equal(await evaluate('document.querySelectorAll("#nodes .tree-node").length <= 48'), true);
  assert.equal(await evaluate('document.body.classList.contains("compact-preview")'), true);
  assert.match(await evaluate('document.querySelector("#visible-count").textContent'), /10,000 nodes shown/);
  assert.equal(await evaluate('document.querySelector("#error").hidden'), true);
  await screenshot('preview-desktop.png');
  await evaluate(`document.querySelector('#strategy').value='interval-target-local-repair'; document.querySelector('#order').value='converging'; document.querySelector('#generate').click();`);
  await waitFor('document.querySelector("#source-badge").textContent === "Browser simulation"');
  await evaluate('document.querySelector("#play").click()');
  await waitFor('document.querySelector("#metric-nodes").textContent === "10000" && document.querySelector("#play-label").textContent === "Replay"');
  assert.equal(await evaluate('document.querySelector("#strategy").value'), 'interval-target-local-repair');
  assert.equal(await evaluate('document.querySelector("#error").hidden'), true);
  await screenshot('preview-v2-desktop.png');
  await page('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await navigate('index.html');
  await waitFor('document.querySelector("#source-badge")?.textContent === "Python implementation"');
  await evaluate(`document.querySelector('#strategy').value='hash-priority'; document.querySelector('#count').value='1000'; document.querySelector('#generate').click();`);
  await waitFor('document.querySelector("#source-badge").textContent === "Browser simulation"');
  await evaluate('document.querySelector("#play").click()');
  await waitFor('document.querySelector("#metric-nodes").textContent === "1000" && document.querySelector("#play-label").textContent === "Replay"');
  assert.equal(await evaluate('document.querySelectorAll("#nodes .tree-node").length <= 12'), true);
  await evaluate('document.querySelector("#tree-stage").scrollIntoView()');
  await screenshot('preview-mobile.png');
  const overflow = await evaluate('[...document.querySelectorAll("body *")].filter(element => element.getBoundingClientRect().right > 391).slice(0,12).map(element => ({tag:element.tagName,id:element.id,className:String(element.className),right:element.getBoundingClientRect().right}))');
  assert.equal(await evaluate('document.documentElement.scrollWidth <= 390'), true, JSON.stringify(overflow));
  assert.deepEqual(exceptions, []);
  console.log(`Browser checks passed: colored trace replay, benchmark navigation/downloads, 10,000-key previews and mobile layout. Screenshots: ${artifacts}`);
} finally {
  socket?.close();
  browser.kill('SIGTERM');
}
