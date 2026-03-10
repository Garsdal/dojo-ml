## 13. End-to-End Example: Boston Housing

### User submits via UI

**Prompt:**
> Improve the accuracy of the Boston housing prediction problem. Start with a linear regression baseline, then try more advanced models. Target: R² > 0.85.

**Tool hints:**
| Name | Description | Source |
|---|---|---|
| `fetch_dataset` | Load the Boston housing dataset | `https://scikit-learn.org/1.0/modules/generated/sklearn.datasets.load_boston.html` |

### What happens under the hood

```
1. POST /agent/run → agent router
2. create_agent_backend("claude") → ClaudeAgentBackend
3. AgentOrchestrator(lab, backend) created
4. orchestrator.start(prompt)
   ├── build_system_prompt(run) → system prompt string
   ├── collect_all_tools(lab) → [ToolDef, ToolDef, ...] (11 tools)
   └── backend.configure(tool_defs, config)
       ├── ClaudeToolAdapter.create_server("agentml", tool_defs) → MCP server
       └── ClaudeSDKClient(options) initialized
5. asyncio.create_task(orchestrator.execute(run))
   └── backend.execute(prompt) → yields AgentEvent stream
       └── ClaudeSDKClient manages the conversation
```

### What appears in the UI

```
● Agent Running — Turn 1

▶ search_knowledge("boston housing")        → No prior knowledge
▶ text: "I'll start by exploring the data..."
▶ create_experiment(hypothesis="Linear regression baseline")  → exp_01ABC
▶ Bash: pip install scikit-learn numpy      → OK
▶ Bash: python train_baseline.py           → {"r2": 0.72, "rmse": 4.87}
▶ log_metrics(exp_01ABC, {r2: 0.72, rmse: 4.87})
▶ complete_experiment(exp_01ABC, metrics...)
▶ write_knowledge("Linear regression baseline achieves R²=0.72")

● Agent Running — Turn 8

▶ create_experiment(hypothesis="Random Forest with default params")  → exp_02DEF
▶ Bash: python train_rf.py                → {"r2": 0.87, "rmse": 3.45}
▶ log_metrics(exp_02DEF, {r2: 0.87, rmse: 3.45})
▶ complete_experiment(exp_02DEF)
▶ write_knowledge("Random Forest significantly outperforms LR, R²=0.87")
▶ compare_experiments([exp_01ABC, exp_02DEF])

● Agent Running — Turn 15

▶ create_experiment(hypothesis="Gradient Boosting with tuned params")  → exp_03GHI
▶ Bash: python train_gb.py                → {"r2": 0.91, "rmse": 2.89}
▶ ...

● Agent Completed — 22 turns, $0.34, 4m 12s

Summary: Best model is Gradient Boosting (R²=0.91). Key findings:
- Feature engineering on LSTAT and RM improves all models
- Random Forest and GB both exceed R²=0.85 target
- Linear regression is a solid baseline at R²=0.72

Experiments: 5 created, 4 completed, 1 failed
Knowledge atoms: 7 recorded
```

### What persists in AgentML

- **Experiments** in `experiment_store` — full lifecycle with metrics
- **Knowledge atoms** in `memory_store` — learnings for future tasks
- **Metrics** in `tracking` (MLflow or file) — full metric history
- **Code** on disk in the agent's working directory — all scripts the agent wrote