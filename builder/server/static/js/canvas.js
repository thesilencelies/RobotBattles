/**
 * Interactive A3 Mat Viewport and Canvas Renderer
 */

import {
  A3_HEIGHT_MM,
  A3_WIDTH_MM,
  CARD_HEIGHT_MM,
  CARD_WIDTH_MM,
  state,
} from "./state.js";

export class MatCanvas {
  constructor(containerEl, svgEl) {
    this.container = containerEl;
    this.svg = svgEl;

    this.layerChassis = svgEl.querySelector("#layer-chassis");
    this.layerCards = svgEl.querySelector("#layer-cards");
    this.layerConnections = svgEl.querySelector("#layer-connections");
    this.layerInteraction = svgEl.querySelector("#layer-interaction");

    this.chassisPoly = svgEl.querySelector("#chassis-poly");
    this.plateName = svgEl.querySelector("#plate-name");
    this.plateTemplate = svgEl.querySelector("#plate-template");
    this.plateImage = svgEl.querySelector("#plate-image");
    this.plateWeight = svgEl.querySelector("#plate-weight");
    this.plateCost = svgEl.querySelector("#plate-cost");
    this.plateFlip = svgEl.querySelector("#plate-flip");

    // Viewport transform (mm coordinate space)
    this.viewBox = {
      x: 0,
      y: 0,
      w: A3_WIDTH_MM,
      h: A3_HEIGHT_MM,
    };

    this.panMode = false;
    this.isPanning = false;
    this.isDraggingCard = false;
    this.draggedCardId = null;
    this.dragStart = { x: 0, y: 0 };
    this.cardStartPos = { x: 0, y: 0 };

    // Multi-touch tracking
    this.activeTouches = new Map();
    this.initialPinchDist = null;
    this.initialViewBoxW = null;

    this._bindEvents();
    state.subscribe(() => this.render());
  }

  _bindEvents() {
    // Mouse wheel zoom
    this.container.addEventListener("wheel", (e) => this._onWheel(e), { passive: false });

    // Pointer events for dragging & panning
    this.svg.addEventListener("pointerdown", (e) => this._onPointerDown(e));
    window.addEventListener("pointermove", (e) => this._onPointerMove(e));
    window.addEventListener("pointerup", (e) => this._onPointerUp(e));
    window.addEventListener("pointercancel", (e) => this._onPointerUp(e));

    // Touch events for two-finger gestures (pinch zoom & pan)
    this.container.addEventListener("touchstart", (e) => this._onTouchStart(e), { passive: false });
    this.container.addEventListener("touchmove", (e) => this._onTouchMove(e), { passive: false });
    this.container.addEventListener("touchend", (e) => this._onTouchEnd(e));
    this.container.addEventListener("touchcancel", (e) => this._onTouchEnd(e));
  }

  screenToSvg(clientX, clientY) {
    const rect = this.svg.getBoundingClientRect();
    const pxX = clientX - rect.left;
    const pxY = clientY - rect.top;

    const svgX = this.viewBox.x + (pxX / rect.width) * this.viewBox.w;
    const svgY = this.viewBox.y + (pxY / rect.height) * this.viewBox.h;
    return { x: svgX, y: svgY };
  }

  _updateViewBox() {
    this.svg.setAttribute("viewBox", `${this.viewBox.x} ${this.viewBox.y} ${this.viewBox.w} ${this.viewBox.h}`);
  }

  zoomAt(svgFocusX, svgFocusY, factor) {
    const minW = 80;
    const maxW = A3_WIDTH_MM * 2.5;

    const newW = Math.max(minW, Math.min(maxW, this.viewBox.w * factor));
    const newH = newW * (A3_HEIGHT_MM / A3_WIDTH_MM);

    // Zoom centered on focus point
    const ratioX = (svgFocusX - this.viewBox.x) / this.viewBox.w;
    const ratioY = (svgFocusY - this.viewBox.y) / this.viewBox.h;

    this.viewBox.x = svgFocusX - ratioX * newW;
    this.viewBox.y = svgFocusY - ratioY * newH;
    this.viewBox.w = newW;
    this.viewBox.h = newH;
    this._updateViewBox();
  }

  zoomIn() {
    this.zoomAt(this.viewBox.x + this.viewBox.w / 2, this.viewBox.y + this.viewBox.h / 2, 0.8);
  }

  zoomOut() {
    this.zoomAt(this.viewBox.x + this.viewBox.w / 2, this.viewBox.y + this.viewBox.h / 2, 1.25);
  }

  zoomFit() {
    this.viewBox = {
      x: 0,
      y: 0,
      w: A3_WIDTH_MM,
      h: A3_HEIGHT_MM,
    };
    this._updateViewBox();
  }

  togglePanMode(btnEl) {
    this.panMode = !this.panMode;
    if (btnEl) {
      btnEl.classList.toggle("active", this.panMode);
    }
    this.svg.classList.toggle("panning", this.panMode);
  }

  _onWheel(e) {
    e.preventDefault();
    const pt = this.screenToSvg(e.clientX, e.clientY);
    const factor = e.deltaY > 0 ? 1.12 : 0.89;
    this.zoomAt(pt.x, pt.y, factor);
  }

  _onPointerDown(e) {
    // If middle click or right click or in pan mode -> pan
    if (e.button === 1 || e.button === 2 || this.panMode) {
      this.isPanning = true;
      this.dragStart = { x: e.clientX, y: e.clientY };
      this.svg.classList.add("panning");
      return;
    }

    if (e.button !== 0) return;

    // Check if clicked on a card
    const cardNode = e.target.closest(".card-node");
    if (cardNode) {
      const cardId = cardNode.getAttribute("data-card-id");
      const card = state.placedCards.find(c => c.id === cardId);
      if (card) {
        state.selectCard(cardId);
        this.isDraggingCard = true;
        this.draggedCardId = cardId;
        const pt = this.screenToSvg(e.clientX, e.clientY);
        this.dragStart = pt;
        this.cardStartPos = { x: card.x, y: card.y };
        return;
      }
    }

    // Clicked background: start pan or deselect
    state.selectCard(null);
    this.isPanning = true;
    this.dragStart = { x: e.clientX, y: e.clientY };
  }

  _onPointerMove(e) {
    if (this.isPanning) {
      const dxPx = e.clientX - this.dragStart.x;
      const dyPx = e.clientY - this.dragStart.y;
      this.dragStart = { x: e.clientX, y: e.clientY };

      const rect = this.svg.getBoundingClientRect();
      const dxSvg = (dxPx / rect.width) * this.viewBox.w;
      const dySvg = (dyPx / rect.height) * this.viewBox.h;

      this.viewBox.x -= dxSvg;
      this.viewBox.y -= dySvg;
      this._updateViewBox();
      return;
    }

    if (this.isDraggingCard && this.draggedCardId) {
      const curSvg = this.screenToSvg(e.clientX, e.clientY);
      const dx = curSvg.x - this.dragStart.x;
      const dy = curSvg.y - this.dragStart.y;

      const newX = this.cardStartPos.x + dx;
      const newY = this.cardStartPos.y + dy;

      state.setPlacedCardPosition(this.draggedCardId, newX, newY);
    }
  }

  _onPointerUp(e) {
    if (this.isPanning) {
      this.isPanning = false;
      this.svg.classList.remove("panning");
    }
    if (this.isDraggingCard) {
      this.isDraggingCard = false;
      this.draggedCardId = null;
    }
  }

  _onTouchStart(e) {
    if (e.touches.length === 2) {
      e.preventDefault();
      this.isDraggingCard = false;
      this.isPanning = false;

      const t1 = e.touches[0];
      const t2 = e.touches[1];
      this.initialPinchDist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
      this.initialViewBoxW = this.viewBox.w;

      const midClientX = (t1.clientX + t2.clientX) / 2;
      const midClientY = (t1.clientY + t2.clientY) / 2;
      this.pinchFocus = this.screenToSvg(midClientX, midClientY);
      this.dragStart = { x: midClientX, y: midClientY };
    }
  }

  _onTouchMove(e) {
    if (e.touches.length === 2 && this.initialPinchDist) {
      e.preventDefault();
      const t1 = e.touches[0];
      const t2 = e.touches[1];
      const dist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
      const ratio = this.initialPinchDist / dist;

      const midClientX = (t1.clientX + t2.clientX) / 2;
      const midClientY = (t1.clientY + t2.clientY) / 2;

      // Pan with 2 fingers
      const dxPx = midClientX - this.dragStart.x;
      const dyPx = midClientY - this.dragStart.y;
      this.dragStart = { x: midClientX, y: midClientY };

      const rect = this.svg.getBoundingClientRect();
      this.viewBox.x -= (dxPx / rect.width) * this.viewBox.w;
      this.viewBox.y -= (dyPx / rect.height) * this.viewBox.h;

      // Zoom with pinch
      if (this.pinchFocus) {
        this.zoomAt(this.pinchFocus.x, this.pinchFocus.y, ratio > 1 ? 1.04 : 0.96);
      }
    }
  }

  _onTouchEnd(e) {
    if (e.touches.length < 2) {
      this.initialPinchDist = null;
    }
  }

  render() {
    this._renderChassis();
    this._renderConnections();
    this._renderCards();
  }

  _renderChassis() {
    const ch = state.chassis;
    if (!ch) return;

    if (this.plateName) this.plateName.textContent = ch.name || "Chassis";
    if (this.plateTemplate) this.plateTemplate.textContent = `Template: ${ch.template || "Square"}`;
    if (this.plateWeight) this.plateWeight.textContent = ch.weight || 0;
    if (this.plateCost) this.plateCost.textContent = `$${ch.cost || 0}`;
    if (this.plateFlip) this.plateFlip.textContent = ch.flip_strength || 0;

    const picUrl = ch.picture_url || (ch.picture ? `/${ch.picture}` : "");
    if (this.plateImage) {
      if (picUrl) {
        this.plateImage.setAttribute("href", picUrl);
        this.plateImage.style.display = "";
      } else {
        this.plateImage.style.display = "none";
      }
    }

    // Update chassis polygon
    if (this.chassisPoly && ch.geometry && ch.geometry.points) {
      const pts = ch.geometry.points.map(p => `${p[0]},${p[1]}`).join(" ");
      this.chassisPoly.setAttribute("points", pts);
    }
  }

  _renderConnections() {
    this.layerConnections.innerHTML = "";
    const conns = state.getConnections();

    // Draw subtle lines connecting the centers of touching cards
    const visited = new Set();
    for (const cardA of state.placedCards) {
      const neighbors = conns.get(cardA.id) || [];
      const boxA = state.getCardBox(cardA);
      const cAx = boxA.xMin + boxA.width / 2;
      const cAy = boxA.yMin + boxA.height / 2;

      for (const idB of neighbors) {
        const pairKey = [cardA.id, idB].sort().join("-");
        if (visited.has(pairKey)) continue;
        visited.add(pairKey);

        const cardB = state.placedCards.find(c => c.id === idB);
        if (!cardB) continue;
        const boxB = state.getCardBox(cardB);
        const cBx = boxB.xMin + boxB.width / 2;
        const cBy = boxB.yMin + boxB.height / 2;

        const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
        line.setAttribute("x1", cAx);
        line.setAttribute("y1", cAy);
        line.setAttribute("x2", cBx);
        line.setAttribute("y2", cBy);
        line.setAttribute("stroke", "#10b981");
        line.setAttribute("stroke-width", "1.2");
        line.setAttribute("stroke-dasharray", "2,2");
        line.setAttribute("opacity", "0.85");
        this.layerConnections.appendChild(line);
      }
    }
  }

  _renderCards() {
    this.layerCards.innerHTML = "";
    const conns = state.getConnections();

    for (const card of state.placedCards) {
      const isSelected = card.id === state.selectedCardId;
      const isTouching = (conns.get(card.id) || []).length > 0;

      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("class", `card-node ${isSelected ? "selected" : ""} ${isTouching ? "touching" : ""}`);
      g.setAttribute("data-card-id", card.id);

      const rot = card.rotation % 360;
      const isRot = rot === 90 || rot === 270;
      const w = isRot ? CARD_HEIGHT_MM : CARD_WIDTH_MM;
      const h = isRot ? CARD_WIDTH_MM : CARD_HEIGHT_MM;

      // Group transformation: translate to card position
      g.setAttribute("transform", `translate(${card.x}, ${card.y})`);

      // Inner group for rotation around card center
      const gInner = document.createElementNS("http://www.w3.org/2000/svg", "g");
      gInner.setAttribute("transform", `rotate(${rot}, ${w / 2}, ${h / 2})`);

      // Card Background / Card Image
      const imgUrl = card.cardData.image_url;
      if (imgUrl) {
        const img = document.createElementNS("http://www.w3.org/2000/svg", "image");
        // Place image matching unrotated standard card dimensions at center
        const imgX = (w - CARD_WIDTH_MM) / 2;
        const imgY = (h - CARD_HEIGHT_MM) / 2;
        img.setAttribute("href", imgUrl);
        img.setAttribute("x", imgX);
        img.setAttribute("y", imgY);
        img.setAttribute("width", CARD_WIDTH_MM);
        img.setAttribute("height", CARD_HEIGHT_MM);
        img.setAttribute("preserveAspectRatio", "none");
        img.setAttribute("filter", "url(#card-shadow)");
        gInner.appendChild(img);
      } else {
        // Fallback vector card block
        const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        rect.setAttribute("x", 0);
        rect.setAttribute("y", 0);
        rect.setAttribute("width", w);
        rect.setAttribute("height", h);
        rect.setAttribute("rx", 3);
        rect.setAttribute("fill", "#1e293b");
        rect.setAttribute("stroke", "#475569");
        rect.setAttribute("stroke-width", 1);
        rect.setAttribute("filter", "url(#card-shadow)");
        gInner.appendChild(rect);

        const txt = document.createElementNS("http://www.w3.org/2000/svg", "text");
        txt.setAttribute("x", w / 2);
        txt.setAttribute("y", h / 2);
        txt.setAttribute("fill", "#ffffff");
        txt.setAttribute("font-size", 6);
        txt.setAttribute("text-anchor", "middle");
        txt.textContent = card.cardData.name;
        gInner.appendChild(txt);
      }

      // Touching connection highlight box
      if (isTouching) {
        const touchBox = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        touchBox.setAttribute("class", "card-touch-box");
        touchBox.setAttribute("x", 0);
        touchBox.setAttribute("y", 0);
        touchBox.setAttribute("width", w);
        touchBox.setAttribute("height", h);
        touchBox.setAttribute("rx", 2);
        g.appendChild(touchBox);
      }

      // Selection bounding box
      if (isSelected) {
        const selBox = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        selBox.setAttribute("class", "card-selection-box");
        selBox.setAttribute("x", -1.5);
        selBox.setAttribute("y", -1.5);
        selBox.setAttribute("width", w + 3);
        selBox.setAttribute("height", h + 3);
        selBox.setAttribute("rx", 3);
        g.appendChild(selBox);
      }

      g.appendChild(gInner);
      this.layerCards.appendChild(g);
    }
  }
}
