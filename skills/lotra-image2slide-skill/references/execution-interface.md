# Current-task execution

All paths below identify the selected project and its registered task. Discover
the supported interpreter and prepare the offline companion once; reuse the
hash-verified project runtime with `run_lotra.py`. See runtime-readiness.md.

```
PYTHON SKILL/scripts/run_lotra.py --project PROJECT start ORIGINAL --name TASK
PYTHON SKILL/scripts/run_lotra.py --project PROJECT next TASK_PATH
PYTHON SKILL/scripts/run_lotra.py --project PROJECT submit TASK_PATH RESULT_JSON
PYTHON SKILL/scripts/run_lotra.py --project PROJECT context-control TASK_PATH resume --out TASK_PATH/scratch/Resume.json
PYTHON SKILL/scripts/run_lotra.py --project PROJECT context-control TASK_PATH status --out TASK_PATH/scratch/Context.json
PYTHON SKILL/scripts/packet_detail.py TASK_PATH REF_PATH SHA256 FIELD --owner OWNER --purpose current_work
```

Use packet `action_references` for the applicable schema; agent-runtime.md
documents advanced operations. Inspect supplied original/current image roles
and exact source coordinates. Reply to the current packet with the complete
contract, never a reduced displayed field or fabricated blanket observation.

Managed selectors validate current dependency membership before body access.
Keep source hashes and all pagination continuations. `ALREADY_READ` provides
the retained reference; `--fresh` returns its body immediately. A repeated
request after that notice also returns the body, so unavailable platform
compaction signals cannot strand work. `context-control resume` validates
the saved state and actual source/artifacts and starts a new read epoch.
It neither closes pending work nor resets a failed quality check.

`context-control TASK_PATH history --request REQUEST --out RESULT` accepts
`{"task_id":"previous-task"}` only when that registered task has the exact
same unchanged original. This is explicit lineage, never a semantic-name
search. Current original child identification and instance checks still apply.
Qualified public constructors contain no source-specific artifact or PASS.

Batch independent checks within one registered task when useful:

```
PYTHON SKILL/scripts/run_lotra.py --project PROJECT batch TASK_PATH --request TASK_PATH/scratch/Batch.json --out TASK_PATH/scratch/Batch-result.json
```

The request has `operations:[{id,argv,depends_on?}]`; `argv` starts with a
supported command and the absolute current task path. See
`config/context-policy.json` and `scripts/core/batch_runtime.py` for supported
finite operations. Output paths must be new task scratch files. Each action
keeps its existing lock, contract and validator; a failed dependency remains
pending. The batch receipt is not whole-result acceptance.

Repeat rejection means inspect the located cause or supply changed evidence,
not resubmit identical invalid input. `context-control attempt` can record a
hash-bound ineffective strategy; it never closes the task. Transient host
failures remain retryable. Continue feasible current `next` work until the
ordinary accepted quality-loop export or a documented external stop.

The package can enforce its managed readers, library searches and adoption.
Arbitrary host filesystem tools and transcript retention require host support;
do not claim that a skill physically intercepts those tools. Provider usage is
recorded by context-usage from actual service JSON, independently of local
read/output/time counters.

Use workflow-control plan/preflight/profile for the current-task repair agenda,
native parsing diagnosis and nonoverlapping command spans. See
[workflow optimization](workflow-optimization.md). All workflow and batch reports
use fresh current-task scratch paths. Batches validate every row before any
action, retain failure logs, and distinguish execution from domain/quality status.
Current packet contracts, per-object checks and final acceptance remain mandatory.
