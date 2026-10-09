/**
 * Spare Parts Drawer Module
 */

import { state } from "./state.js";

export class SparesDrawer {
  constructor(drawerEl, listContainerEl) {
    this.drawer = drawerEl;
    this.listContainer = listContainerEl;

    state.subscribe(() => this.render());
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

    if (state.spareCards.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-notice";
      empty.innerHTML = `No spare parts stored.<br><br>Add spares from the <strong>Add Cards</strong> catalogue or send placed cards here using the inspector.`;
      this.listContainer.appendChild(empty);
      return;
    }

    for (const spare of state.spareCards) {
      const cardData = spare.cardData;
      const item = document.createElement("div");
      item.className = "spare-item";

      const thumb = document.createElement("div");
      thumb.className = "spare-item-thumb";
      if (cardData.image_url) {
        const img = document.createElement("img");
        img.src = cardData.image_url;
        img.alt = cardData.name;
        img.loading = "lazy";
        img.onerror = () => {
          img.style.display = "none";
          thumb.textContent = cardData.name.charAt(0);
        };
        thumb.appendChild(img);
      } else {
        thumb.textContent = cardData.name.charAt(0);
      }

      const title = document.createElement("div");
      title.className = "catalog-card-title";
      title.title = cardData.name;
      title.textContent = cardData.name;

      const stats = document.createElement("div");
      stats.className = "catalog-card-stats";
      stats.innerHTML = `<span class="wt">Wt: ${cardData.weight || 0}</span><span class="cost">$${cardData.cost || 0}</span>`;

      const actions = document.createElement("div");
      actions.className = "spare-actions";

      const btnToChassis = document.createElement("button");
      btnToChassis.className = "btn btn-primary";
      btnToChassis.title = "Move to Active Chassis";
      btnToChassis.textContent = "To Chassis";
      btnToChassis.addEventListener("click", () => {
        state.moveSpareToChassis(spare.id);
        this.close();
      });

      const btnRemove = document.createElement("button");
      btnRemove.className = "btn btn-danger";
      btnRemove.title = "Delete from Supply";
      btnRemove.textContent = "🗑";
      btnRemove.addEventListener("click", () => {
        state.removeSpareCard(spare.id);
      });

      actions.appendChild(btnToChassis);
      actions.appendChild(btnRemove);

      item.appendChild(thumb);
      item.appendChild(title);
      item.appendChild(stats);
      item.appendChild(actions);

      this.listContainer.appendChild(item);
    }
  }
}
