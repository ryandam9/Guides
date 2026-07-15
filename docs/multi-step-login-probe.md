# Config-Driven Multi-Step Login Probe (Playwright)

> **Scope:** A small, throwaway Playwright script that walks a **multi-page login
> flow** (username page → email page → password/OTP page → submit → landing view)
> entirely from a **YAML config**. Built to discover and prototype the selectors
> for a portal whose login differs page-to-page, before wiring anything into a
> larger automation.

Script: [`scripts/run-login-flow.js`](../scripts/run-login-flow.js) ·
Example config: [`scripts/login-flow.example.yaml`](../scripts/login-flow.example.yaml)

---

## 1. What it does

Some portals don't have a single login form — they walk you through several
pages, each with one field, sometimes inside an `<iframe>` or rendered
dynamically. This probe drives that flow from a config file so that adding,
reordering, or re-selecting a field is a **config edit, never a code change**.

For each step it:

1. **Searches every frame** (main document + nested iframes) and **polls until
   the control appears** — so late-rendered and iframed forms both work.
2. Optionally **types a value**, then does an **action** (`enter` / `click` /
   `none`).
3. Moves to the next step, which waits for *its* control — that's how the
   page-to-page transitions are handled.

At the end it waits for a **success signal** (text that only appears once you've
reached the landing/account view).

If a selector isn't found, it **dumps every candidate field and button on the
current page** (with a suggested selector for each) to the console and a JSON
file, plus a screenshot — so you can read off the real id/type and fix that one
line.

## 2. Requirements

Node.js and Playwright (with a browser installed):

```bash
npm install playwright
npx playwright install chromium
```

Run it from a checkout that has `playwright` and `js-yaml` in `node_modules`, or
point it at one:

```bash
SENDCMD_REPO=/path/to/a/checkout node scripts/run-login-flow.js login-flow.yaml
```

## 3. Config format

```yaml
startUrl: "https://YOUR-HOST/logon/…"
successText: "accounts view"     # body text that only appears once logged in
stepTimeoutMs: 20000             # how long to wait for each step's control

steps:
  - name: username
    selector: "id:username"      # selector forms below
    value: "your.username"       # literal value, right here in the file
  - name: password
    selector: "type:password"
    value: "your-password"
    secret: true                 # never echoed in the run log
  - name: log-in
    selector: "css:div.title"
    action: click                # enter | click | none
```

### Selector forms

| Form | Resolves to | Use when |
| --- | --- | --- |
| `id:usernameBox` | `[id="usernameBox"]` | a stable id exists (preferred) |
| `type:email` | `input[type="email"]` | no id — match by tag + type |
| `name:email` | `[name="email"]` | the field has a `name` |
| `testid:accSubmit` | `[data-testid="accSubmit"]` | the app exposes test ids |
| `text:Log in` | control whose visible text is "Log in" | buttons/links by label |
| `css:div.title` | raw CSS, used as-is | anything else |

### Values

Put the literal value in the file (`value: "your.username"`). Add
`secret: true` so passwords aren't echoed in the run log.

> **The config holds plaintext passwords — keep it private:** `chmod 600
> login-flow.yaml`. The script warns at startup if the file is readable by
> group/others.

## 4. MFA / OTP

You complete the OTP **in the browser**; the script just **waits** for the page
that appears afterward — no terminal input:

```yaml
- name: mfa-wait
  waitFor: "type:submit"     # a control that only appears AFTER the OTP page
  timeoutMs: 180000          # generous — time to fetch and type the code
```

When the run reaches it, it prints `⏳ enter the OTP/MFA in the BROWSER —
waiting…`, polls every frame for that selector/text, and continues the instant
it's visible. `waitFor` accepts the same selector forms as everything else.

If you'd rather it hold for an explicit keypress instead, use a `pause` step:

```yaml
- name: mfa
  pause: true
  message: "Approve the MFA push, then press Enter here"
  # expect: "text on the next page"   # optional: auto-continue when it appears
```

## 5. Running it

```bash
chmod 600 login-flow.yaml
node scripts/run-login-flow.js login-flow.yaml

# just dump the first page's fields/buttons (no flow):
node scripts/run-login-flow.js login-flow.yaml --probe
```

The browser is left open at the end so you can inspect the result; press
`Ctrl+C` to close it. Screenshots and candidate-field JSON dumps are written to
the current directory (override with `PROBE_OUT=/some/dir`).

## 6. Notes

- **Iframes / dynamic forms:** handled — every step searches all frames and
  polls up to its timeout, the same way robust portal automations do.
- **This is a probe, not a product.** Once the selectors are dialed in, the
  natural next step is to translate the step list into whatever automation
  consumes it (the config is deliberately close to a declarative
  `login.steps[]` layout).
