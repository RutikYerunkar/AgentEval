"""
Orchestrator Agent - Coordinates the entire evaluation pipeline.
This is the main agent that users interact with.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent
from agents.test_generator import TestGeneratorAgent
from agents.executor import TestExecutorAgent, ServiceClient, OpenAICompatibleClient
from agents.evaluator import EvaluatorAgent
from core.models import (
    AgentActionType,
    AgentTrace,
    EvaluationResult,
    EvaluationRun,
    TestCase,
    TestResult,
)
from core.llm_client import BaseLLMClient


class OrchestratorAgent(BaseAgent):
    """
    Main orchestrator that coordinates test generation, execution, and evaluation.
    
    This agent:
    1. Plans the evaluation strategy
    2. Coordinates test generation
    3. Manages test execution
    4. Orchestrates evaluation
    5. Synthesizes results
    """
    
    def __init__(
        self,
        llm_client: BaseLLMClient,
        service_endpoint: str,
        service_type: str = "simple",  # "simple" or "openai_compatible"
    ):
        super().__init__("Orchestrator", llm_client)
        
        # Initialize sub-agents
        self.test_generator = TestGeneratorAgent(llm_client)
        
        # Initialize service client based on type
        if service_type == "openai_compatible":
            service_client = OpenAICompatibleClient(service_endpoint)
        else:
            service_client = ServiceClient(service_endpoint)
        
        self.executor = TestExecutorAgent(llm_client, service_client)
        self.evaluator = EvaluatorAgent(llm_client)
        
        self.service_endpoint = service_endpoint
    
    async def execute(
        self,
        knowledge_base_content: str,
        run_name: str = "Evaluation Run",
        num_tests: int = 10,
        archetypes: Optional[List[str]] = None,
        custom_tests: Optional[List[TestCase]] = None,
    ) -> EvaluationRun:
        """
        Execute a complete evaluation run.
        
        Args:
            knowledge_base_content: Content of the knowledge base
            run_name: Name for this evaluation run
            num_tests: Number of tests to generate (if not using custom_tests)
            archetypes: List of test archetypes to use
            custom_tests: Optional list of pre-defined test cases
        
        Returns:
            EvaluationRun with complete results
        """
        
        self.start_trace(f"Orchestrate evaluation: {run_name}")
        
        run = EvaluationRun(
            name=run_name,
            service_endpoint=self.service_endpoint,
        )
        
        try:
            # Step 1: Plan the evaluation
            self.log_action(
                action_type=AgentActionType.PLAN,
                description="Planning evaluation strategy",
                input_data={
                    "kb_length": len(knowledge_base_content),
                    "num_tests": num_tests,
                    "archetypes": archetypes,
                },
            )
            
            plan = await self._create_evaluation_plan(
                knowledge_base_content, num_tests, archetypes
            )
            
            # Step 2: Generate or use test cases
            if custom_tests:
                test_cases = custom_tests
                self.log_action(
                    action_type=AgentActionType.GENERATE_TEST,
                    description=f"Using {len(custom_tests)} custom test cases",
                )
            else:
                self.log_action(
                    action_type=AgentActionType.GENERATE_TEST,
                    description=f"Generating {num_tests} test cases",
                )
                test_cases = await self.test_generator.execute(
                    knowledge_base_content,
                    num_tests=num_tests,
                    archetypes=archetypes,
                )
                run.agent_traces.append(self.test_generator.current_trace)
            
            run.total_tests = len(test_cases)
            
            # Step 3: Execute tests
            self.log_action(
                action_type=AgentActionType.EXECUTE_TEST,
                description=f"Executing {len(test_cases)} tests against service",
            )
            
            execution_results = await self.executor.execute(test_cases)
            run.agent_traces.append(self.executor.current_trace)
            
            # Step 4: Evaluate responses
            self.log_action(
                action_type=AgentActionType.EVALUATE,
                description="Evaluating all responses",
            )
            
            for test_case, service_response in execution_results:
                result = await self.evaluator.execute(
                    test_case,
                    service_response,
                    knowledge_base_context=knowledge_base_content[:10000],
                )
                run.test_results.append(result)
                
                if result.overall_result == EvaluationResult.PASS:
                    run.passed_tests += 1
                else:
                    run.failed_tests += 1
            
            run.agent_traces.append(self.evaluator.current_trace)
            
            # Step 5: Synthesize results
            self.log_action(
                action_type=AgentActionType.SYNTHESIZE,
                description="Synthesizing evaluation results",
            )
            
            synthesis = await self._synthesize_results(run)
            
            run.completed_at = datetime.utcnow()
            run.description = synthesis.get("summary", "")
            
            self.log_action(
                action_type=AgentActionType.SYNTHESIZE,
                description="Evaluation complete",
                output_data={
                    "total_tests": run.total_tests,
                    "passed": run.passed_tests,
                    "failed": run.failed_tests,
                    "pass_rate": f"{run.pass_rate:.1%}",
                },
            )
            
            self.end_trace(success=True, output=run)
            run.agent_traces.append(self.current_trace)
            
            return run
            
        except Exception as e:
            self.end_trace(success=False, error=str(e))
            run.description = f"Evaluation failed: {str(e)}"
            run.completed_at = datetime.utcnow()
            return run
    
    async def _create_evaluation_plan(
        self,
        kb_content: str,
        num_tests: int,
        archetypes: Optional[List[str]],
    ) -> Dict[str, Any]:
        """Create a plan for the evaluation."""
        
        prompt = f"""Create an evaluation plan for testing a RAG-based AI service.

## Knowledge Base Preview
{kb_content[:5000]}...

## Parameters
- Number of tests: {num_tests}
- Requested archetypes: {archetypes or "all available"}

## Available Test Archetypes
- factual_recall: Direct fact retrieval
- synthesis: Combining multiple sources
- ambiguity_handling: Unclear queries
- out_of_scope: Questions outside KB
- adversarial: Tricky/misleading queries
- multi_step: Complex reasoning

## Instructions
Create a test distribution plan. Consider:
1. Coverage of key topics in the KB
2. Balance of difficulty levels
3. Mix of test types

Return JSON:
{{
    "strategy": "brief description of testing strategy",
    "archetype_distribution": {{"archetype_name": count}},
    "focus_areas": ["areas to focus testing on"],
    "risk_areas": ["potential problem areas to probe"]
}}"""
        
        return await self.think_json(prompt)
    
    async def _synthesize_results(self, run: EvaluationRun) -> Dict[str, Any]:
        """Synthesize the evaluation results into insights."""
        
        # Collect all issues
        all_issues = []
        for result in run.test_results:
            all_issues.extend([i.to_dict() for i in result.issues])
        
        # Collect scores by criterion
        scores_by_criterion = {}
        for result in run.test_results:
            for score in result.scores:
                if score.criterion not in scores_by_criterion:
                    scores_by_criterion[score.criterion] = []
                scores_by_criterion[score.criterion].append(score.score)
        
        avg_scores = {
            k: sum(v) / len(v) if v else 0
            for k, v in scores_by_criterion.items()
        }
        
        prompt = f"""Synthesize evaluation results for a RAG AI service.

## Summary Statistics
- Total Tests: {run.total_tests}
- Passed: {run.passed_tests}
- Failed: {run.failed_tests}
- Pass Rate: {run.pass_rate:.1%}
- Mean Score: {run.mean_score:.2f}

## Scores by Criterion
{json.dumps(avg_scores, indent=2)}

## Issues Found ({len(all_issues)} total)
{json.dumps(all_issues[:20], indent=2)}  # First 20 issues

## Failed Tests
{json.dumps([r.to_dict() for r in run.test_results if r.overall_result != EvaluationResult.PASS][:10], indent=2)}

## Instructions
Provide:
1. Executive summary (2-3 sentences)
2. Key strengths identified
3. Critical issues that need attention
4. Specific recommendations

Return JSON:
{{
    "summary": "executive summary",
    "strengths": ["strength 1", "strength 2"],
    "critical_issues": ["issue 1", "issue 2"],
    "recommendations": ["recommendation 1", "recommendation 2"],
    "risk_level": "low|medium|high|critical"
}}"""
        
        return await self.think_json(prompt)
    
    async def run_quick_evaluation(
        self,
        knowledge_base_content: str,
        num_tests: int = 5,
    ) -> Dict[str, Any]:
        """
        Run a quick evaluation and return a summary.
        Useful for demos and quick checks.
        """
        
        run = await self.execute(
            knowledge_base_content=knowledge_base_content,
            run_name="Quick Evaluation",
            num_tests=num_tests,
            archetypes=["factual_recall", "adversarial"],
        )
        
        return {
            "run_id": run.run_id,
            "summary": run.to_dict(),
            "test_results": [r.to_dict() for r in run.test_results],
            "traces": [t.to_dict() for t in run.agent_traces],
        }
