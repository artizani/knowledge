"""Synthesis tests for the Knowledge API CDK stack.

Run from the ``infra`` directory:

    cd infra && python -m pytest

Uses ``skip_bundling`` context so no Docker build is required.
"""
from __future__ import annotations

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from stacks.knowledge_stack import KnowledgeApiStack


@pytest.fixture(scope="module")
def template() -> Template:
    app = cdk.App(context={"skip_bundling": True})
    stack = KnowledgeApiStack(app, "TestStack")
    return Template.from_stack(stack)


def test_creates_python313_lambda(template: Template):
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Runtime": "python3.13",
            "Handler": "handler.handler",
            "Architectures": ["arm64"],
            "Timeout": 30,
        },
    )


def test_lambda_has_secret_arn_env(template: Template):
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Environment": {
                "Variables": Match.object_like({"AUTH_REQUIRED": "true"})
            }
        },
    )


def test_references_secret(template: Template):
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Environment": {
                "Variables": Match.object_like({"SECRET_ARN": Match.any_value()})
            }
        },
    )


def test_creates_secret(template: Template):
    # The secret is externally managed; the stack only references it.
    template.resource_count_is("AWS::SecretsManager::Secret", 0)
    template.resource_count_is("AWS::IAM::Policy", 1)


def test_creates_http_api(template: Template):
    template.has_resource_properties(
        "AWS::ApiGatewayV2::Api", {"ProtocolType": "HTTP"}
    )


def test_creates_proxy_route(template: Template):
    template.has_resource_properties(
        "AWS::ApiGatewayV2::Route", {"RouteKey": "ANY /{proxy+}"}
    )


def test_lambda_can_read_secret(template: Template):
    # A policy granting secretsmanager:GetSecretValue must exist.
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Action": Match.array_with(
                                    ["secretsmanager:GetSecretValue"]
                                ),
                                "Resource": Match.any_value(),
                            }
                        )
                    ]
                )
            }
        },
    )


def test_log_group_created(template: Template):
    template.resource_count_is("AWS::Logs::LogGroup", 1)
