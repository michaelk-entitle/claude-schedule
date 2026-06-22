# Making `/schedule` seamless — lessons + design

Purpose: turn the live session below into a concrete plan so a user who installs the
plugin can say *"run X every weekday at 9am"* and have it **just work** — no `pip install`,
no CLI by hand, minimal prompts, and an honest story for the one truly-privileged step (wake).

---

## 1. What actually went wrong this session (the friction log)

Every item here is a real snag we hit, in order:

1. **`/schedule` ran the *cloud* workflow.** Typing `/schedule` loaded the cloud-routines
   skill and opened a 4-option modal. The repo *intends* to steer to local, but the steer
   is documentation, not behavior — the cloud flow still drove the conversation.
2. **The request was sub-hourly ("every 5 min").** Cloud rejects `<1h`; the local CLI is
   **clock-time only** (`--time HH:MM`, no interval). The user got bounced between tools
   across *three* modals before anyone said "this combination isn't supported anywhere."
3. **Cloud can't touch local files.** The goal was a file in `~/Projects`. Cloud agents run
   in a throwaway sandbox — a fact that should have routed us to "local" instantly.
4. **The CLI wasn't installed.** Plugin installed ≠ engine installed. The status hook said
   *"claude-schedule not installed"* and we had to `pipx install` from source by hand. This
   is the single biggest "user had to do something" moment.
5. **Wake needed `sudo`.** Real wake-from-sleep means arming the macOS wake slot, which needs
   root. We printed the command; the user ran it.
6. **This is a *managed* Mac (BeyondTrust EPM).** The prompt the user hit was the corporate
   **"Confirm Operation" Yes/No**, not a Unix password. A local `sudoers` `NOPASSWD` rule
   *cannot* suppress that — it's central policy. The harness also (correctly) blocked us from
   writing a `sudoers` file at all.
7. **Too many round-trips.** Three `AskUserQuestion` modals fired before a single action.
   Seamless means *infer and act*, confirm once.

**The throughline:** none of these were caused by Python existing. They were caused by
*routing*, *bootstrap*, and *the wake privilege* — all UX/packaging problems.

---

## 2. Goal

Installing the plugin should be the only step. After that:

- `/schedule` (and natural-language "run … every …") is intercepted by **one skill** that
  loads on invocation and does the work behind the scenes.
- The user answers at most one question (usually just a timeout), and the job is installed.
- No separate install step, no CLI typed by hand.
- The one unavoidable privileged step (wake) is handled honestly, and **skipped by default**
  so the common case needs *zero* privileged actions.

---

## 3. Design: the skill *is* the wrapper

### 3.1 Trigger
The skill activates when the user invokes `/schedule`, types `/loop` with a recurring
schedule, asks in natural language ("every weekday at 9am…"), or the `CronCreate` hook fires.
On activation it runs the **classifier** below *before* asking anything.

### 3.2 Classifier (do this first, silently)
Route on the request itself — this kills snags #1–#3:

| Signal in the request | Route | Why |
|---|---|---|
| Interval `< 1h` (`every 5 min`, `*/15`) | **`/loop`** (session) or **plain cron** (persistent) | Neither cloud nor the local engine does sub-hourly *by design*. Say so once, offer cron one-liner, stop. |
| Touches a **local path / repo / local MCP** | **local job** | Cloud sandbox can't reach the user's disk. |
| Pure remote analysis, `≥1h`, no local deps | **cloud routine** *or* local | Either works; default local unless the user wants cloud. |
| Clock-time, persistent, local | **local job** (the happy path) | This is what the engine is for. |

Echo the routing decision in one line ("This is local + sub-hourly → cron, not a Claude
job"), don't open a modal to ask which tool.

### 3.3 No engine to bootstrap (kills snag #4)
**Decision: Option B — pure skill, no runtime.** There is nothing to install: the skill emits
the OS artifact directly from Bash per `SKILL.md`. Plugin installed = ready. This deletes the
`pip install` step that was the biggest "user had to do something" moment.

### 3.4 Execute with minimal confirmation (kills snag #7)
Infer name (from the prompt), repo (cwd), days/time (from the phrasing), model (default),
permission-mode (`auto`). Ask **only** what can't be inferred and matters — realistically
just the **timeout** (and only if the user didn't say). Then install and report.

### 3.5 Wake & managed machines — be honest, default to no-wake (kills snags #5–#6)
- **Hard requirement: arm the wake ONCE, never per run.** Wake permission is requested a
  single time at setup and that's it — no `sudo` and no prompt on any subsequent scheduled
  run. This falls out of using `pmset repeat wakeorpoweron`, which is a *repeating* wake: one
  arm covers every future run at that time, and the runs themselves never touch a privileged
  command. The per-run path must stay 100% sudo-free; if a design ever needs root at fire
  time, it's wrong.
- The **only** time a second prompt is acceptable is when the user *changes the wake time*
  (the single macOS slot must be re-armed). The skill must not re-prompt for anything else —
  adding more jobs at the same time reuses the existing slot silently.
- **Default `--no-wake`.** Most users either leave the machine awake or only sleep the
  display; launchd/systemd `Persistent` catch-up covers the rest. Zero privileged steps.
- Offer wake-from-sleep as an **opt-in** ("want it to wake the machine? that's one `sudo` you
  run once, never again").
- **Detect a managed Mac** (BeyondTrust EPM / Jamf / an MDM profile). If present, warn that
  the privileged prompt is *corporate policy*, a local `sudoers` rule won't silence it, and
  the real fix is asking IT to whitelist `pmset repeat`.
- **Never** write `sudoers` or run the privileged command for the user. Print it; they run
  it (the harness enforces this, and it's the right boundary).
- Remember: the macOS wake slot only needs re-arming when the **time changes**. Same-time
  jobs reuse the existing slot → no re-prompt. The skill should know this and not re-ask.

---

## 4. Chosen scope — Option B, pure skill (and what it deliberately drops)

A pure-skill engine only stays robust if it's a **small correct subset**, not a full
reimplementation. The Python engine handled fiddly cross-platform/wake-union/timeout logic;
re-doing all of that in Markdown-driven Bash would be fragile. So B is scoped hard:

**In scope (the happy path):**
- **One backend: macOS `launchd`.** Emit a LaunchAgent plist with `StartCalendarInterval`
  (hour/minute/weekday) and `launchctl bootstrap gui/$UID` to load it.
- **One shape: clock-time daily/weekly.** No intervals (sub-hourly already routes to
  cron/`loop` in §3.2).
- **`--no-wake` by default.** No `pmset`, no `sudo`, no managed-Mac prompt in the common case.
- **Keep-awake during the run** via stock `caffeinate -i` wrapping `claude -p`.
- **Timeout** via a pure-shell guard embedded in the plist's command
  (`claude … & pid=$!; (sleep N; kill $pid) & wait $pid`) — no `timeout`/`gtimeout` dep
  (neither is stock on macOS).
- Log to a file; expose **run-now** as a manual smoke test (§5.5).

**Explicitly out of scope** (say so; don't half-build it):
- Linux/systemd and Windows/schtasks — `launchd` only for now.
- Wake-from-sleep — opt-in only, and only by **printing** the one `sudo pmset` command for
  the user to run; never automated, never via a `sudoers` rule.
- The multi-job wake-slot *union* — only relevant once wake is in scope.

> ponytail: the lazy win is deleting the *install step* (done — no runtime) and refusing to
> rebuild the parts that earned the Python engine its complexity. A small launchd-only skill
> that always works beats a cross-platform one that sometimes does.

---

## 5. Concrete next steps (Option B)

1. **Write the launchd plist template** the skill fills in: `StartCalendarInterval` from the
   parsed time/days, command = `caffeinate -i` + the timeout-guarded `claude -p`, log path.
   Load with `launchctl bootstrap gui/$UID <plist>`. Removes snag #4 (nothing to install).
2. **Fold the classifier (§3.2) into `SKILL.md`** so `/schedule` routes
   local/cloud/cron/loop itself — removes snags #1–#3 and most of the modals.
3. **Default no-wake**; gate wake behind an explicit opt-in that *prints* the `sudo pmset
   repeat` command **once** (it's a repeating wake — that single arm covers all future runs;
   scheduled runs are sudo-free), with the managed-Mac (EPM) warning. Re-prompt only on a
   wake-time change. Removes snags #5–#6 from the default path.
4. **Reduce to one question** (timeout) by inferring name/repo/days/time/model from the
   request — snag #7.
5. **run-now smoke test:** the skill should immediately trigger the new job once
   (`launchctl kickstart -k gui/$UID/<label>`) and tail the log to prove it works — this was
   the one part of the session that went perfectly; preserve the behavior.
6. **Leave a calibration knob:** clock drift / DST / a laptop that was fully off at fire time
   all bite real schedules. Set `StartCalendarInterval` to fire and rely on launchd catch-up;
   document that fully-powered-off Apple Silicon can't self-start (sleep only).
