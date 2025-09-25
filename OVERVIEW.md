# ClaudeControl Overview

ClaudeControl is a Python toolkit for understanding, validating, and automating command-line programs. It combines three long-standing strengths—investigation, testing, and automation—with a fourth pillar: deterministic record and replay of terminal sessions. Together these capabilities make it possible to tame unfamiliar CLIs, codify the workflows you discover, and then simulate them predictably in CI, development, or offline demos.

## Core Capabilities

### 1. Investigation 
ClaudeControl explores a target CLI to map out its behaviors:
- Launches sessions through `Session` helpers to capture prompts, inputs, and outputs automatically.
- Crawls built-in help, subcommands, and usage patterns.
- Infers state transitions, environment dependencies, and error pathways.
- Produces structured reports that document commands, options, and observed outputs so teams can learn a tool quickly.

### 2. Testing 
The testing layer hardens CLIs against regressions:
- Provides black-box tests that exercise startup/shutdown, error handling, and concurrency.
- Generates fuzz and performance scenarios with seeded randomness for reproducibility.
- Integrates with `pytest` so suites can be automated in CI.
- Supplies fixtures and helpers to mix live programs and recorded runs.

### 3. Automation 
Automation APIs orchestrate complex terminal workflows:
- The high-level `Session` abstraction wraps `pexpect` so scripts can `expect`, `send`, and synchronize with prompts.
- Patterns handle login sequences, pagination, and other interactive flows reliably.
- Recovery hooks detect timeouts or failures and re-establish state where possible.
- Automation pipelines can chain multiple CLIs, manage credentials, and coordinate parallel tasks.

### 4. Record & Replay 
New replay functionality mirrors Talkback’s tape model for terminals:
- Recorder segments live `Session` traffic into exchanges and persists JSON5 “tapes” with timing, prompts, and exit codes.
- Player streams recorded tapes back through the `Session` transport, optionally falling back to the real program when no match exists.
- Configurable record modes (`NEW`, `OVERWRITE`, `DISABLED`) and fallback policies (`NOT_FOUND`, `PROXY`) give teams control over authoring and CI safety.
- Matchers and normalizers compare program, arguments, environment, prompts, input payloads, and optional state hashes to select the correct exchange.
- Decorators, redactors, and naming hooks let teams customize tapes, scrub secrets, and enforce naming conventions.
- Latency profiles and probabilistic error injection simulate production-like timing or failure conditions during playback.
- Exit summaries highlight which tapes were created or went unused in a run, keeping tape libraries healthy.

## How It Works

### Architecture at a Glance
- **Session Transport** – Every `Session` is backed by a transport that can target a live `pexpect` child process or a replay `Player`, so existing APIs keep working whether you run live or from tape.
- **Replay Package** – The `claudecontrol.replay` package houses modes, tape models, stores, matchers, decorators, latency/error policies, recorders, players, and summaries. Tape data is stored as human-editable JSON5 with optional schema validation and file locking.
- **Tape Store** – A `TapeStore` indexes all tapes under a root directory, normalizes matching keys, and tracks usage for summaries.
- **Config & Hooks** – Global defaults live alongside the existing `~/.claude-control/config.json`; sessions accept overrides for record mode, fallback policy, tape paths, matchers, decorators, redactors, and latency/error policies.
- **CLI Integration** – The `ccontrol` CLI adds `rec`, `play`, and `proxy` subcommands for authoring tapes, running purely from tapes, or mixing replay with live fallbacks. Tape management commands support listing, validating, and cleaning recordings.

### Workflow Lifecycle
1. **Investigate** – Point ClaudeControl at an unfamiliar CLI to enumerate commands, prompts, and inputs.
2. **Test** – Use the testing harness to stress scenarios, capture regressions, and validate behavior.
3. **Record** – Enable recording mode to capture deterministic tapes of high-value workflows, with decorators and redactors ensuring clean artifacts.
4. **Replay** – Swap in playback mode to run fast, deterministic simulations in CI or demos without launching real binaries, while latency/error knobs emulate production edge cases.
5. **Automate** – Combine tapes and live sessions to build resilient automation that can rehearse flows offline and execute them for real when needed.

## Perfect For
- **Developers & DevOps** – Understand new CLI surfaces, create deployment automation, and gate releases with deterministic replays.
- **Security Professionals** – Reproduce tool behaviors, fuzz for vulnerabilities, and orchestrate repeatable offense/defense drills.
- **QA Engineers** – Automate regression suites against recorded sessions and mix in live runs when coverage gaps appear.
- **System Administrators** – Script legacy CLIs, sync cross-environment configurations, and rehearse change windows safely.
- **Data Engineers** – Automate database shells, ETL tools, and pipelines with confidence in both live and replayed environments.

## Philosophy
1. **Zero Configuration** – Sensible defaults get you running instantly, with tapes stored in sensible locations and replay disabled until requested.
2. **Safety First** – Fallback policies, redaction hooks, and tape summaries prevent accidental live runs or leaking secrets.
3. **Deterministic by Default** – Seeds, latency control, and error injection make tests predictable yet realistic.
4. **Human-Friendly Artifacts** – JSON5 tapes with annotations, decorators, and pretty-printed text are easy to inspect and review.
5. **Complete Coverage** – From investigation through replay, every stage of working with CLIs is handled in one cohesive library.

ClaudeControl unifies discovery, testing, automation, and replay so teams can master complex command-line ecosystems end to end.
