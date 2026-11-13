# Source this file to point Terraform, Terragrunt, Terraformer and boto3 at a local AWS Emulator
# (github.com/aws/aws-emulator), the second local target next to Moto (scripts/moto-env.sh).
#   source scripts/emulator-env.sh
# Start the emulator first (see docs/aws-emulator.md). It serves HTTPS on 127.0.0.1:9297
# with a self-signed certificate, and on every start writes a fresh CA, a config file and a
# pair of run-only keys to ~/.aws/emulator/<port>/. This file reads them from there.
# AWS_ENDPOINT_URL is the safety net: every AWS call goes to the emulator, never to real AWS.
export KIT_TARGET=emulator
export EMULATOR_PORT="${EMULATOR_PORT:-9297}"
export EMULATOR_URL="${EMULATOR_URL:-https://127.0.0.1:$EMULATOR_PORT}"
_kit_emu_dir="${EMULATOR_DIR:-$HOME/.aws/emulator/$EMULATOR_PORT}"
if [ ! -f "$_kit_emu_dir/emulator_credentials" ]; then
  echo "emulator-env.sh: $_kit_emu_dir/emulator_credentials not found; start the emulator first" >&2
  return 1 2>/dev/null || exit 1
fi
export AWS_ENDPOINT_URL="$EMULATOR_URL"
# The emulator signs nothing with your real keys: it rejects them. Use the run-only keys it wrote.
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE
export AWS_SHARED_CREDENTIALS_FILE="$_kit_emu_dir/emulator_credentials"
export AWS_CONFIG_FILE="$_kit_emu_dir/config"
# Trust the emulator's self-signed CA. boto3 and the Terraform AWS provider both read AWS_CA_BUNDLE.
export AWS_CA_BUNDLE="$_kit_emu_dir/ca.pem"
# S3 Control (the provider reads bucket tags through it) puts the account ID in front of the
# host. 000000000000.localhost resolves to this machine; 000000000000.127.0.0.1 does not.
export AWS_ENDPOINT_URL_S3_CONTROL="${EMULATOR_URL/127.0.0.1/localhost}"
# The emulator's certificate names only localhost, so that host fails TLS verification.
# The brownfield demo's provider turns verification off when this is set (live/root.hcl does
# the same for KIT_TARGET=emulator). Last resort, local only: see docs/aws-emulator.md.
export TF_VAR_local_emulator_insecure_tls=true
export AWS_EC2_METADATA_DISABLED=true
export AWS_DISABLE_HOST_PREFIX_INJECTION=true
export AWS_REGION=us-east-1
export AWS_DEFAULT_REGION=us-east-1
