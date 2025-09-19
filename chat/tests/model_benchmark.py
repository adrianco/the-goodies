#!/usr/bin/env python3
"""
Model Benchmark Suite for Chat Interface
=========================================

Comprehensive testing and comparison of LLM models.
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Any
import sys

# Add parent directories to path
sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.improved_chat import ImprovedChatInterface
from src.model_manager import ModelManager
from src.query_processor import QueryProcessor
from src.response_logger import ResponseLogger

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ModelBenchmark:
    """Complete model comparison benchmark suite"""

    def __init__(self, output_dir: Path = None):
        """
        Initialize benchmark suite

        Args:
            output_dir: Directory for results (defaults to chat/results)
        """
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / 'results'
        self.output_dir = output_dir
        self.output_dir.mkdir(exist_ok=True)

        # Load test queries
        test_file = Path(__file__).parent / 'test_queries.json'
        with open(test_file) as f:
            self.test_queries = json.load(f)

        # Initialize components
        self.model_manager = ModelManager()
        self.query_processor = QueryProcessor()
        self.response_logger = ResponseLogger(self.output_dir)

        # Results storage
        self.results = {}

    async def run_complete_benchmark(self) -> Dict[str, Any]:
        """
        Run full benchmark suite on all models

        Returns:
            Complete benchmark results
        """
        print("🚀 Starting Model Comparison Benchmark")
        print("=" * 50)

        # Check available models
        available_models = self.model_manager.list_available_models()
        print("\n📦 Available Models:")
        for model_name, info in available_models.items():
            status = "✅" if info['exists'] else "❌"
            size = f"({info.get('size_mb', 0):.1f} MB)" if info['exists'] else "(not found)"
            print(f"  {status} {model_name}: {info['description']} {size}")

        # Filter to existing models
        models_to_test = [name for name, info in available_models.items() if info['exists']]

        if not models_to_test:
            print("\n❌ No models found! Please download models to chat/models/")
            return {}

        print(f"\n🧪 Testing {len(models_to_test)} models with {self.count_queries()} queries")

        # Run benchmarks on each model
        for model_name in models_to_test:
            print(f"\n📊 Benchmarking {model_name}...")
            self.results[model_name] = await self.benchmark_model(model_name)

        # Calculate aggregate scores
        self.calculate_scores()

        # Save results
        self.save_results()

        # Generate report
        report_file = self.generate_report()

        print(f"\n✅ Benchmark Complete!")
        print(f"📈 Results saved to {self.output_dir}")
        print(f"📄 Report: {report_file}")

        return self.results

    async def benchmark_model(self, model_name: str) -> Dict[str, Any]:
        """
        Benchmark a single model

        Args:
            model_name: Name of model to benchmark

        Returns:
            Benchmark results for the model
        """
        results = {
            'model': model_name,
            'test_results': {},
            'metrics': {
                'total_queries': 0,
                'successful_queries': 0,
                'failed_queries': 0,
                'total_time_ms': 0,
                'average_time_ms': 0
            },
            'category_scores': {}
        }

        # Create chat interface for this model
        chat = ImprovedChatInterface(model_name=model_name)

        try:
            await chat.initialize()

            # Test each category
            for category_name, queries in self.test_queries.items():
                print(f"  Testing {category_name}: {len(queries)} queries")
                category_results = []

                for query_data in queries:
                    # Run query
                    result = await self.test_query(chat, query_data)
                    category_results.append(result)

                    # Update metrics
                    results['metrics']['total_queries'] += 1
                    if result['success']:
                        results['metrics']['successful_queries'] += 1
                        results['metrics']['total_time_ms'] += result.get('time_ms', 0)
                    else:
                        results['metrics']['failed_queries'] += 1

                results['test_results'][category_name] = category_results

                # Calculate category score
                results['category_scores'][category_name] = self.calculate_category_score(category_results)

            # Calculate averages
            if results['metrics']['successful_queries'] > 0:
                results['metrics']['average_time_ms'] = (
                    results['metrics']['total_time_ms'] / results['metrics']['successful_queries']
                )

        except Exception as e:
            logger.error(f"Error benchmarking {model_name}: {e}")
            results['error'] = str(e)

        finally:
            await chat.cleanup()

        return results

    async def test_query(self, chat: ImprovedChatInterface, query_data: Dict) -> Dict[str, Any]:
        """
        Test a single query

        Args:
            chat: Chat interface to test
            query_data: Query test data

        Returns:
            Test result
        """
        result = {
            'query_id': query_data['id'],
            'query': query_data['query'],
            'category': query_data.get('category', 'unknown'),
            'success': False
        }

        try:
            # Process query
            response = await chat.process_query(query_data['query'])

            # Evaluate response
            result['response'] = response['response'][:200]  # Truncate for storage
            result['time_ms'] = response['metrics']['response_time_ms']
            result['tool_used'] = response['intent']['tool']
            result['success'] = True

            # Check tool selection accuracy
            if 'expected_tool' in query_data:
                result['correct_tool'] = (response['intent']['tool'] == query_data['expected_tool'])
            else:
                result['correct_tool'] = None

            # Evaluate response quality
            result['quality_score'] = self.evaluate_response_quality(
                query_data['query'],
                response['response'],
                response.get('tool_result')
            )

        except Exception as e:
            logger.error(f"Error testing query {query_data['id']}: {e}")
            result['error'] = str(e)

        return result

    def evaluate_response_quality(self, query: str, response: str, tool_result: Any) -> float:
        """
        Evaluate the quality of a response

        Args:
            query: Original query
            response: Generated response
            tool_result: Result from tool execution

        Returns:
            Quality score between 0 and 1
        """
        score = 0.0

        # Check if response is not empty
        if response and len(response) > 10:
            score += 0.3

        # Check if response mentions relevant keywords from query
        query_words = set(query.lower().split())
        response_words = set(response.lower().split())
        overlap = len(query_words & response_words) / len(query_words) if query_words else 0
        score += overlap * 0.3

        # Check if tool result was incorporated (if available)
        if tool_result:
            if isinstance(tool_result, list) and len(tool_result) > 0:
                # Check if response mentions items from results
                if any(str(item) in response for item in tool_result[:3]):
                    score += 0.2
            score += 0.2  # Successful tool execution

        return min(score, 1.0)

    def calculate_category_score(self, category_results: List[Dict]) -> Dict[str, float]:
        """
        Calculate aggregate score for a category

        Args:
            category_results: List of test results for a category

        Returns:
            Category scores
        """
        if not category_results:
            return {'overall': 0.0}

        successful = sum(1 for r in category_results if r['success'])
        total = len(category_results)

        scores = {
            'success_rate': successful / total if total > 0 else 0,
            'average_time_ms': 0,
            'average_quality': 0,
            'tool_accuracy': 0
        }

        # Calculate averages for successful queries
        if successful > 0:
            successful_results = [r for r in category_results if r['success']]

            scores['average_time_ms'] = sum(r.get('time_ms', 0) for r in successful_results) / successful
            scores['average_quality'] = sum(r.get('quality_score', 0) for r in successful_results) / successful

            # Tool accuracy (for queries with expected tools)
            tool_checks = [r for r in successful_results if r.get('correct_tool') is not None]
            if tool_checks:
                scores['tool_accuracy'] = sum(1 for r in tool_checks if r['correct_tool']) / len(tool_checks)

        # Calculate overall score
        scores['overall'] = (
            scores['success_rate'] * 0.3 +
            scores['average_quality'] * 0.3 +
            scores['tool_accuracy'] * 0.2 +
            (1.0 - min(scores['average_time_ms'] / 5000, 1.0)) * 0.2  # Speed score
        )

        return scores

    def calculate_scores(self):
        """Calculate aggregate scores for all models"""
        for model_name, results in self.results.items():
            if 'error' in results:
                continue

            # Calculate overall model score
            category_scores = results.get('category_scores', {})
            if category_scores:
                overall_scores = [scores.get('overall', 0) for scores in category_scores.values()]
                results['overall_score'] = sum(overall_scores) / len(overall_scores)
            else:
                results['overall_score'] = 0

    def count_queries(self) -> int:
        """Count total number of test queries"""
        return sum(len(queries) for queries in self.test_queries.values())

    def save_results(self):
        """Save benchmark results to file"""
        results_file = self.output_dir / 'benchmark_results.json'
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        logger.info(f"Results saved to {results_file}")

    def generate_report(self) -> Path:
        """
        Generate markdown report

        Returns:
            Path to generated report
        """
        report_file = self.output_dir / 'benchmark_report.md'

        with open(report_file, 'w') as f:
            f.write("# LLM Model Benchmark Report\n\n")
            f.write(f"Total Queries Tested: {self.count_queries()}\n\n")

            # Model Comparison Table
            f.write("## Model Comparison\n\n")
            f.write("| Model | Overall Score | Success Rate | Avg Time (ms) | Tool Accuracy |\n")
            f.write("|-------|--------------|--------------|---------------|---------------|\n")

            for model_name, results in self.results.items():
                if 'error' in results:
                    f.write(f"| {model_name} | ERROR | - | - | - |\n")
                else:
                    metrics = results['metrics']
                    # Calculate aggregate tool accuracy
                    tool_accuracies = []
                    for cat_scores in results['category_scores'].values():
                        if 'tool_accuracy' in cat_scores:
                            tool_accuracies.append(cat_scores['tool_accuracy'])
                    avg_tool_accuracy = sum(tool_accuracies) / len(tool_accuracies) if tool_accuracies else 0

                    f.write(f"| {model_name} | "
                           f"{results.get('overall_score', 0):.2f} | "
                           f"{metrics['successful_queries']}/{metrics['total_queries']} | "
                           f"{metrics.get('average_time_ms', 0):.1f} | "
                           f"{avg_tool_accuracy:.1%} |\n")

            # Category Breakdown
            f.write("\n## Category Performance\n\n")
            for model_name, results in self.results.items():
                if 'error' not in results:
                    f.write(f"\n### {model_name}\n\n")
                    f.write("| Category | Success Rate | Avg Quality | Avg Time (ms) |\n")
                    f.write("|----------|--------------|-------------|---------------|\n")

                    for category, scores in results.get('category_scores', {}).items():
                        f.write(f"| {category} | "
                               f"{scores.get('success_rate', 0):.1%} | "
                               f"{scores.get('average_quality', 0):.2f} | "
                               f"{scores.get('average_time_ms', 0):.1f} |\n")

            # Recommendations
            f.write("\n## Recommendations\n\n")
            if self.results:
                # Find best model by score
                best_model = max(self.results.items(),
                               key=lambda x: x[1].get('overall_score', 0) if 'error' not in x[1] else 0)
                f.write(f"- **Best Overall**: {best_model[0]}\n")

                # Find fastest model
                fastest_model = min(self.results.items(),
                                  key=lambda x: x[1]['metrics'].get('average_time_ms', float('inf'))
                                  if 'error' not in x[1] else float('inf'))
                f.write(f"- **Fastest**: {fastest_model[0]}\n")

        logger.info(f"Report generated at {report_file}")
        return report_file


async def main():
    """Main entry point for benchmark suite"""
    benchmark = ModelBenchmark()
    results = await benchmark.run_complete_benchmark()

    # Print summary
    print("\n📊 Summary:")
    for model_name, result in results.items():
        if 'error' not in result:
            print(f"  {model_name}: Score={result.get('overall_score', 0):.2f}, "
                 f"Success={result['metrics']['successful_queries']}/{result['metrics']['total_queries']}")


if __name__ == "__main__":
    asyncio.run(main())