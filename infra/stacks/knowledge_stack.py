"""CDK stack for the Knowledge API.

Provisions:

* an API Gateway HTTP API proxying all routes to a Python 3.13 Lambda,
* a Python 3.13 Lambda running the FastAPI app via Mangum,
* least-privilege IAM (Lambda reads only the external secret),
* a CloudWatch log group with a bounded retention.

The secret itself is **not** managed by this stack. Create it manually (or via
a separate one-off process) at ``knowledge-api/config`` and populate it with
``SUPABASE_URL``, ``SUPABASE_SERVICE_ROLE_KEY``, ``SUPABASE_ANON_KEY``,
``API_TOKEN``, and ``JWT_SECRET``. This prevents CDK deploys from overwriting
secret values.

Bundling installs ``requirements.txt`` into the Lambda asset using the official
Lambda build image (requires Docker). Pass ``-c skip_bundling=true`` to skip
bundling (used by the synth unit test, which only asserts resource shape).
"""
from __future__ import annotations

from pathlib import Path

from aws_cdk import (
    BundlingOptions,
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_integrations as integrations
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = PROJECT_ROOT / "app"
SECRET_NAME = "knowledge-api/config"

# Install runtime deps into the asset root, then copy the app package + handler.
_BUNDLE_CMD = (
    "pip install --no-cache-dir -r requirements.txt -t /asset-output "
    "&& cp -au app handler.py /asset-output"
)

_ASSET_EXCLUDES = [
    ".venv",
    ".git",
    "infra",
    "tests",
    "scripts",
    "**/__pycache__",
    "*.pyc",
    "cdk.out",
    ".pytest_cache",
    "htmlcov",
    "*.db",
]


class KnowledgeApiStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        log_level = self.node.try_get_context("log_level") or "INFO"

        # -- Secret --------------------------------------------------------- #
        # Reference an externally-managed secret. This stack will NOT create or
        # modify the secret value, so manual/CD secret updates are preserved.
        secret = secretsmanager.Secret.from_secret_name_v2(
            self,
            "KnowledgeApiSecret",
            secret_name=SECRET_NAME,
        )

        # -- Lambda --------------------------------------------------------- #
        log_group = logs.LogGroup(
            self,
            "KnowledgeApiLogGroup",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        fn = lambda_.Function(
            self,
            "KnowledgeApiFunction",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="handler.handler",
            code=self._lambda_code(),
            memory_size=512,
            timeout=Duration.seconds(30),
            architecture=lambda_.Architecture.ARM_64,
            log_group=log_group,
            environment={
                "SECRET_ARN": secret.secret_arn,
                "LOG_LEVEL": log_level,
                "AUTH_REQUIRED": "true",
            },
        )
        # Least privilege: the function can read only its own secret.
        secret.grant_read(fn)

        # -- HTTP API ------------------------------------------------------- #
        http_api = apigwv2.HttpApi(
            self,
            "KnowledgeHttpApi",
            api_name="knowledge-api",
            description="Knowledge API HTTP endpoint.",
        )
        http_api.add_routes(
            path="/{proxy+}",
            methods=[apigwv2.HttpMethod.ANY],
            integration=integrations.HttpLambdaIntegration(
                "KnowledgeLambdaIntegration", handler=fn
            ),
        )

        CfnOutput(self, "ApiUrl", value=http_api.api_endpoint)
        CfnOutput(self, "SecretArn", value=secret.secret_arn)
        CfnOutput(self, "FunctionName", value=fn.function_name)

    def _lambda_code(self) -> lambda_.Code:
        if self.node.try_get_context("skip_bundling"):
            # Fast path for unit synth tests: no Docker, small asset.
            return lambda_.Code.from_asset(str(APP_DIR))
        return lambda_.Code.from_asset(
            str(PROJECT_ROOT),
            exclude=_ASSET_EXCLUDES,
            bundling=BundlingOptions(
                image=lambda_.Runtime.PYTHON_3_13.bundling_image,
                command=["bash", "-c", _BUNDLE_CMD],
            ),
        )
