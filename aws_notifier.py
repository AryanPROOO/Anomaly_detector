import os
import json
import logging
from typing import Dict, Any

logger = logging.getLogger("AWSNotifier")
logger.setLevel(logging.INFO)

class AWSNotifier:
    """
    Handles pushing alerts to AWS CloudWatch Logs and AWS SNS Topic.
    Falls back gracefully to Mock Mode when AWS environment credentials or boto3 setup are not present.
    """
    def __init__(
        self,
        log_group_name: str = "/aws/log-anomaly-detector/alerts",
        log_stream_name: str = "alerts-stream",
        sns_topic_arn: str = None
    ):
        self.log_group_name = log_group_name
        self.log_stream_name = log_stream_name
        self.sns_topic_arn = sns_topic_arn or os.environ.get("AWS_SNS_TOPIC_ARN", "")
        self.region = os.environ.get("AWS_REGION", "us-east-1")
        self.mock_mode = True
        self.cw_client = None
        self.sns_client = None

        self._init_aws()

    def _init_aws(self):
        try:
            import boto3
            # Check if AWS credentials exist
            aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
            aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")

            if aws_access_key and aws_secret_key:
                self.cw_client = boto3.client("logs", region_name=self.region)
                self.sns_client = boto3.client("sns", region_name=self.region)

                # Ensure log group & stream exist
                try:
                    self.cw_client.create_log_group(logGroupName=self.log_group_name)
                except Exception:
                    pass  # Group already exists

                try:
                    self.cw_client.create_log_stream(
                        logGroupName=self.log_group_name,
                        logStreamName=self.log_stream_name
                    )
                except Exception:
                    pass  # Stream already exists

                self.mock_mode = False
                logger.info(f"[AWSNotifier] Initialized real AWS clients in region {self.region}")
            else:
                logger.info("[AWSNotifier] AWS credentials not found in environment. Operating in AWS Mock Mode.")
                self.mock_mode = True
        except Exception as e:
            logger.warning(f"[AWSNotifier] Boto3 client initialization error ({e}). Using AWS Mock Mode.")
            self.mock_mode = True

    def push_alert(self, alert_dict: Dict[str, Any]) -> bool:
        """
        Pushes alert payload to AWS CloudWatch Logs & AWS SNS.
        Returns True if push succeeded (or mock logged successfully).
        """
        payload_str = json.dumps(alert_dict, indent=2)

        if self.mock_mode:
            print("\n==================== [MOCK AWS CLOUDWATCH LOGS & SNS PUSH] ====================")
            print(f"Target CloudWatch Log Group: {self.log_group_name}")
            print(f"Target Log Stream:          {self.log_stream_name}")
            print(f"Target SNS Topic ARN:        {self.sns_topic_arn or 'arn:aws:sns:us-east-1:123456789012:log-anomalies'}")
            print("Payload:")
            print(payload_str)
            print("=================================================================================\n")
            return True

        # Real AWS Push
        success = True
        # 1. CloudWatch Logs
        try:
            import time
            timestamp_ms = int(time.time() * 1000)
            self.cw_client.put_log_events(
                logGroupName=self.log_group_name,
                logStreamName=self.log_stream_name,
                logEvents=[
                    {
                        'timestamp': timestamp_ms,
                        'message': payload_str
                    }
                ]
            )
            logger.info(f"[AWSNotifier] Successfully pushed alert {alert_dict.get('id')} to CloudWatch")
        except Exception as e:
            logger.error(f"[AWSNotifier] Failed to push to CloudWatch Logs: {e}")
            success = False

        # 2. AWS SNS
        if self.sns_topic_arn:
            try:
                subject = f"[{alert_dict.get('severity')}] Log Anomaly: {alert_dict.get('title')}"
                self.sns_client.publish(
                    TopicArn=self.sns_topic_arn,
                    Subject=subject[:100],
                    Message=payload_str
                )
                logger.info(f"[AWSNotifier] Successfully published alert {alert_dict.get('id')} to SNS Topic")
            except Exception as e:
                logger.error(f"[AWSNotifier] Failed to publish to SNS: {e}")
                success = False

        return success

    def status_summary(self) -> Dict[str, Any]:
        return {
            "mode": "MOCK_MODE" if self.mock_mode else "REAL_AWS",
            "region": self.region,
            "cloudwatch_log_group": self.log_group_name,
            "cloudwatch_log_stream": self.log_stream_name,
            "sns_topic_arn": self.sns_topic_arn or "arn:aws:sns:us-east-1:123456789012:log-anomalies (mock)"
        }
