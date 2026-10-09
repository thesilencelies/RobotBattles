/**
 * Central state store for Robot Builder
 */

export const CARD_WIDTH_MM = 44.0;
export const CARD_HEIGHT_MM = 64.0;
export const A3_WIDTH_MM = 420.0;
export const A3_HEIGHT_MM = 297.0;

class RobotState {
  constructor() {
    this.robotName = "Combat_Bot";
    this.chassis = null;
    this.placedCards = [];  // Array of { id, cardData, x, y, rotation }
    this.spareCards = [];   // Array of { id, cardData }
    this.selectedCardId = null;

    this.snapEnabled = true;
    this.snapStepMm = 10.0;

    this.cardCatalog = [];
    this.chassisList = [];

    this._idCounter = 1;
    this._listeners = new Set();
  }

  subscribe(listener) {
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  notify() {
    for (const fn of this._listeners) {
      try {
        fn(this);
      } catch (err) {
        console.error("State listener error:", err);
      }
    }
  }

  generateId() {
    return `c_${Date.now()}_${this._idCounter++}`;
  }

  setChassis(chassis) {
    this.chassis = chassis;
    this.notify();
  }

  setRobotName(name) {
    this.robotName = (name || "Combat_Bot").trim();
    this.notify();
  }

  setSnapEnabled(val) {
    this.snapEnabled = Boolean(val);
    this.notify();
  }

  snapCoord(val) {
    if (!this.snapEnabled) return val;
    return Math.round(val / this.snapStepMm) * this.snapStepMm;
  }

  addCardToChassis(cardData, x = 180.0, y = 110.0, rotation = 0) {
    // If adding a chassis card from catalogue, set it as the active chassis instead
    if (cardData.type === "chassis") {
      this.setChassis(cardData);
      return null;
    }

    const card = {
      id: this.generateId(),
      cardData,
      x: this.snapCoord(x),
      y: this.snapCoord(y),
      rotation: rotation % 360,
    };
    this.placedCards.push(card);
    this.selectedCardId = card.id;
    this.notify();
    return card;
  }

  addCardToSpares(cardData) {
    if (cardData.type === "chassis") return null;
    const spare = {
      id: this.generateId(),
      cardData,
    };
    this.spareCards.push(spare);
    this.notify();
    return spare;
  }

  moveCardToSpares(cardId) {
    const idx = this.placedCards.findIndex(c => c.id === cardId);
    if (idx === -1) return;
    const [removed] = this.placedCards.splice(idx, 1);
    this.spareCards.push({
      id: removed.id,
      cardData: removed.cardData,
    });
    if (this.selectedCardId === cardId) {
      this.selectedCardId = null;
    }
    this.notify();
  }

  moveSpareToChassis(spareId, x = 160.0, y = 100.0) {
    const idx = this.spareCards.findIndex(s => s.id === spareId);
    if (idx === -1) return;
    const [spare] = this.spareCards.splice(idx, 1);
    const card = {
      id: spare.id,
      cardData: spare.cardData,
      x: this.snapCoord(x),
      y: this.snapCoord(y),
      rotation: 0,
    };
    this.placedCards.push(card);
    this.selectedCardId = card.id;
    this.notify();
  }

  setPlacedCardPosition(cardId, x, y, snap = null) {
    const card = this.placedCards.find(c => c.id === cardId);
    if (!card) return;
    const doSnap = snap !== null ? snap : this.snapEnabled;
    card.x = doSnap ? this.snapCoord(x) : x;
    card.y = doSnap ? this.snapCoord(y) : y;
    this.notify();
  }

  rotatePlacedCard(cardId, deltaAngle = 90) {
    const card = this.placedCards.find(c => c.id === cardId);
    if (!card) return;
    card.rotation = (card.rotation + deltaAngle + 360) % 360;
    this.notify();
  }

  duplicatePlacedCard(cardId) {
    const card = this.placedCards.find(c => c.id === cardId);
    if (!card) return;
    const clone = {
      id: this.generateId(),
      cardData: card.cardData,
      x: this.snapCoord(card.x + 10),
      y: this.snapCoord(card.y + 10),
      rotation: card.rotation,
    };
    this.placedCards.push(clone);
    this.selectedCardId = clone.id;
    this.notify();
  }

  removePlacedCard(cardId) {
    const idx = this.placedCards.findIndex(c => c.id === cardId);
    if (idx === -1) return;
    this.placedCards.splice(idx, 1);
    if (this.selectedCardId === cardId) {
      this.selectedCardId = null;
    }
    this.notify();
  }

  removeSpareCard(spareId) {
    const idx = this.spareCards.findIndex(s => s.id === spareId);
    if (idx === -1) return;
    this.spareCards.splice(idx, 1);
    this.notify();
  }

  selectCard(cardId) {
    this.selectedCardId = cardId;
    this.notify();
  }

  getCardBox(card) {
    const rot = card.rotation % 360;
    const isRot = rot === 90 || rot === 270;
    const w = isRot ? CARD_HEIGHT_MM : CARD_WIDTH_MM;
    const h = isRot ? CARD_WIDTH_MM : CARD_HEIGHT_MM;
    return {
      xMin: card.x,
      yMin: card.y,
      xMax: card.x + w,
      yMax: card.y + h,
      width: w,
      height: h,
    };
  }

  getConnections() {
    // Calculates adjacency between cards (touching within 3mm)
    const tolerance = 3.0;
    const boxes = new Map();
    for (const card of this.placedCards) {
      boxes.set(card.id, this.getCardBox(card));
    }

    const conns = new Map();
    for (const card of this.placedCards) {
      conns.set(card.id, []);
    }

    const ids = Array.from(boxes.keys());
    for (let i = 0; i < ids.length; i++) {
      const idA = ids[i];
      const boxA = boxes.get(idA);
      for (let j = i + 1; j < ids.length; j++) {
        const idB = ids[j];
        const boxB = boxes.get(idB);

        const touching = !(
          boxA.xMax < boxB.xMin - tolerance ||
          boxA.xMin > boxB.xMax + tolerance ||
          boxA.yMax < boxB.yMin - tolerance ||
          boxA.yMin > boxB.yMax + tolerance
        );

        if (touching) {
          conns.get(idA).push(idB);
          conns.get(idB).push(idA);
        }
      }
    }
    return conns;
  }

  getComputedStats() {
    const chassisWt = this.chassis ? Number(this.chassis.weight || 0) : 0;
    const chassisCost = this.chassis ? Number(this.chassis.cost || 0) : 0;
    const flipStr = this.chassis ? Number(this.chassis.flip_strength || 0) : 0;

    let cardsWt = 0;
    let cardsCost = 0;
    for (const card of this.placedCards) {
      cardsWt += Number(card.cardData.weight || 0);
      cardsCost += Number(card.cardData.cost || 0);
    }

    let sparesCost = 0;
    for (const spare of this.spareCards) {
      sparesCost += Number(spare.cardData.cost || 0);
    }

    return {
      activeWeight: chassisWt + cardsWt,
      activeCost: chassisCost + cardsCost,
      chassisWeight: chassisWt,
      chassisCost: chassisCost,
      cardsWeight: cardsWt,
      cardsCost: cardsCost,
      flipStrength: flipStr,
      sparesCount: this.spareCards.length,
      sparesCost: sparesCost,
      totalPoolCost: chassisCost + cardsCost + sparesCost,
    };
  }

  loadRobot(parsedData) {
    if (parsedData.chassis) {
      const cName = parsedData.chassis.name;
      const matched = (this.chassisList || []).find(
        c => c.name.toLowerCase() === cName.toLowerCase() ||
             (cName.length > 3 && c.name.toLowerCase().includes(cName.toLowerCase()))
      );
      this.chassis = matched || parsedData.chassis;
    } else {
      // Fallback: check if any placed card was actually the chassis
      const placed = parsedData.placed_cards || [];
      const chassisCardIdx = placed.findIndex(c => {
        const name = (c.card || (c.cardData && c.cardData.name) || "").toLowerCase();
        return (this.chassisList || []).some(ch => ch.name.toLowerCase() === name);
      });
      if (chassisCardIdx !== -1) {
        const chCard = placed[chassisCardIdx];
        const name = (chCard.card || (chCard.cardData && chCard.cardData.name) || "").toLowerCase();
        const matched = (this.chassisList || []).find(ch => ch.name.toLowerCase() === name);
        if (matched) this.chassis = matched;
        placed.splice(chassisCardIdx, 1);
      }
    }
    this.placedCards = (parsedData.placed_cards || []).map(c => {
      const parsedX = Number(c.x);
      const parsedY = Number(c.y);
      const parsedRot = Number(c.rotation);
      return {
        id: c.id || this.generateId(),
        cardData: c.card_data || c.cardData || { name: c.card, weight: 0, cost: 0 },
        x: Number.isFinite(parsedX) ? parsedX : 100.0,
        y: Number.isFinite(parsedY) ? parsedY : 100.0,
        rotation: Number.isFinite(parsedRot) ? parsedRot : 0,
      };
    });
    this.spareCards = (parsedData.spare_cards || []).map(s => ({
      id: s.id || this.generateId(),
      cardData: s.card_data || s.cardData || { name: s.card, weight: 0, cost: 0 },
    }));
    this.selectedCardId = null;
    this.notify();
  }
}

export const state = new RobotState();
