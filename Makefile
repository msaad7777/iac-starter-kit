# One command for the checks that need no AWS mock: `make check`.
# Needs terraform, kyverno and uv on PATH (trivy is optional locally). No cloud account, no network
# after the first `terraform init` and `uv sync`.
# The plan and policy checks against Moto, the brownfield demo and the ADR check run in CI
# (.github/workflows/ci.yml); run them locally with `make check-moto` after starting moto_server.
.PHONY: check fmt modules trivy k8s-policies pulumi agent assistant check-moto

check: fmt modules trivy k8s-policies pulumi agent assistant

fmt:
	terraform fmt -recursive -check modules brownfield/discover brownfield/adopt policies
	terragrunt hcl format --check --working-dir live

modules:
	@set -e; for m in modules/*/; do \
	  echo "== $$m"; \
	  (cd "$$m" && terraform init -input=false -backend=false >/dev/null && terraform validate && terraform test); \
	done

trivy:
	@if command -v trivy >/dev/null; then trivy config --exit-code 1 --quiet modules; \
	else echo "trivy not installed: skipped (CI runs it)"; fi

k8s-policies:
	kyverno test policies/kubernetes/tests

pulumi agent assistant:
	cd $@ && uv sync --frozen && uv run pytest -q

# Needs moto_server on 127.0.0.1:5000 (see the README). Same steps as the CI plans-and-policies job.
check-moto:
	. scripts/moto-env.sh && scripts/plan-json.sh dev && scripts/plan-json.sh prod
	scripts/check-policies.sh
	. scripts/moto-env.sh && scripts/test-policies.sh
	scripts/brownfield-demo.sh
