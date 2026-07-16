'use strict';

// ── Ad-hoc CONFIG-DRIVEN multi-step login probe (throwaway — NOT the repo) ────
// Walks a multi-PAGE login (sketch: page1 username+password+"Log in" → page2
// email+Enter → page3 password+Enter → page4 Submit → wait for the Account view)
// entirely from a YAML config. Each step names ONE control by a selector, an
// optional value to type, and an action (enter | click | none). Steps run in
// order; the runner WAITS for each step's control to appear (up to a timeout),
// so page transitions and dynamically-generated forms are handled automatically.
//
// It searches EVERY frame (main doc + nested iframes), because a portal often
// renders the login form inside an <iframe>.
//
// This is a STANDALONE script — its only dependencies are `playwright` and
// `js-yaml`. Install them once in this folder:
//   npm install                 # if you have the package.json next to this file
//   # …or explicitly:
//   npm install js-yaml playwright && npx playwright install chromium
//
// Usage:
//   node run-login-flow.js login-flow.yaml
//   node run-login-flow.js login-flow.yaml --probe   # just dump the first page
//
// Secrets: put values straight in the config file (chmod 600 it). A value of
// "env:VAR" reads from an env var instead; mark a step `secret: true` so its
// value is never echoed in the run log.

const path = require('path');
const fs = require('fs');
const readline = require('readline');

// Lazy terminal prompt — for `pause` steps (finish MFA by hand, then Enter) and
// `prompt:` values (type an OTP at runtime so it's never in the config/env).
let _rl = null;
const rl = () => (_rl = _rl || readline.createInterface({ input: process.stdin, output: process.stdout }));
const ask = (q) => new Promise((res) => rl().question(q, (a) => res(a)));

// ── Dependencies — resolved from THIS folder's node_modules ───────────────────
// Node resolves a bare require() from node_modules walking up from this file, so
// `npm install` in this directory (or any parent) is all that's needed.
function need(mod) {
  try { return require(mod); }
  catch {
    console.error(`\n✗ Missing dependency "${mod}". Install the two deps in this folder, then re-run:\n` +
      `    npm install js-yaml playwright\n` +
      `    npx playwright install chromium\n`);
    process.exit(2);
  }
}
const { chromium } = need('playwright');
const yaml = need('js-yaml');

const cfgPath = process.argv[2];
const PROBE_ONLY = process.argv.includes('--probe');
if (!cfgPath) {
  console.error('Usage: node run-login-flow.js <config.yaml> [--probe]');
  process.exit(2);
}
const cfg = yaml.load(fs.readFileSync(cfgPath, 'utf8')) || {};

// The config holds plaintext credentials now — warn if others can read it.
try {
  const mode = fs.statSync(cfgPath).mode & 0o777;
  if (mode & 0o077) console.warn(`[warn] ${cfgPath} is accessible by group/others (mode ${mode.toString(8)}) but holds plaintext passwords. Run: chmod 600 ${cfgPath}`);
} catch { /* best-effort */ }
const OUT_DIR = process.env.PROBE_OUT || process.cwd();
const STEP_TIMEOUT = cfg.stepTimeoutMs || 20000;

// ── Selector spec → a per-frame locator factory ──────────────────────────────
// Forms: id:X · type:X (input[type=X]) · name:X · testid:X · text:X · css:<raw>.
// A bare string with no prefix is treated as raw CSS.
function locatorFactory(spec) {
  const s = String(spec);
  const i = s.indexOf(':');
  const kind = i > 0 ? s.slice(0, i) : 'css';
  const val = i > 0 ? s.slice(i + 1) : s;
  switch (kind) {
    case 'id': return (f) => f.locator(`[id="${val}"]`);
    case 'type': return (f) => f.locator(`input[type="${val}"]`);
    case 'name': return (f) => f.locator(`[name="${val}"]`);
    case 'testid': return (f) => f.locator(`[data-testid="${val}"]`);
    case 'text': return (f) => f.getByText(val, { exact: false });
    case 'css': default: return (f) => f.locator(val);
  }
}

// Poll EVERY frame until the spec resolves to a visible element (dynamic render
// + iframes), mirroring sendcmd's findClickable/fillField. Returns the locator
// (already .first()) or null on timeout.
async function findInAnyFrame(page, spec, { timeout = STEP_TIMEOUT } = {}) {
  const make = locatorFactory(spec);
  const deadline = Date.now() + timeout;
  let announced = false;
  do {
    for (const frame of page.frames()) {
      let el;
      try { el = make(frame).first(); } catch { continue; } // frame detached
      if (await el.isVisible().catch(() => false)) return el;
    }
    if (!announced) { console.log(`      · waiting for ${spec} (all frames)…`); announced = true; }
    await page.waitForTimeout(250);
  } while (Date.now() < deadline);
  return null;
}

async function resolveValue(step) {
  const v = step.value;
  if (v == null) return null;
  const s = String(v);
  if (s.startsWith('env:')) {
    const name = s.slice(4);
    const got = process.env[name];
    if (got == null || got === '') {
      console.error(`   ✗ step "${step.name}": env var ${name} is unset. Run: export ${name}='…'`);
      process.exit(3);
    }
    return got;
  }
  // prompt:Message — read the value from the terminal at runtime (OTP / MFA
  // code). Kept out of the config and env by design.
  if (s.startsWith('prompt:')) {
    const msg = s.slice('prompt:'.length) || `Enter value for "${step.name}"`;
    return (await ask(`   ⌨  ${msg}: `)).trim();
  }
  return s;
}

// Dump the candidate inputs/buttons across all frames — shown when a step's
// selector misses, so you can read off the real id/type and fix the config.
async function dumpCandidates(page, tag) {
  const collect = () => {
    const vis = (el) => {
      const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none';
    };
    const at = (el, n) => el.getAttribute(n) || '';
    const inputs = [...document.querySelectorAll('input,textarea,select')]
      .filter((e) => e.type !== 'hidden' && vis(e))
      .map((e) => ({ tag: e.tagName.toLowerCase(), type: e.type || '', id: at(e, 'id'), name: at(e, 'name'), fc: at(e, 'formcontrolname'), testid: at(e, 'data-testid'), ph: at(e, 'placeholder') }));
    const buttons = [...document.querySelectorAll('button,a,[role="button"],input[type="submit"],input[type="button"],div.title')]
      .filter(vis)
      .map((e) => ({ tag: e.tagName.toLowerCase(), text: (e.innerText || e.value || '').trim().slice(0, 60), id: at(e, 'id'), testid: at(e, 'data-testid') }))
      .filter((b) => b.text || b.id || b.testid);
    return { url: location.href, title: document.title, inputs, buttons };
  };
  console.log(`\n══ candidates on ${tag} ══════════════════════════════`);
  for (const frame of page.frames()) {
    const d = await frame.evaluate(collect).catch(() => null);
    if (!d || (!d.inputs.length && !d.buttons.length)) continue;
    const where = frame === page.mainFrame() ? 'main document' : `iframe ${frame.url()}`;
    console.log(`  ── ${where}  (${d.url})`);
    for (const i of d.inputs) {
      const best = i.id ? `id:${i.id}` : i.name ? `name:${i.name}` : i.fc ? `css:[formcontrolname="${i.fc}"]` : `type:${i.type}`;
      console.log(`     input type=${i.type} ${i.ph ? `ph=${JSON.stringify(i.ph)} ` : ''}→ selector: "${best}"`);
    }
    for (const b of d.buttons) {
      const best = b.testid ? `testid:${b.testid}` : b.id ? `id:${b.id}` : `text:${b.text}`;
      console.log(`     ${b.tag} text=${JSON.stringify(b.text)} → selector: "${best}"`);
    }
  }
  const file = path.join(OUT_DIR, `login-probe-${tag.replace(/\W+/g, '_')}.json`);
  const record = [];
  for (const frame of page.frames()) {
    const d = await frame.evaluate(collect).catch(() => null);
    if (d) record.push({ frame: frame === page.mainFrame() ? 'main' : frame.url(), ...d });
  }
  fs.writeFileSync(file, JSON.stringify(record, null, 2));
  console.log(`   📄 ${file}`);
}

// Wait until some frame's visible body text contains the success phrase.
async function waitForSuccess(page, phrase, timeout = 30000) {
  const re = new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i');
  const deadline = Date.now() + timeout;
  do {
    for (const frame of page.frames()) {
      const txt = await frame.evaluate(() => document.body ? document.body.innerText : '').catch(() => '');
      if (re.test(txt)) return true;
    }
    await page.waitForTimeout(400);
  } while (Date.now() < deadline);
  return false;
}

(async () => {
  const browser = await chromium.launch({ headless: false, args: ['--start-maximized'] });
  const context = await browser.newContext({ viewport: null });
  const page = await context.newPage();

  console.log(`Opening ${cfg.startUrl} …`);
  await page.goto(cfg.startUrl, { waitUntil: 'domcontentloaded' }).catch((e) => console.warn('goto:', e.message));
  await page.waitForTimeout(1000);

  if (PROBE_ONLY) {
    await dumpCandidates(page, 'start');
    console.log('\n--probe: dumped the first page only. Remove --probe to run the full flow.');
    await page.waitForTimeout(1500);
    await browser.close();
    return;
  }

  let ok = true;
  for (const [n, step] of (cfg.steps || []).entries()) {
    const tag = `${n + 1}/${cfg.steps.length} ${step.name || step.selector || step.waitFor || 'pause'}`;
    console.log(`\n▶ step ${tag}`);

    // waitFor step — NO terminal input. You do the OTP/MFA in the BROWSER; the
    // runner just watches until the page that appears AFTER it shows up (its
    // selector/text becomes visible), then continues. Give it a long timeout so
    // there's time to fetch and type the code by hand.
    if (step.waitFor) {
      const to = step.timeoutMs || 180000;
      console.log(`   ⏳ enter the OTP/MFA in the BROWSER — waiting (up to ${Math.round(to / 1000)}s) for ${JSON.stringify(step.waitFor)} …`);
      const seen = await findInAnyFrame(page, step.waitFor, { timeout: to });
      if (seen) { console.log('   ✓ next page detected — continuing'); await page.waitForTimeout(step.waitMs || 300); continue; }
      if (step.optional) { console.log('   • optional wait — not seen, continuing'); continue; }
      console.error(`   ✗ ${JSON.stringify(step.waitFor)} never appeared`);
      await dumpCandidates(page, `waitfor-miss-${n + 1}`);
      ok = false; break;
    }

    // Pause step (or any step with pause: true) — hold for a manual action
    // (approve MFA in the browser, read an OTP off your phone), then continue
    // when you press Enter here. `expect:` optionally waits for the resulting
    // page instead of a keypress (whichever you prefer).
    if (step.action === 'pause' || step.pause) {
      const msg = step.message || 'Complete the MFA/OTP step in the browser';
      if (step.expect) {
        console.log(`   ⏸  ${msg} — waiting for ${JSON.stringify(step.expect)} to appear (or press Enter to force-continue)…`);
        const raced = await Promise.race([
          waitForSuccess(page, step.expect, step.timeoutMs || 120000).then((r) => (r ? 'found' : 'timeout')),
          ask('').then(() => 'enter'),
        ]);
        console.log(raced === 'found' ? '   ▶ detected — continuing' : '   ▶ continuing');
      } else {
        await ask(`   ⏸  ${msg}, then press Enter here to continue… `);
      }
      // A pause step may still name a field to fill AFTER the wait (e.g. type an
      // OTP once the OTP page is up); if it has no selector, it's a pure pause.
      if (!step.selector) { await page.waitForTimeout(step.waitMs || 300); continue; }
    }

    const el = await findInAnyFrame(page, step.selector, { timeout: step.timeoutMs || STEP_TIMEOUT });
    if (!el) {
      if (step.optional) { console.log('   • optional — not found, skipping'); continue; }
      console.error(`   ✗ selector not found: ${step.selector}`);
      await dumpCandidates(page, `miss-step-${n + 1}`);
      await page.screenshot({ path: path.join(OUT_DIR, `login-probe-miss-${n + 1}.png`), fullPage: true }).catch(() => {});
      ok = false;
      break;
    }
    const value = await resolveValue(step);
    if (value != null) {
      await el.fill(value, { timeout: 5000 }).catch(async () => { await el.click().catch(() => {}); await el.type(value); });
      console.log(`   ✓ filled ${step.secret ? '(secret hidden)' : JSON.stringify(value)}`);
    }
    const action = step.action || (value != null ? 'none' : 'click');
    if (action === 'enter') { await el.press('Enter'); console.log('   ↵ pressed Enter'); }
    else if (action === 'click') { await el.click(); console.log('   ✓ clicked'); }
    await page.waitForTimeout(step.waitMs || 800);
  }

  if (ok) {
    const phrase = cfg.successText || cfg.successSelector || 'accounts view';
    console.log(`\n⏳ waiting for the Account view (body contains ${JSON.stringify(phrase)})…`);
    const reached = await waitForSuccess(page, phrase, cfg.successTimeoutMs || 30000);
    console.log(reached ? '\n✅ Account view reached — the flow works.' : '\n⚠ Did not detect the Account view within the timeout.');
    if (!reached) await dumpCandidates(page, 'after-submit');
    await page.screenshot({ path: path.join(OUT_DIR, 'login-probe-final.png'), fullPage: true }).catch(() => {});
    console.log(`   📸 ${path.join(OUT_DIR, 'login-probe-final.png')}`);
  }

  console.log('\nBrowser left open — inspect, then press Ctrl+C to close.');
  await new Promise(() => {});
})().catch((e) => { console.error(e); process.exit(1); });
