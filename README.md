# AI Agent-Powered Evaluation Platform

An intelligent, agent-based platform for evaluating AI services (RAG chatbots, LLM applications, etc.) using autonomous AI agents.

## Overview

This platform uses a **multi-agent architecture** to automatically:
1. **Generate** test cases from your knowledge base
2. **Execute** tests against your AI service
3. **Evaluate** responses using LLM-based judging
4. **Report** comprehensive results with actionable insights

```
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR AGENT                           │
│                  (Coordinates Pipeline)                         │
└────────────┬─────────────────┬─────────────────┬───────────────┘
             │                 │                 │
             ▼                 ▼                 ▼
┌────────────────┐   ┌────────────────┐   ┌────────────────┐
│ TEST GENERATOR │   │   EXECUTOR     │   │   EVALUATOR    │
│     AGENT      │   │     AGENT      │   │     AGENT      │
│                │   │                │   │                │
│ • Analyzes KB  │   │ • Calls API    │   │ • LLM Judge    │
│ • Creates tests│   │ • Captures     │   │ • Detects      │
│ • Varies types │   │   responses    │   │   issues       │
└────────────────┘   └────────────────┘   └────────────────┘
```

## Quick Start

### 1. Install Dependencies: pip install -r requirements.txt

### 2. Set Environment Variables(CLI): export  OPENAI_API_KEY="your-api-key"

### 3. Run Against Hosted Service(CLI): python main.py --service-url http://localhost:9090 --kb-path ./knowledge_base --num-tests testset_size

## Project Structure

```
ai-agent-eval-platform/
├── main.py              # CLI runner
├── requirements.txt
│
├── core/
│   ├── models.py        # Data models (TestCase, Trace, etc.)
│   └── llm_client.py    # LLM client abstraction
│
└── agents/
    ├── base_agent.py    # Base agent with tracing
    ├── test_generator.py# Test case generation
    ├── executor.py      # Test execution
    ├── evaluator.py     # Response evaluation
    └── orchestrator.py  # Pipeline coordination
```

## Example Outputs

This repo includes example outputs from a real evaluation run:

| File | Description |
|------|-------------|
| `results.json` | Full evaluation results in JSON format |
| `Outputs.docx` | Screenshots of terminal output |

These demonstrate the platform evaluating a RAG service against SEC 10-K filings (AAPL, NVDA, META, MSFT, AMZN).

## Test Archetypes

The platform generates diverse test cases across multiple archetypes:

| Archetype | Description |
|-----------|-------------|
| `factual_recall` | Tests direct fact retrieval from knowledge base |
| `synthesis` | Tests combining information from multiple sources |
| `ambiguity_handling` | Tests handling of unclear or ambiguous queries |
| `out_of_scope` | Tests correct identification of unsupported questions |
| `adversarial` | Tests robustness against misleading queries |
| `multi_step` | Tests complex reasoning chains |

## Evaluation Criteria

Each response is evaluated against multiple criteria:

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Relevance | 1.5x | Does the response address the question? |
| Accuracy | 2.0x | Are facts correct based on the KB? |
| Completeness | 1.0x | Are all aspects covered? |
| Grounding | 1.5x | Is the response grounded (no hallucination)? |
| Coherence | 0.5x | Is it well-structured? |
| Safety | 1.0x | No harmful content? |

## Issue Detection

The platform detects and classifies issues:

- **HALLUCINATION**: Information not in the context
- **FACTUAL_ERROR**: Incorrect facts
- **MISSING_INFO**: Expected information not provided
- **GROUNDING_FAILURE**: Not properly using context
- **SAFETY_ISSUE**: Harmful or inappropriate content

Each issue has a severity: `critical`, `high`, `medium`, `low`, `info`
