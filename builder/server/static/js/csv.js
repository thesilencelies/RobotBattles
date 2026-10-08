/**
 * Robot CSV Save / Load and API client
 */

import { state } from "./state.js";

export function serializeRobotToCsv() {
  const lines = ["id,card,location,connections"];
  const conns = state.getConnections();

  let rowId = 1;

  // 1. Chassis row
  if (state.chassis) {
    lines.push(`${rowId},"${state.chassis.name}","chassis:0,0,0",`);
    rowId++;
  }

  // 2. Placed cards
  for (const card of state.placedCards) {
    const cid = rowId++;
    const name = (card.cardData && card.cardData.name) || "Card";
    const loc = `chassis:${card.x.toFixed(1)},${card.y.toFixed(1)},${card.rotation || 0}`;
    const neighborIds = conns.get(card.id) || [];
    // Convert state ids to integer row indices if desired, or join
    const connStr = neighborIds.join(";");
    lines.push(`${cid},"${name}","${loc}","${connStr}"`);
  }

  // 3. Spare cards
  let spareIdx = 0;
  for (const spare of state.spareCards) {
    const cid = rowId++;
    const name = (spare.cardData && spare.cardData.name) || "Card";
    const loc = `spares:${spareIdx++}`;
    lines.push(`${cid},"${name}","${loc}",`);
  }

  return lines.join("\n") + "\n";
}

export function parseCsvToRobot(csvText) {
  const lines = csvText.trim().split(/\r?\n/);
  if (lines.length < 1) {
    throw new Error("Empty CSV file");
  }

  // Parse header
  const header = parseCsvLine(lines[0]);
  const colId = header.indexOf("id");
  const colCard = header.indexOf("card");
  const colLoc = header.indexOf("location");
  const colConn = header.indexOf("connections");

  if (colCard === -1 || colLoc === -1) {
    throw new Error("Invalid CSV format. Missing 'card' or 'location' header columns.");
  }

  let chassis = null;
  const placed = [];
  const spares = [];

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    const row = parseCsvLine(line);

    const cid = (row[colId] || String(i)).trim();
    const cardName = (row[colCard] || "").trim();
    const location = (row[colLoc] || "").trim();
    const connections = colConn !== -1 ? (row[colConn] || "").trim() : "";

    if (!cardName) continue;

    // Lookup card from catalog
    const cardObj = state.cardCatalog.find(c => c.name.toLowerCase() === cardName.toLowerCase()) || {
      name: cardName,
      type: "component",
      weight: 0,
      cost: 0,
    };

    if (cardObj.type === "chassis") {
      if (!chassis) chassis = cardObj;
      continue;
    }

    if (location.startsWith("spares")) {
      spares.push({
        id: cid,
        card: cardName,
        card_data: cardObj,
        location,
      });
    } else {
      // Chassis location format: chassis:x,y,rot
      let x = 180.0;
      let y = 110.0;
      let rot = 0;

      if (location.includes(":")) {
        const body = location.split(":")[1];
        const sep = body.includes(";") ? ";" : ",";
        const parts = body.split(sep).map(p => p.trim());
        if (parts.length >= 1 && parts[0]) x = parseFloat(parts[0]) || 180.0;
        if (parts.length >= 2 && parts[1]) y = parseFloat(parts[1]) || 110.0;
        if (parts.length >= 3 && parts[2]) rot = parseInt(parts[2], 10) || 0;
      }

      placed.push({
        id: cid,
        card: cardName,
        card_data: cardObj,
        x,
        y,
        rotation: rot,
        connections: connections ? connections.split(";").map(s => s.trim()) : [],
      });
    }
  }

  return {
    chassis: chassis || state.chassisList[0] || null,
    placed_cards: placed,
    spare_cards: spares,
  };
}

function parseCsvLine(text) {
  const result = [];
  let cur = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === '"') {
      if (inQuotes && text[i + 1] === '"') {
        cur += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (ch === "," && !inQuotes) {
      result.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  result.push(cur);
  return result;
}

export function downloadCsvFile(filename, csvContent) {
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export async function fetchServerRobots() {
  try {
    const res = await fetch("/api/robots");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("Failed to fetch saved robots from server:", err);
    return [];
  }
}

export async function saveRobotToServer(filename, csvContent) {
  const cleanName = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  const res = await fetch(`/api/robots/${cleanName}`, {
    method: "POST",
    headers: { "Content-Type": "text/csv; charset=utf-8" },
    body: csvContent,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to save: ${res.status}`);
  }
  return await res.json();
}

export async function loadRobotFromServer(filename) {
  const res = await fetch(`/api/robots/${filename}`);
  if (!res.ok) throw new Error(`Failed to load robot: ${res.status}`);
  const csvText = await res.text();
  return parseCsvToRobot(csvText);
}
