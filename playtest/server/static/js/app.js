/**
 * Robot Battles Playtest App Master Controller
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

    // 3 Action Cards planning state
    this.selectedCards = ["Wait", "Wait", "Wait"];
    this.activeSlotIndex = 0;
    this.actionCardsList = [];
    this.actionCardsMap = new Map();
    this.activeFilter = "all";
  }

  async init() {
    this._cacheElements();
    this._bindTabs();
    await this._loadActionCards();
    this._renderActionCardsDrawer();
    this._bindActionPlanningControls();

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
    this.btnExportLog = document.getElementById("btn-export-log");
    this.btnExportLogTab = document.getElementById("btn-export-log-tab");
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

    // Turn Planning: 3 Action Cards Dock Elements
    this.budgetLeftSpent = document.getElementById("budget-left-spent");
    this.budgetLeftMax = document.getElementById("budget-left-max");
    this.budgetRightSpent = document.getElementById("budget-right-spent");
    this.budgetRightMax = document.getElementById("budget-right-max");
    this.budgetBarLeft = document.getElementById("budget-bar-left");
    this.budgetBarRight = document.getElementById("budget-bar-right");
    this.slotCards = document.querySelectorAll(".action-slot-card");
    this.actionCardsGrid = document.getElementById("action-cards-grid");
    this.categoryFilterButtons = document.querySelectorAll(".btn-filter-cat");
    this.presetButtons = document.querySelectorAll(".btn-preset");
    this.btnExecuteTurn = document.getElementById("btn-execute-turn");

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
      if (this.currentMatch.phase !== "game_over") {
        this._updatePlanningPreview();
      }
    } else if (tabName === "builder" && this.builderController) {
      setTimeout(() => this.builderController.zoomFit(), 100);
    }
  }

  async _loadActionCards() {
    try {
      const data = await PlaytestApi.getActionCards();
      this.actionCardsList = data.cards || [];
      this.actionCardsMap = new Map();
      for (const card of this.actionCardsList) {
        this.actionCardsMap.set(card.code, card);
      }
    } catch (err) {
      console.error("Could not load action cards:", err);
    }
  }

  _renderActionCardsDrawer() {
    if (!this.actionCardsGrid) return;
    this.actionCardsGrid.innerHTML = "";

    const filteredCards = this.actionCardsList.filter(card => {
      if (this.activeFilter === "all") return true;
      return card.category === this.activeFilter;
    });

    for (const card of filteredCards) {
      const item = document.createElement("div");
      item.className = "action-card-item";
      item.dataset.code = card.code;
      item.title = `${card.name}: ${card.motion} (L: ${card.left}, R: ${card.right})`;

      const thumb = document.createElement("img");
      thumb.className = "action-card-thumb";
      thumb.src = `/CardImages/${card.image}`;
      thumb.alt = card.code;
      thumb.onerror = () => { thumb.style.display = "none"; };
      item.appendChild(thumb);

      const title = document.createElement("div");
      title.className = "action-card-title";
      title.textContent = card.code;
      item.appendChild(title);

      const cost = document.createElement("div");
      cost.className = "action-card-cost-tag";
      cost.textContent = `L:${card.left} R:${card.right}`;
      item.appendChild(cost);

      item.addEventListener("click", () => {
        if (item.classList.contains("disabled")) return;
        this._selectDrawerCard(card.code);
      });

      this.actionCardsGrid.appendChild(item);
    }
  }

  _selectDrawerCard(cardCode) {
    this.selectedCards[this.activeSlotIndex] = cardCode;
    // Advance to next slot in sequence
    this.activeSlotIndex = (this.activeSlotIndex + 1) % 3;
    this._updateTurnPlanningControls();
  }

  _bindActionPlanningControls() {
    // 3 Slot card selections & clear buttons
    this.slotCards.forEach((slotEl) => {
      const slotIdx = parseInt(slotEl.dataset.slot, 10);
      slotEl.addEventListener("click", (e) => {
        if (e.target.closest(".btn-clear-slot")) {
          e.stopPropagation();
          this.selectedCards[slotIdx] = "Wait";
          this._updateTurnPlanningControls();
          return;
        }
        this.activeSlotIndex = slotIdx;
        this._updateTurnPlanningControls();
      });
    });

    // Category filter buttons
    this.categoryFilterButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        this.activeFilter = btn.dataset.cat || "all";
        this.categoryFilterButtons.forEach(b => b.classList.toggle("active", b === btn));
        this._renderActionCardsDrawer();
        this._updateTurnPlanningControls();
      });
    });

    // Tactical Preset buttons
    this.presetButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const preset = btn.dataset.preset;
        const pBot = this.currentMatch?.player_robot;
        const maxL = pBot?.left_drive_max ?? 3;
        const maxR = pBot?.right_drive_max ?? 3;
        const maxFwd = Math.min(3, Math.min(maxL, maxR));

        switch (preset) {
          case "rush":
            if (maxFwd >= 3) {
              this.selectedCards = ["3 F", "Wait", "Wait"];
            } else if (maxFwd >= 2) {
              this.selectedCards = ["2 F", "Wait", "Wait"];
            } else if (maxFwd >= 1) {
              this.selectedCards = ["1F", "Wait", "Wait"];
            } else {
              this.selectedCards = ["Wait", "Wait", "Wait"];
            }
            break;
          case "advance-pivot":
            this.selectedCards = ["1F", "90 PR", "Wait"];
            break;
          case "turn-right":
            this.selectedCards = ["90 R", "Wait", "Wait"];
            break;
          case "turn-left":
            this.selectedCards = ["90 L", "Wait", "Wait"];
            break;
          case "spin-180":
            this.selectedCards = ["180 P", "Wait", "Wait"];
            break;
          case "wait":
          case "clear":
            this.selectedCards = ["Wait", "Wait", "Wait"];
            break;
        }
        this.activeSlotIndex = 0;
        this._updateTurnPlanningControls();
      });
    });

    // Execute Turn button
    if (this.btnExecuteTurn) {
      this.btnExecuteTurn.addEventListener("click", () => this._onExecuteTurn());
    }

    // Playcount (Max Rounds) Select Change
    if (this.playcountSelect) {
      this.playcountSelect.addEventListener("change", (e) => {
        if (e.target.value === "custom") {
          const val = prompt("Enter max rounds / playcount (1 - 100):", "20");
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
            this.playcountSelect.value = "20";
          }
        }
      });
    }

    // New Match & Reset Buttons
    this.btnNewMatch.addEventListener("click", async () => {
      const autoName = this.autoSelect.value;
      const csv = this.builderController ? this.builderController.getRobotCSV() : "";
      const maxRounds = this.playcountSelect ? (parseInt(this.playcountSelect.value, 10) || 20) : 20;
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

    const handleExport = () => this._exportMatchLog();
    if (this.btnExportLog) {
      this.btnExportLog.addEventListener("click", handleExport);
    }
    if (this.btnExportLogTab) {
      this.btnExportLogTab.addEventListener("click", handleExport);
    }

    if (this.btnToggleTopBar && this.viewArena) {
      this.btnToggleTopBar.addEventListener("click", () => {
        const isCollapsed = this.viewArena.classList.toggle("top-bar-collapsed");
        this.btnToggleTopBar.textContent = isCollapsed ? "▼ Show Controls" : "▲ Hide Controls";
      });
    }
  }

  async _exportMatchLog() {
    try {
      const data = await PlaytestApi.exportMatchLog();
      const jsonStr = JSON.stringify(data, null, 2);
      const blob = new Blob([jsonStr], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const mId = data.match_id || "match";
      const rd = data.round !== undefined ? data.round : 1;
      a.href = url;
      a.download = `match_${mId}_round_${rd}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      alert("Failed to export match log: " + err.message);
    }
  }

  async _deployFromBuilder(csvText, robotName) {
    try {
      const autoName = this.autoSelect ? this.autoSelect.value : "Vyper_flipper";
      const maxRounds = this.playcountSelect ? (parseInt(this.playcountSelect.value, 10) || 20) : 20;
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
      if (this.currentMatch) {
        const allDamageSteps = this.currentMatch.damage_steps || [];
        if (this.currentMatch.player_robot) {
          this.currentMatch.player_robot.last_damage_steps = allDamageSteps.filter(s => s.robot_id === "player");
        }
        if (this.currentMatch.automaton_robot) {
          this.currentMatch.automaton_robot.last_damage_steps = allDamageSteps.filter(s => s.robot_id === "automaton");
        }
      }
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
    this.btnExecuteTurn.textContent = "⚙️ Executing 3 Action Cards...";
    this.arenaRenderer.clearPlanningPreview();

    let totalL = 0;
    let totalR = 0;
    for (const code of this.selectedCards) {
      const c = this.actionCardsMap.get(code) || { left: 0, right: 0 };
      totalL += (c.left || 0);
      totalR += (c.right || 0);
    }

    try {
      const data = await PlaytestApi.submitTurn({
        cards: this.selectedCards,
        left: totalL,
        right: totalR,
      });
      this.currentMatch = data.match;

      const allDamageSteps = this.currentMatch.damage_steps || [];
      const pSteps = allDamageSteps.filter(s => s.robot_id === "player");
      const aSteps = allDamageSteps.filter(s => s.robot_id === "automaton");

      if (this.currentMatch.player_robot) {
        this.currentMatch.player_robot.last_damage_steps = pSteps;
      }
      if (this.currentMatch.automaton_robot) {
        this.currentMatch.automaton_robot.last_damage_steps = aSteps;
      }

      // Animate trajectory movement on arena
      this.arenaRenderer.animateTurn(this.currentMatch, () => {
        this._runDamageTrainSequence(pSteps, aSteps, allDamageSteps);
      });

    } catch (err) {
      alert("Turn failed: " + err.message);
      this.btnExecuteTurn.disabled = false;
      this.btnExecuteTurn.textContent = "🚀 Lock in 3 Cards & Execute Turn";
    }
  }

  _runDamageTrainSequence(pSteps, aSteps, allDamageSteps) {
    if (!allDamageSteps || allDamageSteps.length === 0) {
      this._updateMatchUi();
      return;
    }

    // Determine sequence of tabs based on chronological combat events
    const firstBot = allDamageSteps[0].robot_id;
    const sequence = [];

    if (firstBot === "player") {
      if (pSteps.length > 0) sequence.push({ tab: "player-robot", container: this.playerRobotContainer, steps: pSteps, robot: this.currentMatch.player_robot, isAuto: false });
      if (aSteps.length > 0) sequence.push({ tab: "automaton-robot", container: this.automatonRobotContainer, steps: aSteps, robot: this.currentMatch.automaton_robot, isAuto: true });
    } else {
      if (aSteps.length > 0) sequence.push({ tab: "automaton-robot", container: this.automatonRobotContainer, steps: aSteps, robot: this.currentMatch.automaton_robot, isAuto: true });
      if (pSteps.length > 0) sequence.push({ tab: "player-robot", container: this.playerRobotContainer, steps: pSteps, robot: this.currentMatch.player_robot, isAuto: false });
    }

    let seqIndex = 0;
    const playNext = () => {
      if (seqIndex >= sequence.length) {
        this.switchTab("arena");
        this._updateMatchUi();
        return;
      }

      const item = sequence[seqIndex];
      seqIndex++;

      this.switchTab(item.tab);
      RobotViewRenderer.renderRobotState(item.container, item.robot, item.isAuto, null, null, this.currentMatch ? this.currentMatch.player_robot : null);

      setTimeout(() => {
        RobotViewRenderer.animateDamageTrain(item.container, item.steps, () => {
          setTimeout(playNext, 450);
        });
      }, 250);
    };

    // Pause briefly on arena after movement ends before stepping to robot view
    setTimeout(playNext, 500);
  }

  _updateMatchUi() {
    if (!this.currentMatch) return;

    const m = this.currentMatch;
    const pBot = m.player_robot;
    const aBot = m.automaton_robot;

    // HUD Header
    const maxRounds = m.max_rounds || 20;
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

    // Render Views
    this.arenaRenderer.render(m);
    RobotViewRenderer.renderRobotState(this.playerRobotContainer, pBot, false);
    RobotViewRenderer.renderRobotState(this.automatonRobotContainer, aBot, true, m.automaton_roll, m.automaton_action, pBot);
    CombatLogRenderer.renderLog(this.logContainer, m.log);

    // Update Turn Planning Dock (drive meters, slots, card drawer, preview)
    this._updateTurnPlanningControls();
  }

  _updateTurnPlanningControls() {
    const pBot = this.currentMatch?.player_robot;
    const maxL = Math.max(1, pBot?.left_drive_max ?? 1);
    const maxR = Math.max(1, pBot?.right_drive_max ?? 1);

    // Calculate spent drive budget
    let totalL = 0;
    let totalR = 0;
    for (const code of this.selectedCards) {
      const c = this.actionCardsMap.get(code) || { left: 0, right: 0 };
      totalL += (c.left || 0);
      totalR += (c.right || 0);
    }

    if (this.budgetLeftSpent) this.budgetLeftSpent.textContent = String(totalL);
    if (this.budgetLeftMax) this.budgetLeftMax.textContent = String(maxL);
    if (this.budgetRightSpent) this.budgetRightSpent.textContent = String(totalR);
    if (this.budgetRightMax) this.budgetRightMax.textContent = String(maxR);

    const pctL = Math.min(100, Math.round((totalL / maxL) * 100));
    const pctR = Math.min(100, Math.round((totalR / maxR) * 100));

    if (this.budgetBarLeft) {
      this.budgetBarLeft.style.width = `${pctL}%`;
      this.budgetBarLeft.classList.toggle("budget-over", totalL > maxL);
    }
    if (this.budgetBarRight) {
      this.budgetBarRight.style.width = `${pctR}%`;
      this.budgetBarRight.classList.toggle("budget-over", totalR > maxR);
    }

    // Update 3 Slot Displays
    this.slotCards.forEach((slotEl, idx) => {
      const code = this.selectedCards[idx] || "Wait";
      const card = this.actionCardsMap.get(code) || {
        code, name: code, left: 0, right: 0, image: "Action_Wait.png"
      };

      slotEl.classList.toggle("active", idx === this.activeSlotIndex);

      const img = slotEl.querySelector(".slot-card-img");
      if (img) {
        img.src = `/CardImages/${card.image}`;
        img.style.display = "block";
        img.onerror = () => { img.style.display = "none"; };
      }

      const codeEl = slotEl.querySelector(".slot-card-code");
      if (codeEl) codeEl.textContent = card.code;

      const nameEl = slotEl.querySelector(".slot-card-name");
      if (nameEl) nameEl.textContent = card.name;

      const costEl = slotEl.querySelector(".slot-card-cost");
      if (costEl) costEl.textContent = `L: ${card.left} • R: ${card.right}`;
    });

    // Update disabled state for cards in drawer
    const currentSlotCode = this.selectedCards[this.activeSlotIndex] || "Wait";
    const currentCard = this.actionCardsMap.get(currentSlotCode) || { left: 0, right: 0 };
    const baseL = totalL - (currentCard.left || 0);
    const baseR = totalR - (currentCard.right || 0);

    if (this.actionCardsGrid) {
      const items = this.actionCardsGrid.querySelectorAll(".action-card-item");
      items.forEach(item => {
        const cCode = item.dataset.code;
        const cData = this.actionCardsMap.get(cCode);
        if (cData) {
          const canAfford = (baseL + cData.left <= maxL) && (baseR + cData.right <= maxR);
          item.classList.toggle("disabled", !canAfford);
        }
      });
    }

    // Update Execute Button
    if (this.btnExecuteTurn) {
      const isOverBudget = totalL > maxL || totalR > maxR;
      if (this.currentMatch && this.currentMatch.phase === "game_over") {
        this.btnExecuteTurn.disabled = false;
        this.btnExecuteTurn.textContent = "🔄 Match Complete — Tap for New Match";
      } else {
        this.btnExecuteTurn.disabled = isOverBudget;
        if (isOverBudget) {
          this.btnExecuteTurn.textContent = `⚠️ Over Drive Budget (L: ${totalL}/${maxL}, R: ${totalR}/${maxR})`;
        } else {
          this.btnExecuteTurn.textContent = "🚀 Lock in 3 Cards & Execute Turn";
        }
      }
    }

    // Update Planning Preview on Arena
    this._updatePlanningPreview();
  }

  async _updatePlanningPreview() {
    if (this.currentMatch && this.currentMatch.player_robot && this.currentMatch.player_robot.pose) {
      if (this.currentMatch.phase !== "game_over" && !this.arenaRenderer.animating) {
        await this.arenaRenderer.renderActionPlanPreview(
          this.currentMatch.player_robot.pose,
          this.selectedCards,
          this.currentMatch.player_robot.chassis_template || "Square"
        );
      }
    } else {
      this.arenaRenderer.clearPlanningPreview();
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const app = new PlaytestApp();
  window.app = app;
  window.RobotViewRenderer = RobotViewRenderer;
  app.init();
});
