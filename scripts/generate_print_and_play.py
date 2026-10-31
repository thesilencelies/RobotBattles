#!/usr/bin/env python3
"""
generate_print_and_play.py

Master Print and Play (PnP) generator for Robot Battles.
Produces two publication-ready PDF documents:
1. build/robot_battles_pnp_a4.pdf (10 pages A4 Landscape, 1:1 True Scale):
   - Pages 1-6: All 44 Component and Weapon Cards (56x87mm US card size + 2.5mm bleed, 4x2 grid).
   - Page 7: Core Movement Templates (Straight, Spin Disc, Pivot Fan, 50mm scale bar).
   - Page 8: Forward Curves 1 (Medium Curve, Sharp Curve, 50mm scale bar).
   - Page 9: Forward Curves 2 & Weapons (Gentle Curve, Circle, Large Circle, Line, Bar, Prongs, 50mm scale bar).
   - Page 10: Arena Miniatures & Tokens (P1 & P2 Triangle, Square, Wide robots; Spin & Damage tokens, 50mm scale bar).

2. build/robot_battles_pnp_a3.pdf (8 pages A3 Landscape):
   - Pages 1-3: Robot Chassis Mats (Square/Nautiloid, Triangle/Viper, Wide/SSP 2.0).
   - Pages 4-8: Pre-built Automata Sheets (Nightwing, Chonk, Beater, Vyper Flipper, Vyper Spinner).

Usage:
    python scripts/generate_print_and_play.py [--force-rebuild-cards] [--clean]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = REPO_ROOT / "build"
CARD_BUILD_DIR = REPO_ROOT / "cardCreation" / "build"
TEMPLATES_DIR = REPO_ROOT / "movement_templates"
CHASSIS_DIR = REPO_ROOT / "chassisSheets"
AUTOMATA_DIR = REPO_ROOT / "automata"


TEMPLATES_LATEX_SOURCE = r"""\documentclass{article}
\usepackage{tikz}
\usepackage{graphicx}
\usepackage{geometry}
\geometry{a4paper, landscape, margin=0mm}
\pagestyle{empty}
\usetikzlibrary{calc,patterns,arrows.meta}

\definecolor{primaryDark}{HTML}{1A202C}
\definecolor{accentBlue}{HTML}{2B6CB0}
\definecolor{arenaRed}{HTML}{C53030}
\definecolor{amberNote}{HTML}{D69E2E}
\definecolor{boxBorder}{HTML}{CBD5E0}
\definecolor{boxBg}{HTML}{F7FAFC}
\definecolor{textDark}{HTML}{2D3748}

\def\rbTeamBlue{blue}
\def\rbTeamRed{red}
\def\rbTeamGhost{ghost}
\def\rbWeaponBar{bar}
\def\rbWeaponDisc{disc}
\def\rbWeaponForks{forks}
\def\rbTrue{true}

\pgfkeys{
  /rbchassis/.is family, /rbchassis,
  team/.store in = \rbTeam,
  weapon/.store in = \rbWeapon,
  arrow/.store in = \rbArrow,
  center/.store in = \rbCenter,
  blue/.style = {team = blue},
  red/.style = {team = red},
  ghost/.style = {team = ghost},
}

\newcommand{\rbApplyStyle}{%
  \ifx\rbTeam\rbTeamGhost
    \def\rbBodyFill{gray!15}%
    \def\rbBodyDraw{gray!60}%
    \def\rbFadedFill{gray!10}%
    \def\rbFadedDraw{gray!35}%
    \def\rbWheelFill{gray!45}%
    \def\rbWheelDraw{gray!65}%
    \def\rbArrowDraw{gray!60}%
    \def\rbLineWidth{0.9pt}%
    \def\rbLineType{dashed}%
  \else
    \ifx\rbTeam\rbTeamRed
      \def\rbBodyFill{arenaRed!20}%
      \def\rbBodyDraw{arenaRed}%
      \def\rbFadedFill{arenaRed!15}%
      \def\rbFadedDraw{arenaRed!50}%
      \def\rbWheelFill{primaryDark}%
      \def\rbWheelDraw{primaryDark!80!black}%
      \def\rbArrowDraw{green!60!black}%
      \def\rbLineWidth{1.3pt}%
      \def\rbLineType{solid}%
    \else
      \def\rbBodyFill{accentBlue!25}%
      \def\rbBodyDraw{accentBlue}%
      \def\rbFadedFill{accentBlue!15}%
      \def\rbFadedDraw{accentBlue!50}%
      \def\rbWheelFill{primaryDark}%
      \def\rbWheelDraw{primaryDark!80!black}%
      \def\rbArrowDraw{green!60!black}%
      \def\rbLineWidth{1.3pt}%
      \def\rbLineType{solid}%
    \fi
  \fi
}

\newcommand{\chassisSquare}[5][blue]{%
  \begingroup
  \pgfkeys{/rbchassis, team=blue, weapon=none, arrow=true, center=true, #1}%
  \rbApplyStyle
  \begin{scope}[shift={(#2,#3)}, rotate={-(#4)}, scale={(#5)}]
    \fill[\rbWheelFill, draw=\rbWheelDraw, line width=0.4pt] (-0.99, -0.68) rectangle (-0.85, -0.22);
    \fill[\rbWheelFill, draw=\rbWheelDraw, line width=0.4pt] (-0.99,  0.22) rectangle (-0.85,  0.68);
    \fill[\rbWheelFill, draw=\rbWheelDraw, line width=0.4pt] ( 0.85, -0.68) rectangle ( 0.99, -0.22);
    \fill[\rbWheelFill, draw=\rbWheelDraw, line width=0.4pt] ( 0.85,  0.22) rectangle ( 0.99,  0.68);
    \draw[fill=\rbBodyFill, draw=\rbBodyDraw, line width=\rbLineWidth, \rbLineType, rounded corners=2pt]
      (-0.92, -0.92) rectangle (0.92, 0.92);
    \ifx\rbCenter\rbTrue
      \fill[primaryDark] (0, 0) circle [radius=0.08];
    \fi
    \ifx\rbWeapon\rbWeaponBar
      \draw[line width=2.4pt, draw=arenaRed] (-0.75, 0.92) -- (0.75, 0.92);
    \fi
    \ifx\rbWeapon\rbWeaponDisc
      \fill[arenaRed] (0, 0.92) circle [radius=0.14];
    \fi
    \ifx\rbArrow\rbTrue
      \draw[-{Triangle[width=2.4mm,length=3.2mm]}, line width=1.4pt, draw=\rbArrowDraw]
        (0, -0.35) -- (0, 0.65);
    \fi
  \end{scope}%
  \endgroup
}

\newcommand{\chassisWide}[5][blue]{%
  \begingroup
  \pgfkeys{/rbchassis, team=blue, weapon=none, arrow=true, center=true, #1}%
  \rbApplyStyle
  \begin{scope}[shift={(#2,#3)}, rotate={-(#4)}, scale={(#5)}]
    \fill[\rbWheelFill, draw=\rbWheelDraw, line width=0.4pt] (-1.99, -0.30) rectangle (-1.85, 0.30);
    \fill[\rbWheelFill, draw=\rbWheelDraw, line width=0.4pt] ( 1.85, -0.30) rectangle ( 1.99, 0.30);
    \draw[fill=\rbBodyFill, draw=\rbBodyDraw, line width=\rbLineWidth, \rbLineType, rounded corners=2pt]
      (-1.92, -0.42) rectangle (1.92, 0.42);
    \ifx\rbCenter\rbTrue
      \fill[primaryDark] (0, 0) circle [radius=0.08];
    \fi
    \ifx\rbWeapon\rbWeaponDisc
      \fill[arenaRed] (0, 0.42) circle [radius=0.14];
    \fi
    \ifx\rbWeapon\rbWeaponForks
      \draw[line width=2pt, draw=amberNote!90!black] (-1.35, 0.42) -- (-0.65, 0.42);
      \draw[line width=2pt, draw=amberNote!90!black] ( 0.65, 0.42) -- ( 1.35, 0.42);
    \fi
    \ifx\rbWeapon\rbWeaponBar
      \draw[line width=2.4pt, draw=arenaRed] (-1.40, 0.42) -- (1.40, 0.42);
    \fi
    \ifx\rbArrow\rbTrue
      \draw[-{Triangle[width=2.4mm,length=3.2mm]}, line width=1.4pt, draw=\rbArrowDraw]
        (0, -0.25) -- (0, 0.32);
    \fi
  \end{scope}%
  \endgroup
}

\newcommand{\chassisTriangle}[5][blue]{%
  \begingroup
  \pgfkeys{/rbchassis, team=blue, weapon=none, arrow=true, center=true, #1}%
  \rbApplyStyle
  \begin{scope}[shift={(#2,#3)}, rotate={-(#4)}, scale={(#5)}]
    \fill[\rbFadedFill] (-1.5, -1.0) rectangle (1.5, 0.0);
    \fill[\rbFadedFill] (-0.5,  0.0) rectangle (0.5, 1.0);
    \draw[\rbFadedDraw, dashed, line width=0.4pt]
      (-1.5, -1.0) -- (1.5, -1.0) -- (1.5, 0.0) -- (0.5, 0.0) --
      (0.5, 1.0) -- (-0.5, 1.0) -- (-0.5, 0.0) -- (-1.5, 0.0) -- cycle;
    \draw[\rbFadedDraw, dashed, line width=0.3pt] (-0.5, -1.0) -- (-0.5, 0.0);
    \draw[\rbFadedDraw, dashed, line width=0.3pt] ( 0.5, -1.0) -- ( 0.5, 0.0);
    \draw[\rbFadedDraw, dashed, line width=0.3pt] (-0.5,  0.0) -- ( 0.5, 0.0);
    \fill[\rbWheelFill, draw=\rbWheelDraw, line width=0.4pt] (-1.47, -0.80) rectangle (-1.33, -0.20);
    \fill[\rbWheelFill, draw=\rbWheelDraw, line width=0.4pt] ( 1.33, -0.80) rectangle ( 1.47, -0.20);
    \draw[fill=\rbBodyFill, draw=\rbBodyDraw, line width=\rbLineWidth, \rbLineType, line join=round]
      (-1.40, -0.92) -- (1.40, -0.92) -- (1.40, -0.10) -- (0.0, 0.95) -- (-1.40, -0.10) -- cycle;
    \ifx\rbCenter\rbTrue
      \fill[primaryDark] (0, -0.20) circle [radius=0.08];
    \fi
    \ifx\rbWeapon\rbWeaponBar
      \draw[line width=2.4pt, draw=arenaRed] (-0.45, 0.58) -- (0.0, 0.95) -- (0.45, 0.58);
    \fi
    \ifx\rbWeapon\rbWeaponDisc
      \fill[arenaRed] (0, 0.95) circle [radius=0.14];
    \fi
    \ifx\rbArrow\rbTrue
      \draw[-{Triangle[width=2.4mm,length=3.2mm]}, line width=1.4pt, draw=\rbArrowDraw]
        (0, -0.55) -- (0, 0.65);
    \fi
  \end{scope}%
  \endgroup
}

\begin{document}

% ==============================================================================
% PAGE 1 (Overall Page 7): CORE MOVEMENT TEMPLATES
% ==============================================================================
\noindent
\begin{tikzpicture}[x=1mm, y=1mm]
  \useasboundingbox (0, 0) rectangle (297, 210);

  % Header
  \node[anchor=north west] at (15, 202) {\sffamily\bfseries\Large ROBOT BATTLES --- MOVEMENT TEMPLATES (CORE)};
  \node[anchor=north west] at (15, 195) {\sffamily\small 100\% True Scale (Do not scale/shrink when printing). Cut along template outer border.};

  % Scale Bar
  \draw[line width=1.5pt] (225, 200) -- (275, 200);
  \draw[line width=1.0pt] (225, 197) -- (225, 203);
  \draw[line width=1.0pt] (275, 197) -- (275, 203);
  \node[anchor=north] at (250, 197) {\sffamily\scriptsize\bfseries 50 mm SCALE BAR};

  % Straight Template: length 220mm, width 85mm
  \node[anchor=north west, inner sep=0pt] at (15, 188) {\includegraphics[angle=-90, width=220mm]{movement_templates/straight.png}};

  % Spin Disc (bottom left) - 90mm x 90mm
  \node[anchor=south west, inner sep=0pt] at (15, 6) {\includegraphics[width=90mm, height=90mm]{movement_templates/spin.png}};

  % Pivot Fan (bottom right) - 150mm x 85mm
  \node[anchor=south west, inner sep=0pt] at (125, 6) {\includegraphics[width=150mm, height=85mm]{movement_templates/pivot.png}};
\end{tikzpicture}
\newpage

% ==============================================================================
% PAGE 2 (Overall Page 8): FORWARD CURVES 1 (MEDIUM & SHARP)
% ==============================================================================
\noindent
\begin{tikzpicture}[x=1mm, y=1mm]
  \useasboundingbox (0, 0) rectangle (297, 210);

  % Header
  \node[anchor=north west] at (15, 202) {\sffamily\bfseries\Large ROBOT BATTLES --- MOVEMENT TEMPLATES (FORWARD CURVES 1)};
  \node[anchor=north west] at (15, 195) {\sffamily\small 100\% True Scale. Flip face-down for left turns ($R > L$). Align front bumper flush with baseline.};

  % Scale Bar
  \draw[line width=1.5pt] (225, 200) -- (275, 200);
  \draw[line width=1.0pt] (225, 197) -- (225, 203);
  \draw[line width=1.0pt] (275, 197) -- (275, 203);
  \node[anchor=north] at (250, 197) {\sffamily\scriptsize\bfseries 50 mm SCALE BAR};

  % Medium Curve Template: width 159mm, height 150mm
  \node[anchor=south west, inner sep=0pt] at (15, 20) {\includegraphics[width=159mm, height=150mm]{movement_templates/curve_medium.png}};

  % Sharp Curve Template: 195mm x 108mm, rotated 90 deg -> 108mm wide x 195mm high
  \node[anchor=south west, inner sep=0pt] at (182, 5) {\includegraphics[angle=90, width=108mm]{movement_templates/curve_sharp.png}};
\end{tikzpicture}
\newpage

% ==============================================================================
% PAGE 3 (Overall Page 9): FORWARD CURVES 2 & WEAPONS
% ==============================================================================
\noindent
\begin{tikzpicture}[x=1mm, y=1mm]
  \useasboundingbox (0, 0) rectangle (297, 210);

  % Header
  \node[anchor=north west] at (145, 203) {\sffamily\bfseries\Large ROBOT BATTLES --- GENTLE CURVE \& WEAPONS};
  \node[anchor=north west] at (145, 196) {\sffamily\small 100\% True Scale. Cut along borders. Red zones indicate active strikes.};

  % Scale Bar
  \draw[line width=1.5pt] (225, 188) -- (275, 188);
  \draw[line width=1.0pt] (225, 185) -- (225, 191);
  \draw[line width=1.0pt] (275, 185) -- (275, 191);
  \node[anchor=north] at (250, 185) {\sffamily\scriptsize\bfseries 50 mm SCALE BAR};

  % Gentle Curve Template: 144.7mm x 204.7mm
  \node[anchor=south west, inner sep=0pt] at (5, 2) {\includegraphics[width=144.7mm, height=204.7mm]{movement_templates/curve_gentle.png}};

  % WEAPON TEMPLATES SECTION
  \node[anchor=north west] at (145, 178) {\sffamily\bfseries\large WEAPON \& ACTIVE AREA TEMPLATES};

  % 1. Circle Template (Radius 22mm, Diameter 44mm)
  \begin{scope}[shift={(172, 138)}]
    \draw[line width=0.5pt, gray!40, dashed] (-25, -25) rectangle (25, 25);
    \draw[line width=2.5pt, draw=red!80!black, fill=red!10] (0, 0) circle (22mm);
    \draw[fill=black] (0, 0) circle (3.5mm);
    \node[anchor=north] at (0, -25.5) {\sffamily\scriptsize\bfseries Circle (44mm)};
  \end{scope}

  % 2. Large Circle Template (Radius 30mm, Diameter 60mm)
  \begin{scope}[shift={(242, 138)}]
    \draw[line width=0.5pt, gray!40, dashed] (-33, -33) rectangle (33, 33);
    \draw[line width=3.0pt, draw=red!80!black, fill=red!10] (0, 0) circle (30mm);
    \draw[line width=1.2pt, draw=red!80!black, dashed] (0, 0) circle (22mm);
    \draw[fill=black, rounded corners=1.5mm] (-6, -6) rectangle (6, 6);
    \draw[fill=white] (0, 0) circle (1.5mm);
    \node[anchor=north] at (0, -33.5) {\sffamily\scriptsize\bfseries Large Circle (60mm)};
  \end{scope}

  % 3. Bar Template (48mm x 18mm)
  \begin{scope}[shift={(172, 75)}]
    \draw[line width=0.5pt, gray!40, dashed] (-27, -15) rectangle (27, 15);
    \draw[fill=black, draw=black] (-24, -9) rectangle (24, 3);
    \draw[fill=red!80!black, draw=red!90!black, line width=0.8pt] (-24, 3) rectangle (24, 9);
    \node[anchor=north] at (0, -15.5) {\sffamily\scriptsize\bfseries Bar (48$\times$18mm)};
  \end{scope}

  % 4. Line Template (8mm x 32mm)
  \begin{scope}[shift={(210, 75)}]
    \draw[line width=0.5pt, gray!40, dashed] (-8, -20) rectangle (8, 20);
    \draw[fill=black, draw=black] (-4, -16) rectangle (4, -4);
    \draw[fill=red!80!black, draw=red!90!black, line width=0.8pt] (-4, -4) rectangle (4, 16);
    \node[anchor=north] at (0, -20.5) {\sffamily\scriptsize\bfseries Line (8$\times$32mm)};
  \end{scope}

  % 5. Prongs Template (48mm wide, 34mm deep)
  \begin{scope}[shift={(252, 75)}]
    \draw[line width=0.5pt, gray!40, dashed] (-27, -20) rectangle (27, 20);
    \draw[fill=black, draw=black] (-24, -16) rectangle (24, -8);
    \draw[fill=black, draw=black] (-24, -8) rectangle (-12, 4);
    \draw[fill=red!80!black, draw=red!90!black, line width=0.8pt] (-24, 4) rectangle (-12, 16);
    \draw[fill=black, draw=black] (12, -8) rectangle (24, 4);
    \draw[fill=red!80!black, draw=red!90!black, line width=0.8pt] (12, 4) rectangle (24, 16);
    \node[anchor=north] at (0, -20.5) {\sffamily\scriptsize\bfseries Prongs (48$\times$32mm)};
  \end{scope}

  % Notes at bottom
  \node[anchor=south west, text width=145mm] at (145, 8) {
    \sffamily\scriptsize
    \textbf{Usage Instructions:}\\
    $\bullet$ \textbf{Gentle Curve Template:} Use for high-speed mild curves (L3 R2, L4 R3, L5 R4). Flip face-down for left turns.\\
    $\bullet$ \textbf{Weapon Templates:} Attach or place at front/center of robot miniature during combat. When robot contacts opponent, active red zone triggers weapon strike.
  };
\end{tikzpicture}
\newpage

% ==============================================================================
% PAGE 4 (Overall Page 10): ARENA MINIATURES & TOKENS
% ==============================================================================
\noindent
\begin{tikzpicture}[x=1mm, y=1mm]
  \useasboundingbox (0, 0) rectangle (297, 210);

  % Header
  \node[anchor=north west] at (15, 203) {\sffamily\bfseries\Large ROBOT BATTLES --- ARENA MINIATURES \& TOKENS};
  \node[anchor=north west] at (15, 196) {\sffamily\small 100\% True Scale. Cut along dashed boxes. Place on arena grid to execute movement.};

  % Scale Bar
  \draw[line width=1.5pt] (225, 201) -- (275, 201);
  \draw[line width=1.0pt] (225, 198) -- (225, 204);
  \draw[line width=1.0pt] (275, 198) -- (275, 204);
  \node[anchor=north] at (250, 198) {\sffamily\scriptsize\bfseries 50 mm SCALE BAR};

  % Section: Player 1 (Blue)
  \node[anchor=north west] at (15, 186) {\sffamily\bfseries\large PLAYER 1 / TEAM A (BLUE)};

  % P1 Triangle
  \begin{scope}[shift={(55, 145)}]
    \draw[line width=0.5pt, gray!40, dashed] (-33, -25) rectangle (33, 25);
    \chassisTriangle[blue]{0}{0}{0}{20}
    \node[anchor=center, textDark] at (0, -29) {\sffamily\scriptsize\bfseries P1 TRIANGLE};
  \end{scope}

  % P1 Square
  \begin{scope}[shift={(135, 145)}]
    \draw[line width=0.5pt, gray!40, dashed] (-23, -25) rectangle (23, 25);
    \chassisSquare[blue]{0}{0}{0}{20}
    \node[anchor=center, textDark] at (0, -29) {\sffamily\scriptsize\bfseries P1 SQUARE};
  \end{scope}

  % P1 Wide
  \begin{scope}[shift={(225, 145)}]
    \draw[line width=0.5pt, gray!40, dashed] (-43, -15) rectangle (43, 15);
    \chassisWide[blue]{0}{0}{0}{20}
    \node[anchor=center, textDark] at (0, -19) {\sffamily\scriptsize\bfseries P1 WIDE};
  \end{scope}

  % Section: Player 2 / Automaton (Red)
  \node[anchor=north west] at (15, 96) {\sffamily\bfseries\large PLAYER 2 / AUTOMATON (RED)};

  % P2 Triangle
  \begin{scope}[shift={(55, 55)}]
    \draw[line width=0.5pt, gray!40, dashed] (-33, -25) rectangle (33, 25);
    \chassisTriangle[red]{0}{0}{0}{20}
    \node[anchor=center, textDark] at (0, -29) {\sffamily\scriptsize\bfseries P2 TRIANGLE};
  \end{scope}

  % P2 Square
  \begin{scope}[shift={(135, 55)}]
    \draw[line width=0.5pt, gray!40, dashed] (-23, -25) rectangle (23, 25);
    \chassisSquare[red]{0}{0}{0}{20}
    \node[anchor=center, textDark] at (0, -29) {\sffamily\scriptsize\bfseries P2 SQUARE};
  \end{scope}

  % P2 Wide
  \begin{scope}[shift={(225, 78)}]
    \draw[line width=0.5pt, gray!40, dashed] (-43, -15) rectangle (43, 15);
    \chassisWide[red]{0}{0}{0}{20}
    \node[anchor=center, textDark] at (0, -19) {\sffamily\scriptsize\bfseries P2 WIDE};
  \end{scope}

  % Tokens Section (Bottom Right)
  \node[anchor=north west] at (190, 48) {\sffamily\bfseries\small GAME COUNTERS \& TOKENS};

  % Spin counters (4 tokens)
  \foreach \i/\val in {0/1, 1/2, 2/3, 3/4} {
    \begin{scope}[shift={(198 + \i*22, 34)}]
      \draw[fill=yellow!20, draw=orange!90!black, line width=1.2pt] (0, 0) circle (8mm);
      \node[anchor=center] at (0, 1.5) {\sffamily\scriptsize\bfseries SPIN};
      \node[anchor=center] at (0, -3) {\sffamily\bfseries\small +\val};
    \end{scope}
  }

  % Damage tokens (4 tokens)
  \foreach \i/\val in {0/DAM, 1/DAM, 2/DEST, 3/DEST} {
    \begin{scope}[shift={(198 + \i*22, 14)}]
      \ifnum \i < 2
        \draw[fill=orange!25, draw=orange!90!black, line width=1.2pt] (0, 0) circle (8mm);
        \node[anchor=center, orange!90!black] at (0, 0) {\sffamily\tiny\bfseries DAMAGED};
      \else
        \draw[fill=red!25, draw=red!90!black, line width=1.2pt] (0, 0) circle (8mm);
        \node[anchor=center, red!90!black] at (0, 0) {\sffamily\tiny\bfseries DESTROYED};
      \fi
    \end{scope}
  }
\end{tikzpicture}

\end{document}
"""


def check_tool(tool_name: str) -> None:
    if shutil.which(tool_name) is None:
        sys.exit(f"Error: required tool '{tool_name}' is not installed or not in PATH.")


def build_cards_sheet(force: bool = False) -> Path:
    """Builds cardCreation/build/print_sheet_a4.pdf if missing or forced."""
    output_pdf = CARD_BUILD_DIR / "print_sheet_a4.pdf"
    if output_pdf.is_file() and not force:
        return output_pdf

    print("Building A4 card print sheets (56x87mm cards with 2.5mm bleed)...")
    cmd = [
        sys.executable,
        str(REPO_ROOT / "cardCreation" / "generateCards.py"),
    ]
    res = subprocess.run(cmd, cwd=REPO_ROOT / "cardCreation")
    if res.returncode != 0:
        sys.exit(f"Error running generateCards.py (exit code {res.returncode})")

    tex_file = CARD_BUILD_DIR / "print_sheet_a4.tex"
    if not tex_file.is_file():
        # Fall back to generate_card_sheet.py
        cmd = [
            sys.executable,
            str(REPO_ROOT / "cardCreation" / "generate_card_sheet.py"),
            "--csv", str(CARD_BUILD_DIR / "all_cards.csv"),
            "--output", str(tex_file),
            "--cols", "4",
            "--rows", "2",
            "--a4",
        ]
        res = subprocess.run(cmd, cwd=REPO_ROOT / "cardCreation")
        if res.returncode != 0:
            sys.exit("Error generating print_sheet_a4.tex")

    cmd = ["pdflatex", "-interaction=nonstopmode", tex_file.name]
    res = subprocess.run(cmd, cwd=CARD_BUILD_DIR, stdout=subprocess.DEVNULL)
    if res.returncode != 0 or not output_pdf.is_file():
        sys.exit("Error compiling print_sheet_a4.tex to PDF")

    return output_pdf


def build_movement_templates_if_missing() -> None:
    """Ensures movement template PNGs exist."""
    required = ["straight.png", "spin.png", "pivot.png", "curve_gentle.png", "curve_medium.png", "curve_sharp.png"]
    missing = [f for f in required if not (TEMPLATES_DIR / f).is_file()]
    if missing:
        print(f"Missing movement templates ({missing}), generating...")
        cmd = [sys.executable, str(REPO_ROOT / "generate_movement_templates.py")]
        res = subprocess.run(cmd, cwd=REPO_ROOT)
        if res.returncode != 0:
            sys.exit("Error generating movement templates.")


def build_a4_pnp_pdf(output_path: Path, force_cards: bool = False) -> Path:
    """Compiles and merges all cards and templates into A4 PnP PDF."""
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    cards_pdf = build_cards_sheet(force=force_cards)
    build_movement_templates_if_missing()

    # Write and compile template pages (Pages 7-10)
    tpl_tex = BUILD_DIR / "pnp_templates_a4.tex"
    with open(tpl_tex, "w", encoding="utf-8") as fh:
        fh.write(TEMPLATES_LATEX_SOURCE)

    print("Compiling movement & weapon templates, miniatures, and tokens...")
    cmd = [
        "pdflatex",
        "-interaction=nonstopmode",
        f"-output-directory={BUILD_DIR}",
        str(tpl_tex),
    ]
    res = subprocess.run(cmd, cwd=REPO_ROOT, stdout=subprocess.DEVNULL)
    tpl_pdf = BUILD_DIR / "pnp_templates_a4.pdf"
    if res.returncode != 0 or not tpl_pdf.is_file():
        sys.exit("Error compiling pnp_templates_a4.tex to PDF")

    print(f"Merging cards ({cards_pdf.name}) and templates ({tpl_pdf.name}) into {output_path.name}...")
    cmd = [
        "qpdf",
        "--empty",
        "--pages",
        str(cards_pdf),
        str(tpl_pdf),
        "--",
        str(output_path),
    ]
    res = subprocess.run(cmd, cwd=REPO_ROOT)
    if res.returncode != 0 or not output_path.is_file():
        sys.exit(f"Error merging A4 PnP PDF via qpdf (exit code {res.returncode})")

    return output_path


def build_a3_pnp_pdf(output_path: Path) -> Path:
    """Merges all 3 chassis mats and 5 automata sheets into A3 PnP PDF."""
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    # Ensure chassis sheets exist
    chassis_files = [
        CHASSIS_DIR / "viper_wedge_chassis_sheet.pdf",
        CHASSIS_DIR / "nautiloid_drum_chassis_sheet.pdf",
        CHASSIS_DIR / "ssp_20_billet_chassis_sheet.pdf",
    ]
    if any(not f.is_file() for f in chassis_files):
        print("Chassis sheets missing, generating...")
        cmd = [sys.executable, str(REPO_ROOT / "scripts" / "generate_chassis_sheets.py")]
        res = subprocess.run(cmd, cwd=REPO_ROOT)
        if res.returncode != 0:
            sys.exit("Error generating chassis sheets.")

    automata_pdf = AUTOMATA_DIR / "automata_sheets.pdf"
    if not automata_pdf.is_file():
        sys.exit(f"Error: Automata sheets not found at {automata_pdf}")

    print(f"Merging 3 chassis mats and 5 automata sheets into {output_path.name}...")
    cmd = [
        "qpdf",
        "--empty",
        "--pages",
        *[str(f) for f in chassis_files],
        str(automata_pdf),
        "--",
        str(output_path),
    ]
    res = subprocess.run(cmd, cwd=REPO_ROOT)
    if res.returncode != 0 or not output_path.is_file():
        sys.exit(f"Error merging A3 PnP PDF via qpdf (exit code {res.returncode})")

    return output_path


def get_pdf_info(pdf_path: Path) -> dict:
    """Extract page count and file size."""
    size_mb = pdf_path.stat().st_size / (1024 * 1024)
    pages = "?"
    try:
        out = subprocess.check_output(["pdfinfo", str(pdf_path)], text=True)
        for line in out.splitlines():
            if line.startswith("Pages:"):
                pages = line.split(":", 1)[1].strip()
    except Exception:
        pass
    return {"size_mb": size_mb, "pages": pages}


def main():
    parser = argparse.ArgumentParser(
        description="Generate Print and Play PDFs for Robot Battles (A4 Cards & Templates, A3 Chassis & Automata)."
    )
    parser.add_argument(
        "--output-a4",
        type=Path,
        default=BUILD_DIR / "robot_battles_pnp_a4.pdf",
        help="Target path for A4 Print and Play PDF (default: build/robot_battles_pnp_a4.pdf)",
    )
    parser.add_argument(
        "--output-a3",
        type=Path,
        default=BUILD_DIR / "robot_battles_pnp_a3.pdf",
        help="Target path for A3 Print and Play PDF (default: build/robot_battles_pnp_a3.pdf)",
    )
    parser.add_argument(
        "--force-rebuild-cards",
        action="store_true",
        help="Force re-generation and compilation of all 44 card TikZ files",
    )
    args = parser.parse_args()

    check_tool("pdflatex")
    check_tool("qpdf")

    start_time = time.perf_counter()
    print("=" * 80)
    print(" GENERATING PRINT AND PLAY (PnP) PDF PACKAGES")
    print(f" Repository: {REPO_ROOT}")
    print("=" * 80)

    # 1. Build A4 PnP PDF
    a4_pdf = build_a4_pnp_pdf(args.output_a4, force_cards=args.force_rebuild_cards)
    a4_info = get_pdf_info(a4_pdf)

    # 2. Build A3 PnP PDF
    a3_pdf = build_a3_pnp_pdf(args.output_a3)
    a3_info = get_pdf_info(a3_pdf)

    elapsed = time.perf_counter() - start_time
    print("\n" + "=" * 80)
    print(" ✔ PRINT AND PLAY GENERATION COMPLETE")
    print(f" A4 Package: {a4_pdf} ({a4_info['pages']} pages, {a4_info['size_mb']:.2f} MB)")
    print(f" A3 Package: {a3_pdf} ({a3_info['pages']} pages, {a3_info['size_mb']:.2f} MB)")
    print(f" Total time: {elapsed:.2f}s")
    print("=" * 80)


if __name__ == "__main__":
    main()
