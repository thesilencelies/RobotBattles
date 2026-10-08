/**
 * Combat Robotics Playtest App Master Controller
 */

import { MatCanvas } from "/js/canvas.js";
import { CardCatalogue } from "/js/cards.js";
import { serializeRobotToCsv } from "/js/csv.js";
import { SparesDrawer } from "/js/spares.js";
import { state } from "/js/state.js";
import { PlaytestApi } from "./api.js";
import { ArenaRenderer } from "./arena.js";
import { CombatLogRenderer } from "./log.js";
import { RobotViewRenderer } from "./robot_view.js";

class PlaytestApp {
  constructor() {
    this.currentMatch = null;
    this.arenaRenderer = null;
    this.builderCanvas = null;
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

    // 2. Initialize Builder Component
    await this._initBuilder();

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

    // Builder elements
    this.builderContainer = document.getElementById("canvas-container");
    this.matSvg = document.getElementById("mat-svg");
    this.btnDeployToBattle = document.getElementById("btn-deploy-to-battle");
  }

  _bindTabs() {
    this.tabs.forEach(tab => {
      tab.addEventListener("click", () => {
        const targetView = tab.dataset.tab;
        this.switchTab(targetView);
      });
    });
  }

  switchTab(tabName) {
    this.activeTab = tabName;
    this.tabs.forEach(t => t.classList.toggle("active", t.dataset.tab === tabName));
    this.tabViews.forEach(v => v.classList.toggle("active", v.id === `view-${tabName}`));

    if (tabName === "arena" && this.currentMatch) {
      this.arenaRenderer.render(this.currentMatch);
    } else if (tabName === "builder" && this.builderCanvas) {
      setTimeout(() => this.builderCanvas.zoomFit(), 50);
    }
  }

  _bindBattleControls() {
    // Steppers and Sliders
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

    // Presets
    this.presetButtons.forEach(btn => {
      btn.addEventListener("click", () => {
        const action = btn.dataset.preset;
        const maxL = this.currentMatch?.player_robot?.left_drive_max || 3;
        const maxR = this.currentMatch?.player_robot?.right_drive_max || 3;

        switch (action) {
          case "forward":
            this.turnLeft = maxL;
            this.turnRight = maxR;
            break;
          case "pivot-left":
            this.turnLeft = -Math.min(maxL, 2);
            this.turnRight = Math.min(maxR, 2);
            break;
          case "pivot-right":
            this.turnLeft = Math.min(maxL, 2);
            this.turnRight = -Math.min(maxR, 2);
            break;
          case "curve-left":
            this.turnLeft = Math.max(0, maxL - 2);
            this.turnRight = maxR;
            break;
          case "curve-right":
            this.turnLeft = maxL;
            this.turnRight = Math.max(0, maxR - 2);
            break;
          case "reverse":
            this.turnLeft = -1;
            this.turnRight = -1;
            break;
          case "stop":
            this.turnLeft = 0;
            this.turnRight = 0;
            break;
        }
        updateSliders();
      });
    });

    // Turn Execution
    this.btnExecuteTurn.addEventListener("click", async () => {
      await this._onExecuteTurn();
    });

    // Match management
    this.btnNewMatch.addEventListener("click", async () => {
      const auto = this.autoSelect.value;
      const csv = serializeRobotToCsv(state);
      await this._startMatch(csv, auto, state.robotName || "Player 1");
    });

    this.btnResetMatch.addEventListener("click", async () => {
      await PlaytestApi.resetBattle();
      await this._loadBattleState();
    });

    if (this.btnDeployToBattle) {
      this.btnDeployToBattle.addEventListener("click", async () => {
        const auto = this.autoSelect.value;
        const csv = serializeRobotToCsv(state);
        await this._startMatch(csv, auto, state.robotName || "Custom Bot");
        this.switchTab("arena");
      });
    }
  }

  async _loadBattleState() {
    try {
      const data = await PlaytestApi.getBattleState();
      this.currentMatch = data.match;
      this._updateMatchUi();
    } catch (err) {
      console.error("Failed to load match state:", err);
    }
  }

  async _startMatch(csvContent, automaton, playerName) {
    try {
      const data = await PlaytestApi.startNewBattle(csvContent, automaton, playerName);
      this.currentMatch = data.match;
      this._updateMatchUi();
      this.arenaRenderer.render(this.currentMatch);
    } catch (err) {
      alert("Error starting match: " + err.message);
    }
  }

  async _onExecuteTurn() {
    if (!this.currentMatch || this.currentMatch.phase === "game_over") return;

    this.btnExecuteTurn.disabled = true;
    this.btnExecuteTurn.textContent = "Moving...";

    try {
      const data = await PlaytestApi.executeTurn(this.turnLeft, this.turnRight);
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

    if (m.automaton_roll !== null && m.automaton_action) {
      this.hudAutoBanner.innerHTML = `
        <span>🤖 <strong>${aBot.name}</strong> rolled 🎲 ${m.automaton_roll} ➔ <strong>${m.automaton_action.toUpperCase()}</strong> [L: ${m.automaton_choice.left}, R: ${m.automaton_choice.right}]</span>
      `;
    } else {
      this.hudAutoBanner.innerHTML = `<span>Opponent: <strong>${aBot.name}</strong> (Ready)</span>`;
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

  async _initBuilder() {
    try {
      const [cardsRes, chassisRes] = await Promise.all([
        fetch("/api/cards").then(r => r.json()),
        fetch("/api/chassis").then(r => r.json()),
      ]);

      state.cardCatalog = cardsRes.all || [];
      state.chassisList = chassisRes || [];

      // Set default chassis
      const defaultChassis = state.chassisList.find(c => c.name.includes("Viper")) || state.chassisList[0];
      if (defaultChassis) state.setChassis(defaultChassis);

      // Initialize Builder Components
      this.builderCanvas = new MatCanvas(this.builderContainer, this.matSvg);
      new CardCatalogue(
        document.getElementById("drawer-catalogue"),
        document.getElementById("catalogue-list"),
        document.getElementById("card-search-input"),
        document.querySelectorAll(".pill")
      );
      new SparesDrawer(
        document.getElementById("drawer-spares"),
        document.getElementById("spares-list")
      );

      // Load initial bot build (Vyper_Spinner) into builder
      const defaultCsv = await fetch("/api/robots/Vyper_Spinner").then(r => r.text()).catch(() => "");
      if (defaultCsv) {
        fromCsvToState(defaultCsv);
      }

    } catch (err) {
      console.warn("Builder init warning:", err);
    }
  }
}

function fromCsvToState(csvText) {
  fetch("/api/robots/parse", {
    method: "POST",
    headers: { "Content-Type": "text/csv" },
    body: csvText,
  })
    .then(r => r.json())
    .then(parsed => {
      if (parsed.chassis) state.setChassis(parsed.chassis);
      state.placedCards = parsed.placed_cards || [];
      state.spareCards = parsed.spare_cards || [];
      state.recalculate();
    })
    .catch(console.error);
}

document.addEventListener("DOMContentLoaded", () => {
  const app = new PlaytestApp();
  app.init();
});
