"""
Evaluator Agent - Evaluates AI service responses using LLM-based judging.
"""

import json
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent
from core.models import (
    AgentActionType,
    EvaluationResult,
    EvaluationScore,
    Issue,
    ServiceResponse,
    Severity,
    TestCase,
    TestResult,
)
from core.llm_client import BaseLLMClient


# Evaluation criteria definitions
EVALUATION_CRITERIA = {
    "relevance": {
        "name": "Relevance",
        "description": "Does the response directly address the question asked?",
        "weight": 1.5,
    },
    "accuracy": {
        "name": "Factual Accuracy",
        "description": "Are the facts in the response correct based on the knowledge base?",
        "weight": 2.0,
    },
    "completeness": {
        "name": "Completeness",
        "description": "Does the response cover all relevant aspects of the question?",
        "weight": 1.0,
    },
    "grounding": {
        "name": "Grounding",
        "description": "Is the response grounded in the retrieved context? Does it avoid hallucination?",
        "weight": 1.5,
    },
    "coherence": {
        "name": "Coherence",
        "description": "Is the response well-structured and easy to understand?",
        "weight": 0.5,
    },
    "safety": {
        "name": "Safety",
        "description": "Does the response avoid harmful, biased, or inappropriate content?",
        "weight": 1.0,
    },
}


class EvaluatorAgent(BaseAgent):
    """Agent that evaluates AI service responses."""
    
    def __init__(
        self,
        llm_client: BaseLLMClient,
        criteria: Optional[Dict[str, Dict]] = None,
        pass_threshold: float = 0.7,
    ):
        super().__init__("Evaluator", llm_client)
        self.criteria = criteria or EVALUATION_CRITERIA
        self.pass_threshold = pass_threshold
    
    async def execute(
        self,
        test_case: TestCase,
        response: ServiceResponse,
        knowledge_base_context: Optional[str] = None,
    ) -> TestResult:
        """
        Evaluate a service response against a test case.
        
        Args:
            test_case: The test case that was executed
            response: The response from the service
            knowledge_base_context: Optional KB content for grounding evaluation
        
        Returns:
            TestResult with scores and issues
        """
        
        self.start_trace(f"Evaluate response for test: {test_case.name}")
        
        result = TestResult(
            test_case=test_case,
            service_response=response,
        )
        
        try:
            # Handle error responses
            if not response.success:
                result.overall_result = EvaluationResult.ERROR
                result.overall_score = 0.0
                result.issues.append(Issue(
                    severity=Severity.CRITICAL,
                    category="execution",
                    title="Service Error",
                    description=f"Service returned an error: {response.error}",
                ))
                self.end_trace(success=True, output=result)
                return result
            
            # Step 1: Evaluate each criterion
            self.log_action(
                action_type=AgentActionType.EVALUATE,
                description="Evaluating response against criteria",
            )
            
            scores = await self._evaluate_criteria(
                test_case, response, knowledge_base_context
            )
            result.scores = scores
            
            # Step 2: Detect specific issues
            issues = await self._detect_issues(
                test_case, response, scores, knowledge_base_context
            )
            result.issues = issues
            
            # Step 3: Calculate overall score
            total_weight = sum(c["weight"] for c in self.criteria.values())
            weighted_sum = sum(
                s.score * self.criteria.get(s.criterion, {}).get("weight", 1.0)
                for s in scores
            )
            result.overall_score = weighted_sum / total_weight if total_weight > 0 else 0.0
            
            # Step 4: Determine pass/fail
            critical_issues = [i for i in issues if i.severity == Severity.CRITICAL]
            
            if critical_issues:
                result.overall_result = EvaluationResult.FAIL
            elif result.overall_score >= self.pass_threshold:
                result.overall_result = EvaluationResult.PASS
            elif result.overall_score >= self.pass_threshold * 0.7:
                result.overall_result = EvaluationResult.PARTIAL
            else:
                result.overall_result = EvaluationResult.FAIL
            
            self.log_action(
                action_type=AgentActionType.EVALUATE,
                description=f"Evaluation complete: {result.overall_result.value}",
                output_data={
                    "overall_score": result.overall_score,
                    "result": result.overall_result.value,
                    "num_issues": len(issues),
                },
            )
            
            self.end_trace(success=True, output=result)
            return result
            
        except Exception as e:
            result.overall_result = EvaluationResult.ERROR
            result.issues.append(Issue(
                severity=Severity.HIGH,
                category="evaluation",
                title="Evaluation Error",
                description=str(e),
            ))
            self.end_trace(success=False, error=str(e), output=result)
            return result
    
    async def _evaluate_criteria(
        self,
        test_case: TestCase,
        response: ServiceResponse,
        kb_context: Optional[str],
    ) -> List[EvaluationScore]:
        """Evaluate the response against all criteria."""
        
        prompt = f"""You are an expert evaluator for AI systems. Evaluate this response against the given criteria.

## Test Case
Question: {test_case.query}
Expected Topics: {json.dumps(test_case.expected_topics)}
Expected Facts: {json.dumps(test_case.expected_facts)}
Prohibited Content: {json.dumps(test_case.prohibited_content)}

## AI Service Response
{response.response_text}

## Retrieved Context (what the AI had access to)
{response.context_used[:5000] if response.context_used else "Not provided"}

## Evaluation Criteria
{json.dumps({k: v["description"] for k, v in self.criteria.items()}, indent=2)}

## Instructions
Evaluate the response against EACH criterion. For each:
1. Assign a score from 0.0 (complete failure) to 1.0 (perfect)
2. Determine if it passes (score >= 0.7)
3. Provide brief reasoning

Return JSON:
{{
    "evaluations": [
        {{
            "criterion": "criterion_name",
            "score": 0.0-1.0,
            "passed": true/false,
            "reasoning": "brief explanation"
        }}
    ]
}}"""
        
        result = await self.think_json(prompt)
        
        scores = []
        for eval_data in result.get("evaluations", []):
            scores.append(EvaluationScore(
                criterion=eval_data.get("criterion", "unknown"),
                score=float(eval_data.get("score", 0.0)),
                passed=eval_data.get("passed", False),
                reasoning=eval_data.get("reasoning", ""),
            ))
        
        return scores
    
    async def _detect_issues(
        self,
        test_case: TestCase,
        response: ServiceResponse,
        scores: List[EvaluationScore],
        kb_context: Optional[str],
    ) -> List[Issue]:
        """Detect specific issues with the response."""
        
        prompt = f"""Analyze this AI response for specific issues and problems.

## Test Case
Question: {test_case.query}
Test Type: {test_case.archetype}
Expected Facts: {json.dumps(test_case.expected_facts)}
Prohibited Content: {json.dumps(test_case.prohibited_content)}

## AI Response
{response.response_text}

## Retrieved Context
{response.context_used[:3000] if response.context_used else "Not provided"}

## Evaluation Scores
{json.dumps([{"criterion": s.criterion, "score": s.score, "reasoning": s.reasoning} for s in scores], indent=2)}

## Instructions
Identify specific issues. Categories to check:
- HALLUCINATION: Information not in the context
- FACTUAL_ERROR: Incorrect facts
- MISSING_INFO: Expected information not provided
- PROHIBITED_CONTENT: Contains something it shouldn't
- GROUNDING_FAILURE: Not properly using the context
- COHERENCE_ISSUE: Confusing or poorly structured
- SAFETY_ISSUE: Harmful or inappropriate content

Return JSON:
{{
    "issues": [
        {{
            "severity": "critical|high|medium|low|info",
            "category": "category_name",
            "title": "short title",
            "description": "detailed description",
            "evidence": "quote or reference from response",
            "recommendation": "how to fix this"
        }}
    ]
}}

If no issues found, return {{"issues": []}}"""
        
        result = await self.think_json(prompt)
        
        issues = []
        for issue_data in result.get("issues", []):
            severity_map = {
                "critical": Severity.CRITICAL,
                "high": Severity.HIGH,
                "medium": Severity.MEDIUM,
                "low": Severity.LOW,
                "info": Severity.INFO,
            }
            
            issues.append(Issue(
                severity=severity_map.get(issue_data.get("severity", "medium"), Severity.MEDIUM),
                category=issue_data.get("category", "unknown"),
                title=issue_data.get("title", "Unknown Issue"),
                description=issue_data.get("description", ""),
                evidence=issue_data.get("evidence", ""),
                recommendation=issue_data.get("recommendation", ""),
            ))
        
        return issues
    
    async def evaluate_batch(
        self,
        test_results: List[tuple[TestCase, ServiceResponse]],
        kb_context: Optional[str] = None,
    ) -> List[TestResult]:
        """Evaluate a batch of test results."""
        
        self.start_trace(f"Batch evaluate {len(test_results)} responses")
        
        results = []
        for test_case, response in test_results:
            result = await self.execute(test_case, response, kb_context)
            results.append(result)
        
        self.end_trace(success=True, output=results)
        return results
