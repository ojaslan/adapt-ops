"""
Persistence layer for metrics history and MAB state.
Handles JSON-based storage for simplicity (can swap for SQLite/PostgreSQL).
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import threading
import config


class MetricStore:
    """Thread-safe metrics persistence."""
    
    def __init__(self, db_path: Path = config.DATA_DIR / "metrics.jsonl"):
        self.db_path = db_path
        self.lock = threading.RLock()
        self.db_path.parent.mkdir(exist_ok=True, parents=True)
    
    def append_metric(self, metric_dict: Dict[str, Any]) -> None:
        """Append metric to JSONL file."""
        with self.lock:
            metric_dict['_stored_at'] = datetime.utcnow().isoformat()
            with open(self.db_path, 'a') as f:
                f.write(json.dumps(metric_dict) + '\n')
            
            # Trim history if too large
            self._trim_history()
    
    def _trim_history(self) -> None:
        """Keep only last N metrics."""
        if self.db_path.stat().st_size > 10_000_000:  # ~10MB
            lines = []
            with open(self.db_path, 'r') as f:
                lines = f.readlines()
            
            if len(lines) > config.MAX_HISTORY_SIZE:
                with open(self.db_path, 'w') as f:
                    f.writelines(lines[-config.MAX_HISTORY_SIZE:])
    
    def get_metrics(self, limit: int = 100, hours_back: int = 24) -> List[Dict]:
        """Fetch recent metrics."""
        if not self.db_path.exists():
            return []
        
        cutoff = datetime.utcnow() - timedelta(hours=hours_back)
        metrics = []
        
        with self.lock:
            try:
                with open(self.db_path, 'r') as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            m = json.loads(line)
                            stored_at = datetime.fromisoformat(m.get('_stored_at', ''))
                            if stored_at >= cutoff:
                                metrics.append(m)
                        except (json.JSONDecodeError, ValueError):
                            continue
            except FileNotFoundError:
                pass
        
        return metrics[-limit:]
    
    def get_stats_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Aggregate metrics stats."""
        metrics = self.get_metrics(limit=10000, hours_back=hours)
        
        if not metrics:
            return {
                'total_count': 0,
                'anomalies_detected': 0,
                'healings_triggered': 0,
                'healing_success_rate': 0.0,
                'avg_build_duration': 0.0,
                'avg_test_pass_rate': 0.0
            }
        
        anomalies = len([m for m in metrics if m.get('anomaly_detected')])
        healings = len([m for m in metrics if m.get('healing_triggered')])
        successful = len([m for m in metrics if m.get('healing_successful')])
        healing_rate = (successful / healings * 100) if healings > 0 else 0.0
        
        build_durations = [m.get('build_duration_secs', 0) for m in metrics]
        test_rates = [m.get('test_pass_rate', 0) for m in metrics]
        
        return {
            'total_count': len(metrics),
            'time_window_hours': hours,
            'anomalies_detected': anomalies,
            'healings_triggered': healings,
            'healing_success_rate': round(healing_rate, 2),
            'avg_build_duration': round(sum(build_durations) / len(build_durations), 2) if build_durations else 0,
            'avg_test_pass_rate': round(sum(test_rates) / len(test_rates), 2) if test_rates else 0,
        }


class AnomalyStore:
    """Track anomalies for analysis."""
    
    def __init__(self, db_path: Path = config.DATA_DIR / "anomalies.jsonl"):
        self.db_path = db_path
        self.lock = threading.RLock()
        self.db_path.parent.mkdir(exist_ok=True, parents=True)
    
    def record_anomaly(self, anomaly_type: str, severity: str, score: float, context: Dict) -> None:
        """Record detected anomaly."""
        with self.lock:
            record = {
                'timestamp': datetime.utcnow().isoformat(),
                'type': anomaly_type,
                'severity': severity,
                'score': round(score, 3),
                'context': context
            }
            with open(self.db_path, 'a') as f:
                f.write(json.dumps(record) + '\n')
    
    def get_anomalies(self, limit: int = 100, anomaly_type: Optional[str] = None) -> List[Dict]:
        """Fetch recent anomalies."""
        if not self.db_path.exists():
            return []
        
        anomalies = []
        with self.lock:
            try:
                with open(self.db_path, 'r') as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            a = json.loads(line)
                            if anomaly_type is None or a.get('type') == anomaly_type:
                                anomalies.append(a)
                        except json.JSONDecodeError:
                            continue
            except FileNotFoundError:
                pass
        
        return anomalies[-limit:]
    
    def get_anomaly_stats(self) -> Dict[str, Any]:
        """Aggregate anomaly stats."""
        anomalies = self.get_anomalies(limit=10000)
        
        if not anomalies:
            return {'total': 0, 'by_type': {}, 'by_severity': {}}
        
        by_type = {}
        by_severity = {}
        
        for a in anomalies:
            atype = a.get('type', 'unknown')
            severity = a.get('severity', 'LOW')
            by_type[atype] = by_type.get(atype, 0) + 1
            by_severity[severity] = by_severity.get(severity, 0) + 1
        
        return {
            'total': len(anomalies),
            'by_type': by_type,
            'by_severity': by_severity
        }


class HealingStore:
    """Track healing actions and outcomes."""
    
    def __init__(self, db_path: Path = config.DATA_DIR / "healings.jsonl"):
        self.db_path = db_path
        self.lock = threading.RLock()
        self.db_path.parent.mkdir(exist_ok=True, parents=True)
    
    def record_healing(
        self,
        anomaly_type: str,
        action: str,
        success: bool,
        reward: float,
        metadata: Dict = None
    ) -> None:
        """Record healing attempt."""
        with self.lock:
            record = {
                'timestamp': datetime.utcnow().isoformat(),
                'anomaly': anomaly_type,
                'action': action,
                'success': success,
                'reward': round(reward, 3),
                'metadata': metadata or {}
            }
            with open(self.db_path, 'a') as f:
                f.write(json.dumps(record) + '\n')
    
    def get_healings(self, limit: int = 100, action: Optional[str] = None) -> List[Dict]:
        """Fetch recent healings."""
        if not self.db_path.exists():
            return []
        
        healings = []
        with self.lock:
            try:
                with open(self.db_path, 'r') as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            h = json.loads(line)
                            if action is None or h.get('action') == action:
                                healings.append(h)
                        except json.JSONDecodeError:
                            continue
            except FileNotFoundError:
                pass
        
        return healings[-limit:]
    
    def get_action_performance(self) -> Dict[str, Dict[str, Any]]:
        """Get performance metrics per action."""
        healings = self.get_healings(limit=10000)
        
        performance = {}
        for h in healings:
            action = h.get('action', 'unknown')
            if action not in performance:
                performance[action] = {'count': 0, 'successes': 0, 'total_reward': 0.0}
            
            performance[action]['count'] += 1
            if h.get('success'):
                performance[action]['successes'] += 1
            performance[action]['total_reward'] += h.get('reward', 0)
        
        # Calculate rates
        for action in performance:
            p = performance[action]
            p['success_rate'] = round(p['successes'] / p['count'] * 100, 2) if p['count'] > 0 else 0
            p['avg_reward'] = round(p['total_reward'] / p['count'], 3) if p['count'] > 0 else 0
        
        return performance
