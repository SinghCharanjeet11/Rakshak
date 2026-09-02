# Rakshak — AI workflow

> Where AI is used today, where it may go next, and where it must never go.
>
> Companion to `01-architecture.md` (the membrane) and `08-status.md` (what is built).

---

## 0. The governing rule

Everything below is decided by one test:

> **Can this AI output change a PASS/FAIL?**
> If yes, it does not ship. If no, it is fair game.

That is not conservatism — it is the product. A verifier that can hallucinate its verdict has
nothing to sell. Every proposal in this document is arranged so the deterministic core stays
the only thing that decides, and every model output crosses the validation membrane before it
touches anything.

**The corollary matters just as much:** adding more AI does not make this project more
impressive to a panel that has seen fifty agent demos. What is unusual here is knowing where
*not* to put it. If asked "is the AI decorative?", the answer is the architecture, not a
longer feature list.

---

## 1. What AI does today

Three agents, all outside the verdict path. Two are code-complete and tested against a mocked
provider but have **never run against a live model** (see `08-status.md` FR2/FR6).

| Agent | Job | Touches a verdict? | State |
|---|---|---|---|
| `llm/ingestion_agent.py` | free text → `Action[]` | No — output crosses the membrane and is re-validated | built, mock-tested |
| `llm/explanation_agent.py` | decided `Violation` → prose + remediation | No — display text attached after the fact | built, mock-tested |
| `llm/scenario_gen.py` | rule-pack → synthetic test batches | No — its output is *input to be judged* | scaffolded, never run |

Provider access is confined to `llm/_provider.py`. Swapping model vendors is a one-file change,
and `core/` cannot import any of it — enforced by `tests/test_isolation.py`.

**What is already proven** (`tests/test_injection_e2e.py`): even a model that *fully obeys* an
injected instruction cannot produce a false PASS. It can deny verification — a compromised
parser can return nothing — but it cannot falsify one. That distinction is the honest version
of the claim and it is worth stating exactly that way.

---

## 2. Proposals, ranked

### ① Rule-pack authoring from regulation text — **do this one**

**What.** Paste a circular, an amendment, or a clause. The model proposes a rule entry in the
existing closed condition vocabulary. A human reviews the diff and commits it.

```
circular text ──▶ authoring agent ──▶ draft rule YAML
                                          │
                        ═══ MEMBRANE ═══  │  Rule.model_validate + closed-kind check
                                          ▼
                                  human review ──▶ committed rule-pack (deterministic data)
```

**Why it is the strongest option.**

- It answers the one real objection to a rule engine: *"who maintains this when RBI amends the
  framework?"* Right now the answer is "a person, by hand". With this, the answer is "the model
  drafts, a human approves, and the artifact stays deterministic."
- **It reuses the membrane in a second place.** The condition vocabulary is already a closed
  set of six kinds — a model that invents `kind: vibes_based_check` is *rejected at load*, by
  the same mechanism that rejects a hallucinated `Action`. That is the architecture's central
  idea demonstrated twice, on two different kinds of AI output. Very few projects can show
  their core pattern generalising.
- It attacks **OPEN-2** directly: the assistant can locate and quote the clause text for each
  of the 5 unverified values, so a human is verifying rather than hunting.
- It never touches a verdict. The output is *data that will later be applied deterministically*.

**Effort.** Moderate. New agent + prompt, a `POST /rules/draft` endpoint, and a review UI that
shows the proposed YAML beside the clause it came from. The validation half already exists —
`rules_loader.py` already rejects unknown kinds.

**Risk.** The model will confidently mis-encode a threshold. Mitigation is the point: the draft
is never auto-committed, and `value_verified: false` already exists as the field that says
"a human has not confirmed this number".

**What it proves on stage.** "When the regulator publishes an amendment, Rakshak drafts the
rule-pack diff and a compliance officer approves it. The rules stay deterministic data — the
AI just writes the first draft."

---

### ② Finish the adversarial scenario generator — **cheapest real win**

**What.** `llm/scenario_gen.py` already exists. Give it the rule-pack and ask for action
batches that probe under-tested rules, especially boundaries: one rupee under a threshold, one
minute short of a notice window, an exempt MCC with a second unrelated breach.

**Why.** It is AI used to **attack your own engine**, which is a much better story than AI used
to decorate it. It also produces a *measured* result, which the project currently lacks in this
area: "generated N scenarios, found these boundary cases, all now pinned by tests."

**Effort.** Low — the module and the JSON contract exist. Needs a runner, a way to persist
interesting cases into the seed corpus, and a report of rule coverage.

**Risk.** Low. Generated actions are inputs like any other; the engine judges them.

**Watch for.** If it finds a genuine bug, that is a *good* outcome and belongs in the pitch.
Do not quietly fix and hide it.

---

### ③ LLM injection classifier as a second signal

**What.** Today `scan_for_injection()` is a regex heuristic over eleven patterns. Add a model
classifier alongside it that scores an input for instruction-like content, and emit **both**
signals.

**Why.** Regex catches the phrasings we thought of. An unusual payload — base64, a foreign
language, a novel framing — walks past it. Emitting both makes the disagreement visible, which
is itself a useful signal.

**Effort.** Low–moderate.

**Constraint.** It stays a *signal*, never a gate. Nothing about it may block a run, because
the architecture does not need it to: the membrane and the non-agentic core already make a
successful injection unable to change a verdict. Turning it into a filter would add a failure
mode in exchange for nothing.

---

### ④ Natural-language query over stored reports

**What.** "Show me every AFA breach over ₹50,000 last month" → the model emits a **structured
filter object**, the filter is validated, and the query runs deterministically against the
store.

**Why.** Same membrane pattern a third time: NL → validated structure → deterministic
execution. Never NL → answer.

**Effort.** Moderate. **Value.** Good demo, less architectural weight than ①.

---

### ⑤ Agent behaviour profiling

**What.** Across many runs for one tenant, summarise how an agent's behaviour is drifting —
"retry attempts rose after v3; quiet-hours breaches began appearing on 12 Aug."

**Why.** Moves Rakshak from per-batch verdicts toward monitoring a fleet of agents over time,
which is the larger product. Prose over statistics the deterministic layer computed.

**Effort.** Higher — needs the aggregation layer first. **Not for the buildathon.**

---

## 3. Explicit non-goals

Naming these is part of the pitch. Each is a plausible-sounding idea that would make the
product worse.

| Non-goal | Why not |
|---|---|
| **An LLM that decides compliance** | The thesis. A judging system that hallucinates its judgment is worthless. |
| **A multi-agent "judge panel" that votes** | Three models agreeing is not determinism — it is three chances to be wrong, at triple the cost, with no citation. |
| **RAG over the circular for verdicts** | A threshold is not probable. ₹15,000 is ₹15,000. RAG retrieves likely text for a model to interpret — precisely the failure mode this design removes. The rule-pack is a versioned artifact, not a corpus. See the note below. |
| **Autonomous remediation** (the agent fixes itself) | Track 02 is defence-only. Rakshak reports; something else acts. |
| **Fine-tuning a compliance model** | Would move the law into weights — unciteable, unversionable, unauditable. The opposite of the product. |
| **Streaming token UI** | Irrelevant to a batch verifier; complexity for show. |

### On RAG specifically

It will be asked, so have the answer ready. RAG is the right tool when a corpus is too large to
fit in context and approximate retrieval is acceptable. Neither holds here: the rule-pack is six
rules in two YAML files, and "approximately the right threshold" is a wrong verdict. Where the
circular's actual text *is* wanted — next to a citation in the report — the right implementation
is a `clause_text` field in the rule-pack: versioned with the rule, quoted verbatim, and unable
to drift from what the engine applied.

---

## 4. Recommended sequence

Nothing here should start before the blocked items in `08-status.md` — a beautiful AI feature
on top of unverified regulatory values is worth less than one verified threshold.

1. **Prove what exists.** Add a key, run the free-text path and `injected_log.txt` against a
   live model once. Converts FR2/FR6 from claims into demonstrations. *(Hours.)*
2. ~~**Settle OPEN-1**~~ — **CLOSED 2026-09-02: OpenAI, deliberately not the Agent SDK.** The pitch now
   states that as a design decision. (Original note follows.) The pitch cannot claim the SDK while the
   code calls OpenAI, and a technical panel will read the repo.
3. **② Scenario generator.** Cheap, already scaffolded, produces a measurable result.
4. **① Rule-pack authoring.** The flagship. Build it only if there is real time left, and build
   the *review* step first — a draft nobody checks is worse than no draft.
5. **③ Injection classifier** if time allows.
6. ④ and ⑤ are post-buildathon.

---

## 5. How to talk about it

If asked *"where is the AI?"*:

> "In three places, all deliberately outside the verdict. It turns messy free-text logs into
> structured actions, it explains violations after they are decided, and it red-teams our own
> rule engine by generating adversarial batches.
>
> What it never does is decide compliance. That is pure, versioned, deterministic code — and
> that is enforced by a test that walks the AST of every core module and fails the build if one
> of them so much as imports a model.
>
> The interesting engineering here isn't adding AI. It's the membrane that lets us use AI on
> messy reality without ever letting it near the verdict."
