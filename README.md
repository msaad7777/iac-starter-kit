# IaC starter kit for AWS: FinOps and AI infrastructure

A free, opinionated starting point for teams adopting infrastructure as code on AWS, whichever way they arrive:

- **Greenfield:** no IaC yet. Agree tags, set up state, then build from tested modules with Terragrunt.
- **Brownfield:** resources were made by hand (ClickOps) or by old scripts. Discover them, import them with zero changes, then adopt them into the standard modules.

Cost control and GPU inference are built in, not bolted on. Kyverno policies check every Terraform plan before apply. A small RAG assistant answers questions about the kit and the tools it uses, with citations. A provisioning agent turns a plain-English request into a branch of Terragrunt units that has passed the same checks, for a person to review.

Everything runs locally against [Moto](https://github.com/getmoto/moto), a local AWS mock. **You need no AWS account, API key or paid service to try any of it**, and CI runs the same way.

| Tool | Used for |
|---|---|
| Terraform 1.11 | five tested modules (`terraform test` with mock providers) |
| Terragrunt 1.2 | dev and prod live layout, DRY provider, tags and state |
| Kyverno 1.20 | 5 policies on Terraform plan JSON, 3 on Kubernetes manifests |
| Terraform `import` blocks | brownfield discovery and adoption |
| Terraformer | bulk export, tested and documented (the project is archived) |
| Pulumi (Python) | the same secure bucket as a component, with unit tests on mocks |
| Trivy | misconfiguration scan in CI |
| LangChain, Chroma, Ollama | "Ask the kit" assistant, local models only |
| Ollama, gpt-oss:20b, `diagrams` | provisioning agent: request → units → gated branch, plan diagram and ADR draft |

## Architecture

![iac-starter-kit architecture: greenfield and brownfield ways in, modules and Terragrunt live config, the pull-request checks (Terraform tests, Trivy, plan JSON checked by Kyverno policies) and the local RAG assistant, with the measured results](docs/architecture.png)

<details>
<summary>Same diagram as text (Mermaid)</summary>

```mermaid
flowchart TB
    subgraph Paths["Two ways in"]
        G["Greenfield<br/>docs/greenfield.md"] --> M
        B1["Brownfield: discover.py<br/>read-only API calls → import blocks"] --> B2["terraform plan -generate-config-out<br/>→ reviewed config"]
        B2 --> B3["Adopt into modules<br/>import { to = module.x... }"]
        B3 --> M
    end

    subgraph Code["Code"]
        M["modules/<br/>tags · s3-bucket · network · budget · gpu-inference"]
        M --> L["live/ (Terragrunt)<br/>root.hcl: provider, default_tags, state<br/>dev/ prod/ units"]
        P["pulumi/<br/>SecureBucket component"]
    end

    subgraph CI["Every pull request (GitHub Actions)"]
        L --> T1["terraform fmt · validate · test<br/>(mock providers)"]
        L --> T2["Trivy config scan"]
        L --> T3["terragrunt plan → JSON<br/>(against Moto)"]
        T3 --> K["Kyverno: 5 plan policies<br/>tags · public S3 · IMDSv2 · GPU spend · NAT"]
        F["Non-compliant fixture plan"] --> K2["every policy must fire"]
        P --> T4["pytest with Pulumi mocks"]
    end

    subgraph RAG["Ask the kit (local)"]
        D1["kit files + OpenTofu, AWS provider,<br/>Terragrunt, Kyverno, Pulumi, Terraformer docs"] --> D2["Chroma + BM25"]
        D2 --> D3["hybrid retrieval → cross-encoder re-rank"]
        D3 --> D4["gpt-oss:20b via Ollama<br/>cited answer or decline"]
    end
```

</details>

## What's in the kit

### Modules (`modules/`)

| Module | What it does | Tests |
|---|---|---|
| `tags` | standard tag set with validation: `cost-center` must look like `CC-1234`, environment must be dev, staging or prod, extra tags can't override the standard keys | 4 |
| `s3-bucket` | public access blocked, bucket-owner ownership, SSE-S3 or KMS with bucket keys, versioning, lifecycle (Intelligent-Tiering after 30 days, old versions expire), TLS-only policy | 4 |
| `network` | VPC across 1–4 AZs, public and private subnets, NAT strategy `none`, `single` or `per_az`, free S3 and DynamoDB gateway endpoints, optional flow logs to S3 | 5 |
| `budget` | monthly AWS Budget filtered by cost centre, alerts at 80 % actual and 100 % forecast, optional Cost Anomaly Detection | 4 |
| `gpu-inference` | spot-first GPU Auto Scaling group across g6, g5 and g4dn, IMDSv2, encrypted gp3, optional office-hours scale-to-zero, tags that reach the instances | 6 |

All 23 tests use `mock_provider`, so `terraform test` needs no cloud credentials.

### Live layout (`live/`)

Terragrunt keeps the provider, default tags and state in one place (`root.hcl`). Each unit lists only what differs per environment:

| Unit | dev | prod |
|---|---|---|
| `network` | 2 AZs, one shared NAT gateway | 3 AZs, a NAT gateway per AZ |
| `assets-bucket` | old versions kept 14 days | old versions kept 90 days |
| `budget` | $300 a month | $2,000 a month plus anomaly detection |
| `llm-inference` | at most 1 GPU instance, scaled to zero outside 08:00–19:00 on weekdays | 1 on-demand instance always on, up to 4 |

State is local by default. `KIT_BACKEND=s3 KIT_STATE_BUCKET=<bucket>` switches to the S3 backend with native lock files (`use_lockfile`), so no DynamoDB table is needed.

### Policies (`policies/`)

Kyverno `ValidatingPolicy` resources. The Terraform ones read `terraform show -json` output, so they work on any plan, not only Terragrunt's.

| Policy | Checks |
|---|---|
| `require-finops-tags` | every taggable resource has `cost-center`, `owner` and `environment`; Auto Scaling groups propagate `cost-center` |
| `s3-block-public-access` | every bucket has all four public access block settings on |
| `require-imdsv2` | launch templates and instances require IMDSv2 tokens |
| `gpu-spend-guardrails` | GPU groups are at most 50 % on-demand above the base; dev GPU groups have a scale-to-zero schedule |
| `dev-nat-gateway-limit` | at most one NAT gateway outside prod |
| `require-cost-labels` (K8s) | workloads carry `cost-center` and `team` labels |
| `gpu-workload-guardrails` (K8s) | GPU requests equal limits; GPU pods go to spot nodes unless marked critical |
| `require-pinned-images` (K8s) | no `:latest` or untagged images |

CI checks both directions: all 8 dev and prod plans pass every policy, and a deliberately non-compliant plan (`policies/terraform/tests/noncompliant`) makes every policy fail. The Kubernetes policies have 15 `kyverno test` cases.

### Guides (`docs/`)

- [greenfield.md](docs/greenfield.md): tags first, state second, layout, rollout order.
- [brownfield.md](docs/brownfield.md): discover, import with zero changes, adopt into modules; Terraformer compared.
- [finops.md](docs/finops.md): cost defaults in the modules, budgets as code, policies that block waste.
- [ai-infrastructure.md](docs/ai-infrastructure.md): GPU inference on EC2 and guardrails for GPU workloads on Kubernetes.

## Brownfield, measured

`scripts/brownfield-demo.sh` seeds Moto with a "ClickOps" estate (a bucket, a VPC, a subnet and a security group with port 443 open to the world), then:

1. `discover.py` writes 4 import blocks, skipping the default VPC and default security groups.
2. Terraform's generated config is reviewed into `legacy.tf`. Plan: **4 to import, 0 to add, 0 to change, 0 to destroy.**
3. The bucket is adopted into the `s3-bucket` module. Plan: **1 to import, 6 to add, 1 to change, 0 to destroy.** The 6 additions are the hardening it was missing; the change is the FinOps tags.

The script fails if either summary changes, and CI runs it on every push.

Terraformer, run on the same estate, exported 14 resources instead of 4 (the default VPC, its 6 subnets and 2 default security groups came along), with names like `tfer--subnet-1bf5f134aebbf7561`. Details are in [brownfield.md](docs/brownfield.md).

## Agent: from a request to a reviewed branch

`agent/` turns a plain-English request into Terragrunt units built only from the kit's modules, runs the kit's own gates on them, and leaves a git branch with a PR description, a diagram drawn from the plan and a draft decision record. A person reviews it and merges. The agent never applies, and never talks to real AWS.

![kit-agent architecture: request, the model's tool loop, the plan and policy gates against a local AWS mock, then the fixed steps that draw the diagram, draft the ADR and commit a branch for human review](docs/agent-architecture.png)

```text
$ uv run kit-agent "Staging GPU inference for team llm-serving, all spot, at most 3 instances, budget \$1500."
outcome: pr
attempts: 1, model calls: 8, 237.7 s
branch: agent/staging-gpu-inference-for-team-llm-servi-3dc25d  (not pushed; PR body in ~/iac-starter-kit/agent/runs/staging-gpu-inference-for-team-llm-servi/pr-body.md)
```

The same request in eval run 4 produced this [PR body](agent/eval/results/examples-run4/pr-13/pr-body.md), [ADR draft](agent/eval/results/examples-run4/pr-13/0001-staging-gpu-inference-for-llm-serving.md) and [diagram](agent/eval/results/examples-run4/pr-13/0001-staging-gpu-inference-for-llm-serving.png).

### How it works

The pipeline is a fixed sequence in code. There is no coordinator model deciding what happens next:

1. **Request → units.** gpt-oss:20b (through Ollama, local) works through 9 tools: `list_modules`, `create_env`, `write_unit`, `delete_unit`, `read_unit`, `run_plan`, `run_policies`, `finish` and `refuse`. It can't run a shell, read other files or write anything except a unit.
2. **Gates.** `run_plan` calls `scripts/plan-json.sh` (Terragrunt plan against Moto) and `run_policies` calls `scripts/check-policies.sh` (the 5 Kyverno plan policies). If either fails, the model gets the errors back and fixes its units, with at most 3 plan runs.
3. **Diagram.** Code draws it from the plan JSON with the [`diagrams`](https://github.com/mingrammer/diagrams) library (MIT, needs Graphviz), never the model. Each resource block gets its own icon (×N when counted). Resources that only configure another one, such as bucket versioning or route table associations, are listed on their parent. Edges come from the references Terraform records in the plan, plus a dashed edge for each Terragrunt dependency.
4. **ADR draft.** `docs/adr/NNNN-<slug>.md`, MADR style, status **Proposed**. Code writes the facts: modules, add/change/destroy counts per unit, policy results and the diagram link. The model writes only the context, the options and the rationale, through one JSON-schema-constrained call.
5. **Branch and PR body.** Each request runs in its own git worktree, so your checkout is never touched. Only files under `live/` and `docs/adr/` can be committed. Nothing is pushed: opening the PR is your step.

The rules the model must follow are also enforced in code:

| Rule | Where it's enforced |
|---|---|
| Write only under `live/`, never `root.hcl` or `_envcommon/`, no symlink escapes | `safe_path` raises before any write |
| Only the kit's modules | an unknown module stops the run as a refusal |
| Only the module's real variables | unknown or missing variables go back to the model |
| `prod` needs the label `prod-approved` | a prod write without it stops the run |
| The budget is the amount the request states | `finish` is rejected otherwise; no stated amount stops the run |
| No invented ARNs or IDs | values like `arn:…`, `subnet-…` must appear in the request |
| A stated on-demand share is kept as asked | a GPU unit that changes it is rejected, so the policy gate or a refusal decides |
| `finish` only after both gates pass with nothing written since | checked in `finish` |
| Plans only against a local mock | the gate asserts `KIT_TARGET` is `moto` or `emulator` and the endpoint is local |

CI gets two new jobs. `agent` runs the 86 unit tests, which use a scripted fake model and need no Ollama. `adr-status` runs `scripts/check-adr-status.sh` and fails while any ADR the PR adds or changes is still Proposed, so the reviewer has to read it, name themselves and set it to Accepted before merging.

### Results

25 requests in [`agent/eval/requests.jsonl`](agent/eval/requests.jsonl): 14 valid ones and 11 that must be refused (public buckets ×2, no budget ×2, unknown modules ×3, prod with no approval label ×2, an explicit policy break ×2). Every branch is checked again from scratch: a fresh worktree, plan, policies, diagram coverage against that plan, and the ADR's facts against that plan. Model gpt-oss:20b, `think` low, temperature 0, `num_ctx` 4096, on an M4 laptop, with another job using the same Ollama server throughout. Every number comes from [`agent/eval/results/`](agent/eval/results).

Run 4, the final code (`run4.json`):

| Measure | Result |
|---|---|
| Valid requests that ended in a branch passing every gate | **12 of 14** (86%) |
| Bad requests refused | **10 of 11**, all by the model; the 11th failed without a branch |
| Bad requests that became a branch | 0 |
| Policy violations in a branch | **0** |
| Branches failing the fresh re-check | 0 |
| Plan attempts per branch | mean 1.0, max 2 across all requests; all 12 branches passed on the first attempt |
| Time per request | median 202 s, p90 283 s; branches median 238 s, refusals median 41 s |
| Model calls per request | mean 5.6; largest prompt 2,420 tokens |
| Diagram coverage | 182 of 182 planned resources shown (100%) |
| ADR facts that differ from the plan | 0 of 12 ADRs |
| ADRs left Proposed / with sections drafted by the model | 12 / 12 |
| Requests with an invalid tool call fed back to the model | 2 (both recovered) |

The 3 misses:

- **pr-05** (a GPU group that "should scale to zero outside office hours"): both gates passed, then the model wrote the PR title and reasons as prose 3 times instead of calling `finish`. The run stopped with no branch.
- **pr-10** (GPU inference for team vision): the model asked for a module called `llm-inference`, which is the name of an existing unit in `live/`, not a module. The guard stopped it as a refusal.
- **ref-11** (a prod budget with no approval label): the model gave the right reason but wrote `{"action": "refuse", ...}` as text 3 times instead of calling `refuse`. It failed safe, with no branch, but it isn't counted as a correct refusal.

All 4 runs side by side (the same 25 requests):

| Run | Valid → passing branch | Bad requests refused | Bad request → branch | Violations in branches | Median time |
|---|---|---|---|---|---|
| 1 | 12 / 14 | 11 / 11 | 0 | 0 | 94 s |
| 2 | 10 / 14 | 10 / 11 | 1 | 0 | 85 s |
| 3 | 11 / 14 | 9 / 11 | 0 | 0 | 184 s |
| 4 | 12 / 14 | 10 / 11 | 0 | 0 | 202 s |

Runs 3 and 4 were slower because another model job shared the Ollama server. Run 4 took 91 minutes in total.

### What failed, and what changed

The eval was run four times. The fixes between runs came from reading the failures, so the last run is not a blind test: treat it as a regression baseline.

- **Run 1: valid work refused after the gates passed** (pr-06, pr-07). The model replied in text, and the fallback nudge said "call a tool, or call refuse", so it refused. The nudge now depends on the state: once both gates pass with nothing written since, it says to call `finish`.
- **Run 2: valid requests refused for missing details** (pr-03 and pr-13 had no CIDR or zones; pr-09 was misread as prod). The prompt now gives network defaults and says a value the kit can default is never a reason to refuse.
- **Run 2: a stated requirement silently changed.** ref-07 asks for 100% on-demand GPUs, which breaks the 50% policy. The model quietly set 50% and opened a branch: the gates passed, but it wasn't what was asked. A guard now rejects a GPU unit whose on-demand share differs from the one the request states, so the policy gate or a refusal decides.
- **Run 3: Ollama HTTP 500s** (4 requests). The response body showed the cause: gpt-oss wrote invalid JSON inside a tool call (a stray quote), and Ollama failed to parse it. At temperature 0 a plain retry repeats it exactly. Now the error goes back to the model as a message, and the third one in a run stops it. In run 4, pr-14 and ref-07 both hit this once and recovered. Other 5xx errors get one retry after 5 s.
- **Not fixed:** the model sometimes writes a tool call as prose or in its own JSON shape (pr-05, ref-11 in run 4). Accepting more shapes would be tuning to this eval, so these stay safe failures with no branch.

During the build, before the eval:

- **The model invented a KMS key ARN** for a bucket and **turned on cost anomaly detection** in staging, which would have made a second anomaly monitor in an account that allows one. Both are now rejected in code, and the prompt says to leave variables unset unless the request asks.
- **Tool calls written as text.** gpt-oss sometimes replies with the tool call as a JSON object in its message instead of calling the tool. A reply that is exactly one JSON object naming a known tool is accepted and counted; anything else gets a nudge.
- **The ADR said the bucket had no encryption.** The kit's modules always encrypt. The ADR prompt now lists what each module does by default.

The model's ADR prose still needs a careful read. In the example above, one "option" raises the budget to $2,000, which the request rules out, and the model merged its consequences into one bullet. In run 3 the same request produced prose about a "Spot Fleet", but the module uses an Auto Scaling group. That's why ADRs start as Proposed and CI blocks the merge until someone accepts them.

### Diagram icons

Only AWS is exercised end to end. The kit has no GCP or Azure modules, so the `google_` → GCP and `azurerm_` → Azure icon mappings are unit-tested only.

- **AWS:** "We allow customers and partners to use these toolkits and assets to create architecture diagrams" ([AWS Architecture Icons](https://aws.amazon.com/architecture/icons/)).
- **Azure:** Microsoft "permits the use of these icons in architectural diagrams, training materials, or documentation" ([Azure architecture icons](https://learn.microsoft.com/en-us/azure/architecture/icons/)).
- **Google Cloud:** the [icons page](https://cloud.google.com/icons) offers them "for your diagrams, technical documentation, and more" but states no licence. Check it before publishing GCP diagrams.

## Ask the kit

`assistant/` is a RAG assistant over the kit's own files and the open-licensed docs of the tools it uses. It answers with numbered citations that link to the exact file, or declines when the sources don't cover the question.

```text
$ kit-assistant ask "How can the S3 backend lock state without a DynamoDB table?"
The S3 backend can lock state by using a lock file stored in the same bucket.
When `use_lockfile = true` is set, OpenTofu/Terraform performs conditional writes with an
`If-None-Match` header, creating a lock object in the bucket that protects the state file.
This native S3 locking mechanism removes the need for a DynamoDB lock table. [1][2]
  [1] IaC starter kit: docs/greenfield.md
  [2] OpenTofu docs: website/docs/language/settings/backends/s3.mdx

$ kit-assistant ask "What is the capital of Australia?"
The kit and the docs it indexes do not cover that question.
  (declined: retrieval_gate (top rerank score -11.18))
```

It uses the same pipeline as [mars-rag](https://github.com/msaad7777/mars-rag), and runs locally on free models:

- **Retrieval:** dense (bge-small through FastEmbed) and BM25 search, fused by reciprocal rank.
- **Re-ranking:** a cross-encoder picks the top 5.
- **Generation:** gpt-oss:20b through Ollama.
- **Three decline gates:**
  1. a low re-rank score;
  2. the model saying the context is insufficient;
  3. no valid citation.

What's different here:

- **Chunking follows the structure.**
  - Markdown is split by heading with a small custom splitter, because LangChain's header splitter strips the indentation that YAML and HCL examples depend on.
  - `.tf` and `.hcl` files are split at `resource`, `module` and `variable` blocks.
- **Citations point to files.** Each chunk keeps its repo, path and section, so `[2]` links to the exact doc at the pinned commit.

### Results

Measured on 33 answerable and 11 unanswerable questions. The corpus is 148 documents, split into 1,824 chunks. Every number comes from [`assistant/eval/results/`](assistant/eval/results).

| Metric | Result |
|---|---|
| RAGAS faithfulness | **0.960** |
| RAGAS context precision (with reference) | **0.825** |
| RAGAS context recall | **0.898** |
| Citation accuracy (cited passage supports the sentence) | **0.811** (53 citations checked) |
| Unanswerable questions correctly declined | **11 / 11** |
| Answerable questions wrongly declined | **2 / 33** (6.1 %) |
| Latency p50 / p95 (all 44 questions, M4 laptop) | 12.0 s / 20.7 s |

### Retrieval ablation (no LLM, top 5)

A hit means a gold document is in the top 5.

| Mode | Hit@5 | MRR@5 |
|---|---|---|
| Dense only | 0.879 | 0.730 |
| BM25 only | 0.939 | 0.733 |
| Hybrid (RRF) | **1.000** | 0.787 |
| BM25 + re-rank | 0.970 | 0.825 |
| Hybrid + re-rank (used) | 0.970 | **0.829** |

- Hybrid retrieval found a gold document for every question.
- Re-ranking pushed one Terragrunt document out of the top 5, but put the right document higher on average, raising MRR from 0.787 to 0.829.
- Dense retrieval alone missed 2 of the 10 questions about the kit's own files. BM25 matched exact names such as `use_lockfile` and `expose = true`.
- The re-ranker runs on CPU and is the slowest step: 4.2 s per query in this run, 1.6 s in the first run on the same machine.

### Declining

The retrieval gate (a re-rank score below -2.0) declined 5 of the 11 unanswerable questions without calling the model, and blocked no answerable question. The model itself declined the other 6, for example "How do I make Checkov skip a check?" and "What is the default Elastic IP quota?". Those questions are close to the corpus topics, but the corpus doesn't answer them.

A sweep of the gate threshold, from `retrieval.json`:

| Threshold | Answerable blocked | Unanswerable blocked |
|---|---|---|
| -4 | 0 % | 18 % |
| -2 (used) | 0 % | 45 % |
| 1 | 3 % | 55 % |
| 2 | 3 % | 64 % |

### What went wrong in the eval

- **The first run lost 5 answers to citation format.** gpt-oss sometimes cites in its native style, `【3】` or `【3†L5-L9】`. Gate 3 found no `[n]`, so it declined good answers: 6 of 32 answerable questions were wrongly declined in run 1. Those citations are now rewritten to `[n]` before the gates run, with a unit test. Run 2 is the one reported here.
- **One "unanswerable" question was answerable.** "How do I set up Azure Blob Storage as a Terraform backend?" was labelled unanswerable, but run 1 answered it from an `azurerm` example in the Terragrunt docs. It was moved to the answerable set (q33).
- **The 2 remaining wrong declines.**
  - The kit's own "plan without an AWS account" answer had no valid citation. The right files ranked first.
  - The time-zone format for `aws_autoscaling_schedule`: the right passage ranked second, but the model said the context was insufficient.

  Both are safe failures.
- **Citation accuracy is lower than mars-rag's** (0.811 against 0.919). Each cited sentence is checked on its own. Of the 10 citations judged unsupported, 4 are sentences that begin with "This…", which loses the subject from the previous sentence. Those 4 weren't checked by hand, so the number stands as measured.
- **The judge is noisy.** The same gpt-oss model generates the answers and judges them. It gave faithfulness 0.33 to "Cost Anomaly Monitors come in two main types: `DIMENSIONAL` and `CUSTOM`", which is copied almost verbatim from the cited doc. A separate judge model would be more trustworthy.
- **Small, hand-written test set.** The kit's author wrote the 33 questions; mars-rag's questions were drafted from chunks. Hybrid retrieval wins here and BM25 won there, so neither result generalises. Treat the numbers as a regression baseline, not a benchmark.

## Data sources and licences

The assistant downloads documentation at pinned commits (listed in [`assistant/data/manifest.json`](assistant/data/manifest.json)), so the eval can be reproduced. No pages were scraped.

| Source | Licence | Files |
|---|---|---|
| This kit (docs, modules, live config, policies, scripts) | MIT | 57 |
| [OpenTofu docs](https://github.com/opentofu/opentofu) (Terraform language, state, import, testing) | MPL-2.0 | 32 |
| [Terraform AWS provider docs](https://github.com/hashicorp/terraform-provider-aws) | MPL-2.0 | 19 |
| [Terragrunt docs](https://github.com/gruntwork-io/terragrunt) | MIT | 20 |
| [Pulumi docs](https://github.com/pulumi/docs) | Apache-2.0 | 13 |
| [Kyverno docs](https://github.com/kyverno/website) | Apache-2.0 | 5 |
| [Terraformer docs](https://github.com/GoogleCloudPlatform/terraformer) | Apache-2.0 | 2 |

Left out on purpose:

- **HashiCorp's Terraform docs** have no open licence. OpenTofu's MPL-2.0 docs cover the same language.
- **FinOps Foundation material** isn't under a licence that allows redistribution in an index like this.
- **This README** isn't indexed, so the eval numbers can't leak into answers.

## What failed during the build

- **The budget filter was literal text.** In `modules/budget`, `"user:cost-center$${var.cost_center}"` escapes the interpolation, so the Cost Explorer filter would have been the string `${var.cost_center}`. A `terraform test` assertion caught it; the module now uses `format()`.
- **A Moto run called real AWS.** AWS provider 6.x reads bucket tags through S3 Control, which had no endpoint override, so one apply sent requests with fake keys to the real service (403, nothing created). The kit now overrides `s3control` too and sets `AWS_ENDPOINT_URL` as a catch-all. The brownfield seed script refuses to run against any endpoint that isn't local.
- **Default tags didn't reach GPU instances.** Provider `default_tags` don't apply to Auto Scaling group tags or launch template `tag_specifications`. The `require-finops-tags` policy failed the dev and prod plans, which showed that GPU instances would have launched with no `cost-center`. The module now merges `data.aws_default_tags`.
- **Terraform rejected its own generated config.** `-generate-config-out` produced a file that failed to plan with five errors (conflicting and incomplete subnet and VPC arguments). It needs a review step; the reviewed file is in the repo next to the raw one.
- **Terraformer** needs a named `default` profile and exits with status 0 even when every service fails, so the wrapper checks that files were generated.
- **Kyverno loaded zero policies silently.** `kyverno apply <dir>` loaded no policies once the directory also held test fixtures, and the run still looked clean. The check script now passes the policy files explicitly and fails unless the pass count equals the number of policies.
- **Moto gaps.** Moto doesn't implement `DescribeSubscribersForNotification`, so the budget unit is plan-only against Moto. It also drops S3 Control tags, which leaves a permanent tag diff on applied buckets.

## Limitations and next steps

- **No cost estimates in pull requests.** Infracost would add them, but its CLI needs an API key from an Infracost account. The kit runs with no accounts at all, so it's not wired in.
- **AWS only.** Azure and GCP modules would follow the same layout.
- **Moto is not AWS.** Plans and the brownfield demo run against a mock. Apply in a sandbox account before trusting a module in production.
- The assistant's eval set is small and hand-written by the author of the kit; see the caveats in [Ask the kit](#ask-the-kit).
- **The agent's eval is small too:** 25 hand-written requests, and the fixes between runs came from reading failures on the same set. Run 4 is a regression baseline, not a blind score.
- **ADR numbers can collide.** The agent numbers each ADR from the branch it starts on, so two agent branches open at once can both take `0001`. Renumber on merge.
- **CI has no apply step.** If one is added, it must run after merge and only against Moto or the AWS Emulator.
- **Diagram edges between units are approximate.** The dashed edge from a network unit to a GPU unit starts at the network unit's first resource, not at the subnets the GPU group uses.
- **Timing depends on the machine.** The eval shared one Ollama server with another job; on a free machine the agent is faster.

## How to run

You need [Terraform](https://developer.hashicorp.com/terraform/install) 1.11 or later, [Terragrunt](https://terragrunt.gruntwork.io/) 1.2, the [Kyverno CLI](https://kyverno.io/docs/kyverno-cli/) 1.20 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/msaad7777/iac-starter-kit && cd iac-starter-kit

# Module tests (no AWS needed)
for m in modules/*/; do (cd "$m" && terraform init -backend=false >/dev/null && terraform test); done

# Start Moto, the local AWS mock
uvx --from "moto[server]==5.1.*" moto_server -H 127.0.0.1 -p 5000 &

# Plan every unit and check the policies
source scripts/moto-env.sh
scripts/plan-json.sh dev && scripts/plan-json.sh prod
scripts/check-policies.sh
scripts/test-policies.sh

# Brownfield demo
PYTHON="uvx --python 3.12 --with boto3 python" scripts/brownfield-demo.sh

# Kubernetes policies and Pulumi
kyverno test policies/kubernetes/tests
(cd pulumi && uv run pytest -q)
```

On Linux, add `127.0.0.1 123456789012.localhost` to `/etc/hosts` if S3 Control calls fail to resolve (CI does this).

[AWS Emulator](https://github.com/aws/aws-emulator) works as an optional second local target: `source scripts/emulator-env.sh` instead of `moto-env.sh`. It passes the same plan, policy and brownfield steps, and gives a cleaner apply round trip than Moto, but two calls the kit needs aren't implemented yet. Setup, measured results and caveats are in [docs/aws-emulator.md](docs/aws-emulator.md). CI still uses Moto.

The assistant needs [Ollama](https://ollama.com) and about 14 GB of disk for the model:

```bash
ollama pull gpt-oss:20b
cd assistant && uv sync
uv run kit-assistant fetch --pinned   # download the docs at the commits in data/manifest.json
uv run kit-assistant ingest           # chunk and index (a few minutes on CPU)
uv run kit-assistant ask "How do I move from a DynamoDB lock table to S3 lock files?"
uv run kit-assistant serve            # FastAPI on http://127.0.0.1:8010
uv run pytest -q                      # unit tests, no models needed
```

The provisioning agent uses the same Ollama model, Moto (started above) and [Graphviz](https://graphviz.org) for the diagrams (`brew install graphviz` or `apt-get install graphviz`):

```bash
source scripts/moto-env.sh
cd agent && uv sync
uv run kit-agent "Dev bucket for team docs with versioning turned off, and a \$40 budget."
uv run pytest -q                      # 86 unit tests with a scripted model, no Ollama needed
uv run python eval/run_eval.py --tag mine   # the 25-request eval, about 1.5 hours on a laptop
```

The agent leaves a local branch named `agent/<slug>` and writes the PR body under `agent/runs/`. It never pushes; open the PR yourself.

## Layout

```text
modules/        tags, s3-bucket, network, budget, gpu-inference (each with tests/)
live/           Terragrunt: root.hcl, _envcommon/, dev/, prod/
policies/       terraform/ (plan JSON) and kubernetes/ Kyverno policies, with tests
brownfield/     seed_clickops.py, discover/, adopt/, terraformer/
pulumi/         SecureBucket component and mock-based tests
scripts/        moto-env, emulator-env, plan-json, check-policies, test-policies, brownfield-demo, check-adr-status
docs/           greenfield, brownfield, finops, ai-infrastructure, aws-emulator
assistant/      the "Ask the kit" RAG assistant and its eval
agent/          the provisioning agent, its tests and its eval
```

## Licence

MIT. The documentation the assistant downloads keeps its own licence, listed above.
