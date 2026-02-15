"""
Test Generator Agent - Generates test cases from knowledge base content.
"""

import json
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent
from core.models import AgentActionType, TestCase, TestCaseType
from core.llm_client import BaseLLMClient


# Test generation archetypes
ARCHETYPES = {
    "factual_recall": {
        "name": "Factual Recall",
        "description": "Tests whether the service can accurately retrieve and present facts from the knowledge base",
        "prompt_hint": "Questions that have clear, factual answers in the source documents",
    },
    "synthesis": {
        "name": "Information Synthesis",
        "description": "Tests whether the service can combine information from multiple sources",
        "prompt_hint": "Questions requiring combining information from different parts of the knowledge base",
    },
    "ambiguity_handling": {
        "name": "Ambiguity Handling",
        "description": "Tests how the service handles ambiguous or unclear queries",
        "prompt_hint": "Questions that could be interpreted multiple ways or lack context",
    },
    "out_of_scope": {
        "name": "Out of Scope",
        "description": "Tests whether the service correctly identifies questions outside its knowledge",
        "prompt_hint": "Questions about topics not covered in the knowledge base",
    },
    "adversarial": {
        "name": "Adversarial",
        "description": "Tests robustness against tricky or potentially misleading queries",
        "prompt_hint": "Questions with false premises, leading questions, or attempts to elicit incorrect information",
    },
    "multi_step": {
        "name": "Multi-Step Reasoning",
        "description": "Tests whether the service can follow multi-step reasoning chains",
        "prompt_hint": "Questions requiring multiple reasoning steps or conditional logic",
    },
}


class TestGeneratorAgent(BaseAgent):
    """Agent that generates test cases from knowledge base content."""
    
    def __init__(self, llm_client: BaseLLMClient):
        super().__init__("TestGenerator", llm_client)
    
    async def execute(
        self,
        knowledge_base_content: str,
        num_tests: int = 10,
        archetypes: Optional[List[str]] = None,
        difficulty_distribution: Optional[Dict[str, float]] = None,
    ) -> List[TestCase]:
        """
        Generate test cases based on knowledge base content.
        
        Args:
            knowledge_base_content: The content of the knowledge base
            num_tests: Number of test cases to generate
            archetypes: List of archetype names to use (default: all)
            difficulty_distribution: Distribution of difficulties (default: balanced)
        
        Returns:
            List of generated TestCase objects
        """
        
        self.start_trace(f"Generate {num_tests} test cases")
        
        try:
            # Step 1: Analyze the knowledge base
            self.log_action(
                action_type=AgentActionType.PLAN,
                description="Analyzing knowledge base content",
                input_data={"kb_length": len(knowledge_base_content)},
            )
            
            kb_analysis = await self._analyze_knowledge_base(knowledge_base_content)
            
            # Step 2: Plan test generation
            archetypes = archetypes or list(ARCHETYPES.keys())
            difficulty_distribution = difficulty_distribution or {"easy": 0.3, "medium": 0.5, "hard": 0.2}
            
            plan = await self._create_generation_plan(
                kb_analysis, num_tests, archetypes, difficulty_distribution
            )
            
            self.log_action(
                action_type=AgentActionType.PLAN,
                description="Created test generation plan",
                output_data={"plan": plan},
            )
            
            # Step 3: Generate test cases
            test_cases = await self._generate_test_cases(
                knowledge_base_content, kb_analysis, plan
            )
            
            self.log_action(
                action_type=AgentActionType.GENERATE_TEST,
                description=f"Generated {len(test_cases)} test cases",
                output_data={"num_tests": len(test_cases)},
            )
            
            self.end_trace(success=True, output=test_cases)
            return test_cases
            
        except Exception as e:
            self.end_trace(success=False, error=str(e))
            raise
    
    async def _analyze_knowledge_base(self, content: str) -> Dict[str, Any]:
        """Analyze the knowledge base to understand its structure and content."""
        
        prompt = f"""Analyze this knowledge base content and extract key information for test generation.

<knowledge_base>
{content[:15000]}  
</knowledge_base>

Provide a JSON analysis with:
{{
    "main_topics": ["list of main topics covered"],
    "key_entities": ["important entities, names, concepts"],
    "key_facts": ["specific facts that could be tested"],
    "procedures": ["any procedures or processes described"],
    "relationships": ["relationships between entities"],
    "potential_ambiguities": ["areas that might be ambiguous"],
    "gaps": ["topics that seem incomplete or missing"]
}}"""
        
        return await self.think_json(prompt)
    
    async def _create_generation_plan(
        self,
        kb_analysis: Dict[str, Any],
        num_tests: int,
        archetypes: List[str],
        difficulty_distribution: Dict[str, float],
    ) -> Dict[str, Any]:
        """Create a plan for generating test cases."""
        
        # Distribute tests across archetypes and difficulties
        tests_per_archetype = num_tests // len(archetypes)
        remainder = num_tests % len(archetypes)
        
        plan = {
            "total_tests": num_tests,
            "archetype_distribution": {},
            "difficulty_distribution": difficulty_distribution,
        }
        
        for i, archetype in enumerate(archetypes):
            count = tests_per_archetype + (1 if i < remainder else 0)
            plan["archetype_distribution"][archetype] = count
        
        return plan
    
    async def _generate_test_cases(
        self,
        kb_content: str,
        kb_analysis: Dict[str, Any],
        plan: Dict[str, Any],
    ) -> List[TestCase]:
        """Generate the actual test cases."""
        
        all_tests = []
        
        for archetype, count in plan["archetype_distribution"].items():
            if count == 0:
                continue
            
            archetype_info = ARCHETYPES.get(archetype, ARCHETYPES["factual_recall"])
            
            prompt = f"""Generate {count} test cases for an AI RAG service evaluation.

## Knowledge Base Analysis
{json.dumps(kb_analysis, indent=2)}

## Test Archetype: {archetype_info['name']}
{archetype_info['description']}
Hint: {archetype_info['prompt_hint']}

## Knowledge Base Content (excerpt)
{kb_content[:10000]}

## Requirements
- Generate exactly {count} test cases
- Each test should have a clear expected outcome
- Vary the difficulty: {json.dumps(plan['difficulty_distribution'])}
- Make questions realistic and natural

## Output Format
Return a JSON array of test cases:
[
    {{
        "name": "short descriptive name",
        "query": "the actual question to ask the service",
        "expected_topics": ["topics the answer should cover"],
        "expected_facts": ["specific facts that should appear"],
        "prohibited_content": ["things that should NOT appear"],
        "difficulty": "easy|medium|hard",
        "reasoning": "why this is a good test case"
    }}
]"""
            
            try:
                tests_data = await self.think_json(prompt)
                
                if isinstance(tests_data, list):
                    for test_data in tests_data:
                        test = TestCase(
                            name=test_data.get("name", "Unnamed Test"),
                            description=test_data.get("reasoning", ""),
                            test_type=TestCaseType.SINGLE_TURN,
                            query=test_data.get("query", ""),
                            expected_topics=test_data.get("expected_topics", []),
                            expected_facts=test_data.get("expected_facts", []),
                            prohibited_content=test_data.get("prohibited_content", []),
                            archetype=archetype,
                            difficulty=test_data.get("difficulty", "medium"),
                        )
                        all_tests.append(test)
            
            except Exception as e:
                self.log_action(
                    action_type=AgentActionType.REASONING,
                    description=f"Error generating {archetype} tests: {str(e)}",
                    output_data={"error": str(e)},
                )
        
        return all_tests
    
    async def generate_from_document(
        self,
        document_content: str,
        document_name: str,
        num_tests: int = 5,
    ) -> List[TestCase]:
        """Generate test cases from a single document."""
        
        self.start_trace(f"Generate tests from document: {document_name}")
        
        prompt = f"""Generate {num_tests} diverse test cases from this document.

## Document: {document_name}
{document_content[:12000]}

Generate test cases that:
1. Test factual recall
2. Test understanding of procedures/processes (if any)
3. Test edge cases and ambiguous situations
4. Include at least one adversarial test

Return JSON array:
[
    {{
        "name": "descriptive name",
        "query": "the question",
        "expected_topics": ["topics"],
        "expected_facts": ["facts"],
        "difficulty": "easy|medium|hard",
        "archetype": "factual_recall|synthesis|ambiguity_handling|adversarial"
    }}
]"""
        
        try:
            tests_data = await self.think_json(prompt)
            
            tests = []
            for test_data in tests_data:
                test = TestCase(
                    name=test_data.get("name", ""),
                    query=test_data.get("query", ""),
                    expected_topics=test_data.get("expected_topics", []),
                    expected_facts=test_data.get("expected_facts", []),
                    archetype=test_data.get("archetype", "factual_recall"),
                    difficulty=test_data.get("difficulty", "medium"),
                    relevant_sources=[document_name],
                )
                tests.append(test)
            
            self.end_trace(success=True, output=tests)
            return tests
            
        except Exception as e:
            self.end_trace(success=False, error=str(e))
            raise
