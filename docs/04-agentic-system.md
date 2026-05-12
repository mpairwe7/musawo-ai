# 4. Agentic System — Musawo AI

## Agent Architecture

```
User query → Supervisor → Route to mode agent
                              ↓
              VHT Agent ← Maternal Agent ← Community Agent
                              ↓
                    Triage Agent (multi-step iCCM)
```

## Supervisor (`agents/supervisor.py`)

Keyword-based mode classifier:
- **VHT mode**: clinical terms (fever, cough, diarrhea, malaria, pneumonia)
- **Maternal mode**: pregnancy terms (pregnant, antenatal, delivery, breastfeeding)
- **Community mode**: general health, prevention, nutrition

## Triage Agent (`agents/triage_agent.py`)

Stateful iCCM (Integrated Community Case Management) workflow:

1. **Danger check**: convulsions, unconscious, vomiting everything
2. **Assessment**: fever, cough, diarrhea, malnutrition, measles
3. **Classification**: severe → refer, moderate → treat, mild → home care
4. **Treatment**: ACTs, ORS, zinc, amoxicillin, vitamin A
5. **Follow-up**: return visit schedule, danger sign education

Conditions classified: malaria, pneumonia, diarrhea, measles, SAM, MAM

## Routing Decision (`agents/state.py`)

```python
@dataclass
class RouteDecision:
    mode: Mode          # vht | maternal | community
    confidence: float   # 0.0 - 1.0
    reason: str         # why this route was chosen
```
