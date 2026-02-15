"""
Core data models for the AI Agent-powered Evaluation Platform.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
import json


# =============================================================================
# ENUMS
# =============================================================================

class TestCaseType(Enum):
    SINGLE_TURN = "single_turn"
    MULTI_TURN = "multi_turn"
    ADVERSARIAL = "adversarial"


class AgentActionType(Enum):
    PLAN = "plan"
    GENERATE_TEST = "generate_test"
    EXECUTE_TEST = "execute_test"
    EVALUATE = "evaluate"
    SYNTHESIZE = "synthesize"
    TOOL_CALL = "tool_call"
    REASONING = "reasoning"


class EvaluationResult(Enum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"
    ERROR = "error"


class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# =============================================================================
# CORE DATA MODELS
# =============================================================================

@dataclass
class TestCase:
    """A single test case to run against the AI service."""
    test_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    description: str = ""
    test_type: TestCaseType = TestCaseType.SINGLE_TURN
    
    query: str = ""
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    
    expected_topics: List[str] = field(default_factory=list)
    expected_facts: List[str] = field(default_factory=list)
    prohibited_content: List[str] = field(default_factory=list)
    relevant_sources: List[str] = field(default_factory=list)
    
    archetype: str = ""
    difficulty: str = "medium"
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "name": self.name,
            "description": self.description,
            "test_type": self.test_type.value,
            "query": self.query,
            "expected_topics": self.expected_topics,
            "expected_facts": self.expected_facts,
            "archetype": self.archetype,
            "difficulty": self.difficulty,
        }


@dataclass
class ServiceResponse:
    """Response from the AI service being tested."""
    response_text: str = ""
    context_used: str = ""
    latency_ms: int = 0
    raw_response: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    
    @property
    def success(self) -> bool:
        return self.error is None


@dataclass
class EvaluationScore:
    """Score for a single evaluation criterion."""
    criterion: str
    score: float
    passed: bool
    reasoning: str
    evidence: List[str] = field(default_factory=list)


@dataclass
class Issue:
    """An issue found during evaluation."""
    issue_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    severity: Severity = Severity.MEDIUM
    category: str = ""
    title: str = ""
    description: str = ""
    evidence: str = ""
    recommendation: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "severity": self.severity.value,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
        }


@dataclass
class TestResult:
    """Complete result of running and evaluating a test case."""
    result_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    test_case: TestCase = field(default_factory=TestCase)
    service_response: ServiceResponse = field(default_factory=ServiceResponse)
    
    overall_result: EvaluationResult = EvaluationResult.ERROR
    overall_score: float = 0.0
    scores: List[EvaluationScore] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)
    
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "result_id": self.result_id,
            "test_case": self.test_case.to_dict(),
            "response": self.service_response.response_text[:500] + "..." if len(self.service_response.response_text) > 500 else self.service_response.response_text,
            "overall_result": self.overall_result.value,
            "overall_score": round(self.overall_score, 2),
            "scores": [
                {"criterion": s.criterion, "score": round(s.score, 2), "passed": s.passed, "reasoning": s.reasoning}
                for s in self.scores
            ],
            "issues": [i.to_dict() for i in self.issues],
            "latency_ms": self.service_response.latency_ms,
        }


# =============================================================================
# AGENT TRACE MODELS
# =============================================================================

@dataclass
class AgentAction:
    """A single action taken by an agent."""
    action_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    action_type: AgentActionType = AgentActionType.REASONING
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    description: str = ""
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    
    prompt: Optional[str] = None
    completion: Optional[str] = None
    model_used: Optional[str] = None
    
    latency_ms: int = 0
    tokens_used: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type.value,
            "timestamp": self.timestamp.isoformat(),
            "description": self.description,
            "latency_ms": self.latency_ms,
        }


@dataclass
class AgentTrace:
    """Complete trace of an agent's execution."""
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    agent_name: str = ""
    task_description: str = ""
    
    actions: List[AgentAction] = field(default_factory=list)
    
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    success: bool = False
    error_message: Optional[str] = None
    final_output: Any = None
    
    def add_action(self, action: AgentAction) -> None:
        self.actions.append(action)
    
    @property
    def total_latency_ms(self) -> int:
        return sum(a.latency_ms for a in self.actions)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "agent_name": self.agent_name,
            "task": self.task_description,
            "num_actions": len(self.actions),
            "actions": [a.to_dict() for a in self.actions],
            "success": self.success,
            "total_latency_ms": self.total_latency_ms,
        }


# =============================================================================
# EVALUATION RUN MODELS
# =============================================================================

@dataclass
class EvaluationRun:
    """A complete evaluation run with multiple test cases."""
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    description: str = ""
    
    service_endpoint: str = ""
    knowledge_base_id: str = ""
    
    test_results: List[TestResult] = field(default_factory=list)
    agent_traces: List[AgentTrace] = field(default_factory=list)
    
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    @property
    def pass_rate(self) -> float:
        if self.total_tests == 0:
            return 0.0
        return self.passed_tests / self.total_tests
    
    @property
    def mean_score(self) -> float:
        if not self.test_results:
            return 0.0
        return sum(r.overall_score for r in self.test_results) / len(self.test_results)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "name": self.name,
            "service_endpoint": self.service_endpoint,
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "pass_rate": f"{self.pass_rate:.1%}",
            "mean_score": round(self.mean_score, 2),
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
