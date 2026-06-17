"""
GitHub Actions Integration for ADAPT-OPS

This module provides utilities to integrate ADAPT-OPS with GitHub Actions.
It collects workflow metrics and sends them to the ADAPT-OPS API for
anomaly detection and self-healing.
"""

import json
import os
import time
import requests
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class GitHubActionsMetricsCollector:
    """Collects CI/CD metrics from GitHub Actions workflow runs."""

    def __init__(
        self,
        github_token: str,
        repository: str,
        adapt_ops_url: str = "http://localhost:8000"
    ):
        self.github_token = github_token
        self.repository = repository
        self.adapt_ops_url = adapt_ops_url
        self.github_api_url = "https://api.github.com"

    def get_workflow_run_metrics(self, run_id: int) -> Optional[Dict]:
        """
        Fetch metrics from a GitHub Actions workflow run.
        
        Args:
            run_id: GitHub Actions workflow run ID
            
        Returns:
            Dict with pipeline metrics or None if fetch fails
        """
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }

        # Get workflow run details
        run_url = f"{self.github_api_url}/repos/{self.repository}/actions/runs/{run_id}"
        response = requests.get(run_url, headers=headers)
        if response.status_code != 200:
            logger.error(f"Failed to fetch workflow run {run_id}")
            return None

        run = response.json()
        
        # Calculate metrics
        started_at = run.get("run_number", 0)
        status = run.get("status", "unknown")
        conclusion = run.get("conclusion", "unknown")
        
        # Fetch job details for more metrics
        jobs_url = run["jobs_url"]
        jobs_response = requests.get(jobs_url, headers=headers)
        jobs = jobs_response.json().get("jobs", [])
        
        # Aggregate job metrics
        total_jobs = len(jobs)
        failed_jobs = sum(1 for j in jobs if j.get("conclusion") == "failure")
        
        # Estimate durations
        duration_secs = 0
        for job in jobs:
            if job.get("started_at") and job.get("completed_at"):
                started = time.fromisoformat(job["started_at"].replace("Z", "+00:00"))
                completed = time.fromisoformat(job["completed_at"].replace("Z", "+00:00"))
                duration_secs += (completed - started).total_seconds()
        
        # Calculate metrics for ADAPT-OPS
        failure_rate = failed_jobs / max(1, total_jobs)
        build_duration = duration_secs
        
        metrics = {
            "build_duration_secs": build_duration,
            "test_pass_rate": 1.0 - failure_rate,
            "failure_rate": failure_rate,
            "queue_depth": 0,  # Would need more context to calculate
            "cpu_utilization": 0.5,  # Placeholder
            "memory_utilization": 0.5,  # Placeholder
            "deploy_success_rate": 1.0 if conclusion == "success" else 0.0,
            "flaky_test_count": 0,  # Would need test report parsing
            "retry_count": int(run.get("run_number", 0)) - int(run.get("workflow_id", 1)),
        }
        
        return metrics

    def send_metrics_to_adapt_ops(self, metrics: Dict) -> Optional[Dict]:
        """
        Send metrics to ADAPT-OPS API.
        
        Args:
            metrics: Pipeline metrics dict
            
        Returns:
            ADAPT-OPS response or None if request fails
        """
        try:
            response = requests.post(
                f"{self.adapt_ops_url}/ingest",
                json=metrics,
                timeout=10
            )
            if response.status_code == 200:
                logger.info("Metrics sent to ADAPT-OPS")
                return response.json()
            else:
                logger.warning(f"ADAPT-OPS returned {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Failed to send metrics to ADAPT-OPS: {e}")
            return None

    def process_workflow_run(self, run_id: int) -> bool:
        """
        Full workflow: collect metrics and send to ADAPT-OPS.
        
        Args:
            run_id: GitHub Actions workflow run ID
            
        Returns:
            True if successful, False otherwise
        """
        metrics = self.get_workflow_run_metrics(run_id)
        if not metrics:
            return False

        result = self.send_metrics_to_adapt_ops(metrics)
        return result is not None


def create_from_github_env() -> Optional[GitHubActionsMetricsCollector]:
    """
    Create collector from GitHub Actions environment variables.
    
    Expected env vars:
    - GITHUB_TOKEN: GitHub API token
    - GITHUB_REPOSITORY: owner/repo
    - ADAPT_OPS_URL: ADAPT-OPS API URL (optional, defaults to localhost:8000)
    
    Returns:
        GitHubActionsMetricsCollector or None if env vars missing
    """
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPOSITORY")
    url = os.getenv("ADAPT_OPS_URL", "http://localhost:8000")
    
    if not token or not repo:
        logger.error("Missing GITHUB_TOKEN or GITHUB_REPOSITORY env vars")
        return None

    return GitHubActionsMetricsCollector(token, repo, url)
