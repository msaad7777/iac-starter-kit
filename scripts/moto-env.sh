# Source this file to point Terraform, Terragrunt, Terraformer and boto3 at a local Moto server.
#   source scripts/moto-env.sh
# AWS_ENDPOINT_URL is the safety net: any service the provider block does not list
# still goes to Moto instead of the real AWS API.
export KIT_TARGET=moto
export MOTO_URL="${MOTO_URL:-http://localhost:5000}"
export AWS_ENDPOINT_URL="$MOTO_URL"
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_REGION=us-east-1
export AWS_DEFAULT_REGION=us-east-1
unset AWS_PROFILE AWS_SESSION_TOKEN

# Terraformer requires a named "default" profile even when keys are in the environment.
# Give it a throwaway profile with the fake Moto keys, never your real ~/.aws files.
_kit_aws_dir="${TMPDIR:-/tmp}/iac-starter-kit-moto-aws"
mkdir -p "$_kit_aws_dir"
printf '[default]\naws_access_key_id = test\naws_secret_access_key = test\n' > "$_kit_aws_dir/credentials"
printf '[default]\nregion = us-east-1\n' > "$_kit_aws_dir/config"
export AWS_SHARED_CREDENTIALS_FILE="$_kit_aws_dir/credentials"
export AWS_CONFIG_FILE="$_kit_aws_dir/config"
