# Robot Battles

This project is a card and tabletop miniature game about combat robotics. Build a robot within your budget and weight limit, then defeat your opponents in a tournament of destruction.

> **Theme & Vibe:** A simple-to-pick-up game that simulates preparing a robot for a competition and fighting it in the arena. Chaotic, scrambling for fixes, and dramatic hits --- *"You don't know what's going to happen when you enter the box."* The game's emphasis is more on making the bot than driving it.

---

## Core Gameplay

The core gameplay is split into two main parts:

### 1. Robot Construction (Cards & Chassis)
- **Chassis:** Each robot is built onto a chassis mat that determines its shape, base weight, cost, flip strength, and any special abilities.
- **Component Cards:** Represent modules such as motors, batteries, ESCs, armor, and weapons. Cards must physically sit on the chassis.
- **Resource Connectivity:** A component is active only if its input requirements (Power, Spin, Pressure) are supplied by connected (touching) components.
- **Budgets:** Robots must be built within the chosen cost budget (typically \$25) and weight capacity. Players may enter up to two robots (e.g., clusterbots) within the total budget.

### 2. Robot Battling (Arena & Miniatures)
- **The Arena:** Matches take place on an arena map featuring starting zones, perimeter walls, and hazard/pit zones (where thrown robots exit the arena).
- **Match Length:** Played for 10 rounds or until a robot is immobilized (has no active drive or cannot unflip).

## Game Formats

- **Limited (Recommended):** Players build robots from a central pool with an unlimited basic pile and a rotating 9-card face-up market of special cards within a \$25 budget.
- **Preconstructed:** Players bring pre-built decks up to the agreed budget.

- **Tournament:** Multi-round competition (typically 3 battles) where damaged components cannot be reused and players must repair robots from spare parts between rounds.
- **Automaton (AI / Solo / Odd Players):** Pre-built robots controlled by rolling a d6 on an action table to balance tournament numbers or allow solo play.

---

## Rules Documentation

Full rules writeup, diagrams, and quick-reference summaries are located in the [`rules/`](rules/) directory:
- [PDF Rulebook](rules/combat_robotics_game.pdf) --- Formatted 6-page printable rulebook with diagrams and reference tables.
- [LaTeX Source](rules/combat_robotics_game.tex) --- LaTeX source code for the rulebook.
- [Draft Rules (.docx)](rules/Combat%20robotics%20game.docx) --- Original draft rules document.

---

## Code Elements

This repository contains code used to:
- Scrape possible component ideas and datasheets (`scripts/fetch_components.py`)
- Generate card layouts and definitions from component datasheets (`cardCreation/generateCards.py`)
- Generate printable A3 chassis mats from CSV (`scripts/generate_chassis_sheets.py`)

---

## Interactive Robot Builder UI

An interactive web-based tool for building robots that runs locally on both mobile devices (via Termux on Android) and desktop browsers with zero external dependencies.

- **Launch:**
  ```bash
  sh builder.sh
  ```
  Or directly with Python:
  ```bash
  python3 -m builder.server
  ```
- **Features:**
  - **A3 Chassis Mat Generation:** Select any chassis template from `cardDefinitions/chassis.csv` (Square, Triangle, Wide) rendered onto an A3 landscape workspace (420mm × 297mm).
  - **Card Placement & Grid Snapping:** Place cards on the chassis with real-time 10mm grid snapping and 90° rotation.
  - **Touch Adjacency:** Automatically detects and visualizes physical contact connections between cards.
  - **Live Stat Tracking:** Dynamically calculates active robot weight and cost, flip strength, and supply deck budget.
  - **Spare Parts Tray:** Dedicated space for spare components kept in your supply pool between tournament rounds.
  - **CSV Save & Load:** Export and restore robot configurations to/from CSV files matching the automata specification (`id,card,location,connections`).
  - **Mobile Optimized:** Touch pinch-to-zoom, pan, touch dragging, and PWA manifest for "Add to Home Screen".
