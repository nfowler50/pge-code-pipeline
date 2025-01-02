import aws_cdk as core
import aws_cdk.assertions as assertions

from pge_code_pipeline.pge_code_pipeline_stack import PgeCodePipelineStack

# example tests. To run these tests, uncomment this file along with the example
# resource in pge_code_pipeline/pge_code_pipeline_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = PgeCodePipelineStack(app, "pge-code-pipeline")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
