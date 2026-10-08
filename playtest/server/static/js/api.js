/**
 * HTTP API client for Combat Robotics Playtest App
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

  static async startNewBattle(playerCsv, automatonName = "Vyper_Spinner", playerName = "Player 1") {
    const res = await fetch("/api/battle/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        player_csv: playerCsv,
        automaton: automatonName,
        player_name: playerName,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || "Failed to start battle");
    }
    return res.json();
  }

  static async executeTurn(left, right, fixedRoll = null) {
    const payload = { left: Number(left), right: Number(right) };
    if (fixedRoll !== null) {
      payload.fixed_roll = Number(fixedRoll);
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

  static async resetBattle() {
    const res = await fetch("/api/battle/reset", { method: "POST" });
    if (!res.ok) throw new Error("Failed to reset battle");
    return res.json();
  }
}
