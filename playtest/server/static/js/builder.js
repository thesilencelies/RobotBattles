/**
 * Embedded Robot Builder Controller for Robot Battles Playtest App
 * Adopts full standalone builder functionality plus "Deploy to Arena" bridge.
 */

import { MatCanvas } from "/js/canvas.js";
import { CardCatalogue } from "/js/cards.js";
import {
  downloadCsvFile,
  fetchServerRobots,
  loadRobotFromServer,
  parseCsvToRobot,
  saveRobotToServer,
  serializeRobotToCsv,
} from "/js/csv.js";
import { SparesDrawer } from "/js/spares.js";
import { state } from "/js/state.js";

export class BuilderController {
  constructor(options = {}) {
    this.canvas = null;
    this.catalogue = null;
    this.spares = null;
    this.onDeploy = options.onDeploy || null;
  }

  async init() {
    this._cacheElements();
    this._bindUiEvents();

    try {
      const [cardsRes, chassisRes] = await Promise.all([
        fetch("/api/cards").then(r => r.json()),
        fetch("/api/chassis").then(r => r.json()),
      ]);

      state.cardCatalog = cardsRes.all || [];
      state.chassisList = chassisRes || [];

      this._populateChassisSelect();

      const defaultChassis = state.chassisList.find(c => c.name.includes("Viper")) || state.chassisList[0];
      if (defaultChassis) {
        state.setChassis(defaultChassis);
      }

      this.canvas = new MatCanvas(this.canvasContainer, this.matSvg);
      this.catalogue = new CardCatalogue(
        this.drawerCatalogue,
        this.catalogueList,
        this.cardSearchInput,
        this.categoryPills
      );
      this.spares = new SparesDrawer(this.drawerSpares, this.sparesList);

      state.subscribe(() => this._onStateChange());
      this._onStateChange();

      // Load initial default robot (Vyper_Spinner) if available
      try {
        const resp = await fetch("/api/robots/Vyper_Spinner");
        if (resp.ok) {
          const csvText = await resp.text();
          const parsed = parseCsvToRobot(csvText);
          state.loadRobot(parsed);
        }
      } catch (err) {
        console.warn("Could not load default Vyper_Spinner:", err);
      }

      setTimeout(() => {
        if (this.canvas) this.canvas.zoomFit();
      }, 150);

    } catch (err) {
      console.error("Builder initialization error:", err);
    }
  }

  zoomFit() {
    if (this.canvas) {
      this.canvas.zoomFit();
    }
  }

  getRobotCSV() {
    return serializeRobotToCsv();
  }

  _cacheElements() {
    this.robotNameInput = document.getElementById("robot-name-input");
    this.chassisSelect = document.getElementById("chassis-select");
    this.btnSnapToggle = document.getElementById("btn-snap-toggle");
    this.btnSaveModal = document.getElementById("btn-save-modal");
    this.btnLoadModal = document.getElementById("btn-load-modal");
    this.btnPrintSheet = document.getElementById("btn-print-sheet");
    this.btnDeployToArena = document.getElementById("btn-deploy-to-arena");

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

    // Mobile / Bottom Navigation Tabs
    this.tabBtnCanvas = document.getElementById("tab-btn-canvas");
    this.tabBtnCatalogue = document.getElementById("tab-btn-catalogue");
    this.tabBtnSpares = document.getElementById("tab-btn-spares");

    // Drawers
    this.drawerCatalogue = document.getElementById("drawer-catalogue");
    this.btnCloseCatalogue = document.getElementById("btn-close-catalogue");
    this.cardSearchInput = document.getElementById("card-search-input");
    this.categoryPills = document.querySelectorAll(".category-pills .pill-btn, .pills-row .pill");
    this.catalogueList = document.getElementById("catalogue-list");

    this.drawerSpares = document.getElementById("drawer-spares");
    this.btnCloseSpares = document.getElementById("btn-close-spares");
    this.sparesList = document.getElementById("spares-list");

    // Storage Modal
    this.modalStorage = document.getElementById("modal-storage");
    this.modalStorageTitle = document.getElementById("modal-storage-title");
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

  _bindUiEvents() {
    if (this.robotNameInput) {
      this.robotNameInput.addEventListener("input", (e) => {
        state.setRobotName(e.target.value);
        if (this.downloadFilenameLbl) {
          this.downloadFilenameLbl.textContent = `${state.robotName}.csv`;
        }
      });
    }

    if (this.chassisSelect) {
      this.chassisSelect.addEventListener("change", (e) => {
        const found = state.chassisList.find(c => c.name === e.target.value);
        if (found) {
          state.setChassis(found);
          if (this.canvas) this.canvas.zoomFit();
        }
      });
    }

    if (this.btnSnapToggle) {
      this.btnSnapToggle.addEventListener("click", () => {
        state.setSnapEnabled(!state.snapEnabled);
      });
    }

    // Deploy to Arena Button
    if (this.btnDeployToArena) {
      this.btnDeployToArena.addEventListener("click", () => {
        if (!state.placedCards || state.placedCards.length === 0) {
          alert("Cannot deploy: Place components and active drive on your chassis first!");
          return;
        }
        const csvText = serializeRobotToCsv();
        if (this.onDeploy) {
          this.onDeploy(csvText, state.robotName);
        }
      });
    }

    // Canvas zoom & pan
    if (this.btnZoomIn) this.btnZoomIn.addEventListener("click", () => this.canvas && this.canvas.zoomIn());
    if (this.btnZoomOut) this.btnZoomOut.addEventListener("click", () => this.canvas && this.canvas.zoomOut());
    if (this.btnZoomFit) this.btnZoomFit.addEventListener("click", () => this.canvas && this.canvas.zoomFit());
    if (this.btnPanToggle) {
      this.btnPanToggle.addEventListener("click", () => {
        if (this.canvas) {
          const isPan = this.canvas.togglePanMode();
          this.btnPanToggle.classList.toggle("active", isPan);
        }
      });
    }

    // Card Inspector actions
    if (this.btnRotateCard) {
      this.btnRotateCard.addEventListener("click", () => {
        if (state.selectedCardId) state.rotateCard(state.selectedCardId, 90);
      });
    }
    if (this.btnToSpares) {
      this.btnToSpares.addEventListener("click", () => {
        if (state.selectedCardId) state.moveCardToSpares(state.selectedCardId);
      });
    }
    if (this.btnDupCard) {
      this.btnDupCard.addEventListener("click", () => {
        if (state.selectedCardId) state.duplicateCard(state.selectedCardId);
      });
    }
    if (this.btnDelCard) {
      this.btnDelCard.addEventListener("click", () => {
        if (state.selectedCardId) state.removePlacedCard(state.selectedCardId);
      });
    }
    if (this.btnCloseInspector) {
      this.btnCloseInspector.addEventListener("click", () => {
        state.selectedCardId = null;
        state.notify();
      });
    }

    // Drawers toggle
    if (this.tabBtnCatalogue) this.tabBtnCatalogue.addEventListener("click", () => this._openDrawer("catalogue"));
    if (this.tabBtnSpares) this.tabBtnSpares.addEventListener("click", () => this._openDrawer("spares"));
    if (this.badgeSparesToggle) this.badgeSparesToggle.addEventListener("click", () => this._openDrawer("spares"));

    if (this.btnCloseCatalogue) this.btnCloseCatalogue.addEventListener("click", () => this._closeDrawers());
    if (this.btnCloseSpares) this.btnCloseSpares.addEventListener("click", () => this._closeDrawers());
    if (this.tabBtnCanvas) this.tabBtnCanvas.addEventListener("click", () => this._closeDrawers());

    // Storage Modal
    if (this.btnSaveModal) {
      this.btnSaveModal.addEventListener("click", () => this._openStorageModal("save"));
    }
    if (this.btnLoadModal) {
      this.btnLoadModal.addEventListener("click", () => this._openStorageModal("load"));
    }
    if (this.btnCloseModal) {
      this.btnCloseModal.addEventListener("click", () => this._closeStorageModal());
    }

    if (this.tabFileOps) {
      this.tabFileOps.addEventListener("click", () => {
        this.tabFileOps.classList.add("active");
        if (this.tabServerOps) this.tabServerOps.classList.remove("active");
        if (this.panelFileOps) this.panelFileOps.classList.add("active");
        if (this.panelServerOps) this.panelServerOps.classList.remove("active");
      });
    }

    if (this.tabServerOps) {
      this.tabServerOps.addEventListener("click", () => {
        this.tabServerOps.classList.add("active");
        if (this.tabFileOps) this.tabFileOps.classList.remove("active");
        if (this.panelServerOps) this.panelServerOps.classList.add("active");
        if (this.panelFileOps) this.panelFileOps.classList.remove("active");
        this._refreshSavedRobotsList();
      });
    }

    if (this.btnDownloadCsv) {
      this.btnDownloadCsv.addEventListener("click", () => {
        downloadCsvFile(`${state.robotName || "Combat_Bot"}.csv`);
      });
    }

    if (this.btnTriggerUpload && this.fileUploadInput) {
      this.btnTriggerUpload.addEventListener("click", () => {
        this.fileUploadInput.click();
      });

      this.fileUploadInput.addEventListener("change", (e) => {
        const file = e.target.files && e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (evt) => {
          try {
            const parsed = parseCsvToRobot(evt.target.result);
            state.loadRobot(parsed);
            this._closeStorageModal();
          } catch (err) {
            alert("Error loading CSV: " + err.message);
          }
        };
        reader.readAsText(file);
      });
    }

    if (this.btnServerSave && this.serverSaveName) {
      this.btnServerSave.addEventListener("click", async () => {
        const name = (this.serverSaveName.value || state.robotName || "bot").trim();
        try {
          await saveRobotToServer(name);
          alert(`Saved ${name}.csv to server!`);
          this._refreshSavedRobotsList();
        } catch (err) {
          alert("Save failed: " + err.message);
        }
      });
    }

    if (this.btnPrintSheet) {
      this.btnPrintSheet.addEventListener("click", () => {
        if (!state.chassis) return;
        window.open(`/chassisSheets/${state.chassis.template.toLowerCase()}_sheet.html`, "_blank");
      });
    }
  }

  _populateChassisSelect() {
    if (!this.chassisSelect) return;
    this.chassisSelect.innerHTML = "";
    for (const c of state.chassisList) {
      const opt = document.createElement("option");
      opt.value = c.name;
      opt.textContent = `${c.name} (${c.template}) - Wt:${c.weight} $${c.cost}`;
      this.chassisSelect.appendChild(opt);
    }
  }

  _openDrawer(type) {
    if (type === "catalogue" && this.drawerCatalogue) {
      this.drawerCatalogue.classList.add("open");
      if (this.drawerSpares) this.drawerSpares.classList.remove("open");
      if (this.tabBtnCatalogue) this.tabBtnCatalogue.classList.add("active");
      if (this.tabBtnSpares) this.tabBtnSpares.classList.remove("active");
    } else if (type === "spares" && this.drawerSpares) {
      this.drawerSpares.classList.add("open");
      if (this.drawerCatalogue) this.drawerCatalogue.classList.remove("open");
      if (this.tabBtnSpares) this.tabBtnSpares.classList.add("active");
      if (this.tabBtnCatalogue) this.tabBtnCatalogue.classList.remove("active");
    }
  }

  _closeDrawers() {
    if (this.drawerCatalogue) this.drawerCatalogue.classList.remove("open");
    if (this.drawerSpares) this.drawerSpares.classList.remove("open");
    if (this.tabBtnCatalogue) this.tabBtnCatalogue.classList.remove("active");
    if (this.tabBtnSpares) this.tabBtnSpares.classList.remove("active");
    if (this.tabBtnCanvas) this.tabBtnCanvas.classList.add("active");
  }

  _openStorageModal(mode) {
    if (!this.modalStorage) return;
    this.modalStorage.classList.remove("hidden");
    if (this.serverSaveName) {
      this.serverSaveName.value = state.robotName || "Combat_Bot";
    }
    if (mode === "save") {
      if (this.modalStorageTitle) this.modalStorageTitle.textContent = "Save Robot CSV";
    } else {
      if (this.modalStorageTitle) this.modalStorageTitle.textContent = "Load Robot CSV";
    }
  }

  _closeStorageModal() {
    if (this.modalStorage) {
      this.modalStorage.classList.add("hidden");
    }
  }

  async _refreshSavedRobotsList() {
    if (!this.savedRobotsList) return;
    this.savedRobotsList.innerHTML = `<div class="empty-notice">Loading saved robots...</div>`;
    try {
      const robots = await fetchServerRobots();
      if (!robots || robots.length === 0) {
        this.savedRobotsList.innerHTML = `<div class="empty-notice">No saved robots found.</div>`;
        return;
      }
      this.savedRobotsList.innerHTML = "";
      for (const r of robots) {
        const item = document.createElement("div");
        item.className = "saved-robot-item";
        item.innerHTML = `
          <div class="robot-item-info">
            <strong>${r.name}</strong>
            <span class="robot-item-path">${r.path}</span>
          </div>
          <button class="btn btn-sm btn-secondary">Load</button>
        `;
        item.querySelector("button").addEventListener("click", async () => {
          try {
            const parsed = await loadRobotFromServer(r.name);
            state.loadRobot(parsed);
            state.setRobotName(r.name);
            this._closeStorageModal();
          } catch (err) {
            alert("Error loading robot: " + err.message);
          }
        });
        this.savedRobotsList.appendChild(item);
      }
    } catch (err) {
      this.savedRobotsList.innerHTML = `<div class="empty-notice">Failed to load saved robots list.</div>`;
    }
  }

  _onStateChange() {
    const stats = state.getComputedStats();

    if (this.statWeightVal) this.statWeightVal.textContent = stats.activeWeight;
    if (this.statCostVal) this.statCostVal.textContent = `$${stats.activeCost}`;
    if (this.statFlipVal) this.statFlipVal.textContent = stats.flipStrength;
    if (this.statSparesCount) this.statSparesCount.textContent = stats.sparesCount;
    if (this.statSparesCost) this.statSparesCost.textContent = `($${stats.sparesCost})`;
    if (this.statTotalPoolVal) this.statTotalPoolVal.textContent = `$${stats.totalPoolCost}`;
    if (this.navSparesBadge) this.navSparesBadge.textContent = stats.sparesCount;

    if (this.btnSnapToggle) {
      this.btnSnapToggle.classList.toggle("active", state.snapEnabled);
      const label = this.btnSnapToggle.querySelector(".label");
      if (label) label.textContent = state.snapEnabled ? "Snap: ON" : "Snap: OFF";
    }

    if (this.chassisSelect && state.chassis && this.chassisSelect.value !== state.chassis.name) {
      this.chassisSelect.value = state.chassis.name;
    }

    if (this.cardInspector) {
      if (state.selectedCardId) {
        const card = state.placedCards.find(c => c.id === state.selectedCardId);
        if (card) {
          this.cardInspector.classList.remove("hidden");
          if (this.inspectorCardName) this.inspectorCardName.textContent = card.cardData.name || "Card";
          if (this.inspectorCardStats) {
            this.inspectorCardStats.textContent = `Wt: ${card.cardData.weight || 0} | $${card.cardData.cost || 0} | ${card.rotation}°`;
          }
        } else {
          this.cardInspector.classList.add("hidden");
        }
      } else {
        this.cardInspector.classList.add("hidden");
      }
    }
  }
}
