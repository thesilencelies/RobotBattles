/**
 * Application Entry Point and Controller
 */

import { MatCanvas } from "./canvas.js";
import { CardCatalogue } from "./cards.js";
import {
  downloadCsvFile,
  fetchServerRobots,
  loadRobotFromServer,
  parseCsvToRobot,
  saveRobotToServer,
  serializeRobotToCsv,
} from "./csv.js";
import { SparesDrawer } from "./spares.js";
import { state } from "./state.js";

class App {
  constructor() {
    this.canvas = null;
    this.catalogue = null;
    this.spares = null;
  }

  async init() {
    this._cacheElements();
    this._bindUiEvents();

    try {
      // 1. Load card catalogue and chassis definitions
      const [cardsRes, chassisRes] = await Promise.all([
        fetch("/api/cards").then(r => r.json()),
        fetch("/api/chassis").then(r => r.json()),
      ]);

      state.cardCatalog = cardsRes.all || [];
      state.chassisList = chassisRes || [];

      // 2. Populate Chassis Selector
      this._populateChassisSelect();

      // 3. Set default chassis (Viper Wedge Chassis or first)
      const defaultChassis = state.chassisList.find(c => c.name.includes("Viper")) || state.chassisList[0];
      if (defaultChassis) {
        state.setChassis(defaultChassis);
      }

      // 4. Initialize Components
      this.canvas = new MatCanvas(this.canvasContainer, this.matSvg);
      this.catalogue = new CardCatalogue(
        this.drawerCatalogue,
        this.catalogueList,
        this.cardSearchInput,
        this.categoryPills
      );
      this.spares = new SparesDrawer(this.drawerSpares, this.sparesList);

      // 5. Subscribe to State changes
      state.subscribe(() => this._onStateChange());
      this._onStateChange();

      // Fit canvas view
      setTimeout(() => {
        this.canvas.zoomFit();
      }, 100);

    } catch (err) {
      console.error("Initialization error:", err);
      alert("Failed to load game assets. Check if server is running.");
    }
  }

  _cacheElements() {
    this.robotNameInput = document.getElementById("robot-name-input");
    this.chassisSelect = document.getElementById("chassis-select");
    this.btnSnapToggle = document.getElementById("btn-snap-toggle");
    this.btnSaveModal = document.getElementById("btn-save-modal");
    this.btnLoadModal = document.getElementById("btn-load-modal");
    this.btnPrintSheet = document.getElementById("btn-print-sheet");

    // Stats
    this.statWeightVal = document.getElementById("stat-weight-val");
    this.statCostVal = document.getElementById("stat-cost-val");
    this.statFlipVal = document.getElementById("stat-flip-val");
    this.statSparesCount = document.getElementById("stat-spares-count");
    this.statSparesCost = document.getElementById("stat-spares-cost");
    this.statTotalPoolVal = document.getElementById("stat-total-pool-val");
    this.badgeSparesToggle = document.getElementById("badge-spares-toggle");
    this.navSparesBadge = document.getElementById("nav-spares-badge");

    // Canvas & Controls
    this.canvasContainer = document.getElementById("canvas-container");
    this.matSvg = document.getElementById("mat-svg");
    this.btnZoomIn = document.getElementById("btn-zoom-in");
    this.btnZoomOut = document.getElementById("btn-zoom-out");
    this.btnZoomFit = document.getElementById("btn-zoom-fit");
    this.btnPanToggle = document.getElementById("btn-pan-toggle");

    // Inspector
    this.cardInspector = document.getElementById("card-inspector");
    this.inspectorCardName = document.getElementById("inspector-card-name");
    this.inspectorCardStats = document.getElementById("inspector-card-stats");
    this.btnRotateCard = document.getElementById("btn-rotate-card");
    this.btnToSpares = document.getElementById("btn-to-spares");
    this.btnDupCard = document.getElementById("btn-dup-card");
    this.btnDelCard = document.getElementById("btn-del-card");
    this.btnCloseInspector = document.getElementById("btn-close-inspector");

    // Bottom Navigation
    this.tabBtnCanvas = document.getElementById("tab-btn-canvas");
    this.tabBtnCatalogue = document.getElementById("tab-btn-catalogue");
    this.tabBtnSpares = document.getElementById("tab-btn-spares");

    // Drawers
    this.drawerCatalogue = document.getElementById("drawer-catalogue");
    this.drawerSpares = document.getElementById("drawer-spares");
    this.catalogueList = document.getElementById("catalogue-list");
    this.sparesList = document.getElementById("spares-list");
    this.cardSearchInput = document.getElementById("card-search-input");
    this.categoryPills = document.querySelector(".category-pills");
    this.btnCloseCatalogue = document.getElementById("btn-close-catalogue");
    this.btnCloseSpares = document.getElementById("btn-close-spares");

    // Modal
    this.modalStorage = document.getElementById("modal-storage");
    this.btnCloseModal = document.getElementById("btn-close-modal");
    this.tabFileOps = document.getElementById("tab-file-ops");
    this.tabServerOps = document.getElementById("tab-server-ops");
    this.panelFileOps = document.getElementById("panel-file-ops");
    this.panelServerOps = document.getElementById("panel-server-ops");
    this.btnDownloadCsv = document.getElementById("btn-download-csv");
    this.downloadFilenameLbl = document.getElementById("download-filename-lbl");
    this.fileUploadInput = document.getElementById("file-upload-input");
    this.btnTriggerUpload = document.getElementById("btn-trigger-upload");
    this.serverSaveName = document.getElementById("server-save-name");
    this.btnServerSave = document.getElementById("btn-server-save");
    this.savedRobotsList = document.getElementById("saved-robots-list");
  }

  _populateChassisSelect() {
    this.chassisSelect.innerHTML = "";
    for (const ch of state.chassisList) {
      const opt = document.createElement("option");
      opt.value = ch.name;
      opt.textContent = `${ch.name} (${ch.template || "Square"}) - Wt:${ch.weight} $${ch.cost}`;
      this.chassisSelect.appendChild(opt);
    }
  }

  _bindUiEvents() {
    // Robot Name
    this.robotNameInput.addEventListener("input", (e) => {
      state.setRobotName(e.target.value);
    });

    // Chassis Selector
    this.chassisSelect.addEventListener("change", (e) => {
      const selected = state.chassisList.find(c => c.name === e.target.value);
      if (selected) {
        state.setChassis(selected);
      }
    });

    // Snap Toggle
    this.btnSnapToggle.addEventListener("click", () => {
      state.setSnapEnabled(!state.snapEnabled);
    });

    // Zoom Controls
    this.btnZoomIn.addEventListener("click", () => this.canvas && this.canvas.zoomIn());
    this.btnZoomOut.addEventListener("click", () => this.canvas && this.canvas.zoomOut());
    this.btnZoomFit.addEventListener("click", () => this.canvas && this.canvas.zoomFit());
    this.btnPanToggle.addEventListener("click", () => this.canvas && this.canvas.togglePanMode(this.btnPanToggle));

    // Print A3 Sheet
    this.btnPrintSheet.addEventListener("click", () => {
      if (state.chassis) {
        window.open(`/api/chassis/${encodeURIComponent(state.chassis.name)}/svg`, "_blank");
      }
    });

    // Inspector Actions
    this.btnRotateCard.addEventListener("click", () => {
      if (state.selectedCardId) state.rotatePlacedCard(state.selectedCardId, 90);
    });
    this.btnToSpares.addEventListener("click", () => {
      if (state.selectedCardId) state.moveCardToSpares(state.selectedCardId);
    });
    this.btnDupCard.addEventListener("click", () => {
      if (state.selectedCardId) state.duplicatePlacedCard(state.selectedCardId);
    });
    this.btnDelCard.addEventListener("click", () => {
      if (state.selectedCardId) state.removePlacedCard(state.selectedCardId);
    });
    this.btnCloseInspector.addEventListener("click", () => {
      state.selectCard(null);
    });

    // Bottom Navigation Tabs
    this.tabBtnCanvas.addEventListener("click", () => {
      this._setActiveNavTab("canvas");
      this.catalogue.close();
      this.spares.close();
    });
    this.tabBtnCatalogue.addEventListener("click", () => {
      this._setActiveNavTab("catalogue");
      this.spares.close();
      this.catalogue.open();
    });
    this.tabBtnSpares.addEventListener("click", () => {
      this._setActiveNavTab("spares");
      this.catalogue.close();
      this.spares.open();
    });
    this.badgeSparesToggle.addEventListener("click", () => {
      this._setActiveNavTab("spares");
      this.catalogue.close();
      this.spares.open();
    });

    this.btnCloseCatalogue.addEventListener("click", () => {
      this.catalogue.close();
      this._setActiveNavTab("canvas");
    });
    this.btnCloseSpares.addEventListener("click", () => {
      this.spares.close();
      this._setActiveNavTab("canvas");
    });

    // Save/Load Modals
    this.btnSaveModal.addEventListener("click", () => this._openStorageModal("save"));
    this.btnLoadModal.addEventListener("click", () => this._openStorageModal("load"));
    this.btnCloseModal.addEventListener("click", () => this._closeStorageModal());

    this.tabFileOps.addEventListener("click", () => this._switchStorageTab("file"));
    this.tabServerOps.addEventListener("click", () => this._switchStorageTab("server"));

    // File download
    this.btnDownloadCsv.addEventListener("click", () => {
      const csv = serializeRobotToCsv();
      downloadCsvFile(`${state.robotName}.csv`, csv);
    });

    // File upload
    this.btnTriggerUpload.addEventListener("click", () => this.fileUploadInput.click());
    this.fileUploadInput.addEventListener("change", (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (event) => {
        try {
          const csvText = event.target.result;
          const parsed = parseCsvToRobot(csvText);
          state.loadRobot(parsed);
          state.setRobotName(file.name.replace(/\.[^/.]+$/, ""));
          this._closeStorageModal();
          alert(`Loaded robot from ${file.name}`);
        } catch (err) {
          alert(`Error loading CSV: ${err.message}`);
        }
      };
      reader.readAsText(file);
      e.target.value = "";
    });

    // Server Save/Load
    this.btnServerSave.addEventListener("click", async () => {
      const name = (this.serverSaveName.value || state.robotName || "my_robot").trim();
      try {
        const csv = serializeRobotToCsv();
        await saveRobotToServer(name, csv);
        alert(`Saved ${name}.csv to server!`);
        this._refreshServerRobotsList();
      } catch (err) {
        alert(`Failed to save: ${err.message}`);
      }
    });
  }

  _setActiveNavTab(tab) {
    this.tabBtnCanvas.classList.toggle("active", tab === "canvas");
    this.tabBtnCatalogue.classList.toggle("active", tab === "catalogue");
    this.tabBtnSpares.classList.toggle("active", tab === "spares");
  }

  _openStorageModal(mode = "save") {
    this.modalStorage.classList.remove("hidden");
    this.downloadFilenameLbl.textContent = `${state.robotName}.csv`;
    this.serverSaveName.value = state.robotName;
    this._refreshServerRobotsList();
  }

  _closeStorageModal() {
    this.modalStorage.classList.add("hidden");
  }

  _switchStorageTab(tab) {
    this.tabFileOps.classList.toggle("active", tab === "file");
    this.tabServerOps.classList.toggle("active", tab === "server");
    this.panelFileOps.classList.toggle("active", tab === "file");
    this.panelServerOps.classList.toggle("active", tab === "server");
  }

  async _refreshServerRobotsList() {
    this.savedRobotsList.innerHTML = `<div class="empty-notice">Loading saved robots...</div>`;
    const robots = await fetchServerRobots();
    this.savedRobotsList.innerHTML = "";

    if (!robots || robots.length === 0) {
      this.savedRobotsList.innerHTML = `<div class="empty-notice">No robots saved in automata/ yet.</div>`;
      return;
    }

    for (const r of robots) {
      const row = document.createElement("div");
      row.className = "robot-row-item";
      row.innerHTML = `
        <span class="robot-row-name">${r.name}</span>
        <button class="btn btn-secondary btn-load-server" data-filename="${r.filename}">Load</button>
      `;
      row.querySelector(".btn-load-server").addEventListener("click", async () => {
        try {
          const parsed = await loadRobotFromServer(r.filename);
          state.loadRobot(parsed);
          state.setRobotName(r.name);
          this._closeStorageModal();
          alert(`Loaded ${r.name} from server!`);
        } catch (err) {
          alert(`Failed to load ${r.name}: ${err.message}`);
        }
      });
      this.savedRobotsList.appendChild(row);
    }
  }

  _onStateChange() {
    const stats = state.getComputedStats();

    // Stats Bar
    this.statWeightVal.textContent = stats.activeWeight;
    this.statCostVal.textContent = `$${stats.activeCost}`;
    this.statFlipVal.textContent = stats.flipStrength;
    this.statSparesCount.textContent = stats.sparesCount;
    this.statSparesCost.textContent = `($${stats.sparesCost})`;
    this.statTotalPoolVal.textContent = `$${stats.totalPoolCost}`;
    this.navSparesBadge.textContent = stats.sparesCount;

    // Grid Snap button
    this.btnSnapToggle.classList.toggle("active", state.snapEnabled);
    this.btnSnapToggle.querySelector(".label").textContent = state.snapEnabled ? "Snap: ON" : "Snap: OFF";

    // Chassis Selector Sync
    if (state.chassis && this.chassisSelect.value !== state.chassis.name) {
      this.chassisSelect.value = state.chassis.name;
    }

    // Selected Card Inspector
    if (state.selectedCardId) {
      const card = state.placedCards.find(c => c.id === state.selectedCardId);
      if (card) {
        this.cardInspector.classList.remove("hidden");
        this.inspectorCardName.textContent = card.cardData.name || "Card";
        this.inspectorCardStats.textContent = `Wt: ${card.cardData.weight || 0} | $${card.cardData.cost || 0} | ${card.rotation}°`;
      } else {
        this.cardInspector.classList.add("hidden");
      }
    } else {
      this.cardInspector.classList.add("hidden");
    }
  }
}

// Start app on DOMContentLoaded
window.addEventListener("DOMContentLoaded", () => {
  const app = new App();
  app.init();
});
