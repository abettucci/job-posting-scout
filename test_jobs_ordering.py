"""Regression coverage for the active Jobs queue ordering.

The table's range key is a source-prefixed job id, so it cannot be used as a
proxy for recency. This test makes that access-path requirement explicit
without depending on AWS.
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "aws" / "lambdas"))


try:
    import boto3  # noqa: F401
except ModuleNotFoundError:
    # Unit-test the Dynamo query construction without requiring the AWS Lambda
    # runtime dependency in a local frontend-oriented checkout.
    class _Condition:
        def __init__(self, *_args):
            pass

        def eq(self, *_args):
            return self

        def gte(self, *_args):
            return self

        def not_exists(self):
            return self

        def __and__(self, _other):
            return self

        def __or__(self, _other):
            return self

    boto3_module = types.ModuleType("boto3")
    dynamodb_module = types.ModuleType("boto3.dynamodb")
    conditions_module = types.ModuleType("boto3.dynamodb.conditions")
    conditions_module.Key = _Condition
    conditions_module.Attr = _Condition
    boto3_module.dynamodb = dynamodb_module
    sys.modules["boto3"] = boto3_module
    sys.modules["boto3.dynamodb"] = dynamodb_module
    sys.modules["boto3.dynamodb.conditions"] = conditions_module

from shared.db import DynamoDBClient  # noqa: E402


class _FakeJobsTable:
    def __init__(self):
        self.calls = []

    def query(self, **kwargs):
        self.calls.append(kwargs)
        return {"Items": [{"job_id": "freehire:new", "timestamp": "2026-10-06T01:46:19+00:00", "score": 72}]}


class _IndexUnavailable(Exception):
    response = {"Error": {"Code": "ValidationException"}}


class _IndexRolloutJobsTable(_FakeJobsTable):
    def query(self, **kwargs):
        self.calls.append(kwargs)
        if "IndexName" in kwargs:
            raise _IndexUnavailable()
        return {"Items": [{"job_id": "legacy:row", "score": 72}]}


class JobsOrderingTests(unittest.TestCase):
    def test_historical_salary_currency_is_rechecked_against_current_profile(self):
        db = DynamoDBClient.__new__(DynamoDBClient)
        db.jobs = _FakeJobsTable()
        db.jobs.query = lambda **kwargs: {"Items": [{
            "job_id": "other-board:php-salary", "location": "Remote", "score": 90,
            "description": "Salary PHP 60000 per month",
        }]}
        profile = {"eligible_regions": ["Argentina", "LATAM", "Worldwide"]}
        items, _ = db.get_user_jobs("user-1", deal_breaker=False, discovery_profile=profile)
        self.assertEqual(items, [])
        audit, _ = db.get_user_jobs("user-1", deal_breaker=True, discovery_profile=profile)
        self.assertIn("PHP", audit[0]["reasons"][0])

    def test_discovery_refills_pages_after_rejecting_legacy_regional_posting(self):
        db = DynamoDBClient.__new__(DynamoDBClient)
        db.jobs = _FakeJobsTable()
        pages = iter([
            {"Items": [{"job_id": "onlinejobs:old", "location": "Remote", "score": 90}],
             "LastEvaluatedKey": {"user_id": "user-1", "job_id": "onlinejobs:old"}},
            {"Items": [{"job_id": "eligible", "location": "Argentina", "score": 80}]},
        ])
        def query(**kwargs):
            db.jobs.calls.append(kwargs)
            return next(pages)
        db.jobs.query = query
        items, cursor = db.get_user_jobs("user-1", limit=1, deal_breaker=False,
                                         discovery_profile={"eligible_regions": ["Argentina", "Worldwide"]})
        self.assertEqual([job["job_id"] for job in items], ["eligible"])
        self.assertIsNone(cursor)
        self.assertEqual(len(db.jobs.calls), 2)
        self.assertEqual(db.jobs.calls[1]["ExclusiveStartKey"]["job_id"], "onlinejobs:old")

    def test_old_publication_moves_to_audit_even_after_manual_override(self):
        db = DynamoDBClient.__new__(DynamoDBClient)
        db.jobs = _FakeJobsTable()
        db.jobs.query = lambda **kwargs: {"Items": [{
            "job_id": "old", "posted_date": "2000-01-01", "score": 95, "filter_override": True,
        }]}
        items, _ = db.get_user_jobs("user-1", deal_breaker=False, discovery_profile={})
        self.assertEqual(items, [])
        audit, _ = db.get_user_jobs("user-1", deal_breaker=True, discovery_profile={})
        self.assertEqual(audit[0]["job_id"], "old")
        self.assertFalse(audit[0]["filter_override"])
        self.assertIn("older than 90 days", audit[0]["reasons"][0])

    def test_raw_history_remains_available_without_discovery_policy(self):
        db = DynamoDBClient.__new__(DynamoDBClient)
        db.jobs = _FakeJobsTable()
        db.jobs.query = lambda **kwargs: {"Items": [{"job_id": "applied-old", "posted_date": "2000-01-01", "applied": True}]}
        items, _ = db.get_user_jobs("user-1", applied=True)
        self.assertEqual(items[0]["job_id"], "applied-old")

    def test_active_queue_reads_the_newest_timestamp_index(self):
        db = DynamoDBClient.__new__(DynamoDBClient)
        db.jobs = _FakeJobsTable()

        items, next_key = db.get_user_jobs("user-1", limit=50, applied=False, dismissed=False)

        self.assertEqual(items[0]["job_id"], "freehire:new")
        self.assertIsNone(next_key)
        self.assertEqual(db.jobs.calls[0]["IndexName"], "user-timestamp-index")
        self.assertFalse(db.jobs.calls[0]["ScanIndexForward"])

    def test_index_rollout_keeps_the_legacy_queue_available(self):
        db = DynamoDBClient.__new__(DynamoDBClient)
        db.jobs = _IndexRolloutJobsTable()

        items, _ = db.get_user_jobs("user-1", limit=50, applied=False, dismissed=False)

        self.assertEqual(items[0]["job_id"], "legacy:row")
        self.assertIn("IndexName", db.jobs.calls[0])
        self.assertNotIn("IndexName", db.jobs.calls[1])

    def test_auto_filtered_queue_uses_the_same_timestamp_index(self):
        db = DynamoDBClient.__new__(DynamoDBClient)
        db.jobs = _FakeJobsTable()

        items, _ = db.get_user_jobs("user-1", limit=50, applied=False, dismissed=False, deal_breaker=True)

        self.assertEqual(items[0]["job_id"], "freehire:new")
        self.assertEqual(db.jobs.calls[0]["IndexName"], "user-timestamp-index")

    def test_legacy_unknown_seniority_is_returned_as_unclassified(self):
        db = DynamoDBClient.__new__(DynamoDBClient)
        db.jobs = _FakeJobsTable()
        db.jobs.query = lambda **_kwargs: {"Items": [{
            "job_id": "legacy:unknown", "timestamp": "2026-10-06T01:46:19+00:00", "score": 72,
            "seniority_level": "unknown",
        }]}

        items, _ = db.get_user_jobs("user-1", limit=50, applied=False, dismissed=False, deal_breaker=False)

        self.assertIsNone(items[0]["seniority_level"])


if __name__ == "__main__":
    unittest.main()
