/**
 * HTTP API client for Robot Battles Playtest App
 */

export class PlaytestApi {
  static async getCards() {
    const res = await fetch("/api/cards");
    if (!res.ok) throw new Error("Failed to load cards");
    return res.json();
  }

  static async getChassis() {
    const res = await fetch("/api/chassis");
    if (!res.ok) throw new Error("Failed to load chassis");
    return res.json();
  }

  static async getSavedRobots() {
    const res = await fetch("/api/robots");
    if (!res.ok) throw new Error("Failed to load robots");
    return res.json();
  }

  static async getRobotCsv(name) {
    const res = await fetch(`/api/robots/${encodeURIComponent(name)}`);
    if (!res.ok) throw new Error(`Robot ${name} not found`);
    return res.text();
  }

  static async saveRobot(name, csvContent) {
    const res = await fetch(`/api/robots/${encodeURIComponent(name)}`, {
      method: "POST",
      headers: { "Content-Type": "text/csv; charset=utf-8" },
      body: csvContent,
    });
    if (!res.ok) throw new Error("Failed to save robot");
    return res.json();
  }

  static async getBattleState() {
    const res = await fetch("/api/battle/state");
    if (!res.ok) throw new Error("Failed to fetch battle state");
    return res.json();
  }

  static async startNewBattle(playerCsv, automatonName = "Vyper_Spinner", playerName = "Player 1", maxRounds = 10) {
    if (playerCsv && typeof playerCsv === "object") {
      const opts = playerCsv;
      playerCsv = opts.player_csv;
      automatonName = opts.automaton || automatonName;
      playerName = opts.player_name || playerName;
      maxRounds = opts.max_rounds || opts.playcount || maxRounds;
    }
    const res = await fetch("/api/battle/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        player_csv: playerCsv,
        automaton: automatonName,
        player_name: playerName,
        max_rounds: Number(maxRounds) || 20,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || "Failed to start battle");
    }
    return res.json();
  }

  static async startNewMatch(optsOrCsv, automatonName = "Vyper_Spinner", playerName = "Player 1", maxRounds = 10) {
    return this.startNewBattle(optsOrCsv, automatonName, playerName, maxRounds);
  }

  static async getActionCards() {
    const res = await fetch("/api/action_cards");
    if (!res.ok) throw new Error("Failed to load action cards");
    return res.json();
  }

  static async executeTurn(optsOrLeft, right = 0, fixedRoll = null, chosenComponents = null) {
    let payload = {};
    if (optsOrLeft && typeof optsOrLeft === "object" && !Array.isArray(optsOrLeft)) {
      payload = { ...optsOrLeft };
    } else if (Array.isArray(optsOrLeft)) {
      payload = { cards: optsOrLeft, left: Number(right) || 0, right: 0 };
    } else {
      payload = { left: Number(optsOrLeft), right: Number(right) };
    }
    if (fixedRoll !== null && payload.fixed_roll === undefined) {
      payload.fixed_roll = Number(fixedRoll);
    }
    if (chosenComponents && payload.chosen_components === undefined) {
      payload.chosen_components = chosenComponents;
    }
    const res = await fetch("/api/battle/turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || "Failed to execute turn");
    }
    return res.json();
  }

  static async submitTurn(optsOrLeft, right = 0, fixedRoll = null, chosenComponents = null) {
    return this.executeTurn(optsOrLeft, right, fixedRoll, chosenComponents);
  }

  static async updateSupply(chosenComponents) {
    const res = await fetch("/api/battle/supply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chosen_components: chosenComponents }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || "Failed to update supply allocation");
    }
    return res.json();
  }

  static async resetBattle() {
    const res = await fetch("/api/battle/reset", { method: "POST" });
    if (!res.ok) throw new Error("Failed to reset battle");
    return res.json();
  }

  static async resetMatch() {
    return this.resetBattle();
  }

  static async exportMatchLog() {
    const res = await fetch("/api/battle/export");
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || "Failed to export match log");
    }
    return res.json();
  }

  static async getMovementTemplate(left, right) {
    const res = await fetch(`/api/movement/template?left=${encodeURIComponent(left)}&right=${encodeURIComponent(right)}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || "Failed to fetch movement template");
    }
    return res.json();
  }

  static async getActionPlanPreview(cards, pose = null, chassis = "Square") {
    const cardStr = Array.isArray(cards) ? cards.join(",") : String(cards);
    let url = `/api/action_plan_preview?cards=${encodeURIComponent(cardStr)}&chassis=${encodeURIComponent(chassis)}`;
    if (pose) {
      url += `&x=${encodeURIComponent(pose.x)}&y=${encodeURIComponent(pose.y)}&theta=${encodeURIComponent(pose.theta)}`;
    }
    const res = await fetch(url);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || "Failed to fetch action plan preview");
    }
    return res.json();
  }
}
