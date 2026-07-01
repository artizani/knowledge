#!/usr/bin/env python3
"""CDK application entrypoint for the Knowledge API."""
from __future__ import annotations

import os

import aws_cdk as cdk

from stacks.knowledge_stack import KnowledgeApiStack

app = cdk.App()

KnowledgeApiStack(
    app,
    "KnowledgeApiStack",
    env=cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("CDK_DEFAULT_REGION"),
    ),
)

app.synth()
