from aws_cdk import (
    App,
    Stack,
    aws_codepipeline,
    aws_codepipeline_actions,
    aws_codebuild,
    aws_iam,
    aws_s3,
    aws_secretsmanager,
)

from constructs import Construct

class PgeCodePipelineStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)


        # Create the IAM role and policy for Build container to assume
        codebuild_role = aws_iam.Role(
            self, 
            "CodeBuildRole", 
            assumed_by=aws_iam.ServicePrincipal("codebuild.amazonaws.com"),
            inline_policies={
                "AssumeRolePolicy": aws_iam.PolicyDocument(
                    statements=[
                        aws_iam.PolicyStatement(
                            actions=["sts:AssumeRole"],
                            resources=["arn:aws:iam::*:role/cdk-*"]
                        ),
                        aws_iam.PolicyStatement(
                            actions=["cloudformation:*"],
                            resources=["*"]
                        )
                    ]
                )
            }
        )

        # **** 1. Create S3 bucket for storing artifacts ****
        artifact_bucket = aws_s3.Bucket(self, "ArtifactBucket")

        # **** 2. Retrieve GitHub credentials from Secrets Manager ****
        # ASSESSOR MUST PROVIDE THEIR OWN OAUTH TOKEN FOR GITHUB ACCESS. Only permission needed is repo: public_repo
        github_token = aws_secretsmanager.Secret.from_secret_complete_arn(self, 'GitHubToken', 'arn:aws:secretsmanager:us-east-1:975050280026:secret:github-access-token-secret-DLykZ5')

        # GitHub repository details
        repository = "pge-assessment-application"
        owner = "nfowler50"
        branch = "main"

        # **** 3. Create Source stage: Watch GitHub repository ****
        source_output = aws_codepipeline.Artifact()
        source_action = aws_codepipeline_actions.GitHubSourceAction(
            action_name="GitHub",
            owner=owner,
            repo=repository,
            oauth_token=github_token.secret_value,
            branch=branch,
            output=source_output,
        )

        # **** 4. Define build project ****
        build_project = aws_codebuild.PipelineProject(
            self, "BuildProject",
            build_spec=aws_codebuild.BuildSpec.from_object({
                "version": "0.2",
                "phases": {
                    "install": {"commands": [
                        "pip install -r requirements.txt",
                        "pip install -r requirements-dev.txt"
                        ]},
                    "pre_build": {
                        "commands": [
                            "cd lambda-hosted",
                            "pytest test-model_serve.py",
                            "cd ..",
                            "cd ecs-hosted",
                            "pytest test-model_serve.py",
                            "cd ..",
                            "cd lambda-auth",
                            "pytest test-auth.py",
                            "cd ..",
                        ]
                    }
                },
                "artifacts": {"files": ["**/*"]}
            })
        )

        build_output = aws_codepipeline.Artifact("BuildOutput")
        build_action = aws_codepipeline_actions.CodeBuildAction(
            action_name="BuildAndTest",
            project=build_project,
            input=source_output,
            outputs=[build_output],
        )

        # **** 5. Define deployment project for Beta ****
        beta_deploy_project = aws_codebuild.PipelineProject(
            self, "BetaDeployProject",
            role=codebuild_role,
            build_spec=aws_codebuild.BuildSpec.from_object({
                "version": "0.2",
                "phases": {
                    "install": {"commands": [
                        "npm install -g aws-cdk",
                        "pip install -r requirements.txt"
                        ]},
                    "build": {
                        "commands": [
                            "cdk bootstrap",
                            "cdk deploy --all --require-approval never --context env=BETA"
                        ]
                    }
                }
            })
        )
        beta_deploy_action = aws_codepipeline_actions.CodeBuildAction(
            action_name="CdkBootstrapAndDeployToBeta",
            project=beta_deploy_project,
            input=source_output,
        )

        # **** 6. Define deployment project for Production ****
        prod_deploy_project = aws_codebuild.PipelineProject(
            self, "ProdDeployProject",
            role=codebuild_role,
            build_spec=aws_codebuild.BuildSpec.from_object({
                "version": "0.2",
                "phases": {
                    "install": {"commands": [
                        "npm install -g aws-cdk",
                        "pip install -r requirements.txt"
                        ]},
                    "build": {
                        "commands": [
                            "cdk bootstrap",
                            "cdk deploy --all --require-approval never --context env=PROD"
                        ]
                    }
                }
            })
        )
        prod_deploy_action = aws_codepipeline_actions.CodeBuildAction(
            action_name="CdkBootstrapAndDeployToProd",
            project=prod_deploy_project,
            input=source_output,
        )

        # **** 7. Add manual approval step prior to prod deployment ****
        approval_action = aws_codepipeline_actions.ManualApprovalAction(
            action_name="ManualApproval"
        )

        # **** 8. Create the pipeline ****
        pipeline = aws_codepipeline.Pipeline(
            self, "PGEDeploymentPipeline",
            pipeline_name="PGEDeploymentPipeline",
            artifact_bucket=artifact_bucket
        )

        # **** 9. Add stages to the pipeline ****
        pipeline.add_stage(stage_name="Source", actions=[source_action])
        pipeline.add_stage(stage_name="Build", actions=[build_action])
        pipeline.add_stage(stage_name="DeployToBeta", actions=[beta_deploy_action])
        pipeline.add_stage(stage_name="Approval", actions=[approval_action])
        pipeline.add_stage(stage_name="DeployToProd", actions=[prod_deploy_action])

