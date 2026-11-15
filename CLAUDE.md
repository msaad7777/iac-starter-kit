# iac-starter-kit: rules for agents

A free starting point for teams adopting infrastructure as code on AWS, greenfield or brownfield: tested
Terraform modules, Terragrunt live config, Kyverno policy checks on plans, a RAG assistant and a provisioning agent.

## Check command

```bash
make check
```

It runs the CI checks that need no AWS mock: Terraform and Terragrunt format, `terraform validate` and
`terraform test` for every module (mock providers), Trivy (skipped if not installed), the Kyverno Kubernetes
policy tests, and the pytest suites in `pulumi/`, `agent/` and `assistant/`. It needs terraform, terragrunt,
kyverno and uv. `make check-moto` runs the plan, policy and brownfield checks after you start `moto_server`;
CI runs those too.

- Every plan targets Moto (`scripts/moto-env.sh`) or the AWS Emulator (`scripts/emulator-env.sh`). Both set
  `AWS_ENDPOINT_URL`; never remove that safety net. See `docs/aws-emulator.md` for the emulator's limits.
- A module change keeps its `terraform test` cases and the Kyverno policies passing in both directions.
- The agent drafts ADRs as `Proposed`; a person accepts them. CI fails a PR whose ADRs are still `Proposed`.

## Rules

- **Free services only.** Never call real AWS or any paid API, and never add a paid service, key or
  subscription. Models run locally (Ollama or open weights) and tests use fakes.
- **AWS goes to a local mock.** For anything AWS-backed, use the free local
  [AWS Emulator](https://github.com/aws/aws-emulator) or [Moto](https://github.com/getmoto/moto), with
  `AWS_ENDPOINT_URL` pointing at `127.0.0.1`. Never use real AWS credentials or profiles.
- **No IAM-enforcement claims.** The emulator doesn't evaluate IAM policies (and Moto doesn't by default), so a
  call that succeeds locally proves nothing about permissions. Don't write "least privilege enforced" or
  "access denied as expected" unless it's checked another way, and say so.
- **No secrets or personal data.** No keys, tokens, `.env` files, real names, emails, addresses or account
  numbers in code, data, docs or commit messages. Fixtures and demo data are fictional.
- **Report what was run.** Numbers in the README come from committed result files. If you didn't run
  something, say so instead of guessing.
- Keep changes small and reviewable, one branch and pull request per change, and don't merge your own PR.
