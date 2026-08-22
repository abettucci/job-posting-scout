import json
import logging
import os
from dataclasses import dataclass

import boto3

logger = logging.getLogger(__name__)


@dataclass
class Config:
    users_table: str
    searches_table: str
    profiles_table: str
    jobs_table: str
    telegram_codes_table: str
    interviews_table: str
    resumes_table: str
    cv_history_table: str
    telegram_bot_token: str
    anthropic_api_key: str
    jwt_secret: str
    linkedin_email: str
    linkedin_password: str
    region: str
    environment: str
    frontend_url: str


def _get_secret(secret_name: str, region: str) -> dict:
    client = boto3.client("secretsmanager", region_name=region)
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response["SecretString"])


def get_config() -> Config:
    region = os.environ.get("AWS_REGION", "us-east-2")
    secret_name = os.environ.get("SECRETS_NAME", "")

    secrets = {}
    if secret_name:
        try:
            secrets = _get_secret(secret_name, region)
        except Exception as e:
            logger.error(f"Failed to load secrets from Secrets Manager: {e}")

    return Config(
        users_table=os.environ.get("USERS_TABLE", ""),
        searches_table=os.environ.get("SEARCHES_TABLE", ""),
        profiles_table=os.environ.get("PROFILES_TABLE", ""),
        jobs_table=os.environ.get("JOBS_TABLE", ""),
        telegram_codes_table=os.environ.get("TELEGRAM_CODES_TABLE", ""),
        interviews_table=os.environ.get("INTERVIEWS_TABLE", ""),
        resumes_table=os.environ.get("RESUMES_TABLE", ""),
        cv_history_table=os.environ.get("CV_HISTORY_TABLE", ""),
        telegram_bot_token=secrets.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        anthropic_api_key=secrets.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", ""),
        jwt_secret=secrets.get("JWT_SECRET") or os.environ.get("JWT_SECRET", "change-me"),
        linkedin_email=secrets.get("LINKEDIN_EMAIL") or os.environ.get("LINKEDIN_EMAIL", ""),
        linkedin_password=secrets.get("LINKEDIN_PASSWORD") or os.environ.get("LINKEDIN_PASSWORD", ""),
        region=region,
        environment=os.environ.get("ENVIRONMENT", "prod"),
        frontend_url=os.environ.get("FRONTEND_URL", "http://localhost:3000"),
    )
