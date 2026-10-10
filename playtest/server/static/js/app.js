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

    this.isReady = true;
  }

  _cacheElements() {
    // Navigation Tabs (scope to top bar to avoid colliding with builder's bottom nav)
    this.tabs = document.querySelectorAll("#main-nav .nav-tab");
    this.tabViews = document.querySelectorAll(".tab-view");

    // Match Header HUD
    this.hudRound = document.getElementById("hud-round");
    this.hudStatus = document.getElementById("hud-status");
    this.hudAutoBanner = document.getElementById("hud-auto-banner");
    this.btnNewMatch = document.getElementById("btn-new-match");
    this.btnResetMatch = document.getElementById("btn-reset-match");
    this.btnToggleTopBar = document.getElementById("btn-toggle-top-bar");
    this.autoSelect = document.getElementById("auto-select");
    this.playcountSelect = document.getElementById("playcount-select");
    this.viewArena = document.getElementById("view-arena");

    // Arena Stage
    this.arenaSvg = document.getElementById("arena-svg");

    // Combatants Specs Bar
    this.hudPname = document.getElementById("hud-pname");
    this.hudPspecs = document.getElementById("hud-pspecs");
    this.hudPinverted = document.getElementById("hud-pinverted");
    this.hudAname = document.getElementById("hud-aname");
    this.hudAspecs = document.getElementById("hud-aspecs");
    this.hudAinverted = document.getElementById("hud-ainverted");

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

    // Playcount (Max Rounds) Select Change
    if (this.playcountSelect) {
      this.playcountSelect.addEventListener("change", (e) => {
        if (e.target.value === "custom") {
          const val = prompt("Enter max rounds / playcount (1 - 100):", "10");
          const num = parseInt(val, 10);
          if (!isNaN(num) && num > 0) {
            let opt = [...this.playcountSelect.options].find(o => o.value === String(num));
            if (!opt) {
              opt = document.createElement("option");
              opt.value = String(num);
              opt.textContent = `${num} Rds`;
              this.playcountSelect.insertBefore(opt, this.playcountSelect.lastElementChild);
            }
            this.playcountSelect.value = String(num);
          } else {
            this.playcountSelect.value = "10";
          }
        }
      });
    }

    // New Match & Reset Buttons
    this.btnNewMatch.addEventListener("click", async () => {
      const autoName = this.autoSelect.value;
      const csv = this.builderController ? this.builderController.getRobotCSV() : "";
      const maxRounds = this.playcountSelect ? (parseInt(this.playcountSelect.value, 10) || 10) : 10;
      try {
        const data = await PlaytestApi.startNewMatch({
          player_csv: csv,
          automaton: autoName,
          player_name: "Player Bot",
          max_rounds: maxRounds,
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

    if (this.btnToggleTopBar && this.viewArena) {
      this.btnToggleTopBar.addEventListener("click", () => {
        const isCollapsed = this.viewArena.classList.toggle("top-bar-collapsed");
        this.btnToggleTopBar.textContent = isCollapsed ? "▼ Show Controls" : "▲ Hide Controls";
      });
    }
  }

  async _deployFromBuilder(csvText, robotName) {
    try {
      const autoName = this.autoSelect ? this.autoSelect.value : "Vyper_flipper";
      const maxRounds = this.playcountSelect ? (parseInt(this.playcountSelect.value, 10) || 10) : 10;
      const data = await PlaytestApi.startNewMatch({
        player_csv: csvText,
        automaton: autoName,
        player_name: robotName || "Player Bot",
        max_rounds: maxRounds,
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
    if (!this.currentMatch) return;

    if (this.currentMatch.phase === "game_over") {
      // Tap button to start a fresh match
      this.btnNewMatch.click();
      return;
    }

    this.btnExecuteTurn.disabled = true;
    this.btnExecuteTurn.textContent = "⚙️ Executing...";

    try {
      const data = await PlaytestApi.submitTurn(this.turnLeft, this.turnRight);
      this.currentMatch = data.match;

      // Animate trajectory movement on arena
      this.arenaRenderer.animateTurn(this.currentMatch, () => {
        this._updateMatchUi();
      });

    } catch (err) {
      alert("Turn failed: " + err.message);
      this.btnExecuteTurn.disabled = false;
      this.btnExecuteTurn.textContent = "🚀 Lock in Drive & Execute Turn";
    }
  }

  _updateMatchUi() {
    if (!this.currentMatch) return;

    const m = this.currentMatch;
    const pBot = m.player_robot;
    const aBot = m.automaton_robot;

    // HUD Header
    const maxRounds = m.max_rounds || 10;
    this.hudRound.textContent = `Round ${m.round} / ${maxRounds}`;

    if (this.playcountSelect && this.playcountSelect.value !== String(maxRounds)) {
      let opt = [...this.playcountSelect.options].find(o => o.value === String(maxRounds));
      if (!opt) {
        opt = document.createElement("option");
        opt.value = String(maxRounds);
        opt.textContent = `${maxRounds} Rds`;
        this.playcountSelect.insertBefore(opt, this.playcountSelect.lastElementChild);
      }
      this.playcountSelect.value = String(maxRounds);
    }

    if (m.phase === "game_over") {
      this.hudStatus.innerHTML = `<span class="badge badge-danger">🏆 WINNER: ${m.winner.toUpperCase()} (${m.win_reason})</span>`;
      this.btnExecuteTurn.disabled = false;
      this.btnExecuteTurn.textContent = "🔄 Match Complete — Tap for New Match";
    } else {
      this.hudStatus.innerHTML = `<span class="badge badge-success">PLANNING PHASE</span>`;
      this.btnExecuteTurn.disabled = false;
      this.btnExecuteTurn.textContent = "🚀 Lock in Drive & Execute Turn";
    }

    // Combatants Bar: Weight, Cost & Inversion Status
    if (this.hudPname) this.hudPname.textContent = pBot.name;
    if (this.hudPspecs) this.hudPspecs.textContent = `⚖️ ${pBot.total_weight || 0} Wt • 💰 $${pBot.total_cost || 0}`;
    if (this.hudPinverted) this.hudPinverted.style.display = pBot.is_inverted ? "inline-block" : "none";

    if (this.hudAname) this.hudAname.textContent = aBot.name;
    if (this.hudAspecs) this.hudAspecs.textContent = `⚖️ ${aBot.total_weight || 0} Wt • 💰 $${aBot.total_cost || 0}`;
    if (this.hudAinverted) this.hudAinverted.style.display = aBot.is_inverted ? "inline-block" : "none";

    // Spin summary in banner
    const pSpin = Object.values(pBot.weapon_spin_counters || {}).reduce((a, b) => a + b, 0);
    const aSpin = Object.values(aBot.weapon_spin_counters || {}).reduce((a, b) => a + b, 0);
    const pSpinBadge = pSpin > 0 ? ` <span class="badge badge-cyan">🌀 ${pSpin} Spin</span>` : "";
    const aSpinBadge = aSpin > 0 ? ` <span class="badge badge-cyan">🌀 ${aSpin} Spin</span>` : "";

    // Opponent header banner (rolling is executed after player choices and kept strictly to the combat log)
    this.hudAutoBanner.innerHTML = `<span>Opponent: <strong>${aBot.name}</strong>${aSpinBadge}</span>`;

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
  window.app = app;
  app.init();
});
