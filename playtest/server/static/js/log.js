/**
 * Combat Log Renderer
 */

export class CombatLogRenderer {
  static renderLog(container, logEntries) {
    if (!container) return;

    if (!logEntries || logEntries.length === 0) {
      container.innerHTML = `<div class="empty-log">No combat events recorded yet. Plan your turn to begin!</div>`;
      return;
    }

    const html = logEntries.map(entry => {
      let icon = "📝";
      if (entry.phase === "planning") icon = "🧭";
      else if (entry.phase === "movement") icon = "🏎️";
      else if (entry.phase === "collision") icon = "💥";
      else if (entry.phase === "cleanup") icon = "🔧";
      else if (entry.phase === "game_over") icon = "🏆";

      return `
        <div class="log-entry phase-${entry.phase}">
          <div class="log-meta">
            <span class="log-round">R${entry.round}</span>
            <span class="log-icon">${icon}</span>
            <span class="log-phase">${entry.phase.toUpperCase()}</span>
          </div>
          <div class="log-msg">${this._escapeHtml(entry.message)}</div>
        </div>
      `;
    }).reverse().join("");

    container.innerHTML = html;
  }

  static _escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }
}
