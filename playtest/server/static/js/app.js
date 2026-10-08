/**
 * Combat Robotics Playtest App Master Controller
 */

import { PlaytestApi } from "./api.js";
import { ArenaRenderer } from "./arena.js";
import { BuilderController } from "./builder.js";
import { CombatLogRenderer } from "./log.js";
import { RobotViewRenderer } from "./robot_view.js";

class PlaytestApp {
  constructor() {
    this.currentMatch = null;
    this.arenaRenderer = null;
    this.builderController = null;
    this.activeTab = "arena";

    // Turn selection state (2 numbers: left, right)
    this.turnLeft = 0;
    this.turnRight = 0;
  }

  async init() {
    this._cacheElements();
    this._bindTabs();
    this._bindBattleControls();

    // 1. Initialize Arena Renderer
    this.arenaRenderer = new ArenaRenderer(this.arenaSvg);

    // 2. Initialize Builder Controller
    this.builderController = new BuilderController({
      onDeploy: async (csvText, robotName) => {
        await this._deployFromBuilder(csvText, robotName);
      },
    });
    await this.builderController.init();

    // 3. Load or Start Match
    await this._loadBattleState();
  }

  _cacheElements() {
    // Navigation Tabs
    this.tabs = document.querySelectorAll(".nav-tab");
    this.tabViews = document.querySelectorAll(".tab-view");

    // Match Header HUD
    this.hudRound = document.getElementById("hud-round");
    this.hudStatus = document.getElementById("hud-status");
    this.hudAutoBanner = document.getElementById("hud-auto-banner");
    this.btnNewMatch = document.getElementById("btn-new-match");
    this.btnResetMatch = document.getElementById("btn-reset-match");
    this.autoSelect = document.getElementById("auto-select");

    // Arena Stage
    this.arenaSvg = document.getElementById("arena-svg");

    // Turn Planning Controls
    this.leftDriveVal = document.getElementById("left-drive-val");
    this.rightDriveVal = document.getElementById("right-drive-val");
    this.leftSlider = document.getElementById("left-drive-slider");
    this.rightSlider = document.getElementById("right-drive-slider");
    this.btnLeftMinus = document.getElementById("btn-left-minus");
    this.btnLeftPlus = document.getElementById("btn-left-plus");
    this.btnRightMinus = document.getElementById("btn-right-minus");
    this.btnRightPlus = document.getElementById("btn-right-plus");
    this.btnExecuteTurn = document.getElementById("btn-execute-turn");
    this.presetButtons = document.querySelectorAll(".btn-preset");

    // Views
    this.playerRobotContainer = document.getElementById("player-robot-container");
    this.automatonRobotContainer = document.getElementById("automaton-robot-container");
    this.logContainer = document.getElementById("combat-log-container");
  }

  _bindTabs() {
    this.tabs.forEach(tab => {
      tab.addEventListener("click", () => {
        const targetView = tab.dataset.tab;
        if (targetView) {
          this.switchTab(targetView);
        }
      });
    });
  }

  switchTab(tabName) {
    this.activeTab = tabName;
    this.tabs.forEach(t => t.classList.toggle("active", t.dataset.tab === tabName));
    this.tabViews.forEach(v => v.classList.toggle("active", v.id === `view-${tabName}`));

    if (tabName === "arena" && this.currentMatch) {
      this.arenaRenderer.render(this.currentMatch);
    } else if (tabName === "builder" && this.builderController) {
      setTimeout(() => this.builderController.zoomFit(), 100);
    }
  }

  _bindBattleControls() {
    const updateSliders = () => {
      this.leftDriveVal.textContent = this.turnLeft > 0 ? `+${this.turnLeft}` : this.turnLeft;
      this.rightDriveVal.textContent = this.turnRight > 0 ? `+${this.turnRight}` : this.turnRight;
      this.leftSlider.value = this.turnLeft;
      this.rightSlider.value = this.turnRight;
    };

    this.leftSlider.addEventListener("input", (e) => {
      this.turnLeft = parseInt(e.target.value, 10);
      updateSliders();
    });

    this.rightSlider.addEventListener("input", (e) => {
      this.turnRight = parseInt(e.target.value, 10);
      updateSliders();
    });

    this.btnLeftMinus.addEventListener("click", () => {
      const min = parseInt(this.leftSlider.min, 10);
      if (this.turnLeft > min) {
        this.turnLeft--;
        updateSliders();
      }
    });

    this.btnLeftPlus.addEventListener("click", () => {
      const max = parseInt(this.leftSlider.max, 10);
      if (this.turnLeft < max) {
        this.turnLeft++;
        updateSliders();
      }
    });

    this.btnRightMinus.addEventListener("click", () => {
      const min = parseInt(this.rightSlider.min, 10);
      if (this.turnRight > min) {
        this.turnRight--;
        updateSliders();
      }
    });

    this.btnRightPlus.addEventListener("click", () => {
      const max = parseInt(this.rightSlider.max, 10);
      if (this.turnRight < max) {
        this.turnRight++;
        updateSliders();
      }
    });

    // Preset Buttons
    this.presetButtons.forEach(btn => {
      btn.addEventListener("click", () => {
        const preset = btn.dataset.preset;
        const maxL = this.currentMatch ? this.currentMatch.player_robot.left_drive_max : 3;
        const maxR = this.currentMatch ? this.currentMatch.player_robot.right_drive_max : 3;

        switch (preset) {
          case "forward":
            const straight = Math.min(maxL, maxR);
            this.turnLeft = straight;
            this.turnRight = straight;
            break;
          case "curve-left":
            this.turnLeft = Math.min(maxL, 1);
            this.turnRight = Math.min(maxR, 3);
            break;
          case "curve-right":
            this.turnLeft = Math.min(maxL, 3);
            this.turnRight = Math.min(maxR, 1);
            break;
          case "pivot-left":
            this.turnLeft = 0;
            this.turnRight = Math.min(maxR, 2);
            break;
          case "pivot-right":
            this.turnLeft = Math.min(maxL, 2);
            this.turnRight = 0;
            break;
          case "reverse":
            this.turnLeft = maxL > 0 ? -1 : 0;
            this.turnRight = maxR > 0 ? -1 : 0;
            break;
          case "stop":
            this.turnLeft = 0;
            this.turnRight = 0;
            break;
        }
        updateSliders();
      });
    });

    // Execute Turn
    this.btnExecuteTurn.addEventListener("click", () => this._onExecuteTurn());

    // New Match & Reset Buttons
    this.btnNewMatch.addEventListener("click", async () => {
      const autoName = this.autoSelect.value;
      const csv = this.builderController ? this.builderController.getRobotCSV() : "";
      try {
        const data = await PlaytestApi.startNewMatch({
          player_csv: csv,
          automaton: autoName,
          player_name: "Player Bot",
        });
        this.currentMatch = data.match;
        this._updateMatchUi();
      } catch (err) {
        alert("Failed to start new match: " + err.message);
      }
    });

    this.btnResetMatch.addEventListener("click", async () => {
      if (confirm("Reset current match?")) {
        await PlaytestApi.resetMatch();
        await this._loadBattleState();
      }
    });
  }

  async _deployFromBuilder(csvText, robotName) {
    try {
      const autoName = this.autoSelect ? this.autoSelect.value : "Vyper_flipper";
      const data = await PlaytestApi.startNewMatch({
        player_csv: csvText,
        automaton: autoName,
        player_name: robotName || "Player Bot",
      });
      this.currentMatch = data.match;
      this._updateMatchUi();
      this.switchTab("arena");
    } catch (err) {
      alert("Failed to deploy robot: " + err.message);
    }
  }

  async _loadBattleState() {
    try {
      const data = await PlaytestApi.getBattleState();
      this.currentMatch = data.match;
      this._updateMatchUi();
    } catch (err) {
      console.warn("Could not load initial battle state:", err);
    }
  }

  async _onExecuteTurn() {
    if (!this.currentMatch || this.currentMatch.phase === "game_over") return;

    this.btnExecuteTurn.disabled = true;
    this.btnExecuteTurn.textContent = "⚙️ Executing...";

    try {
      const data = await PlaytestApi.submitTurn(this.turnLeft, this.turnRight);
      this.currentMatch = data.match;

      // Animate trajectory movement on arena
      this.arenaRenderer.animateTurn(this.currentMatch, () => {
        this._updateMatchUi();
        this.btnExecuteTurn.disabled = this.currentMatch.phase === "game_over";
        this.btnExecuteTurn.textContent = this.currentMatch.phase === "game_over" ? "Match Complete" : "🚀 Execute Turn";
      });

    } catch (err) {
      alert("Turn failed: " + err.message);
      this.btnExecuteTurn.disabled = false;
      this.btnExecuteTurn.textContent = "🚀 Execute Turn";
    }
  }

  _updateMatchUi() {
    if (!this.currentMatch) return;

    const m = this.currentMatch;
    const pBot = m.player_robot;
    const aBot = m.automaton_robot;

    // HUD Header
    this.hudRound.textContent = `Round ${m.round} / 10`;

    if (m.phase === "game_over") {
      this.hudStatus.innerHTML = `<span class="badge badge-danger">🏆 WINNER: ${m.winner.toUpperCase()} (${m.win_reason})</span>`;
    } else {
      this.hudStatus.innerHTML = `<span class="badge badge-success">PLANNING PHASE</span>`;
    }

    // Spin summary in banner
    const pSpin = Object.values(pBot.weapon_spin_counters || {}).reduce((a, b) => a + b, 0);
    const aSpin = Object.values(aBot.weapon_spin_counters || {}).reduce((a, b) => a + b, 0);
    const pSpinBadge = pSpin > 0 ? ` <span class="badge badge-cyan">🌀 ${pSpin} Spin</span>` : "";
    const aSpinBadge = aSpin > 0 ? ` <span class="badge badge-cyan">🌀 ${aSpin} Spin</span>` : "";

    if (m.automaton_roll !== null && m.automaton_action) {
      this.hudAutoBanner.innerHTML = `
        <span>🤖 <strong>${aBot.name}</strong> rolled 🎲 ${m.automaton_roll} ➔ <strong>${m.automaton_action.toUpperCase()}</strong> [L: ${m.automaton_choice.left}, R: ${m.automaton_choice.right}]${aSpinBadge}</span>
      `;
    } else {
      this.hudAutoBanner.innerHTML = `<span>Opponent: <strong>${aBot.name}</strong>${aSpinBadge} (Ready)</span>`;
    }

    // Drive Sliders Bounds
    const maxL = pBot.left_drive_max;
    const maxR = pBot.right_drive_max;
    this.leftSlider.min = -maxL;
    this.leftSlider.max = maxL;
    this.rightSlider.min = -maxR;
    this.rightSlider.max = maxR;

    this.turnLeft = Math.max(-maxL, Math.min(maxL, this.turnLeft));
    this.turnRight = Math.max(-maxR, Math.min(maxR, this.turnRight));
    this.leftSlider.value = this.turnLeft;
    this.rightSlider.value = this.turnRight;
    this.leftDriveVal.textContent = this.turnLeft > 0 ? `+${this.turnLeft}` : this.turnLeft;
    this.rightDriveVal.textContent = this.turnRight > 0 ? `+${this.turnRight}` : this.turnRight;

    // Render Views
    this.arenaRenderer.render(m);
    RobotViewRenderer.renderRobotState(this.playerRobotContainer, pBot, false);
    RobotViewRenderer.renderRobotState(this.automatonRobotContainer, aBot, true, m.automaton_roll, m.automaton_action);
    CombatLogRenderer.renderLog(this.logContainer, m.log);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const app = new PlaytestApp();
  app.init();
});
