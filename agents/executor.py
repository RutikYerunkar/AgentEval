"""
Test Executor Agent - Executes test cases against the AI service.
"""

import time
from typing import Any, Dict, List, Optional

import httpx

from agents.base_agent import BaseAgent
from core.models import AgentActionType, ServiceResponse, TestCase
from core.llm_client import BaseLLMClient


class ServiceClient:
    """Client for communicating with the AI service being tested."""
    
    def __init__(
        self,
        base_url: str,
        endpoint: str = "/query",
        request_field: str = "question",
        response_field: str = "response",
        context_field: Optional[str] = "context",
        timeout: float = 60.0,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.endpoint = endpoint
        self.request_field = request_field
        self.response_field = response_field
        self.context_field = context_field
        self.timeout = timeout
        self.headers = headers or {"Content-Type": "application/json"}
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def query(self, question: str) -> ServiceResponse:
        """Send a query to the AI service."""
        
        url = f"{self.base_url}{self.endpoint}"
        payload = {self.request_field: question}
        
        start_time = time.time()
        
        try:
            response = await self.client.post(
                url,
                json=payload,
                headers=self.headers,
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code != 200:
                return ServiceResponse(
                    error=f"HTTP {response.status_code}: {response.text}",
                    latency_ms=latency_ms,
                    raw_response={"status_code": response.status_code},
                )
            
            data = response.json()
            
            return ServiceResponse(
                response_text=data.get(self.response_field, ""),
                context_used=data.get(self.context_field, "") if self.context_field else "",
                latency_ms=latency_ms,
                raw_response=data,
            )
            
        except httpx.TimeoutException:
            return ServiceResponse(
                error=f"Request timed out after {self.timeout}s",
                latency_ms=int((time.time() - start_time) * 1000),
            )
        except Exception as e:
            return ServiceResponse(
                error=f"Request failed: {str(e)}",
                latency_ms=int((time.time() - start_time) * 1000),
            )
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


class OpenAICompatibleClient(ServiceClient):
    """Client for OpenAI-compatible chat completion endpoints."""
    
    def __init__(
        self,
        base_url: str,
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
        api_key: Optional[str] = None,
    ):
        super().__init__(base_url, timeout=timeout)
        self.model = model
        self.endpoint = "/v1/chat/completions"
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
    
    async def query(self, question: str, conversation_history: List[Dict] = None) -> ServiceResponse:
        """Send a query using OpenAI chat completion format."""
        
        url = f"{self.base_url}{self.endpoint}"
        
        messages = conversation_history or []
        messages.append({"role": "user", "content": question})
        
        payload = {
            "model": self.model,
            "messages": messages,
        }
        
        start_time = time.time()
        
        try:
            response = await self.client.post(
                url,
                json=payload,
                headers=self.headers,
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code != 200:
                return ServiceResponse(
                    error=f"HTTP {response.status_code}: {response.text}",
                    latency_ms=latency_ms,
                )
            
            data = response.json()
            response_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            return ServiceResponse(
                response_text=response_text,
                latency_ms=latency_ms,
                raw_response=data,
            )
            
        except Exception as e:
            return ServiceResponse(
                error=f"Request failed: {str(e)}",
                latency_ms=int((time.time() - start_time) * 1000),
            )


class TestExecutorAgent(BaseAgent):
    """Agent that executes test cases against the AI service."""
    
    def __init__(
        self,
        llm_client: BaseLLMClient,
        service_client: ServiceClient,
    ):
        super().__init__("TestExecutor", llm_client)
        self.service_client = service_client
    
    async def execute(
        self,
        test_cases: List[TestCase],
        parallel: bool = False,
    ) -> List[tuple[TestCase, ServiceResponse]]:
        """
        Execute a list of test cases against the service.
        
        Args:
            test_cases: List of test cases to execute
            parallel: Whether to execute in parallel (not implemented yet)
        
        Returns:
            List of (TestCase, ServiceResponse) tuples
        """
        
        self.start_trace(f"Execute {len(test_cases)} test cases")
        
        results = []
        
        for i, test in enumerate(test_cases):
            self.log_action(
                action_type=AgentActionType.EXECUTE_TEST,
                description=f"Executing test {i+1}/{len(test_cases)}: {test.name}",
                input_data={"test_id": test.test_id, "query": test.query[:100]},
            )
            
            response = await self.execute_single(test)
            results.append((test, response))
            
            self.log_action(
                action_type=AgentActionType.EXECUTE_TEST,
                description=f"Test {test.test_id} completed",
                output_data={
                    "success": response.success,
                    "latency_ms": response.latency_ms,
                    "response_length": len(response.response_text),
                },
            )
        
        self.end_trace(success=True, output=results)
        return results
    
    async def execute_single(self, test: TestCase) -> ServiceResponse:
        """Execute a single test case."""
        
        if test.test_type == TestCaseType.SINGLE_TURN:
            return await self.service_client.query(test.query)
        
        elif test.test_type == TestCaseType.MULTI_TURN:
            # For multi-turn, execute the conversation history first
            if isinstance(self.service_client, OpenAICompatibleClient):
                return await self.service_client.query(
                    test.query,
                    conversation_history=test.conversation_history,
                )
            else:
                # Fallback: just send the last query
                return await self.service_client.query(test.query)
        
        else:
            return await self.service_client.query(test.query)
    
    async def health_check(self) -> bool:
        """Check if the service is reachable."""
        
        try:
            response = await self.service_client.query("test")
            return response.success or response.error is None
        except Exception:
            return False


from core.models import TestCaseType
