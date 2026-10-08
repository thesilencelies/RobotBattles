/**
 * Robot State & Component Health Visualizer (for Player & Automaton tabs)
 */

export class RobotViewRenderer {
  static renderRobotState(container, robot, isAutomaton = false, lastRoll = null, lastAction = null) {
    if (!container || !robot) return;

    const comps = Object.values(robot.components || {});
    const totalMaxDur = comps.reduce((acc, c) => acc + (c.max_durability || 0), 0);
    const totalCurDur = comps.reduce((acc, c) => acc + (c.current_durability || 0), 0);
    const durPct = totalMaxDur > 0 ? Math.round((totalCurDur / totalMaxDur) * 100) : 0;

    const roleColor = isAutomaton ? "#f43f5e" : "#00e5ff";
    const statusBadges = [];
    if (robot.is_inverted) {
      statusBadges.push(`<span class="badge badge-warning">🔄 INVERTED</span>`);
    } else {
      statusBadges.push(`<span class="badge badge-success">⬆️ UPRIGHT</span>`);
    }
    if (robot.is_raised) {
      statusBadges.push(`<span class="badge badge-purple">🔱 RAISED</span>`);
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

    container.innerHTML = `
      <div class="robot-state-card">
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

        <!-- High-level Metric Badges -->
        <div class="state-metrics-grid">
          <div class="state-metric-box">
            <span class="metric-label">Left Drive</span>
            <span class="metric-val ${robot.left_drive_max === 0 ? 'text-red' : 'text-green'}">
              ${robot.left_drive_max} M
            </span>
          </div>
          <div class="state-metric-box">
            <span class="metric-label">Right Drive</span>
            <span class="metric-val ${robot.right_drive_max === 0 ? 'text-red' : 'text-green'}">
              ${robot.right_drive_max} M
            </span>
          </div>
          <div class="state-metric-box">
            <span class="metric-label">Total Durability</span>
            <span class="metric-val">${totalCurDur} / ${totalMaxDur}</span>
            <div class="durability-bar-track">
              <div class="durability-bar-fill" style="width: ${durPct}%; background-color: ${durPct > 50 ? '#10b981' : durPct > 20 ? '#f59e0b' : '#ef4444'}"></div>
            </div>
          </div>
        </div>

        ${actionTableHtml}

        <!-- Components Grid -->
        <h3 class="section-heading">📦 Components on Chassis (${comps.length})</h3>
        <div class="components-health-grid">
          ${comps.map(c => this._renderComponentCard(c)).join("")}
        </div>
      </div>
    `;
  }

  static _renderComponentCard(comp) {
    const isDestroyed = comp.is_destroyed;
    const isDamaged = comp.is_damaged && !isDestroyed;
    const isInactive = !comp.is_active && !isDestroyed;

    let cardCls = "comp-health-card";
    if (isDestroyed) cardCls += " destroyed";
    else if (isDamaged) cardCls += " damaged";
    else if (isInactive) cardCls += " inactive";

    const durPct = comp.max_durability > 0
      ? Math.round((comp.current_durability / comp.max_durability) * 100)
      : 0;

    let statusTag = `<span class="badge badge-success">OK</span>`;
    if (isDestroyed) {
      statusTag = `<span class="badge badge-danger">DESTROYED</span>`;
    } else if (isDamaged) {
      statusTag = `<span class="badge badge-warning">DAMAGED</span>`;
    } else if (isInactive) {
      statusTag = `<span class="badge badge-gray">NO POWER</span>`;
    }

    const typeIcon = comp.card_type === "weapon" ? "⚔️" : "⚙️";

    return `
      <div class="${cardCls}">
        <div class="comp-head">
          <span class="comp-name">${typeIcon} ${comp.name}</span>
          ${statusTag}
        </div>
        <div class="comp-stats-row">
          <span>Durability: <strong>${comp.current_durability} / ${comp.max_durability}</strong></span>
          <span>Absorption: <strong>${comp.absorption}</strong></span>
        </div>
        <div class="durability-bar-track">
          <div class="durability-bar-fill" style="width: ${durPct}%; background-color: ${durPct > 50 ? '#10b981' : durPct > 20 ? '#f59e0b' : '#ef4444'}"></div>
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

  static _renderAutomataTable(robot, lastRoll, lastAction) {
    const isSpinner = robot.name.includes("Spinner");
    const spinCount = Object.values(robot.weapon_spin_counters || {}).reduce((a, b) => a + b, 0);

    let rows = [];
    let tableNote = "";

    if (isSpinner) {
      if (spinCount >= 2) {
        tableNote = `Active Table: <strong>Charged</strong> (Spin counters >= 2: Currently ${spinCount})`;
        rows = [
          { roll: "1", action: "Retreat", desc: "Face opponent and move back 1 step" },
          { roll: "2", action: "Face", desc: "Rotate on spot to face opponent" },
          { roll: "3–6", action: "Rush", desc: "Drive at opponent at full speed" },
        ];
      } else {
        tableNote = `Active Table: <strong>Uncharged</strong> (Spin counters < 2: Currently ${spinCount})`;
        rows = [
          { roll: "1–3", action: "Retreat", desc: "Face opponent and move back 1 step" },
          { roll: "4–5", action: "Face", desc: "Rotate on spot to face opponent" },
          { roll: "6", action: "Rush", desc: "Drive at opponent at full speed" },
        ];
      }
    } else {
      tableNote = "Always uses Vyper Flipper action table";
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
