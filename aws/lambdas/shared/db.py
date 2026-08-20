import boto3
import logging
from boto3.dynamodb.conditions import Key, Attr
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _to_decimal(obj: Any) -> Any:
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_decimal(v) for v in obj]
    return obj


def _from_decimal(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        f = float(obj)
        return int(f) if f.is_integer() else f
    if isinstance(obj, dict):
        return {k: _from_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_from_decimal(v) for v in obj]
    return obj


class DynamoDBClient:
    def __init__(
        self,
        users_table: str,
        searches_table: str,
        profiles_table: str,
        jobs_table: str,
        telegram_codes_table: str,
        interviews_table: str = "",
        resumes_table: str = "",
        region: str = "us-east-1",
    ):
        db = boto3.resource("dynamodb", region_name=region)
        self.users = db.Table(users_table)
        self.searches = db.Table(searches_table)
        self.profiles = db.Table(profiles_table)
        self.jobs = db.Table(jobs_table)
        self.telegram_codes = db.Table(telegram_codes_table)
        self.interviews = db.Table(interviews_table) if interviews_table else None
        self.resumes = db.Table(resumes_table) if resumes_table else None

    # ── Users ──────────────────────────────────────────────────────────────

    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        try:
            resp = self.users.get_item(Key={"user_id": user_id})
            return _from_decimal(resp.get("Item"))
        except Exception as e:
            logger.error(f"get_user_by_id error: {e}")
            return None

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        try:
            resp = self.users.query(
                IndexName="email-index",
                KeyConditionExpression=Key("email").eq(email.lower()),
            )
            items = resp.get("Items", [])
            return _from_decimal(items[0]) if items else None
        except Exception as e:
            logger.error(f"get_user_by_email error: {e}")
            return None

    def create_user(self, user: Dict) -> bool:
        try:
            self.users.put_item(
                Item=_to_decimal(user),
                ConditionExpression=Attr("user_id").not_exists(),
            )
            return True
        except self.users.meta.client.exceptions.ConditionalCheckFailedException:
            return False
        except Exception as e:
            logger.error(f"create_user error: {e}")
            return False

    def update_user(self, user_id: str, updates: Dict) -> bool:
        if not updates:
            return True
        try:
            expr_parts = [f"#{k} = :{k}" for k in updates]
            names = {f"#{k}": k for k in updates}
            values = {f":{k}": _to_decimal(v) for k, v in updates.items()}
            self.users.update_item(
                Key={"user_id": user_id},
                UpdateExpression="SET " + ", ".join(expr_parts) + ", updated_at = :ts",
                ExpressionAttributeNames=names,
                ExpressionAttributeValues={**values, ":ts": datetime.utcnow().isoformat()},
            )
            return True
        except Exception as e:
            logger.error(f"update_user error: {e}")
            return False

    def get_all_linked_users(self) -> List[Dict]:
        """Return users that have a Telegram chat_id linked (active users for scraping)."""
        try:
            resp = self.users.scan(FilterExpression=Attr("telegram_chat_id").exists())
            return [_from_decimal(u) for u in resp.get("Items", [])]
        except Exception as e:
            logger.error(f"get_all_linked_users error: {e}")
            return []

    # ── Searches ────────────────────────────────────────────────────────────

    def get_user_searches(self, user_id: str) -> List[Dict]:
        try:
            resp = self.searches.query(KeyConditionExpression=Key("user_id").eq(user_id))
            return [_from_decimal(s) for s in resp.get("Items", [])]
        except Exception as e:
            logger.error(f"get_user_searches error: {e}")
            return []

    def get_active_searches(self, user_id: str) -> List[Dict]:
        try:
            resp = self.searches.query(
                KeyConditionExpression=Key("user_id").eq(user_id),
                FilterExpression=Attr("active").eq(True),
            )
            return [_from_decimal(s) for s in resp.get("Items", [])]
        except Exception as e:
            logger.error(f"get_active_searches error: {e}")
            return []

    def create_search(self, search: Dict) -> bool:
        try:
            self.searches.put_item(Item=_to_decimal(search))
            return True
        except Exception as e:
            logger.error(f"create_search error: {e}")
            return False

    def update_search(self, user_id: str, search_id: str, updates: Dict) -> bool:
        if not updates:
            return True
        try:
            expr_parts = [f"#{k} = :{k}" for k in updates]
            names = {f"#{k}": k for k in updates}
            values = {f":{k}": _to_decimal(v) for k, v in updates.items()}
            self.searches.update_item(
                Key={"user_id": user_id, "search_id": search_id},
                UpdateExpression="SET " + ", ".join(expr_parts),
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
            )
            return True
        except Exception as e:
            logger.error(f"update_search error: {e}")
            return False

    def delete_search(self, user_id: str, search_id: str) -> bool:
        try:
            self.searches.delete_item(Key={"user_id": user_id, "search_id": search_id})
            return True
        except Exception as e:
            logger.error(f"delete_search error: {e}")
            return False

    # ── Profiles ────────────────────────────────────────────────────────────

    def get_profile(self, user_id: str) -> Optional[Dict]:
        try:
            resp = self.profiles.get_item(Key={"user_id": user_id})
            item = resp.get("Item")
            return _from_decimal(item) if item else None
        except Exception as e:
            logger.error(f"get_profile error: {e}")
            return None

    def upsert_profile(self, user_id: str, profile: Dict) -> bool:
        try:
            self.profiles.put_item(Item={"user_id": user_id, **_to_decimal(profile)})
            return True
        except Exception as e:
            logger.error(f"upsert_profile error: {e}")
            return False

    # ── Jobs ────────────────────────────────────────────────────────────────

    def is_job_seen(self, user_id: str, job_id: str) -> bool:
        try:
            resp = self.jobs.get_item(Key={"user_id": user_id, "job_id": job_id})
            return "Item" in resp
        except Exception as e:
            logger.error(f"is_job_seen error: {e}")
            return False

    def save_job(self, job: Dict) -> bool:
        ttl = int((datetime.utcnow() + timedelta(days=60)).timestamp())
        try:
            self.jobs.put_item(Item={"ttl": ttl, **_to_decimal(job)})
            return True
        except Exception as e:
            logger.error(f"save_job error: {e}")
            return False

    def get_user_jobs(
        self,
        user_id: str,
        min_score: int = 0,
        limit: int = 50,
        last_key: Optional[Dict] = None,
    ) -> tuple[List[Dict], Optional[Dict]]:
        try:
            kwargs: Dict = {
                "KeyConditionExpression": Key("user_id").eq(user_id),
                "FilterExpression": Attr("score").gte(min_score),
                "Limit": limit,
                "ScanIndexForward": False,
            }
            if last_key:
                kwargs["ExclusiveStartKey"] = last_key
            resp = self.jobs.query(**kwargs)
            items = [_from_decimal(j) for j in resp.get("Items", [])]
            next_key = resp.get("LastEvaluatedKey")
            return items, next_key
        except Exception as e:
            logger.error(f"get_user_jobs error: {e}")
            return [], None

    # ── Telegram codes ───────────────────────────────────────────────────────

    def save_telegram_code(self, code: str, user_id: str) -> bool:
        ttl = int((datetime.utcnow() + timedelta(minutes=10)).timestamp())
        try:
            self.telegram_codes.put_item(
                Item={"code": code, "user_id": user_id, "ttl": ttl}
            )
            return True
        except Exception as e:
            logger.error(f"save_telegram_code error: {e}")
            return False

    def consume_telegram_code(self, code: str) -> Optional[str]:
        """Return user_id and delete the code (single-use)."""
        try:
            resp = self.telegram_codes.get_item(Key={"code": code})
            item = resp.get("Item")
            if not item:
                return None
            now = int(datetime.utcnow().timestamp())
            if item.get("ttl", 0) < now:
                return None
            self.telegram_codes.delete_item(Key={"code": code})
            return item["user_id"]
        except Exception as e:
            logger.error(f"consume_telegram_code error: {e}")
            return None

    # ── Interviews ───────────────────────────────────────────────────────────

    def get_user_interviews(self, user_id: str) -> List[Dict]:
        if not self.interviews:
            return []
        try:
            resp = self.interviews.query(KeyConditionExpression=Key("user_id").eq(user_id))
            return [_from_decimal(i) for i in resp.get("Items", [])]
        except Exception as e:
            logger.error(f"get_user_interviews error: {e}")
            return []

    def create_interview(self, interview: Dict) -> bool:
        if not self.interviews:
            return False
        try:
            self.interviews.put_item(Item=_to_decimal(interview))
            return True
        except Exception as e:
            logger.error(f"create_interview error: {e}")
            return False

    def update_interview(self, user_id: str, interview_id: str, updates: Dict) -> bool:
        if not self.interviews or not updates:
            return bool(not updates)
        try:
            expr_parts = [f"#{k} = :{k}" for k in updates]
            names = {f"#{k}": k for k in updates}
            values = {f":{k}": _to_decimal(v) for k, v in updates.items()}
            self.interviews.update_item(
                Key={"user_id": user_id, "interview_id": interview_id},
                UpdateExpression="SET " + ", ".join(expr_parts),
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
            )
            return True
        except Exception as e:
            logger.error(f"update_interview error: {e}")
            return False

    def delete_interview(self, user_id: str, interview_id: str) -> bool:
        if not self.interviews:
            return False
        try:
            self.interviews.delete_item(Key={"user_id": user_id, "interview_id": interview_id})
            return True
        except Exception as e:
            logger.error(f"delete_interview error: {e}")
            return False

    # ── Resumes ──────────────────────────────────────────────────────────────

    def get_resume(self, user_id: str) -> Optional[Dict]:
        if not self.resumes:
            return None
        try:
            resp = self.resumes.get_item(Key={"user_id": user_id})
            item = resp.get("Item")
            return _from_decimal(item) if item else None
        except Exception as e:
            logger.error(f"get_resume error: {e}")
            return None

    def save_resume(self, user_id: str, resume_data: Dict) -> bool:
        if not self.resumes:
            return False
        try:
            self.resumes.put_item(
                Item={"user_id": user_id, "updated_at": datetime.utcnow().isoformat(), **_to_decimal(resume_data)}
            )
            return True
        except Exception as e:
            logger.error(f"save_resume error: {e}")
            return False