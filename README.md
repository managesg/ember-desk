# Ember Council

**A strategy council for local businesses, built on your own files. Learn AI by doing your real work.**

Ask a real decision ("Should we raise cold brew prices again?"). The Chair reads your files and proposes who should sit. Role-based AI advisors then argue it out around the table: Michelin-level chef, local marketing expert, customer psychologist, food-cost & operations manager, finance advisor, plus investor and market-need seats. Every line cites your files. You get a scored verdict with next steps, and **Learn it** turns that verdict into a short AI lesson built on your own data.

Runs on **Muse Ember (`meta/muse-ember`) via OpenRouter**. Each advisor turn is one short, cheap call.

**Demo video (1 min, 1280x720, replayed from cache at $0):** [demo/ember_council_demo.webm](demo/ember_council_demo.webm) · [mp4](demo/ember_council_demo.mp4) · raw: https://github.com/managesg/ember-desk/raw/main/demo/ember_council_demo.mp4

## What it does

- **Roast-Room-style council table:** original 3D-cartoon role portraits in an arc. The flow runs Brief → Openings → Fault lines → Debate → Vote → Verdict.
- **Customise your council:** pick an industry, toggle the advisors, rename them, change their focus, or add your own.
- **Answers from your files:** price list, FAQ, reviews, sales CSV and inbox are packed with line numbers, and each claim cites `file Lx-y`.
- **Scored verdict + Learn it:** a decision score, next steps, and a 10-minute lesson that teaches AI using this very decision.
- **Voice:** ask by microphone, using the browser's local speech engine (works best in Chrome or Edge).
- **History:** every council is saved to `data/history/` and replays from **Past sessions**. Every model call is logged in `proof/council_log.jsonl`.
- **Live cost meter:** spend and call count are shown in the top bar, and **Proof** lists every generation id, its tokens and its cost.

## Any model, including local Meta models

Default: OpenRouter + `meta/muse-ember`. Any OpenAI-compatible endpoint works through three env vars, so it can run fully offline on a shop PC or a small device:

    # Ollama with a local Meta Llama model ($0 per call)
    set LLM_BASE_URL=http://localhost:11434/v1
    set LLM_MODEL=llama3.2
    set LLM_API_KEY=ollama

LM Studio and llama.cpp servers work the same way.

Or switch engines in the app: **Your council -> Engine** has *Muse Ember via OpenRouter* (default), *Muse Ember via Meta API* (`https://api.meta.ai/v1`, model `muse-ember-1.0`, key from `META_API_KEY`) and *Local Meta Llama* (Ollama on `http://localhost:11434/v1`, model `llama3.2`; first run `ollama pull llama3.2`). **Test engine** sends one short call and shows who answered. Tested tonight: OpenRouter answered in 1.8 s for $0.00016; Meta direct returned HTTP 403 because the only Meta key on this PC is a Muse Code subscription key, which Meta limits to the Muse Code client (a pay-as-you-go key is needed); the local server was running but without `llama3.2`, and the app says so instead of failing silently. Local calls show `$0 local` in the meter.

## Import a meeting (any recorder)

**+ Import a meeting transcript** (under the question box) takes a pasted transcript or a `.txt`, `.vtt`, `.srt` or `.md` file from Zoom, Teams, Otter, Fireflies, Google Meet or Recorder. Timestamps and cue numbers are stripped, speaker names are kept, and the owner can correct the text before adding it. It is saved as `data/meeting_<date>_<title>.txt`, so advisors cite it like any other file (`meeting_2026-11-09_team.txt L3-5`). Recorders and automations (Zapier, Make) can push the same thing with `POST /api/transcript {"title": "...", "text": "..."}`. Google Drive and Meet API connectors (OAuth) are next.

## History and logs

Every council is saved to `data/history/<session_id>.json`: question, industry, seated advisors, every turn with its checked citations, votes, verdict, engine and model, cost and timestamps. **Past sessions** replays them. One summary line per session, and every transcript import, goes to `logs/council_log.jsonl`.

## Run (Python stdlib only, no installs)

    set OPENROUTER_API_KEY=...        # only needed for questions that are not cached yet
    python server.py                  # http://127.0.0.1:8000  (env HOST, PORT, BUDGET_CAP)
    python record.py                  # replays the cache in Chrome via Playwright -> demo video

The key stays server-side and is never logged. A budget guard refuses calls once logged spend reaches the cap. Every response is cached in `cache/`, so the demo replays at $0.

## Proof ($1 Challenge)

| Item | Value |
|---|---|
| Model | `meta/muse-ember` via OpenRouter |
| Per-call log | `proof/council_log.jsonl`: generation id, model, provider, tokens, cost, latency |
| Council build + test spend | $0.0130 logged over 21 live calls (1 Chair proposal, 5 openings, fault lines, 5 rebuttals, draft, 5 votes, verdict, Learn it, plus one v0 call); ~$0.0006 per call, ~1.9-2.4k prompt tokens each |
| Key usage over the live run | `proof/council_key_before.json` -> `council_key_after.json`: +$0.0147 (key-level usage includes a little lag and rounding) |
| One full council | 19 calls, about $0.012; a cached replay costs $0 |
| Total for this account tonight (both projects, all tests) | about $0.13 of the $1 |
| Earlier Ember Desk log | `proof/openrouter_log.jsonl`, key snapshots `proof/key_before.json` / `key_after.json` |

Note: Muse Ember is a reasoning model. With a small `max_tokens` the hidden reasoning used up the budget and `content` came back empty. Setting `reasoning.effort=low` with more output tokens fixed it, and that wasted spend is included above. OpenRouter's key-level usage lags behind the per-call `usage.cost`, so the per-generation log is the authoritative number.

## Data and credits

- All business data is **SAMPLE DATA** (fictional Bluebird Coffee Roasters, `data/`, generated by `gen_data.py`).
- The advisors are role-based AI personas, **not real people**. The portraits are original.
- Table layout adapted from [Roast Room](https://github.com/nateherkai/roast-room) (MIT, © 2026 AI Automation Society). See `LICENSE` and `NOTICE`.

## Feedback

**Muse Ember:** strong at reading a whole small business in one cheap call and keeping citations grounded. Budget `max_tokens` for the hidden reasoning.
**OpenRouter:** `usage.include` made the live cost meter trivial. Key-level usage lags behind per-call cost.
