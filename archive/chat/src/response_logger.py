"""
Response Logger for Model Comparison
=====================================

Logs responses and metrics for comparison analysis.
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime


class ResponseLogger:
    """Log responses and metrics for model comparison"""

    def __init__(self, log_dir: Path = None):
        """
        Initialize response logger

        Args:
            log_dir: Directory for log files (defaults to chat/results)
        """
        if log_dir is None:
            log_dir = Path(__file__).parent.parent / 'results'
        self.log_dir = log_dir
        self.log_dir.mkdir(exist_ok=True)

        # Create session log file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.session_file = self.log_dir / f'session_{timestamp}.jsonl'
        self.comparison_file = self.log_dir / f'comparison_{timestamp}.json'

        # In-memory storage for current session
        self.session_logs = []
        self.comparisons = {}

    def log(self, response: Dict[str, Any]):
        """
        Log a single response

        Args:
            response: Response dictionary with query, response, and metrics
        """
        # Add timestamp if not present
        if 'timestamp' not in response:
            response['timestamp'] = time.time()

        # Add to session logs
        self.session_logs.append(response)

        # Write to JSONL file (append mode)
        with open(self.session_file, 'a') as f:
            f.write(json.dumps(response) + '\n')

    def log_comparison(self, query: str, results: Dict[str, Dict[str, Any]]):
        """
        Log a comparison result across multiple models

        Args:
            query: The query that was tested
            results: Dictionary of model_name -> response data
        """
        comparison = {
            'query': query,
            'timestamp': time.time(),
            'results': results,
            'analysis': self._analyze_comparison(results)
        }

        # Store in memory
        self.comparisons[query] = comparison

        # Write to comparison file
        with open(self.comparison_file, 'w') as f:
            json.dump(self.comparisons, f, indent=2)

    def _analyze_comparison(self, results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze comparison results to identify best performing model

        Args:
            results: Model results to analyze

        Returns:
            Analysis dictionary with rankings and insights
        """
        analysis = {
            'fastest_model': None,
            'longest_response': None,
            'most_tokens': None,
            'highest_tps': None,  # Tokens per second
            'response_times': {},
            'response_lengths': {}
        }

        fastest_time = float('inf')
        longest_response = 0
        most_tokens = 0
        highest_tps = 0

        for model_name, result in results.items():
            if 'error' in result:
                continue

            # Track response time
            if 'time_ms' in result:
                time_ms = result['time_ms']
                analysis['response_times'][model_name] = time_ms
                if time_ms < fastest_time:
                    fastest_time = time_ms
                    analysis['fastest_model'] = model_name

            # Track response length
            if 'response' in result and result['response']:
                length = len(result['response'])
                analysis['response_lengths'][model_name] = length
                if length > longest_response:
                    longest_response = length
                    analysis['longest_response'] = model_name

            # Track tokens
            if 'tokens_generated' in result:
                tokens = result['tokens_generated']
                if tokens > most_tokens:
                    most_tokens = tokens
                    analysis['most_tokens'] = model_name

            # Track tokens per second
            if 'tokens_per_second' in result:
                tps = result['tokens_per_second']
                if tps > highest_tps:
                    highest_tps = tps
                    analysis['highest_tps'] = model_name

        return analysis

    def get_session_summary(self) -> Dict[str, Any]:
        """
        Get summary of current session

        Returns:
            Summary statistics for the session
        """
        if not self.session_logs:
            return {'message': 'No logs in current session'}

        summary = {
            'total_queries': len(self.session_logs),
            'models_used': list(set(log['model'] for log in self.session_logs if 'model' in log)),
            'average_response_time': 0,
            'tools_used': {},
            'session_file': str(self.session_file)
        }

        # Calculate average response time
        response_times = [
            log['metrics']['response_time_ms']
            for log in self.session_logs
            if 'metrics' in log and 'response_time_ms' in log['metrics']
        ]
        if response_times:
            summary['average_response_time'] = sum(response_times) / len(response_times)

        # Count tool usage
        for log in self.session_logs:
            if 'intent' in log and log['intent'].get('tool'):
                tool = log['intent']['tool']
                summary['tools_used'][tool] = summary['tools_used'].get(tool, 0) + 1

        return summary

    def get_comparison_summary(self) -> Dict[str, Any]:
        """
        Get summary of all comparisons

        Returns:
            Summary of model comparisons
        """
        if not self.comparisons:
            return {'message': 'No comparisons run yet'}

        # Aggregate statistics across all comparisons
        model_stats = {}

        for query, comparison in self.comparisons.items():
            for model_name, result in comparison['results'].items():
                if model_name not in model_stats:
                    model_stats[model_name] = {
                        'total_queries': 0,
                        'total_time_ms': 0,
                        'total_tokens': 0,
                        'errors': 0
                    }

                stats = model_stats[model_name]
                stats['total_queries'] += 1

                if 'error' in result:
                    stats['errors'] += 1
                else:
                    if 'time_ms' in result:
                        stats['total_time_ms'] += result['time_ms']
                    if 'tokens_generated' in result:
                        stats['total_tokens'] += result['tokens_generated']

        # Calculate averages
        for model_name, stats in model_stats.items():
            successful_queries = stats['total_queries'] - stats['errors']
            if successful_queries > 0:
                stats['avg_time_ms'] = stats['total_time_ms'] / successful_queries
                stats['avg_tokens'] = stats['total_tokens'] / successful_queries

        return {
            'total_comparisons': len(self.comparisons),
            'model_statistics': model_stats,
            'comparison_file': str(self.comparison_file)
        }

    def export_report(self, output_file: Path = None) -> Path:
        """
        Export a formatted report of all logs and comparisons

        Args:
            output_file: Output file path (defaults to results/report_timestamp.md)

        Returns:
            Path to the generated report
        """
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = self.log_dir / f'report_{timestamp}.md'

        session_summary = self.get_session_summary()
        comparison_summary = self.get_comparison_summary()

        with open(output_file, 'w') as f:
            f.write("# Chat Model Evaluation Report\n\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            # Session Summary
            f.write("## Session Summary\n\n")
            f.write(f"- Total Queries: {session_summary.get('total_queries', 0)}\n")
            f.write(f"- Models Used: {', '.join(session_summary.get('models_used', []))}\n")
            f.write(f"- Avg Response Time: {session_summary.get('average_response_time', 0):.1f}ms\n\n")

            # Tool Usage
            if session_summary.get('tools_used'):
                f.write("### Tool Usage\n\n")
                for tool, count in session_summary['tools_used'].items():
                    f.write(f"- {tool}: {count} times\n")
                f.write("\n")

            # Comparison Summary
            if comparison_summary.get('model_statistics'):
                f.write("## Model Comparison Results\n\n")
                f.write("| Model | Queries | Avg Time (ms) | Avg Tokens | Errors |\n")
                f.write("|-------|---------|---------------|------------|--------|\n")

                for model, stats in comparison_summary['model_statistics'].items():
                    f.write(f"| {model} | {stats['total_queries']} | "
                           f"{stats.get('avg_time_ms', 0):.1f} | "
                           f"{stats.get('avg_tokens', 0):.1f} | "
                           f"{stats['errors']} |\n")

            # Sample Queries
            if self.session_logs:
                f.write("\n## Sample Queries and Responses\n\n")
                for i, log in enumerate(self.session_logs[:5]):  # First 5 queries
                    f.write(f"### Query {i+1}\n\n")
                    f.write(f"**Query:** {log.get('query', 'N/A')}\n\n")
                    f.write(f"**Model:** {log.get('model', 'N/A')}\n\n")
                    f.write(f"**Response:** {log.get('response', 'N/A')}\n\n")
                    if 'metrics' in log:
                        f.write(f"**Response Time:** {log['metrics'].get('response_time_ms', 0):.1f}ms\n\n")
                    f.write("---\n\n")

        return output_file