"""
Base Agent class with tracing capabilities.
"""

import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional

from core.models import AgentAction, AgentActionType, AgentTrace
from core.llm_client import BaseLLMClient, LLMResponse


class BaseAgent(ABC):
    """Base class for all agents in the evaluation platform."""
    
    def __init__(self, name: str, llm_client: BaseLLMClient):
        self.name = name
        self.llm = llm_client
        self.current_trace: Optional[AgentTrace] = None
    
    def start_trace(self, task_description: str) -> AgentTrace:
        """Start a new trace for this agent's execution."""
        self.current_trace = AgentTrace(
            agent_name=self.name,
            task_description=task_description,
        )
        return self.current_trace
    
    def end_trace(self, success: bool = True, error: Optional[str] = None, output: Any = None) -> AgentTrace:
        """End the current trace."""
        if self.current_trace:
            self.current_trace.completed_at = datetime.utcnow()
            self.current_trace.success = success
            self.current_trace.error_message = error
            self.current_trace.final_output = output
        return self.current_trace
    
    def log_action(
        self,
        action_type: AgentActionType,
        description: str,
        input_data: Dict[str, Any] = None,
        output_data: Dict[str, Any] = None,
        prompt: Optional[str] = None,
        completion: Optional[str] = None,
        model: Optional[str] = None,
        latency_ms: int = 0,
        tokens: int = 0,
    ) -> AgentAction:
        """Log an action to the current trace."""
        
        action = AgentAction(
            action_type=action_type,
            description=description,
            input_data=input_data or {},
            output_data=output_data or {},
            prompt=prompt,
            completion=completion,
            model_used=model,
            latency_ms=latency_ms,
            tokens_used=tokens,
        )
        
        if self.current_trace:
            self.current_trace.add_action(action)
        
        return action
    
    async def think(self, prompt: str, system_prompt: Optional[str] = None) -> LLMResponse:
        """Make an LLM call and log it as a reasoning action."""
        
        start_time = time.time()
        response = await self.llm.complete(prompt, system_prompt)
        latency_ms = int((time.time() - start_time) * 1000)
        
        self.log_action(
            action_type=AgentActionType.REASONING,
            description="LLM reasoning",
            input_data={"prompt_preview": prompt[:200] + "..." if len(prompt) > 200 else prompt},
            output_data={"response_preview": response.content[:200] + "..." if len(response.content) > 200 else response.content},
            prompt=prompt,
            completion=response.content,
            model=response.model,
            latency_ms=latency_ms,
            tokens=response.input_tokens + response.output_tokens,
        )
        
        return response
    
    async def think_json(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Make an LLM call expecting JSON and log it."""
        
        start_time = time.time()
        result = await self.llm.complete_json(prompt, system_prompt)
        latency_ms = int((time.time() - start_time) * 1000)
        
        self.log_action(
            action_type=AgentActionType.REASONING,
            description="LLM reasoning (JSON)",
            input_data={"prompt_preview": prompt[:200] + "..."},
            output_data={"result_keys": list(result.keys()) if isinstance(result, dict) else "non-dict"},
            latency_ms=latency_ms,
        )
        
        return result
    
    @abstractmethod
    async def execute(self, *args, **kwargs) -> Any:
        """Execute the agent's primary task."""
        pass
