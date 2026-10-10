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
    this.layerTemplates = this.svg.querySelector("#layer-templates");
    this.layerGhosts = this.svg.querySelector("#layer-ghosts");
    this.layerRobots = this.svg.querySelector("#layer-robots");
    this.layerEffects = this.svg.querySelector("#layer-effects");

    this.animating = false;
    this.animFrame = null;

    // Arena Zoom & Pan state
    this.zoom = 1.0;
    this.pan = { x: 0, y: 0 };
    this.baseW = 800;
    this.baseH = 800;
    this.minZoom = 0.6;
    this.maxZoom = 4.0;

    this._initZoomControls();
  }

  _initZoomControls() {
    this.btnZoomIn = document.getElementById("btn-arena-zoom-in");
    this.btnZoomOut = document.getElementById("btn-arena-zoom-out");
    this.btnZoomFit = document.getElementById("btn-arena-zoom-fit");

    if (this.btnZoomIn) this.btnZoomIn.addEventListener("click", () => this.zoomIn());
    if (this.btnZoomOut) this.btnZoomOut.addEventListener("click", () => this.zoomOut());
    if (this.btnZoomFit) this.btnZoomFit.addEventListener("click", () => this.zoomFit());

    // Wheel zoom on SVG (only intercepts wheel when Ctrl/Cmd is held or already zoomed in, otherwise allows page scroll)
    this.svg.addEventListener("wheel", (e) => {
      if (e.ctrlKey || e.metaKey || this.zoom > 1.05) {
        e.preventDefault();
        const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
        this.setZoom(this.zoom * zoomFactor);
      }
    }, { passive: false });

    // Touch & pointer pan
    let isDragging = false;
    let startPoint = { x: 0, y: 0 };
    let initialPinchDist = null;
    let initialZoom = 1.0;

    this.svg.addEventListener("pointerdown", (e) => {
      if (e.pointerType === "mouse" && e.button !== 0) return;
      // Allow natural touch scrolling on mobile when arena is not zoomed in
      if (e.pointerType === "touch" && this.zoom <= 1.05) return;
      isDragging = true;
      startPoint = { x: e.clientX, y: e.clientY };
      if (this.svg.setPointerCapture) {
        try { this.svg.setPointerCapture(e.pointerId); } catch (_) {}
      }
    });

    this.svg.addEventListener("pointermove", (e) => {
      if (!isDragging) return;
      const dx = (e.clientX - startPoint.x) / (this.zoom * 1.0);
      const dy = (e.clientY - startPoint.y) / (this.zoom * 1.0);
      startPoint = { x: e.clientX, y: e.clientY };
      this.pan.x -= dx;
      this.pan.y -= dy;
      this._clampPan();
      this._updateViewBox();
    });

    const endDrag = (e) => {
      isDragging = false;
      if (this.svg.releasePointerCapture) {
        try { this.svg.releasePointerCapture(e.pointerId); } catch (_) {}
      }
    };
    this.svg.addEventListener("pointerup", endDrag);
    this.svg.addEventListener("pointercancel", endDrag);

    // Touch pinch gesture
    this.svg.addEventListener("touchstart", (e) => {
      if (e.touches.length === 2) {
        initialPinchDist = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY
        );
        initialZoom = this.zoom;
      }
    }, { passive: true });

    this.svg.addEventListener("touchmove", (e) => {
      if (e.touches.length === 2 && initialPinchDist) {
        const dist = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY
        );
        const factor = dist / initialPinchDist;
        this.setZoom(initialZoom * factor);
      }
    }, { passive: true });

    this.svg.addEventListener("touchend", (e) => {
      if (e.touches.length < 2) {
        initialPinchDist = null;
      }
    }, { passive: true });
  }

  zoomIn() {
    this.setZoom(this.zoom * 1.25);
  }

  zoomOut() {
    this.setZoom(this.zoom / 1.25);
  }

  zoomFit() {
    this.zoom = 1.0;
    this.pan = { x: 0, y: 0 };
    this._updateViewBox();
  }

  setZoom(newZoom) {
    this.zoom = Math.max(this.minZoom, Math.min(this.maxZoom, newZoom));
    this._clampPan();
    this._updateViewBox();
  }

  _clampPan() {
    const w = this.baseW / this.zoom;
    const h = this.baseH / this.zoom;
    const maxPanX = Math.max(0, (this.baseW - w) / 2 + 250);
    const maxPanY = Math.max(0, (this.baseH - h) / 2 + 250);
    this.pan.x = Math.max(-maxPanX, Math.min(maxPanX, this.pan.x));
    this.pan.y = Math.max(-maxPanY, Math.min(maxPanY, this.pan.y));
  }

  _updateViewBox() {
    const w = this.baseW / this.zoom;
    const h = this.baseH / this.zoom;
    const x = (this.baseW / 2) - (w / 2) + this.pan.x;
    const y = (this.baseH / 2) - (h / 2) + this.pan.y;
    this.svg.setAttribute("viewBox", `${x} ${y} ${w} ${h}`);
  }

  render(matchState) {
    if (!matchState) return;

    const pBot = matchState.player_robot;
    const aBot = matchState.automaton_robot;

    if (this.layerTemplates) this.layerTemplates.innerHTML = "";

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

    // Render physical movement templates docked at start poses
    if (this.layerTemplates) {
      this.layerTemplates.innerHTML = "";
      this.layerTemplates.style.opacity = "1";
      if (matchState.player_template && matchState.player_template.category !== "stop" && pTraj.length > 0) {
        this._renderMovementTemplate(pTraj[0], matchState.player_choice, matchState.player_template, "player");
      }
      if (matchState.automaton_template && matchState.automaton_template.category !== "stop" && aTraj.length > 0) {
        this._renderMovementTemplate(aTraj[0], matchState.automaton_choice, matchState.automaton_template, "automaton");
      }
    }

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

        // Smoothly fade out physical movement templates
        if (this.layerTemplates) {
          const tLayer = this.layerTemplates;
          tLayer.style.transition = "opacity 0.4s ease";
          tLayer.style.opacity = "0";
          setTimeout(() => {
            tLayer.innerHTML = "";
            tLayer.style.opacity = "1";
            tLayer.style.transition = "";
          }, 400);
        }

        this.render(matchState);
        if (onComplete) onComplete();
      }
    };

    this.animFrame = requestAnimationFrame(step);
  }

  _renderMovementTemplate(startPose, choice, templateInfo, role) {
    if (!startPose || !templateInfo || templateInfo.category === "stop") return;

    const { x, y, theta } = startPose;
    const isPlayer = role === "player";
    const primaryColor = isPlayer ? "#00e5ff" : "#f43f5e";
    const targetColor = isPlayer ? "#38bdf8" : "#fb7185";
    const acrylicFill = isPlayer ? "rgba(0, 229, 255, 0.16)" : "rgba(244, 63, 94, 0.16)";

    const outerG = document.createElementNS("http://www.w3.org/2000/svg", "g");
    outerG.setAttribute("class", `movement-template-overlay template-${role}`);
    outerG.setAttribute("transform", `translate(${x}, ${y}) rotate(${theta})`);

    // Inner transform group handling flip & at_rear
    const innerG = document.createElementNS("http://www.w3.org/2000/svg", "g");
    let innerTransform = "";
    if (templateInfo.flipped) {
      innerTransform += "scale(-1, 1) ";
    }
    if (templateInfo.at_rear && templateInfo.category !== "straight") {
      innerTransform += "scale(1, -1) ";
    }
    if (innerTransform) {
      innerG.setAttribute("transform", innerTransform.trim());
    }

    const cat = templateInfo.category;
    if (cat === "straight") {
      this._buildStraightTemplate(innerG, templateInfo, primaryColor, targetColor, acrylicFill);
    } else if (cat === "spin") {
      this._buildSpinTemplate(innerG, templateInfo, primaryColor, targetColor, acrylicFill);
    } else if (cat === "pivot") {
      this._buildPivotTemplate(innerG, templateInfo, primaryColor, targetColor, acrylicFill);
    } else if (cat === "curve_forward" || cat === "curve_tight") {
      this._buildCurveTemplate(innerG, templateInfo, primaryColor, targetColor, acrylicFill, cat === "curve_tight");
    }

    outerG.appendChild(innerG);

    // Template Title / Type Badge (not flipped so text stays readable)
    const badgeG = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const badgeY = templateInfo.at_rear ? 65 : -55;
    badgeG.setAttribute("transform", `translate(0, ${badgeY})`);

    const badgeBg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    badgeBg.setAttribute("x", "-70");
    badgeBg.setAttribute("y", "-9");
    badgeBg.setAttribute("width", "140");
    badgeBg.setAttribute("height", "18");
    badgeBg.setAttribute("rx", "4");
    badgeBg.setAttribute("fill", "rgba(15, 23, 42, 0.9)");
    badgeBg.setAttribute("stroke", primaryColor);
    badgeBg.setAttribute("stroke-width", "1");
    badgeG.appendChild(badgeBg);

    const badgeText = document.createElementNS("http://www.w3.org/2000/svg", "text");
    badgeText.setAttribute("x", "0");
    badgeText.setAttribute("y", "3.5");
    badgeText.setAttribute("fill", "#ffffff");
    badgeText.setAttribute("font-size", "7.5");
    badgeText.setAttribute("font-weight", "bold");
    badgeText.setAttribute("text-anchor", "middle");
    const flipTag = templateInfo.flipped ? " [FLIP]" : "";
    const rearTag = templateInfo.at_rear ? " [REAR]" : "";
    badgeText.textContent = `📐 ${templateInfo.name}${flipTag}${rearTag}`;
    badgeG.appendChild(badgeText);

    outerG.appendChild(badgeG);
    this.layerTemplates.appendChild(outerG);
  }

  _buildStraightTemplate(parentG, templateInfo, primaryColor, targetColor, acrylicFill) {
    const w = 65.0;
    const u = 40.0;
    const r_mini = 35.0;
    const pairs = templateInfo.pairs || [[1, 1], [2, 2], [3, 3], [4, 4], [5, 5]];
    const max_l = Math.max(...pairs.map(p => p[0]));
    const totalH = max_l * u;
    const atRear = templateInfo.at_rear;

    const startY = atRear ? r_mini : -r_mini;
    const endY = atRear ? (r_mini + totalH) : (-r_mini - totalH);
    const rectY = atRear ? r_mini : (-r_mini - totalH);

    // Acrylic Contour
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", `${-w / 2}`);
    rect.setAttribute("y", `${rectY}`);
    rect.setAttribute("width", `${w}`);
    rect.setAttribute("height", `${totalH}`);
    rect.setAttribute("rx", "3");
    rect.setAttribute("fill", acrylicFill);
    rect.setAttribute("stroke", primaryColor);
    rect.setAttribute("stroke-width", "2");
    parentG.appendChild(rect);

    // Centerline
    const cLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
    cLine.setAttribute("x1", "0");
    cLine.setAttribute("y1", `${startY}`);
    cLine.setAttribute("x2", "0");
    cLine.setAttribute("y2", `${endY}`);
    cLine.setAttribute("stroke", "rgba(148, 163, 184, 0.45)");
    cLine.setAttribute("stroke-width", "1.2");
    cLine.setAttribute("stroke-dasharray", "4,3");
    parentG.appendChild(cLine);

    // START line
    const sLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
    sLine.setAttribute("x1", `${-w / 2}`);
    sLine.setAttribute("y1", `${startY}`);
    sLine.setAttribute("x2", `${w / 2}`);
    sLine.setAttribute("y2", `${startY}`);
    sLine.setAttribute("stroke", "#0f172a");
    sLine.setAttribute("stroke-width", "3.8");
    parentG.appendChild(sLine);

    // Stop lines
    for (const [l, r] of pairs) {
      const lineY = atRear ? (r_mini + l * u) : (-r_mini - l * u);
      const isTarget = (l === templateInfo.canonical_left);

      const mark = document.createElementNS("http://www.w3.org/2000/svg", "line");
      mark.setAttribute("x1", `${-w / 2}`);
      mark.setAttribute("y1", `${lineY}`);
      mark.setAttribute("x2", `${w / 2}`);
      mark.setAttribute("y2", `${lineY}`);

      if (isTarget) {
        mark.setAttribute("stroke", targetColor);
        mark.setAttribute("stroke-width", "3.2");
        parentG.appendChild(mark);

        const lbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
        lbl.setAttribute("x", "0");
        lbl.setAttribute("y", `${lineY + (atRear ? 10 : -4)}`);
        lbl.setAttribute("fill", targetColor);
        lbl.setAttribute("font-size", "8.5");
        lbl.setAttribute("font-weight", "900");
        lbl.setAttribute("text-anchor", "middle");
        lbl.textContent = `★ ${templateInfo.target_line_label}`;
        parentG.appendChild(lbl);
      } else {
        mark.setAttribute("stroke", "rgba(148, 163, 184, 0.45)");
        mark.setAttribute("stroke-width", "1.5");
        mark.setAttribute("stroke-dasharray", "4,3");
        parentG.appendChild(mark);

        const lbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
        lbl.setAttribute("x", `${w / 2 - 4}`);
        lbl.setAttribute("y", `${lineY + (atRear ? 8 : -3)}`);
        lbl.setAttribute("fill", "rgba(148, 163, 184, 0.6)");
        lbl.setAttribute("font-size", "6");
        lbl.setAttribute("text-anchor", "end");
        lbl.textContent = `L${l}`;
        parentG.appendChild(lbl);
      }
    }
  }

  _buildSpinTemplate(parentG, templateInfo, primaryColor, targetColor, acrylicFill) {
    const radius = 35.0;
    const pairs = templateInfo.pairs || [[1, -1], [2, -2], [3, -3], [4, -4]];

    // Acrylic Disc
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", "0");
    circle.setAttribute("cy", "0");
    circle.setAttribute("r", `${radius}`);
    circle.setAttribute("fill", acrylicFill);
    circle.setAttribute("stroke", primaryColor);
    circle.setAttribute("stroke-width", "2");
    parentG.appendChild(circle);

    const pin = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    pin.setAttribute("cx", "0");
    pin.setAttribute("cy", "0");
    pin.setAttribute("r", "3.5");
    pin.setAttribute("fill", "#ffffff");
    parentG.appendChild(pin);

    // Baseline (0°)
    const base = document.createElementNS("http://www.w3.org/2000/svg", "line");
    base.setAttribute("x1", "0");
    base.setAttribute("y1", "0");
    base.setAttribute("x2", "0");
    base.setAttribute("y2", `${-radius}`);
    base.setAttribute("stroke", "#0f172a");
    base.setAttribute("stroke-width", "3.5");
    parentG.appendChild(base);

    for (const [l, r] of pairs) {
      const d_th = l * (Math.PI / 2.0);
      const px = radius * Math.sin(d_th);
      const py = -radius * Math.cos(d_th);
      const isTarget = (l === templateInfo.canonical_left);

      const radLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
      radLine.setAttribute("x1", "0");
      radLine.setAttribute("y1", "0");
      radLine.setAttribute("x2", `${px}`);
      radLine.setAttribute("y2", `${py}`);

      if (isTarget) {
        radLine.setAttribute("stroke", targetColor);
        radLine.setAttribute("stroke-width", "3.2");
        parentG.appendChild(radLine);

        const lbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
        lbl.setAttribute("x", `${px * 1.25}`);
        lbl.setAttribute("y", `${py * 1.25 + 3}`);
        lbl.setAttribute("fill", targetColor);
        lbl.setAttribute("font-size", "8");
        lbl.setAttribute("font-weight", "900");
        lbl.setAttribute("text-anchor", px > 2 ? "start" : px < -2 ? "end" : "middle");
        lbl.textContent = `★ ${templateInfo.target_line_label} (${l * 90}°)`;
        parentG.appendChild(lbl);
      } else {
        radLine.setAttribute("stroke", "rgba(148, 163, 184, 0.45)");
        radLine.setAttribute("stroke-width", "1.5");
        radLine.setAttribute("stroke-dasharray", "3,3");
        parentG.appendChild(radLine);
      }
    }
  }

  _buildPivotTemplate(parentG, templateInfo, primaryColor, targetColor, acrylicFill) {
    const radius = 65.0; // WHEELBASE_MM
    const pv_x = 32.5;
    const pv_y = 0;
    const pairs = templateInfo.pairs || [[1, 0], [2, 0], [3, 0], [4, 0]];

    // Semicircle contour around pivot wheel (32.5, 0)
    // Starts at left wheel (-32.5, 0) and sweeps 180° clockwise
    const pathD = `M ${pv_x} ${pv_y} L -32.5 0 A ${radius} ${radius} 0 0 1 ${pv_x + radius} 0 Z`;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", pathD);
    path.setAttribute("fill", acrylicFill);
    path.setAttribute("stroke", primaryColor);
    path.setAttribute("stroke-width", "2");
    parentG.appendChild(path);

    // Pivot Wheel Center Marker
    const pin = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    pin.setAttribute("cx", `${pv_x}`);
    pin.setAttribute("cy", `${pv_y}`);
    pin.setAttribute("r", "3.5");
    pin.setAttribute("fill", "#ef4444");
    parentG.appendChild(pin);

    // Start Line: (-32.5, 0) to (32.5, 0)
    const startLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
    startLine.setAttribute("x1", "-32.5");
    startLine.setAttribute("y1", "0");
    startLine.setAttribute("x2", `${pv_x}`);
    startLine.setAttribute("y2", "0");
    startLine.setAttribute("stroke", "#0f172a");
    startLine.setAttribute("stroke-width", "3.5");
    parentG.appendChild(startLine);

    for (const [l, r] of pairs) {
      const d_th = l * (Math.PI / 4.0);
      const px = pv_x - radius * Math.cos(d_th);
      const py = pv_y - radius * Math.sin(d_th);
      const isTarget = (l === templateInfo.canonical_left);

      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", `${pv_x}`);
      line.setAttribute("y1", `${pv_y}`);
      line.setAttribute("x2", `${px}`);
      line.setAttribute("y2", `${py}`);

      if (isTarget) {
        line.setAttribute("stroke", targetColor);
        line.setAttribute("stroke-width", "3.2");
        parentG.appendChild(line);

        const lbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
        lbl.setAttribute("x", `${pv_x - (radius * 0.65) * Math.cos(d_th)}`);
        lbl.setAttribute("y", `${pv_y - (radius * 0.65) * Math.sin(d_th) - 4}`);
        lbl.setAttribute("fill", targetColor);
        lbl.setAttribute("font-size", "8");
        lbl.setAttribute("font-weight", "900");
        lbl.setAttribute("text-anchor", "middle");
        lbl.textContent = `★ ${templateInfo.target_line_label} (${l * 45}°)`;
        parentG.appendChild(lbl);
      } else {
        line.setAttribute("stroke", "rgba(148, 163, 184, 0.45)");
        line.setAttribute("stroke-width", "1.5");
        line.setAttribute("stroke-dasharray", "3,3");
        parentG.appendChild(line);
      }
    }
  }

  _buildCurveTemplate(parentG, templateInfo, primaryColor, targetColor, acrylicFill, isTight = false) {
    const w = 65.0;
    const pairs = templateInfo.pairs || [[templateInfo.canonical_left, templateInfo.canonical_right]];
    const max_l = Math.max(...pairs.map(p => p[0]));
    const max_r = Math.max(...pairs.map(p => p[1]));
    const diff = isTight ? (max_l - Math.min(...pairs.map(p => p[1]))) : (max_l - max_r);

    const r_out = w * max_l / diff;
    const r_in = isTight ? Math.abs(w * Math.min(...pairs.map(p => p[1])) / diff) : (w * max_r / diff);
    const cx = isTight ? (-w / 2 + r_out) : (w / 2 + r_in);
    const cy = 0;

    const d_th_max = diff * (Math.PI / 4.0);
    const largeArc = d_th_max > Math.PI ? 1 : 0;

    const p_out_start = [-w / 2, 0];
    const p_in_start = [w / 2, 0];
    const p_out_end = [cx - r_out * Math.cos(d_th_max), cy - r_out * Math.sin(d_th_max)];
    const p_in_end = [cx - r_in * Math.cos(d_th_max), cy - r_in * Math.sin(d_th_max)];

    const pathD = `M ${p_out_start[0]} ${p_out_start[1]} ` +
      `A ${r_out} ${r_out} 0 ${largeArc} 1 ${p_out_end[0]} ${p_out_end[1]} ` +
      `L ${p_in_end[0]} ${p_in_end[1]} ` +
      `A ${r_in} ${r_in} 0 ${largeArc} 0 ${p_in_start[0]} ${p_in_start[1]} Z`;

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", pathD);
    path.setAttribute("fill", acrylicFill);
    path.setAttribute("stroke", primaryColor);
    path.setAttribute("stroke-width", "2");
    parentG.appendChild(path);

    // Centerline
    const r_mid = (r_in + r_out) / 2.0;
    const midD = `M 0 0 A ${r_mid} ${r_mid} 0 ${largeArc} 1 ${cx - r_mid * Math.cos(d_th_max)} ${cy - r_mid * Math.sin(d_th_max)}`;
    const midLine = document.createElementNS("http://www.w3.org/2000/svg", "path");
    midLine.setAttribute("d", midD);
    midLine.setAttribute("fill", "none");
    midLine.setAttribute("stroke", "rgba(148, 163, 184, 0.45)");
    midLine.setAttribute("stroke-width", "1.2");
    midLine.setAttribute("stroke-dasharray", "4,3");
    parentG.appendChild(midLine);

    // Start line
    const startLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
    startLine.setAttribute("x1", `${p_out_start[0]}`);
    startLine.setAttribute("y1", `${p_out_start[1]}`);
    startLine.setAttribute("x2", `${p_in_start[0]}`);
    startLine.setAttribute("y2", `${p_in_start[1]}`);
    startLine.setAttribute("stroke", "#0f172a");
    startLine.setAttribute("stroke-width", "3.5");
    parentG.appendChild(startLine);

    for (const [l, r] of pairs) {
      const d_th = (l - r) * (Math.PI / 4.0);
      const po = [cx - r_out * Math.cos(d_th), cy - r_out * Math.sin(d_th)];
      const pi = [cx - r_in * Math.cos(d_th), cy - r_in * Math.sin(d_th)];
      const isTarget = (l === templateInfo.canonical_left);

      const mark = document.createElementNS("http://www.w3.org/2000/svg", "line");
      mark.setAttribute("x1", `${po[0]}`);
      mark.setAttribute("y1", `${po[1]}`);
      mark.setAttribute("x2", `${pi[0]}`);
      mark.setAttribute("y2", `${pi[1]}`);

      if (isTarget) {
        mark.setAttribute("stroke", targetColor);
        mark.setAttribute("stroke-width", "3.2");
        parentG.appendChild(mark);

        const lbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
        lbl.setAttribute("x", `${(po[0] + pi[0]) / 2}`);
        lbl.setAttribute("y", `${(po[1] + pi[1]) / 2 - 4}`);
        lbl.setAttribute("fill", targetColor);
        lbl.setAttribute("font-size", "8");
        lbl.setAttribute("font-weight", "900");
        lbl.setAttribute("text-anchor", "middle");
        lbl.textContent = `★ ${templateInfo.target_line_label}`;
        parentG.appendChild(lbl);
      } else {
        mark.setAttribute("stroke", "rgba(148, 163, 184, 0.45)");
        mark.setAttribute("stroke-width", "1.5");
        mark.setAttribute("stroke-dasharray", "3,3");
        parentG.appendChild(mark);
      }
    }
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

    // 1. Inverted Outer Warning Aura
    if (robot.is_inverted) {
      const halo = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      halo.setAttribute("cx", "0");
      halo.setAttribute("cy", "0");
      halo.setAttribute("r", "34");
      halo.setAttribute("fill", "rgba(245, 158, 11, 0.16)");
      halo.setAttribute("stroke", "#f59e0b");
      halo.setAttribute("stroke-width", "2.2");
      halo.setAttribute("stroke-dasharray", "6,4");
      g.appendChild(halo);
    }

    // 1b. Chassis Template Polygon
    const templateName = robot.chassis_template || "Triangle";
    const shape = CHASSIS_MINIATURE_SHAPES[templateName] || CHASSIS_MINIATURE_SHAPES.Triangle;
    const pointsStr = shape.map(pt => `${pt[0]},${pt[1]}`).join(" ");

    const chassisPoly = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
    chassisPoly.setAttribute("points", pointsStr);
    if (robot.is_inverted) {
      chassisPoly.setAttribute("fill", "rgba(245, 158, 11, 0.35)");
      chassisPoly.setAttribute("stroke", "#f59e0b");
      chassisPoly.setAttribute("stroke-width", "3.2");
      chassisPoly.setAttribute("stroke-dasharray", "5,3");
    } else {
      chassisPoly.setAttribute("fill", secondaryColor);
      chassisPoly.setAttribute("stroke", primaryColor);
      chassisPoly.setAttribute("stroke-width", "2.8");
    }
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
    if (robot.is_inverted) {
      arrow.setAttribute("stroke", "#f59e0b");
      arrow.setAttribute("stroke-width", "2.2");
      arrow.setAttribute("stroke-dasharray", "4,3");
    } else {
      arrow.setAttribute("stroke", primaryColor);
      arrow.setAttribute("stroke-width", "2.5");
      arrow.setAttribute("marker-end", `url(#arrow-${role})`);
    }
    g.appendChild(arrow);

    // 4. Center Core Dot
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx", "0");
    dot.setAttribute("cy", "0");
    dot.setAttribute("r", "4");
    dot.setAttribute("fill", robot.is_inverted ? "#f59e0b" : primaryColor);
    g.appendChild(dot);

    // 5. Inverted or Status Indicator
    if (robot.is_inverted) {
      const invText = document.createElementNS("http://www.w3.org/2000/svg", "text");
      invText.setAttribute("x", "0");
      invText.setAttribute("y", "4");
      invText.setAttribute("fill", "#ffffff");
      invText.setAttribute("font-size", "14");
      invText.setAttribute("font-weight", "bold");
      invText.setAttribute("text-anchor", "middle");
      invText.textContent = "🔄";
      g.appendChild(invText);

      // Upright prominent pill badge above miniature
      const invBadgeG = document.createElementNS("http://www.w3.org/2000/svg", "g");
      invBadgeG.setAttribute("transform", `rotate(${-theta}) translate(0, -42)`);

      const invPill = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      invPill.setAttribute("x", "-38");
      invPill.setAttribute("y", "-8");
      invPill.setAttribute("width", "76");
      invPill.setAttribute("height", "16");
      invPill.setAttribute("rx", "8");
      invPill.setAttribute("fill", "#f59e0b");
      invPill.setAttribute("stroke", "#ffffff");
      invPill.setAttribute("stroke-width", "1");
      invBadgeG.appendChild(invPill);

      const invPillText = document.createElementNS("http://www.w3.org/2000/svg", "text");
      invPillText.setAttribute("x", "0");
      invPillText.setAttribute("y", "3.5");
      invPillText.setAttribute("fill", "#000000");
      invPillText.setAttribute("font-size", "7.5");
      invPillText.setAttribute("font-weight", "900");
      invPillText.setAttribute("letter-spacing", "0.5");
      invPillText.setAttribute("text-anchor", "middle");
      invPillText.textContent = "⚠️ INVERTED";
      invBadgeG.appendChild(invPillText);

      g.appendChild(invBadgeG);
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
    labelBg.setAttribute("stroke", robot.is_inverted ? "#f59e0b" : primaryColor);
    labelBg.setAttribute("stroke-width", "1");
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
    const rawX = Number(weaponComp.x);
    const rawY = Number(weaponComp.y);
    const cardCx = (Number.isFinite(rawX) ? rawX : 100.0) + cardW / 2.0;
    const cardCy = (Number.isFinite(rawY) ? rawY : 100.0) + cardH / 2.0;
    const lx = (cardCx - MAT_CENTER_X) * MAT_TO_MINI_SCALE;
    const ly = (cardCy - MAT_CENTER_Y) * MAT_TO_MINI_SCALE;

    const wg = document.createElementNS("http://www.w3.org/2000/svg", "g");
    wg.setAttribute("class", "miniature-weapon");

    const spinCount = weaponComp.spin_counters || 0;

    if (wTemplate.includes("Circle") || wName.includes("Spinner") || wName.includes("Blade") || wName.includes("Disc")) {
      // Circle spinner template: centered on equivalent card location
      const isLargeCircle = wTemplate.toLowerCase().includes("large") || wName.includes("Bloodsport");
      const radius = isLargeCircle ? 30 : 22;
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("cx", lx);
      circle.setAttribute("cy", ly);
      circle.setAttribute("r", radius);
      circle.setAttribute("fill", isLargeCircle ? "rgba(239, 68, 68, 0.24)" : "rgba(239, 68, 68, 0.2)");
      circle.setAttribute("stroke", "#ef4444");
      circle.setAttribute("stroke-width", "2.5");
      circle.setAttribute("stroke-dasharray", "6,3");
      wg.appendChild(circle);

      if (isLargeCircle) {
        const innerRing = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        innerRing.setAttribute("cx", lx);
        innerRing.setAttribute("cy", ly);
        innerRing.setAttribute("r", "18");
        innerRing.setAttribute("fill", "none");
        innerRing.setAttribute("stroke", "rgba(239, 68, 68, 0.5)");
        innerRing.setAttribute("stroke-width", "1.2");
        innerRing.setAttribute("stroke-dasharray", "3,3");
        wg.appendChild(innerRing);
      }

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
