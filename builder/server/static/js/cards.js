/**
 * Card Catalogue Drawer Module
 */

import { state } from "./state.js";

export class CardCatalogue {
  constructor(drawerEl, listContainerEl, searchInputEl, categoryPillsEl) {
    this.drawer = drawerEl;
    this.listContainer = listContainerEl;
    this.searchInput = searchInputEl;
    this.categoryPills = categoryPillsEl;

    this.activeCategory = "all";
    this.searchQuery = "";

    this._bindEvents();
  }

  _bindEvents() {
    this.searchInput.addEventListener("input", (e) => {
      this.searchQuery = e.target.value.toLowerCase().trim();
      this.render();
    });

    this.categoryPills.addEventListener("click", (e) => {
      const btn = e.target.closest(".pill-btn");
      if (!btn) return;
      this.categoryPills.querySelectorAll(".pill-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      this.activeCategory = btn.getAttribute("data-category") || "all";
      this.render();
    });
  }

  open() {
    this.drawer.classList.add("open");
    this.render();
  }

  close() {
    this.drawer.classList.remove("open");
  }

  toggle() {
    if (this.drawer.classList.contains("open")) {
      this.close();
    } else {
      this.open();
    }
  }

  render() {
    this.listContainer.innerHTML = "";

    const filtered = state.cardCatalog.filter(card => {
      // Chassis are printed mats, not cards
      if (card.type === "chassis") return false;

      // Category filter
      if (this.activeCategory !== "all" && card.type !== this.activeCategory) {
        return false;
      }
      // Search query filter
      if (this.searchQuery) {
        const textToSearch = [
          card.name,
          card.keywords,
          card.text,
          card.template,
          card.requirements,
          card.outputs,
        ].filter(Boolean).join(" ").toLowerCase();
        if (!textToSearch.includes(this.searchQuery)) {
          return false;
        }
      }
      return true;
    });

    if (filtered.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-notice";
      empty.textContent = "No matching cards found.";
      this.listContainer.appendChild(empty);
      return;
    }

    for (const card of filtered) {
      const item = document.createElement("div");
      item.className = "catalog-card-item";

      const thumb = document.createElement("div");
      thumb.className = "catalog-card-thumb";
      if (card.image_url) {
        const img = document.createElement("img");
        img.src = card.image_url;
        img.alt = card.name;
        img.loading = "lazy";
        thumb.appendChild(img);
      } else {
        thumb.textContent = card.name.charAt(0);
      }

      const title = document.createElement("div");
      title.className = "catalog-card-title";
      title.title = card.name;
      title.textContent = card.name;

      const stats = document.createElement("div");
      stats.className = "catalog-card-stats";
      stats.innerHTML = `<span class="wt">Wt: ${card.weight || 0}</span><span class="cost">$${card.cost || 0}</span>`;

      const actions = document.createElement("div");
      actions.className = "catalog-card-actions";

      const btnAdd = document.createElement("button");
      btnAdd.className = "btn btn-primary";
      btnAdd.title = "Place on Chassis";
      btnAdd.textContent = "+ Chassis";
      btnAdd.addEventListener("click", () => {
        state.addCardToChassis(card);
        this.close();
      });

      const btnSpares = document.createElement("button");
      btnSpares.className = "btn btn-action";
      btnSpares.title = "Add to Spare Parts";
      btnSpares.textContent = "+ Spares";
      btnSpares.addEventListener("click", () => {
        state.addCardToSpares(card);
        // Don't close immediately, allow adding multiple spares
        btnSpares.textContent = "✓ Added";
        setTimeout(() => { btnSpares.textContent = "+ Spares"; }, 800);
      });

      actions.appendChild(btnAdd);
      actions.appendChild(btnSpares);

      item.appendChild(thumb);
      item.appendChild(title);
      item.appendChild(stats);
      item.appendChild(actions);
      this.listContainer.appendChild(item);
    }
  }
}
