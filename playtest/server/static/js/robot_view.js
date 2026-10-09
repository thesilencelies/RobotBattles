/**
 * Robot State & Component Health Visualizer (for Player & Automaton tabs)
 * Features visual SVG Chassis Layout & Supply Tree with zoom/pan and inspection.
 */

const CHASSIS_TEMPLATES = {
  Square: [
    [100.0, 24.0],
    [320.0, 24.0],
    [320.0, 280.0],
    [100.0, 280.0],
  ],
  Triangle: [
    [210.0, 24.0],
    [380.0, 135.0],
    [380.0, 280.0],
    [40.0, 280.0],
    [40.0, 135.0],
  ],
  Wide: [
    [12.0, 65.0],
    [408.0, 65.0],
    [408.0, 235.0],
    [12.0, 235.0],
  ],
};

export class RobotViewRenderer {
  // Cache of zoom/pan state per container (player vs automaton)
  static viewStates = new Map();

  static renderRobotState(container, robot, isAutomaton = false, lastRoll = null, lastAction = null) {
    if (!container || !robot) return;

    const comps = Object.values(robot.components || {});
    const containerId = container.id || (isAutomaton ? "auto-view" : "player-view");

    if (!this.viewStates.has(containerId)) {
      this.viewStates.set(containerId, {
        zoom: 1.0,
        pan: { x: 0, y: 0 },
        selectedCardId: comps.length > 0 ? comps[0].id : null,
      });
    }
    const state = this.viewStates.get(containerId);

    // If previously selected card no longer exists, select first
    if (!comps.some(c => c.id === state.selectedCardId) && comps.length > 0) {
      state.selectedCardId = comps[0].id;
    }

    const roleColor = isAutomaton ? "#f43f5e" : "#00e5ff";
    const statusBadges = [];
    if (robot.is_inverted) {
      statusBadges.push(`<span class="badge badge-warning">🔄 INVERTED</span>`);
    } else {
      statusBadges.push(`<span class="badge badge-success">⬆️ UPRIGHT</span>`);
    }
    if (robot.is_raised) {
      statusBadges.push(`<span class="badge badge-purple">🔱 RAISED (Half Drive)</span>`);
    }
    if (robot.is_eliminated) {
      statusBadges.push(`<span class="badge badge-danger">☠️ ELIMINATED</span>`);
    }

    // Spin counters summary
    const spinCounters = Object.entries(robot.weapon_spin_counters || {})
      .map(([cid, count]) => {
        const comp = robot.components[cid];
        const name = comp ? comp.name : "Weapon";
        return `<span class="badge badge-cyan">🌀 ${name}: ${count} Spin</span>`;
      })
      .join(" ");

    let actionTableHtml = "";
    if (isAutomaton) {
      actionTableHtml = this._renderAutomataTable(robot, lastRoll, lastAction);
    }

    const driveStatus = robot.is_raised
      ? "Raised (Outputs Halved)"
      : (robot.left_drive_max > 0 || robot.right_drive_max > 0 ? "Operational" : "Disabled");

    container.innerHTML = `
      <div class="robot-state-card robot-view-card" data-container-id="${containerId}">
        <!-- Header -->
        <div class="state-header-row">
          <div>
            <h2 class="robot-title" style="color: ${roleColor}">${robot.name}</h2>
            <div class="chassis-subtitle">
              Chassis: <strong>${robot.chassis_name}</strong> (${robot.chassis_template})
              • Flip Strength: <strong>${robot.flip_strength}</strong>
            </div>
          </div>
          <div class="status-badge-group">
            ${statusBadges.join(" ")}
            ${spinCounters}
          </div>
        </div>

        <!-- High-level Metric Badges (Motive Drive with Distinct Logo - No fake 7/7 durability) -->
        <div class="state-metrics-grid">
          <!-- Motive Drive System Card -->
          <div class="state-metric-box motive-drive-card">
            <div class="motive-drive-header">
              <svg class="motive-drive-logo-icon" viewBox="0 0 36 36" width="32" height="32">
                <circle cx="18" cy="18" r="16" fill="#1e293b" stroke="#38bdf8" stroke-width="2.2"/>
                <circle cx="18" cy="18" r="10" fill="#0f172a" stroke="#00e5ff" stroke-width="1.6"/>
                <circle cx="18" cy="18" r="4" fill="#38bdf8"/>
                <line x1="18" y1="2" x2="18" y2="7" stroke="#38bdf8" stroke-width="2.2" stroke-linecap="round"/>
                <line x1="18" y1="29" x2="18" y2="34" stroke="#38bdf8" stroke-width="2.2" stroke-linecap="round"/>
                <line x1="2" y1="18" x2="7" y2="18" stroke="#38bdf8" stroke-width="2.2" stroke-linecap="round"/>
                <line x1="29" y1="18" x2="34" y2="18" stroke="#38bdf8" stroke-width="2.2" stroke-linecap="round"/>
                <line x1="6.7" y1="6.7" x2="10.2" y2="10.2" stroke="#38bdf8" stroke-width="2.2" stroke-linecap="round"/>
                <line x1="25.8" y1="25.8" x2="29.3" y2="29.3" stroke="#38bdf8" stroke-width="2.2" stroke-linecap="round"/>
                <line x1="6.7" y1="29.3" x2="10.2" y2="25.8" stroke="#38bdf8" stroke-width="2.2" stroke-linecap="round"/>
                <line x1="25.8" y1="10.2" x2="29.3" y2="6.7" stroke="#38bdf8" stroke-width="2.2" stroke-linecap="round"/>
              </svg>
              <div class="motive-drive-meta">
                <span class="motive-drive-title">MOTIVE DRIVE</span>
                <span class="motive-drive-sub">${driveStatus}</span>
              </div>
            </div>
            <div class="motive-channels-row">
              <div class="motive-channel ${robot.left_drive_max === 0 ? 'disabled' : 'active'}">
                <span class="chan-label">LEFT</span>
                <span class="chan-val">${robot.left_drive_max} M</span>
              </div>
              <div class="motive-channel ${robot.right_drive_max === 0 ? 'disabled' : 'active'}">
                <span class="chan-label">RIGHT</span>
                <span class="chan-val">${robot.right_drive_max} M</span>
              </div>
            </div>
          </div>

          <!-- Flip Strength -->
          <div class="state-metric-box flip-metric-box">
            <span class="metric-label">Flip Strength</span>
            <span class="metric-val text-amber">⚔️ ${robot.flip_strength}</span>
            <span class="metric-sub">Overcomes opponent flip strength</span>
          </div>

          <!-- Component Status Count -->
          <div class="state-metric-box counts-metric-box">
            <span class="metric-label">Component Integrity</span>
            <div class="integrity-counts-row">
              <span class="badge badge-success">${comps.filter(c => c.is_active && !c.is_damaged && !c.is_destroyed).length} OK</span>
              <span class="badge badge-warning">${comps.filter(c => c.is_damaged && !c.is_destroyed).length} Damaged</span>
              <span class="badge badge-danger">${comps.filter(c => c.is_destroyed).length} Destroyed</span>
              <span class="badge badge-gray">${comps.filter(c => !c.is_active && !c.is_destroyed).length} Inactive</span>
            </div>
          </div>
        </div>

        <!-- Robot Layout & Supply Tree View Section -->
        <div class="robot-layout-section">
          <div class="layout-controls-bar">
            <div class="layout-title-block">
              <h3 class="section-title">🗺️ Chassis Card Layout & Power Supply Tree</h3>
              <span class="layout-hint">Visualizing physical card positions on mat & supply connections</span>
            </div>
            <div class="layout-legend">
              <span class="legend-chip ok"><span class="legend-dot"></span> OK</span>
              <span class="legend-chip damaged"><span class="legend-dot"></span> Damaged</span>
              <span class="legend-chip destroyed"><span class="legend-dot"></span> Destroyed</span>
              <span class="legend-chip inactive"><span class="legend-dot"></span> Inactive</span>
            </div>
            <div class="layout-zoom-tools">
              <button class="btn-zoom-layout" data-zoom="in" title="Zoom In">＋</button>
              <button class="btn-zoom-layout" data-zoom="out" title="Zoom Out">－</button>
              <button class="btn-zoom-layout" data-zoom="fit" title="Reset View">⛶</button>
            </div>
          </div>

          <!-- SVG Layout Stage -->
          <div class="robot-layout-viewport" id="viewport-${containerId}">
            <svg class="robot-layout-svg" id="svg-${containerId}" viewBox="0 0 420 297" preserveAspectRatio="xMidYMid meet">
              <defs>
                <pattern id="layout-grid-10-${containerId}" width="10" height="10" patternUnits="userSpaceOnUse">
                  <path d="M 10 0 L 0 0 0 10" fill="none" stroke="#1e293b" stroke-width="0.3"/>
                </pattern>
                <marker id="arrow-supply-active-${containerId}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#38bdf8"/>
                </marker>
                <marker id="arrow-supply-inactive-${containerId}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#64748b"/>
                </marker>
              </defs>

              <!-- Mat Background -->
              <rect x="0" y="0" width="420" height="297" fill="#070c14" />
              <rect x="0" y="0" width="420" height="297" fill="url(#layout-grid-10-${containerId})" />

              <!-- Chassis Outline Polygon -->
              ${this._renderChassisOutline(robot.chassis_template)}

              <!-- Center Centerlines -->
              <line x1="210" y1="0" x2="210" y2="297" stroke="#334155" stroke-width="0.5" stroke-dasharray="4,4" opacity="0.3"/>
              <line x1="0" y1="150" x2="420" y2="150" stroke="#334155" stroke-width="0.5" stroke-dasharray="4,4" opacity="0.3"/>

              <!-- Supply Graph Arrows Layer -->
              <g class="layer-supply-lines">
                ${this._renderSupplyArrows(robot, containerId)}
              </g>

              <!-- Placed Cards Layer -->
              <g class="layer-placed-cards">
                ${comps.map(c => this._renderCardNode(c, robot, state.selectedCardId === c.id)).join("")}
              </g>
            </svg>
          </div>

          <!-- Card Inspector Panel for Selected Component -->
          <div class="inspected-card-panel" id="inspector-${containerId}">
            ${this._renderInspector(robot.components[state.selectedCardId] || comps[0], robot)}
          </div>
        </div>

        ${actionTableHtml}

        <!-- All Components Health List -->
        <h3 class="section-heading">📦 Components Breakdown (${comps.length})</h3>
        <div class="components-health-grid">
          ${comps.map(c => this._renderComponentCard(c, state.selectedCardId === c.id)).join("")}
        </div>
      </div>
    `;

    // Attach interactivity
    this._attachInteractivity(container, robot, containerId);
  }

  static _renderChassisOutline(templateName) {
    const pts = CHASSIS_TEMPLATES[templateName] || CHASSIS_TEMPLATES.Triangle;
    const ptsStr = pts.map(p => `${p[0]},${p[1]}`).join(" ");
    return `
      <polygon points="${ptsStr}" fill="rgba(30, 41, 59, 0.25)" stroke="#475569" stroke-width="1.8" stroke-dasharray="6,4" />
      <text x="210" y="40" fill="rgba(148, 163, 184, 0.4)" font-size="10" font-family="sans-serif" font-weight="bold" text-anchor="middle">
        CHASSIS TEMPLATE (${(templateName || "TRIANGLE").toUpperCase()})
      </text>
    `;
  }

  static _renderSupplyArrows(robot, containerId) {
    const lines = [];
    const comps = robot.components || {};

    for (const [consumerId, supplierIds] of Object.entries(robot.supply_graph || {})) {
      const consumer = comps[consumerId];
      if (!consumer) continue;

      const cW = (consumer.rotation === 90 || consumer.rotation === 270) ? 64.0 : 44.0;
      const cH = (consumer.rotation === 90 || consumer.rotation === 270) ? 44.0 : 64.0;
      const rawCx = Number(consumer.x);
      const rawCy = Number(consumer.y);
      const cx = (Number.isFinite(rawCx) ? rawCx : 100.0) + cW / 2;
      const cy = (Number.isFinite(rawCy) ? rawCy : 100.0) + cH / 2;

      for (const supplierId of supplierIds) {
        const supplier = comps[supplierId];
        if (!supplier) continue;

        const sW = (supplier.rotation === 90 || supplier.rotation === 270) ? 64.0 : 44.0;
        const sH = (supplier.rotation === 90 || supplier.rotation === 270) ? 44.0 : 64.0;
        const rawSx = Number(supplier.x);
        const rawSy = Number(supplier.y);
        const sx = (Number.isFinite(rawSx) ? rawSx : 100.0) + sW / 2;
        const sy = (Number.isFinite(rawSy) ? rawSy : 100.0) + sH / 2;

        const isActive = supplier.is_active && !supplier.is_destroyed;
        const strokeColor = isActive ? "#38bdf8" : "#64748b";
        const marker = isActive ? `url(#arrow-supply-active-${containerId})` : `url(#arrow-supply-inactive-${containerId})`;

        lines.push(`
          <line x1="${sx}" y1="${sy}" x2="${cx}" y2="${cy}"
                stroke="${strokeColor}" stroke-width="1.8" stroke-dasharray="${isActive ? '4,3' : '2,2'}"
                opacity="${isActive ? '0.85' : '0.45'}"
                marker-end="${marker}" />
        `);
      }
    }
    return lines.join("");
  }

  static _renderCardNode(comp, robot, isSelected) {
    const isDestroyed = comp.is_destroyed;
    const isDamaged = comp.is_damaged && !isDestroyed;
    const isInactive = !comp.is_active && !isDestroyed;

    let statusColor = "#10b981"; // OK
    let fillColor = "rgba(16, 185, 129, 0.16)";
    let statusText = "OK";

    if (isDestroyed) {
      statusColor = "#ef4444";
      fillColor = "rgba(239, 68, 68, 0.22)";
      statusText = "DESTROYED";
    } else if (isDamaged) {
      statusColor = "#f59e0b";
      fillColor = "rgba(245, 158, 11, 0.20)";
      statusText = "DAMAGED";
    } else if (isInactive) {
      statusColor = "#64748b";
      fillColor = "rgba(100, 116, 139, 0.14)";
      statusText = "INACTIVE";
    }

    const rot = comp.rotation || 0;
    const w = (rot === 90 || rot === 270) ? 64.0 : 44.0;
    const h = (rot === 90 || rot === 270) ? 44.0 : 64.0;
    const rawX = Number(comp.x);
    const rawY = Number(comp.y);
    const x = Number.isFinite(rawX) ? rawX : 100.0;
    const y = Number.isFinite(rawY) ? rawY : 100.0;

    const isDrive = comp.outputs && (comp.outputs.includes("D") || comp.outputs.includes("M"));
    const isWeapon = comp.card_type === "weapon" || (comp.outputs && comp.outputs.includes("W"));
    const isPower = !comp.requirements && comp.outputs && (comp.outputs.includes("E") || comp.outputs.includes("S"));

    const icon = isDrive ? "🛞" : isWeapon ? "⚔️" : isPower ? "🔋" : comp.card_type === "chassis" ? "🛡️" : "⚙️";

    const selectionHighlight = isSelected
      ? `<rect x="-2" y="-2" width="${w + 4}" height="${h + 4}" rx="5" fill="none" stroke="#00e5ff" stroke-width="2.5" filter="drop-shadow(0 0 5px #00e5ff)"/>`
      : "";

    // Strike-through line if destroyed
    const strikeLine = isDestroyed
      ? `<line x1="2" y1="2" x2="${w - 2}" y2="${h - 2}" stroke="#ef4444" stroke-width="2.2" opacity="0.8"/>
         <line x1="${w - 2}" y1="2" x2="2" y2="${h - 2}" stroke="#ef4444" stroke-width="2.2" opacity="0.8"/>`
      : "";

    // Spin counter badge in card
    let spinBadgeSvg = "";
    if (isWeapon && (comp.spin_counters > 0 || (comp.keywords && comp.keywords.toLowerCase().includes("spin up")))) {
      spinBadgeSvg = `
        <rect x="2" y="${h - 13}" width="${w - 4}" height="10" rx="2" fill="#0284c7" />
        <text x="${w / 2}" y="${h - 5.5}" fill="#ffffff" font-size="6.5" font-weight="bold" text-anchor="middle">
          🌀 ${comp.spin_counters || 0} Spin
        </text>
      `;
    }

    const shortName = comp.name.length > 13 ? comp.name.substring(0, 12) + "…" : comp.name;

    return `
      <g class="layout-card-node ${isSelected ? 'selected' : ''}" data-cid="${comp.id}" transform="translate(${x}, ${y})" style="cursor: pointer;">
        ${selectionHighlight}
        <!-- Card Rect -->
        <rect width="${w}" height="${h}" rx="3.5"
              fill="${fillColor}"
              stroke="${statusColor}"
              stroke-width="${isSelected ? '2.5' : '1.8'}"
              stroke-dasharray="${isInactive ? '3,2' : 'none'}" />
        ${strikeLine}

        <!-- Card Top Icon & Status Pill -->
        <text x="5" y="11" font-size="9">${icon}</text>
        <rect x="${w - 26}" y="3" width="23" height="8" rx="2" fill="${statusColor}" opacity="0.9"/>
        <text x="${w - 14.5}" y="9" fill="#000000" font-size="5" font-weight="900" text-anchor="middle">
          ${statusText === "DESTROYED" ? "DEAD" : statusText === "INACTIVE" ? "NO PWR" : statusText}
        </text>

        <!-- Card Name -->
        <text x="4" y="24" fill="#f8fafc" font-size="6.5" font-weight="bold" font-family="sans-serif">
          ${shortName}
        </text>

        <!-- Specs Text -->
        <text x="4" y="34" fill="#94a3b8" font-size="5.5" font-family="monospace">
          ${comp.requirements ? `In: ${comp.requirements}` : "Root Power"}
        </text>
        <text x="4" y="42" fill="#38bdf8" font-size="5.5" font-family="monospace">
          ${comp.outputs ? `Out: ${comp.outputs}` : ""}
        </text>

        ${spinBadgeSvg}
      </g>
    `;
  }

  static _renderInspector(comp, robot) {
    if (!comp) {
      return `<div class="inspector-empty">Tap any card in the layout above to view its details.</div>`;
    }

    const isDestroyed = comp.is_destroyed;
    const isDamaged = comp.is_damaged && !isDestroyed;
    const isInactive = !comp.is_active && !isDestroyed;

    let statusBadge = `<span class="badge badge-success">🟢 OK (Operational)</span>`;
    if (isDestroyed) {
      statusBadge = `<span class="badge badge-danger">🔴 DESTROYED</span>`;
    } else if (isDamaged) {
      statusBadge = `<span class="badge badge-warning">🟡 DAMAGED</span>`;
    } else if (isInactive) {
      statusBadge = `<span class="badge badge-gray">⚪ INACTIVE (No Power)</span>`;
    }

    const isDrive = comp.outputs && (comp.outputs.includes("D") || comp.outputs.includes("M"));
    const isWeapon = comp.card_type === "weapon" || (comp.outputs && comp.outputs.includes("W"));

    let spinTag = "";
    if (isWeapon) {
      spinTag = `<span class="badge badge-cyan">🌀 Spin Level: ${comp.spin_counters || 0}</span>`;
    }

    const driveTag = isDrive ? `<span class="badge badge-blue">🛞 Motive Drive Component</span>` : "";

    // Upstream Suppliers
    const suppliers = (robot.supply_graph[comp.id] || [])
      .map(sid => {
        const s = robot.components[sid];
        return s ? `${s.name} (${s.is_active ? 'Active' : 'Offline'})` : sid;
      })
      .join(", ") || "None (Self-Powered / Root)";

    // Downstream Consumers
    const consumers = Object.entries(robot.supply_graph || {})
      .filter(([_, sids]) => sids.includes(comp.id))
      .map(([cid, _]) => {
        const c = robot.components[cid];
        return c ? `${c.name}` : cid;
      })
      .join(", ") || "None (Terminal Component)";

    return `
      <div class="inspector-content">
        <div class="inspector-header">
          <div class="inspector-title-group">
            <span class="inspector-type">${comp.card_type.toUpperCase()}</span>
            <h4 class="inspector-name">${comp.name}</h4>
          </div>
          <div class="inspector-badges">
            ${statusBadge}
            ${driveTag}
            ${spinTag}
          </div>
        </div>

        <div class="inspector-stats-strip">
          <div class="stat-cell">
            <span class="cell-label">Durability</span>
            <span class="cell-val">${comp.max_durability}</span>
          </div>
          <div class="stat-cell">
            <span class="cell-label">Absorption</span>
            <span class="cell-val">${comp.absorption}</span>
          </div>
          <div class="stat-cell">
            <span class="cell-label">Requirements</span>
            <span class="cell-val text-cyan">${comp.requirements || "None"}</span>
          </div>
          <div class="stat-cell">
            <span class="cell-label">Outputs</span>
            <span class="cell-val text-green">${comp.outputs || "None"}</span>
          </div>
        </div>

        <div class="inspector-supply-flow">
          <div><strong>Supplied By:</strong> <span>${suppliers}</span></div>
          <div><strong>Supplies To:</strong> <span>${consumers}</span></div>
        </div>

        ${comp.keywords ? `<div class="inspector-keywords"><strong>Keywords:</strong> ${comp.keywords}</div>` : ""}
        ${comp.text ? `<div class="inspector-text">${comp.text}</div>` : ""}
      </div>
    `;
  }

  static _renderComponentCard(comp, isSelected) {
    const isDestroyed = comp.is_destroyed;
    const isDamaged = comp.is_damaged && !isDestroyed;
    const isInactive = !comp.is_active && !isDestroyed;

    let cardCls = "comp-health-card";
    if (isDestroyed) cardCls += " destroyed";
    else if (isDamaged) cardCls += " damaged";
    else if (isInactive) cardCls += " inactive";
    if (isSelected) cardCls += " active-selected";

    let statusTag = `<span class="badge badge-success">OK</span>`;
    if (isDestroyed) {
      statusTag = `<span class="badge badge-danger">DESTROYED</span>`;
    } else if (isDamaged) {
      statusTag = `<span class="badge badge-warning">DAMAGED</span>`;
    } else if (isInactive) {
      statusTag = `<span class="badge badge-gray">NO POWER</span>`;
    }

    let spinTag = "";
    if (comp.card_type === "weapon" && (comp.spin_counters !== undefined || (comp.keywords && comp.keywords.toLowerCase().includes("spin up")))) {
      spinTag = `<span class="badge badge-cyan" style="background:#0284c7;color:#fff;font-weight:bold;">🌀 Spin: ${comp.spin_counters || 0}</span>`;
    }

    const isDrive = comp.outputs && (comp.outputs.includes("D") || comp.outputs.includes("M"));
    const typeIcon = isDrive ? "🛞" : comp.card_type === "weapon" ? "⚔️" : comp.card_type === "chassis" ? "🛡️" : "📦";

    return `
      <div class="${cardCls}" data-cid="${comp.id}" style="cursor: pointer;">
        <div class="comp-head">
          <span class="comp-name">${typeIcon} ${comp.name}</span>
          <div style="display:flex;gap:4px;align-items:center;">
            ${spinTag}
            ${statusTag}
          </div>
        </div>
        <div class="comp-stats-row">
          <span>Durability: <strong>${comp.max_durability}</strong></span>
          <span>Absorption: <strong>${comp.absorption}</strong></span>
          <span>State: <strong>${isDestroyed ? 'Destroyed' : isDamaged ? 'Damaged' : isInactive ? 'Inactive' : 'Undamaged'}</strong></span>
        </div>
        <div class="comp-specs">
          ${comp.requirements ? `<span class="spec-tag req">Req: ${comp.requirements}</span>` : ""}
          ${comp.outputs ? `<span class="spec-tag out">Out: ${comp.outputs}</span>` : ""}
          ${comp.keywords ? `<span class="spec-tag kw">${comp.keywords}</span>` : ""}
        </div>
        ${comp.text ? `<div class="comp-text">${comp.text}</div>` : ""}
      </div>
    `;
  }

  static _attachInteractivity(container, robot, containerId) {
    const state = this.viewStates.get(containerId);
    const svg = container.querySelector(`#svg-${containerId}`);
    const inspector = container.querySelector(`#inspector-${containerId}`);

    if (!svg || !state) return;

    // 1. Select card on SVG click or list click
    const selectCard = (cid) => {
      state.selectedCardId = cid;
      // Re-render inspector
      const comp = robot.components[cid];
      if (inspector && comp) {
        inspector.innerHTML = this._renderInspector(comp, robot);
      }
      // Update highlights in SVG
      svg.querySelectorAll(".layout-card-node").forEach(node => {
        node.classList.toggle("selected", node.dataset.cid === cid);
      });
      // Update highlights in grid
      container.querySelectorAll(".comp-health-card").forEach(card => {
        card.classList.toggle("active-selected", card.dataset.cid === cid);
      });
    };

    svg.querySelectorAll(".layout-card-node").forEach(node => {
      node.addEventListener("click", (e) => {
        e.stopPropagation();
        selectCard(node.dataset.cid);
      });
    });

    container.querySelectorAll(".comp-health-card").forEach(card => {
      card.addEventListener("click", () => {
        selectCard(card.dataset.cid);
      });
    });

    // 2. Zoom & Pan for SVG layout
    const updateViewBox = () => {
      const baseW = 420;
      const baseH = 297;
      const w = baseW / state.zoom;
      const h = baseH / state.zoom;
      const x = (baseW / 2) - (w / 2) + state.pan.x;
      const y = (baseH / 2) - (h / 2) + state.pan.y;
      svg.setAttribute("viewBox", `${x} ${y} ${w} ${h}`);
    };

    updateViewBox();

    container.querySelectorAll(".btn-zoom-layout").forEach(btn => {
      btn.addEventListener("click", () => {
        const action = btn.dataset.zoom;
        if (action === "in") {
          state.zoom = Math.min(3.5, state.zoom * 1.25);
        } else if (action === "out") {
          state.zoom = Math.max(0.6, state.zoom / 1.25);
        } else if (action === "fit") {
          state.zoom = 1.0;
          state.pan = { x: 0, y: 0 };
        }
        updateViewBox();
      });
    });

    // Mouse wheel zoom
    svg.addEventListener("wheel", (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
      state.zoom = Math.max(0.6, Math.min(3.5, state.zoom * zoomFactor));
      updateViewBox();
    }, { passive: false });

    // Drag to pan
    let isDragging = false;
    let startPt = { x: 0, y: 0 };

    svg.addEventListener("pointerdown", (e) => {
      if (e.target.closest(".layout-card-node")) return;
      isDragging = true;
      startPt = { x: e.clientX, y: e.clientY };
      if (svg.setPointerCapture) {
        try { svg.setPointerCapture(e.pointerId); } catch (_) {}
      }
    });

    svg.addEventListener("pointermove", (e) => {
      if (!isDragging) return;
      const dx = (e.clientX - startPt.x) / (state.zoom * 1.2);
      const dy = (e.clientY - startPt.y) / (state.zoom * 1.2);
      startPt = { x: e.clientX, y: e.clientY };
      state.pan.x -= dx;
      state.pan.y -= dy;
      updateViewBox();
    });

    const endDrag = (e) => {
      isDragging = false;
      if (svg.releasePointerCapture) {
        try { svg.releasePointerCapture(e.pointerId); } catch (_) {}
      }
    };
    svg.addEventListener("pointerup", endDrag);
    svg.addEventListener("pointercancel", endDrag);
  }

  static _renderAutomataTable(robot, lastRoll, lastAction) {
    const rawName = (robot.name || "").toLowerCase().replace(/\s+/g, "_");
    const spinCount = Object.values(robot.weapon_spin_counters || {}).reduce((a, b) => a + b, 0);

    // Identify archetype based on allocation in Action_tables.md
    let archetype = "Full Rush";
    if (rawName.includes("beater") || rawName.includes("nightwing")) {
      archetype = "Balanced";
    } else if (rawName.includes("spinner") || rawName.includes("chonk")) {
      archetype = "Spin Up";
    } else if (rawName.includes("flipper")) {
      archetype = "Full Rush";
    }

    let rows = [];
    let tableNote = "";

    if (archetype === "Spin Up") {
      if (spinCount >= 2) {
        tableNote = `Spin Up (Charged: Spin counters >= 2, Currently ${spinCount})`;
        rows = [
          { roll: "1", action: "Retreat", desc: "Face opponent and move back 1 step" },
          { roll: "2", action: "Face", desc: "Rotate on spot to face opponent" },
          { roll: "3–6", action: "Rush", desc: "Drive at opponent at full speed" },
        ];
      } else {
        tableNote = `Spin Up (Uncharged: Spin counters < 2, Currently ${spinCount})`;
        rows = [
          { roll: "1–3", action: "Retreat", desc: "Face opponent and move back 1 step" },
          { roll: "4–5", action: "Face", desc: "Rotate on spot to face opponent" },
          { roll: "6", action: "Rush", desc: "Drive at opponent at full speed" },
        ];
      }
    } else if (archetype === "Balanced") {
      let maxSpin = 3;
      if (robot.components) {
        for (const comp of Object.values(robot.components)) {
          if (comp.card_type === "weapon" && comp.keywords) {
            const m = comp.keywords.match(/Spin up\s*\(\s*(\d+)/i);
            if (m) maxSpin = parseInt(m[1], 10);
          }
        }
      }
      const isFull = spinCount >= maxSpin;
      if (isFull) {
        tableNote = `Balanced (Full Spin: ${spinCount}/${maxSpin})`;
        rows = [
          { roll: "1", action: "Retreat", desc: "Face opponent and move back 1 step" },
          { roll: "2–3", action: "Face", desc: "Rotate on spot to face opponent" },
          { roll: "4–6", action: "Rush", desc: "Drive at opponent at full speed" },
        ];
      } else {
        tableNote = `Balanced (Spinning Up: ${spinCount}/${maxSpin})`;
        rows = [
          { roll: "1–2", action: "Retreat", desc: "Face opponent and move back 1 step" },
          { roll: "3–4", action: "Face", desc: "Rotate on spot to face opponent" },
          { roll: "5–6", action: "Rush", desc: "Drive at opponent at full speed" },
        ];
      }
    } else {
      tableNote = "Full Rush (Always active)";
      rows = [
        { roll: "1", action: "Retreat", desc: "Face opponent and move back 1 step" },
        { roll: "2", action: "Face", desc: "Rotate on spot to face opponent" },
        { roll: "3–6", action: "Rush", desc: "Drive at opponent at full speed" },
      ];
    }

    return `
      <div class="automata-table-box">
        <div class="table-header-row">
          <h4>🤖 Automaton Action Table (${tableNote})</h4>
          ${lastRoll !== null ? `<span class="last-roll-badge">Last Roll: 🎲 ${lastRoll} (${lastAction})</span>` : ""}
        </div>
        <table class="action-table">
          <thead>
            <tr>
              <th>D6 Roll</th>
              <th>Action</th>
              <th>Behavior</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(r => {
              const isMatch = lastAction && r.action.toLowerCase() === lastAction.toLowerCase();
              return `
                <tr class="${isMatch ? 'row-active-roll' : ''}">
                  <td><span class="roll-pill">🎲 ${r.roll}</span></td>
                  <td><strong>${r.action}</strong></td>
                  <td>${r.desc}</td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      </div>
    `;
  }
}
