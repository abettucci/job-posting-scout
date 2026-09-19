import boto3
import logging
from boto3.dynamodb.conditions import Key, Attr
from datetime import datetime, timedelta, timezone
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
        cv_history_table: str = "",
        company_size_cache_table: str = "",
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
        self.cv_history = db.Table(cv_history_table) if cv_history_table else None
        self.company_size_cache = db.Table(company_size_cache_table) if company_size_cache_table else None

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

    def get_user_job(self, user_id: str, job_id: str) -> Optional[Dict]:
        """Look up a job only within the authenticated user's partition."""
        try:
            resp = self.jobs.get_item(Key={"user_id": user_id, "job_id": job_id})
            item = resp.get("Item")
            return _from_decimal(item) if item else None
        except Exception as e:
            logger.error(f"get_user_job error: {e}")
            return None

    def save_user_job_interview_brief(self, user_id: str, job_id: str, brief: Dict) -> bool:
        """Cache a generated brief without ever addressing another user's job."""
        try:
            self.jobs.update_item(
                Key={"user_id": user_id, "job_id": job_id},
                # Guard against creating an item when an unknown ID is supplied.
                ConditionExpression=Attr("job_id").exists(),
                UpdateExpression="SET interview_brief = :brief, interview_brief_updated_at = :updated",
                ExpressionAttributeValues={
                    ":brief": _to_decimal(brief),
                    ":updated": datetime.utcnow().isoformat(),
                },
            )
            return True
        except self.jobs.meta.client.exceptions.ConditionalCheckFailedException:
            return False
        except Exception as e:
            logger.error(f"save_user_job_interview_brief error: {e}")
            return False

    def set_job_applied(self, user_id: str, job_id: str, applied: bool) -> bool:
        """Mark/unmark a job as applied — never addresses another user's job.
        Storing `applied_at` (instead of just a bool) is what lets the
        "Applied" tab sort by when you applied, not just posting/found date."""
        try:
            if applied:
                update_expr = "SET applied = :applied, applied_at = :applied_at REMOVE dismissed, dismissed_at"
                values = {":applied": applied, ":applied_at": datetime.now(timezone.utc).isoformat()}
            else:
                update_expr = "SET applied = :applied REMOVE applied_at"
                values = {":applied": applied}
            self.jobs.update_item(
                Key={"user_id": user_id, "job_id": job_id},
                ConditionExpression=Attr("job_id").exists(),
                UpdateExpression=update_expr,
                ExpressionAttributeValues=values,
            )
            return True
        except self.jobs.meta.client.exceptions.ConditionalCheckFailedException:
            return False
        except Exception as e:
            logger.error(f"set_job_applied error: {e}")
            return False

    def set_job_dismissed(self, user_id: str, job_id: str, dismissed: bool) -> bool:
        """Dismiss or restore a job without deleting its history.

        Dismissal and application are mutually exclusive queue states: moving a
        job to Dismissed clears any application timestamp, while restoring it
        returns it to the normal Jobs queue.
        """
        try:
            if dismissed:
                update_expr = "SET dismissed = :dismissed, dismissed_at = :dismissed_at REMOVE applied, applied_at"
                values = {":dismissed": True, ":dismissed_at": datetime.now(timezone.utc).isoformat()}
            else:
                update_expr = "REMOVE dismissed, dismissed_at"
                values = None
            kwargs: Dict[str, Any] = {
                "Key": {"user_id": user_id, "job_id": job_id},
                "ConditionExpression": Attr("job_id").exists(),
                "UpdateExpression": update_expr,
            }
            if values is not None:
                kwargs["ExpressionAttributeValues"] = values
            self.jobs.update_item(**kwargs)
            return True
        except self.jobs.meta.client.exceptions.ConditionalCheckFailedException:
            return False
        except Exception as e:
            logger.error(f"set_job_dismissed error: {e}")
            return False

    def get_user_jobs(
        self,
        user_id: str,
        min_score: int = 0,
        limit: int = 50,
        last_key: Optional[Dict] = None,
        applied: Optional[bool] = None,
        dismissed: Optional[bool] = None,
    ) -> tuple[List[Dict], Optional[Dict]]:
        try:
            filter_expr = Attr("score").gte(min_score)
            if applied is not None:
                # Un-applied jobs never had `applied` set at all (older rows) or
                # have it explicitly False — attr_not_exists covers the former.
                filter_expr = filter_expr & (
                    Attr("applied").eq(True) if applied
                    else (Attr("applied").not_exists() | Attr("applied").eq(False))
                )
            if dismissed is not None:
                filter_expr = filter_expr & (
                    Attr("dismissed").eq(True) if dismissed
                    else (Attr("dismissed").not_exists() | Attr("dismissed").eq(False))
                )
            # DynamoDB applies FilterExpression *after* Limit. Keep querying
            # until we have a useful page of matching jobs; otherwise a user
            # with many recently-applied rows could see a partially empty Jobs
            # page (or vice versa) even though more matches exist later.
            items: List[Dict] = []
            next_key = last_key
            while len(items) < limit:
                kwargs: Dict = {
                    "KeyConditionExpression": Key("user_id").eq(user_id),
                    "FilterExpression": filter_expr,
                    "Limit": limit - len(items),
                    "ScanIndexForward": False,
                }
                if next_key:
                    kwargs["ExclusiveStartKey"] = next_key
                resp = self.jobs.query(**kwargs)
                items.extend(_from_decimal(j) for j in resp.get("Items", []))
                next_key = resp.get("LastEvaluatedKey")
                if not next_key:
                    break
            return items[:limit], next_key
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

    # ── Company size cache ────────────────────────────────────────────────────
    # Per-company employee-count lookup from LinkedIn's own company page
    # (scraper/linkedin.py's fetch_linkedin_company_size). Keyed by company
    # LinkedIn slug so multiple job postings from the same employer share one
    # cached result instead of re-visiting the company page every run.

    def get_company_size_cache(self, company_key: str) -> Optional[Dict]:
        if not self.company_size_cache:
            return None
        try:
            resp = self.company_size_cache.get_item(Key={"company_key": company_key})
            item = resp.get("Item")
            return _from_decimal(item) if item else None
        except Exception as e:
            logger.error(f"get_company_size_cache error: {e}")
            return None

    def save_company_size_cache(
        self, company_key: str, size_hint: Optional[str], raw_range: Optional[str], ttl_days: int = 30
    ) -> bool:
        if not self.company_size_cache:
            return False
        ttl = int((datetime.utcnow() + timedelta(days=ttl_days)).timestamp())
        try:
            self.company_size_cache.put_item(Item={
                "company_key": company_key,
                "size_hint": size_hint,
                "raw_range": raw_range,
                "fetched_at": datetime.utcnow().isoformat(),
                "ttl": ttl,
            })
            return True
        except Exception as e:
            logger.error(f"save_company_size_cache error: {e}")
            return False

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

    def get_interview(self, user_id: str, interview_id: str) -> Optional[Dict]:
        if not self.interviews:
            return None
        try:
            resp = self.interviews.get_item(Key={"user_id": user_id, "interview_id": interview_id})
            item = resp.get("Item")
            return _from_decimal(item) if item else None
        except Exception as e:
            logger.error(f"get_interview error: {e}")
            return None

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

    # ── CV History ────────────────────────────────────────────────────────────

    def save_cv_history(self, entry: Dict) -> bool:
        if not self.cv_history:
            return False
        try:
            self.cv_history.put_item(Item=_to_decimal(entry))
            return True
        except Exception as e:
            logger.error(f"save_cv_history error: {e}")
            return False

    def get_user_cv_history(self, user_id: str) -> List[Dict]:
        if not self.cv_history:
            return []
        try:
            resp = self.cv_history.query(
                KeyConditionExpression=Key("user_id").eq(user_id),
                ScanIndexForward=False,
            )
            return [_from_decimal(item) for item in resp.get("Items", [])]
        except Exception as e:
            logger.error(f"get_user_cv_history error: {e}")
            return []

    def get_cv_history_entry(self, user_id: str, created_at: str) -> Optional[Dict]:
        if not self.cv_history:
            return None
        try:
            resp = self.cv_history.get_item(Key={"user_id": user_id, "created_at": created_at})
            item = resp.get("Item")
            return _from_decimal(item) if item else None
        except Exception as e:
            logger.error(f"get_cv_history_entry error: {e}")
            return None

    def delete_cv_history(self, user_id: str, created_at: str) -> bool:
        if not self.cv_history:
            return False
        try:
            self.cv_history.delete_item(Key={"user_id": user_id, "created_at": created_at})
            return True
        except Exception as e:
            logger.error(f"delete_cv_history error: {e}")
            return False
