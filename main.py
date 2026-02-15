#!/usr/bin/env python3
"""
AI Agent-Powered Evaluation Platform - Main Runner

This is the main entry point for running evaluations against AI services.

"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.llm_client import get_llm_client, OpenAIClient, MockLLMClient
from core.models import EvaluationRun, TestCase, TestCaseType
from agents.orchestrator import OrchestratorAgent


def load_knowledge_base(kb_path: str) -> str:
    """Load knowledge base content from a directory or file."""
    
    path = Path(kb_path)
    
    if path.is_file():
        # Single file
        if path.suffix.lower() == ".pdf":
            return load_pdf(path)
        else:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    
    elif path.is_dir():
        # Directory of files
        content_parts = []
        
        for file_path in sorted(path.iterdir()):
            if file_path.is_file() and file_path.suffix.lower() in [".txt", ".md", ".pdf"]:
                try:
                    if file_path.suffix.lower() == ".pdf":
                        print(f"   Loading PDF: {file_path.name}")
                        pdf_content = load_pdf(file_path)
                        content_parts.append(f"# {file_path.name}\n{pdf_content}")
                    else:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content_parts.append(f"# {file_path.name}\n{f.read()}")
                except Exception as e:
                    print(f"   Warning: Could not load {file_path.name}: {e}")
        
        return "\n\n".join(content_parts)
    
    else:
        raise ValueError(f"Knowledge base path not found: {kb_path}")


def load_pdf(pdf_path: Path) -> str:
    """Load ALL content from a PDF file."""
    try:
        from pypdf import PdfReader
        
        reader = PdfReader(str(pdf_path))
        total_pages = len(reader.pages)
        
        text_parts = []
        for i in range(total_pages):
            page_text = reader.pages[i].extract_text()
            if page_text:
                text_parts.append(page_text)
        
        print(f"      → Loaded {total_pages} pages")
        return "\n".join(text_parts)
    
    except ImportError:
        print("   Warning: pypdf not installed. Run: pip install pypdf")
        return f"[PDF content not loaded - install pypdf]"
    except Exception as e:
        return f"[Error loading PDF: {e}]"


def print_results(run: EvaluationRun, verbose: bool = False):
    """Print evaluation results in a nice format."""
    
    print("\n" + "=" * 70)
    print("🤖 AI AGENT-POWERED EVALUATION RESULTS")
    print("=" * 70)
    
    print(f"\n📋 Run: {run.name}")
    print(f"🔗 Service: {run.service_endpoint}")
    print(f"🕐 Started: {run.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
    if run.completed_at:
        duration = (run.completed_at - run.started_at).total_seconds()
        print(f"⏱️  Duration: {duration:.1f}s")
    
    print("\n" + "-" * 70)
    print("📊 SUMMARY")
    print("-" * 70)
    
    # Pass/Fail visualization
    pass_bar = "🟢" * run.passed_tests + "🔴" * run.failed_tests
    print(f"\nTest Results: {pass_bar}")
    print(f"  Total: {run.total_tests} | Passed: {run.passed_tests} | Failed: {run.failed_tests}")
    print(f"  Pass Rate: {run.pass_rate:.1%}")
    print(f"  Mean Score: {run.mean_score:.2f}")
    
    # Issues summary
    all_issues = []
    for result in run.test_results:
        all_issues.extend(result.issues)
    
    if all_issues:
        print(f"\n⚠️  Issues Found: {len(all_issues)}")
        severity_counts = {}
        for issue in all_issues:
            sev = issue.severity.value
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        
        for sev, count in sorted(severity_counts.items()):
            emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}.get(sev, "⚪")
            print(f"    {emoji} {sev.upper()}: {count}")
    
    print("\n" + "-" * 70)
    print("📝 TEST DETAILS")
    print("-" * 70)
    
    for i, result in enumerate(run.test_results, 1):
        status_emoji = "✅" if result.overall_result.value == "pass" else "❌"
        print(f"\n{i}. {status_emoji} {result.test_case.name}")
        print(f"   Query: {result.test_case.query[:80]}...")
        print(f"   Score: {result.overall_score:.2f} | Result: {result.overall_result.value.upper()}")
        
        if verbose:
            print(f"   Response: {result.service_response.response_text[:150]}...")
            if result.issues:
                print(f"   Issues:")
                for issue in result.issues[:3]:
                    print(f"      - [{issue.severity.value}] {issue.title}")
    
    # Agent traces summary
    if run.agent_traces:
        print("\n" + "-" * 70)
        print("🔍 AGENT TRACES")
        print("-" * 70)
        
        for trace in run.agent_traces:
            print(f"\n  📌 {trace.agent_name}: {trace.task_description[:50]}...")
            print(f"     Actions: {len(trace.actions)} | Latency: {trace.total_latency_ms}ms")
            if verbose:
                for action in trace.actions[:5]:
                    print(f"       → {action.action_type.value}: {action.description[:50]}")
    
    print("\n" + "=" * 70)
    print("✨ Evaluation Complete")
    print("=" * 70 + "\n")


async def run_evaluation(
    service_url: str,
    kb_path: str,
    service_type: str = "simple",
    num_tests: int = 5,
    llm_provider: str = "openai",
    verbose: bool = False,
    output_file: str = None,
):
    """Run the evaluation."""
    
    print("\n🚀 Starting AI Agent-Powered Evaluation Platform")
    print("=" * 50)
    
    # Load knowledge base
    print(f"\n📚 Loading knowledge base from: {kb_path}")
    try:
        kb_content = load_knowledge_base(kb_path)
        print(f"   Loaded {len(kb_content)} characters")
    except Exception as e:
        print(f"❌ Error loading knowledge base: {e}")
        return
    
    # Initialize LLM client
    print(f"\n🧠 Initializing LLM client: {llm_provider}")
    try:
        if llm_provider == "mock":
            llm_client = MockLLMClient()
            print("   Using mock LLM (for testing)")
        else:
            llm_client = get_llm_client(llm_provider)
            print(f"   Connected to {llm_provider}")
    except Exception as e:
        print(f"❌ Error initializing LLM: {e}")
        print("   Make sure OPENAI_API_KEY or ANTHROPIC_API_KEY is set")
        return
    
    # Initialize orchestrator
    print(f"\n🤖 Initializing Orchestrator Agent")
    print(f"   Service URL: {service_url}")
    print(f"   Service Type: {service_type}")
    
    orchestrator = OrchestratorAgent(
        llm_client=llm_client,
        service_endpoint=service_url,
        service_type=service_type,
    )
    
    # Run evaluation
    print(f"\n🏃 Running evaluation with {num_tests} test cases...")
    print("   This may take a few minutes...\n")
    
    try:
        run = await orchestrator.execute(
            knowledge_base_content=kb_content,
            run_name=f"Evaluation - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            num_tests=num_tests,
        )
        
        # Print results
        print_results(run, verbose=verbose)
        
        # Save to file if requested
        if output_file:
            output_data = {
                "run": run.to_dict(),
                "test_results": [r.to_dict() for r in run.test_results],
                "agent_traces": [t.to_dict() for t in run.agent_traces],
            }
            with open(output_file, "w") as f:
                json.dump(output_data, f, indent=2, default=str)
            print(f"\n💾 Results saved to: {output_file}")
        
        return run
        
    except Exception as e:
        print(f"\n❌ Evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    parser = argparse.ArgumentParser(
        description="AI Agent-Powered Evaluation Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Evaluate a simple RAG service
  python main.py --service-url http://localhost:9090 --kb-path ./knowledge_base

  # Evaluate an OpenAI-compatible service
  python main.py --service-url http://localhost:8000 --service-type openai_compatible --kb-path ./docs

  # Run with more tests and verbose output
  python main.py --service-url http://localhost:9090 --kb-path ./kb --num-tests 10 --verbose

  # Save results to file
  python main.py --service-url http://localhost:9090 --kb-path ./kb --output results.json
        """
    )
    
    parser.add_argument(
        "--service-url",
        required=True,
        help="URL of the AI service to evaluate (e.g., http://localhost:9090)"
    )
    
    parser.add_argument(
        "--kb-path",
        required=True,
        help="Path to knowledge base (directory or file)"
    )
    
    parser.add_argument(
        "--service-type",
        choices=["simple", "openai_compatible"],
        default="simple",
        help="Type of service API (default: simple)"
    )
    
    parser.add_argument(
        "--num-tests",
        type=int,
        default=5,
        help="Number of test cases to generate (default: 5)"
    )
    
    parser.add_argument(
        "--llm-provider",
        choices=["openai", "anthropic", "mock"],
        default="openai",
        help="LLM provider for test generation and evaluation (default: openai)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show verbose output"
    )
    
    parser.add_argument(
        "--output", "-o",
        help="Output file for JSON results"
    )
    
    args = parser.parse_args()
    
    # Run the evaluation
    asyncio.run(run_evaluation(
        service_url=args.service_url,
        kb_path=args.kb_path,
        service_type=args.service_type,
        num_tests=args.num_tests,
        llm_provider=args.llm_provider,
        verbose=args.verbose,
        output_file=args.output,
    ))


if __name__ == "__main__":
    main()
