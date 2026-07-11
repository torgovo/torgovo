# Torgovo2 Diagram Suite

> **10 SVGs** for visual viewing · **10 `.puml` files** for Enterprise Architect / PlantUML import

---

## Quick Start

### 👁️ View diagrams (visually, no tools needed)
Open the SVG files in any browser:
```
docs/diagrams/svg/
├── DomainModel.svg              (79 KB)   — All entities, fields, relationships
├── SoftwareArchitecture.svg     (32 KB)   — Layered architecture + adapters
├── TradingLifecycle.svg         (36 KB)   — Grid/Martingale bot trading flow
├── BotStartSequence.svg         (25 KB)   — Bot start sequence diagram
├── DatabaseERD.svg              (73 KB)   — Physical DB schema (47 tables)
├── SubscriptionStateMachine.svg (13 KB)   — BotSubscription 6-state lifecycle
├── DataFlow.svg                 (28 KB)   — Money & order data flow
├── TradingEngineStateMachine.svg(19 KB)   — BotEngine state transitions
├── C4ContainerDiagram.svg       (17 KB)   — C4 container view
└── QuantumAISmoothing.svg       (25 KB)   — Return smoothing algorithm
```

### 🏭 Import into Enterprise Architect
1. Install the **PlantUML plugin** for EA (EA 15+): https://marketplace.sparxsystems.com/
2. Open any `.puml` file from `docs/diagrams/plantuml/` directly in EA:
   ```
   docs/diagrams/plantuml/
   ├── 01_domain_model.puml
   ├── 02_software_architecture.puml
   ├── 03_trading_lifecycle.puml
   ├── 04_bot_start_sequence.puml
   ├── 05_database_erd.puml
   ├── 06_subscription_state_machine.puml
   ├── 07_data_flow.puml
   ├── 08_trading_engine_state.puml
   ├── 09_c4_container.puml
   └── 10_quantum_ai_smoothing.puml
   ```
3. EA renders PlantUML as native UML diagrams you can edit, annotate, and export to XMI.

### 🤖 Give to AI Software Engineer
Share the `.puml` files directly — they're standard text-based UML that any modern AI coding tool can read and reason about. The AI will understand:
- Class diagrams (entities, fields, relationships)
- State machines (lifecycles, transitions)
- Sequence diagrams (interaction flows)
- Activity diagrams (trading algorithms)
- Data flow diagrams (money/order movement)

### 📝 Mermaid source (for GitHub rendering)
The original `.md` files in `docs/diagrams/` render natively on GitHub as diagrams:
```
docs/diagrams/
├── 01_DOMAIN_MODEL.md
├── 02_SOFTWARE_ARCHITECTURE.md
├── 03_FLOW_CHARTS.md
├── 04_SEQUENCE_DIAGRAMS.md
├── 05_MVP_SCOPE.md
├── 06_DATABASE_ERD.md
├── 07_C4_CONTAINER_DIAGRAM.md
├── 08_STATE_MACHINES.md
├── 09_DATA_FLOW_DIAGRAM.md
└── 10_COMPONENT_INTERFACES.md
```

---

## Diagram Map

```
┌─────────────────────────────────────────────────────────────────┐
│                       C4 SYSTEM CONTEXT                         │
│  09_c4_container.puml — Users, Admin, Exchanges, TradingView   │
├─────────────────────────────────────────────────────────────────┤
│                    SOFTWARE ARCHITECTURE                        │
│  02_software_architecture.puml — Layers, deps, deployment       │
├─────────────────────────────────────────────────────────────────┤
│                     DOMAIN MODEL (CLASS)                        │
│  01_domain_model.puml — 40+ entities across 10 bounded contexts │
├──────────────────────────────────┬──────────────────────────────┤
│        DATABASE (ERD)            │       STATE MACHINES         │
│  05_database_erd.puml            │  06_subscription_state.puml  │
│  47 tables with PK/FK/indexes    │  08_trading_engine_state.puml│
├──────────────────────────────────┴──────────────────────────────┤
│                    FLOW CHARTS                                   │
│  03_trading_lifecycle.puml — Grid/Martingale full cycle         │
│  10_quantum_ai_smoothing.puml — Return smoothing algorithm      │
├─────────────────────────────────────────────────────────────────┤
│                    SEQUENCE DIAGRAMS                             │
│  04_bot_start_sequence.puml — Bot start interaction             │
├─────────────────────────────────────────────────────────────────┤
│                    DATA FLOW                                     │
│  07_data_flow.puml — Money/order movement for audit             │
└─────────────────────────────────────────────────────────────────┘
```
