/**
 * Arena SVG/Canvas Renderer & Miniature Visualizer
 */

const CHASSIS_MINIATURE_SHAPES = {
  Triangle: [
    [0.0, -36.0],
    [35.0, -5.0],
    [35.0, 35.0],
    [-35.0, 35.0],
    [-35.0, -5.0],
  ],
  Square: [
    [-30.0, -35.0],
    [30.0, -35.0],
    [30.0, 35.0],
    [-30.0, 35.0],
  ],
  Wide: [
    [-42.0, -25.0],
    [42.0, -25.0],
    [42.0, 25.0],
    [-42.0, 25.0],
  ],
};

export class ArenaRenderer {
  constructor(svgElement) {
    this.svg = svgElement;
    this.layerArena = this.svg.querySelector("#layer-arena");
    this.layerGhosts = this.svg.querySelector("#layer-ghosts");
    this.layerRobots = this.svg.querySelector("#layer-robots");
    this.layerEffects = this.svg.querySelector("#layer-effects");

    this.animating = false;
    this.animFrame = null;
  }

  render(matchState) {
    if (!matchState) return;

    const pBot = matchState.player_robot;
    const aBot = matchState.automaton_robot;

    // 1. Render Trajectories (Ghosts)
    this._renderTrajectories(matchState.player_trajectory, matchState.automaton_trajectory);

    // 2. Render Miniatures at current poses
    this.layerRobots.innerHTML = "";
    this._renderMiniature(pBot, "player");
    this._renderMiniature(aBot, "automaton");

    // 3. Render Collision Effect if applicable
    this.layerEffects.innerHTML = "";
    if (matchState.last_collision) {
      this._renderCollisionEffect(matchState.last_collision);
    }
  }

  animateTurn(matchState, onComplete) {
    const pTraj = matchState.player_trajectory || [];
    const aTraj = matchState.automaton_trajectory || [];

    if (pTraj.length === 0 || aTraj.length === 0) {
      this.render(matchState);
      if (onComplete) onComplete();
      return;
    }

    if (this.animating) {
      cancelAnimationFrame(this.animFrame);
    }

    this.animating = true;
    const totalFrames = Math.min(pTraj.length, aTraj.length);
    let frameIdx = 0;
    const pBot = JSON.parse(JSON.stringify(matchState.player_robot));
    const aBot = JSON.parse(JSON.stringify(matchState.automaton_robot));

    // Draw full trajectory ghost lines
    this._renderTrajectories(pTraj, aTraj);
    this.layerEffects.innerHTML = "";

    const step = () => {
      if (frameIdx < totalFrames) {
        pBot.pose = pTraj[frameIdx];
        aBot.pose = aTraj[frameIdx];

        this.layerRobots.innerHTML = "";
        this._renderMiniature(pBot, "player");
        this._renderMiniature(aBot, "automaton");

        frameIdx++;
        this.animFrame = requestAnimationFrame(step);
      } else {
        this.animating = false;
        this.render(matchState);
        if (onComplete) onComplete();
      }
    };

    this.animFrame = requestAnimationFrame(step);
  }

  _renderTrajectories(pTraj, aTraj) {
    this.layerGhosts.innerHTML = "";

    if (pTraj && pTraj.length > 1) {
      const pD = pTraj.map((pt, i) => `${i === 0 ? "M" : "L"} ${pt.x} ${pt.y}`).join(" ");
      const pPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
      pPath.setAttribute("d", pD);
      pPath.setAttribute("fill", "none");
      pPath.setAttribute("stroke", "#00e5ff");
      pPath.setAttribute("stroke-width", "2");
      pPath.setAttribute("stroke-dasharray", "4,3");
      pPath.setAttribute("opacity", "0.55");
      this.layerGhosts.appendChild(pPath);
    }

    if (aTraj && aTraj.length > 1) {
      const aD = aTraj.map((pt, i) => `${i === 0 ? "M" : "L"} ${pt.x} ${pt.y}`).join(" ");
      const aPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
      aPath.setAttribute("d", aD);
      aPath.setAttribute("fill", "none");
      aPath.setAttribute("stroke", "#f43f5e");
      aPath.setAttribute("stroke-width", "2");
      aPath.setAttribute("stroke-dasharray", "4,3");
      aPath.setAttribute("opacity", "0.55");
      this.layerGhosts.appendChild(aPath);
    }
  }

  _renderMiniature(robot, role) {
    if (!robot || !robot.pose) return;

    const { x, y, theta } = robot.pose;
    const isPlayer = role === "player";
    const primaryColor = isPlayer ? "#00e5ff" : "#f43f5e";
    const secondaryColor = isPlayer ? "rgba(0, 229, 255, 0.25)" : "rgba(244, 63, 94, 0.25)";

    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("transform", `translate(${x}, ${y}) rotate(${theta})`);
    g.setAttribute("class", `miniature ${role} ${robot.is_inverted ? "inverted" : ""}`);

    // 1. Chassis Template Polygon
    const templateName = robot.chassis_template || "Triangle";
    const shape = CHASSIS_MINIATURE_SHAPES[templateName] || CHASSIS_MINIATURE_SHAPES.Triangle;
    const pointsStr = shape.map(pt => `${pt[0]},${pt[1]}`).join(" ");

    const chassisPoly = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
    chassisPoly.setAttribute("points", pointsStr);
    chassisPoly.setAttribute("fill", secondaryColor);
    chassisPoly.setAttribute("stroke", primaryColor);
    chassisPoly.setAttribute("stroke-width", "2.8");
    chassisPoly.setAttribute("stroke-linejoin", "round");
    g.appendChild(chassisPoly);

    // 2. Weapon Overlay (Miniature Weapon Template on top)
    const weaponComp = Object.values(robot.components).find(c => c.card_type === "weapon" && !c.is_destroyed);
    if (weaponComp) {
      this._appendWeaponOverlay(g, weaponComp);
    }

    // 3. Heading Direction Marker (Front arrow)
    const arrow = document.createElementNS("http://www.w3.org/2000/svg", "line");
    arrow.setAttribute("x1", "0");
    arrow.setAttribute("y1", "-10");
    arrow.setAttribute("x2", "0");
    arrow.setAttribute("y2", "-32");
    arrow.setAttribute("stroke", primaryColor);
    arrow.setAttribute("stroke-width", "2.5");
    arrow.setAttribute("marker-end", `url(#arrow-${role})`);
    g.appendChild(arrow);

    // 4. Center Core Dot
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx", "0");
    dot.setAttribute("cy", "0");
    dot.setAttribute("r", "4");
    dot.setAttribute("fill", primaryColor);
    g.appendChild(dot);

    // 5. Inverted or Status Indicator
    if (robot.is_inverted) {
      const invText = document.createElementNS("http://www.w3.org/2000/svg", "text");
      invText.setAttribute("x", "0");
      invText.setAttribute("y", "4");
      invText.setAttribute("fill", "#fbbf24");
      invText.setAttribute("font-size", "14");
      invText.setAttribute("font-weight", "bold");
      invText.setAttribute("text-anchor", "middle");
      invText.textContent = "🔄";
      g.appendChild(invText);
    }

    if (robot.is_raised) {
      const raisedText = document.createElementNS("http://www.w3.org/2000/svg", "text");
      raisedText.setAttribute("x", "0");
      raisedText.setAttribute("y", "-14");
      raisedText.setAttribute("fill", "#a855f7");
      raisedText.setAttribute("font-size", "14");
      raisedText.setAttribute("font-weight", "bold");
      raisedText.setAttribute("text-anchor", "middle");
      raisedText.textContent = "🔱";
      g.appendChild(raisedText);
    }

    // 6. Name Label tag (counter-rotated so text stays upright)
    const labelG = document.createElementNS("http://www.w3.org/2000/svg", "g");
    labelG.setAttribute("transform", `rotate(${-theta}) translate(0, 48)`);

    const labelBg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    labelBg.setAttribute("x", "-40");
    labelBg.setAttribute("y", "-9");
    labelBg.setAttribute("width", "80");
    labelBg.setAttribute("height", "18");
    labelBg.setAttribute("rx", "4");
    labelBg.setAttribute("fill", "rgba(15, 23, 42, 0.85)");
    labelBg.setAttribute("stroke", primaryColor);
    labelBg.setAttribute("stroke-width", "0.8");
    labelG.appendChild(labelBg);

    const nameText = document.createElementNS("http://www.w3.org/2000/svg", "text");
    nameText.setAttribute("x", "0");
    nameText.setAttribute("y", "3.5");
    nameText.setAttribute("fill", "#ffffff");
    nameText.setAttribute("font-size", "8.5");
    nameText.setAttribute("font-weight", "bold");
    nameText.setAttribute("text-anchor", "middle");
    nameText.textContent = robot.name.length > 12 ? robot.name.substring(0, 11) + "…" : robot.name;
    labelG.appendChild(nameText);

    g.appendChild(labelG);
    this.layerRobots.appendChild(g);
  }

  _appendWeaponOverlay(parentG, weaponComp) {
    const wName = weaponComp.name;
    const wKeywords = weaponComp.keywords || "";
    const wTemplate = weaponComp.template || (wName.includes("Spinner") ? "Circle" : "Bar");

    const MAT_CENTER_X = 210.0;
    const MAT_CENTER_Y = 150.0;
    const MAT_TO_MINI_SCALE = 0.273;

    const cardW = 44.0;
    const cardH = 64.0;
    const cardCx = (Number(weaponComp.x) || 100) + cardW / 2.0;
    const cardCy = (Number(weaponComp.y) || 100) + cardH / 2.0;
    const lx = (cardCx - MAT_CENTER_X) * MAT_TO_MINI_SCALE;
    const ly = (cardCy - MAT_CENTER_Y) * MAT_TO_MINI_SCALE;

    const wg = document.createElementNS("http://www.w3.org/2000/svg", "g");
    wg.setAttribute("class", "miniature-weapon");

    const spinCount = weaponComp.spin_counters || 0;

    if (wTemplate.includes("Circle") || wName.includes("Spinner") || wName.includes("Blade") || wName.includes("Disc")) {
      // Circle spinner template: centered on equivalent card location
      const radius = wName.includes("Bloodsport") ? 30 : 22;
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("cx", lx);
      circle.setAttribute("cy", ly);
      circle.setAttribute("r", radius);
      circle.setAttribute("fill", "rgba(239, 68, 68, 0.2)");
      circle.setAttribute("stroke", "#ef4444");
      circle.setAttribute("stroke-width", "2.5");
      circle.setAttribute("stroke-dasharray", "6,3");
      wg.appendChild(circle);

      // Red active perimeter tooth / tip
      const tooth1 = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      tooth1.setAttribute("cx", lx);
      tooth1.setAttribute("cy", `${ly - radius}`);
      tooth1.setAttribute("r", "3.5");
      tooth1.setAttribute("fill", "#ef4444");
      wg.appendChild(tooth1);

      // Spin Counter visual badge if spun up
      if (spinCount > 0) {
        const sBadge = document.createElementNS("http://www.w3.org/2000/svg", "g");
        sBadge.setAttribute("transform", `translate(${lx}, ${ly})`);

        const sCircle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        sCircle.setAttribute("r", "7.5");
        sCircle.setAttribute("fill", "#0284c7");
        sCircle.setAttribute("stroke", "#ffffff");
        sCircle.setAttribute("stroke-width", "1");
        sBadge.appendChild(sCircle);

        const sText = document.createElementNS("http://www.w3.org/2000/svg", "text");
        sText.setAttribute("x", "0");
        sText.setAttribute("y", "3");
        sText.setAttribute("fill", "#ffffff");
        sText.setAttribute("font-size", "7.5");
        sText.setAttribute("font-weight", "bold");
        sText.setAttribute("text-anchor", "middle");
        sText.textContent = `${spinCount}`;
        sBadge.appendChild(sText);

        wg.appendChild(sBadge);
      }

    } else if (wTemplate.includes("Prongs") || wName.includes("Scythe") || wName.includes("Claw")) {
      // Dual prongs template centered around lx, ly
      const prongL = document.createElementNS("http://www.w3.org/2000/svg", "line");
      prongL.setAttribute("x1", `${lx - 16}`);
      prongL.setAttribute("y1", `${ly + 6}`);
      prongL.setAttribute("x2", `${lx - 16}`);
      prongL.setAttribute("y2", `${ly - 24}`);
      prongL.setAttribute("stroke", "#ef4444");
      prongL.setAttribute("stroke-width", "3.5");
      prongL.setAttribute("stroke-linecap", "round");
      wg.appendChild(prongL);

      const prongR = document.createElementNS("http://www.w3.org/2000/svg", "line");
      prongR.setAttribute("x1", `${lx + 16}`);
      prongR.setAttribute("y1", `${ly + 6}`);
      prongR.setAttribute("x2", `${lx + 16}`);
      prongR.setAttribute("y2", `${ly - 24}`);
      prongR.setAttribute("stroke", "#ef4444");
      prongR.setAttribute("stroke-width", "3.5");
      prongR.setAttribute("stroke-linecap", "round");
      wg.appendChild(prongR);

    } else if (wTemplate.includes("Line") || wName.includes("Vertical")) {
      // Single line drum / vertical spinner centered at lx, ly
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", `${lx}`);
      line.setAttribute("y1", `${ly + 10}`);
      line.setAttribute("x2", `${lx}`);
      line.setAttribute("y2", `${ly - 22}`);
      line.setAttribute("stroke", "#ef4444");
      line.setAttribute("stroke-width", "4.5");
      line.setAttribute("stroke-linecap", "round");
      wg.appendChild(line);

      if (spinCount > 0) {
        const sBadge = document.createElementNS("http://www.w3.org/2000/svg", "g");
        sBadge.setAttribute("transform", `translate(${lx + 9}, ${ly - 8})`);
        const sCircle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        sCircle.setAttribute("r", "6.5");
        sCircle.setAttribute("fill", "#0284c7");
        sBadge.appendChild(sCircle);
        const sText = document.createElementNS("http://www.w3.org/2000/svg", "text");
        sText.setAttribute("x", "0");
        sText.setAttribute("y", "2.5");
        sText.setAttribute("fill", "#ffffff");
        sText.setAttribute("font-size", "7");
        sText.setAttribute("font-weight", "bold");
        sText.setAttribute("text-anchor", "middle");
        sText.textContent = `${spinCount}`;
        sBadge.appendChild(sText);
        wg.appendChild(sBadge);
      }

    } else {
      // Bar template (Lifter / Beater Bar) centered at lx, ly
      const bar = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      bar.setAttribute("x", `${lx - 24}`);
      bar.setAttribute("y", `${ly - 8}`);
      bar.setAttribute("width", "48");
      bar.setAttribute("height", "14");
      bar.setAttribute("rx", "2");
      bar.setAttribute("fill", "rgba(239, 68, 68, 0.4)");
      bar.setAttribute("stroke", "#ef4444");
      bar.setAttribute("stroke-width", "2");
      wg.appendChild(bar);

      if (spinCount > 0) {
        const sBadge = document.createElementNS("http://www.w3.org/2000/svg", "g");
        sBadge.setAttribute("transform", `translate(${lx}, ${ly - 14})`);
        const sCircle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        sCircle.setAttribute("r", "6.5");
        sCircle.setAttribute("fill", "#0284c7");
        sBadge.appendChild(sCircle);
        const sText = document.createElementNS("http://www.w3.org/2000/svg", "text");
        sText.setAttribute("x", "0");
        sText.setAttribute("y", "2.5");
        sText.setAttribute("fill", "#ffffff");
        sText.setAttribute("font-size", "7");
        sText.setAttribute("font-weight", "bold");
        sText.setAttribute("text-anchor", "middle");
        sText.textContent = `${spinCount}`;
        sBadge.appendChild(sText);
        wg.appendChild(sBadge);
      }
    }

    parentG.appendChild(wg);
  }

  _renderCollisionEffect(collision) {
    const [cx, cy] = collision.contact_point;
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("transform", `translate(${cx}, ${cy})`);

    const isHit = collision.contact_type === "ACTIVE";
    const burstColor = isHit ? "#f59e0b" : "#3b82f6";

    // Shockwave ring
    const ring = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    ring.setAttribute("r", "20");
    ring.setAttribute("fill", "none");
    ring.setAttribute("stroke", burstColor);
    ring.setAttribute("stroke-width", "3");
    ring.setAttribute("opacity", "0.85");
    g.appendChild(ring);

    // Impact burst icon
    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", "0");
    text.setAttribute("y", "7");
    text.setAttribute("font-size", "22");
    text.setAttribute("text-anchor", "middle");
    text.textContent = isHit ? "💥" : "🛡️";
    g.appendChild(text);

    this.layerEffects.appendChild(g);
  }
}
