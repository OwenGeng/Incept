"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { PlayableSchema } from "@/lib/gaming-playable";

type PhaserGameInstance = { destroy: (removeCanvas: boolean, noReturn?: boolean) => void };

type Props = {
  schema: PlayableSchema;
};

const BOARD_COLUMNS = 5;
const BOARD_ROWS = 6;
const BOARD_CELLS = BOARD_COLUMNS * BOARD_ROWS;

function titleForValue(value: number) {
  return value >= 16 ? "Bloom" : value >= 8 ? "Bud" : value >= 4 ? "Sprout" : "Seed";
}

/**
 * A real Phaser scene used by the Studio preview. It deliberately creates its
 * visual pieces with Phaser Graphics instead of its Loader, so the prototype
 * has no external asset dependency. The exported runtime will reuse this
 * scene contract after the no-XHR Phaser build passes validation.
 */
export function PhaserMergePreview({ schema }: Props) {
  const reactId = useId().replace(/:/g, "");
  const mountId = `phaser-merge-${reactId}`;
  const gameRef = useRef<PhaserGameInstance | null>(null);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;

    setRuntimeError(null);
    void import("phaser").then((module) => {
      if (disposed) return;
      // The Phaser package is CommonJS-compatible. Next can expose it either
      // as the module namespace or under `default`, depending on the client
      // chunk format, so support both without changing its public API.
      const compatibleModule = module as unknown as { default?: typeof import("phaser") };
      const Phaser: typeof import("phaser") = compatibleModule.default ?? module;

      const width = schema.metadata.orientation === "portrait" ? 405 : 720;
      const height = schema.metadata.orientation === "portrait" ? 720 : 405;
      const accent = schema.gameplay.accentColor || "#138a72";
      const target = Math.max(4, Math.min(64, Math.round(schema.gameplay.targetValue || 16)));
      const instruction = schema.gameplay.tutorialText || "Tap two identical pieces to merge them";
      const colors = [0xf9d66c, 0x9fe080, 0x5ecb9a, 0x5aa7e5, 0x8a68db, 0xe7699a];
      const values = Array.from({ length: BOARD_CELLS }, (_, index) => (index % 5 < 2 ? 2 : index % 5 < 4 ? 4 : 8));

      class MergeScene extends Phaser.Scene {
        private selectedIndex: number | null = null;
        private tiles: Array<{ value: number; container: Phaser.GameObjects.Container } | null> = [];
        private moves = 0;
        private level = 1;
        private blooms = 0;
        private movesLabel!: Phaser.GameObjects.Text;
        private levelLabel!: Phaser.GameObjects.Text;
        private objectiveLabel!: Phaser.GameObjects.Text;
        private feedbackLabel!: Phaser.GameObjects.Text;
        private boardOriginX = 0;
        private boardOriginY = 0;
        private cellSize = 0;

        create() {
          const background = this.add.graphics();
          background.fillGradientStyle(0x103f37, 0x103f37, 0x4ba875, 0xa7d66d, 1);
          background.fillRect(0, 0, width, height);
          background.fillStyle(0xffffff, 0.08);
          for (let index = 0; index < 32; index += 1) {
            background.fillCircle((index * 79) % width, (index * 137) % height, 8 + (index % 5) * 7);
          }

          const safePadding = 22;
          this.add.text(safePadding, 20, schema.metadata.title || "Garden Merge", {
            fontFamily: "Arial, sans-serif", fontSize: "24px", fontStyle: "700", color: "#ffffff",
          });
          this.levelLabel = this.add.text(width - safePadding, 23, "Level 1", {
            fontFamily: "Arial, sans-serif", fontSize: "15px", fontStyle: "700", color: "#16463b",
            backgroundColor: "#ffffff", padding: { x: 10, y: 7 },
          }).setOrigin(1, 0);
          this.movesLabel = this.add.text(safePadding, 60, "0 moves", {
            fontFamily: "Arial, sans-serif", fontSize: "14px", color: "#e7fff2",
          });
          this.objectiveLabel = this.add.text(width - safePadding, 60, `Grow ${titleForValue(target)} × 0 / 3`, {
            fontFamily: "Arial, sans-serif", fontSize: "14px", color: "#e7fff2",
          }).setOrigin(1, 0);
          this.add.text(width / 2, 98, instruction, {
            fontFamily: "Arial, sans-serif", fontSize: "15px", fontStyle: "700", color: "#17463a",
            backgroundColor: "#ffffffdf", padding: { x: 14, y: 10 }, align: "center",
            wordWrap: { width: width - 50, useAdvancedWrap: true },
          }).setOrigin(0.5, 0);

          this.cellSize = Math.floor(Math.min((width - 40) / BOARD_COLUMNS, (height - 245) / BOARD_ROWS));
          const boardWidth = BOARD_COLUMNS * this.cellSize;
          const boardHeight = BOARD_ROWS * this.cellSize;
          this.boardOriginX = (width - boardWidth) / 2;
          this.boardOriginY = 146 + Math.max(0, (height - 245 - boardHeight) / 2);
          this.add.rectangle(width / 2, this.boardOriginY + boardHeight / 2, boardWidth + 12, boardHeight + 12, 0x0a3028, 0.72).setStrokeStyle(2, 0xffffff, 0.24);

          this.feedbackLabel = this.add.text(width / 2, height - 97, "Find two matching garden pieces.", {
            fontFamily: "Arial, sans-serif", fontSize: "14px", fontStyle: "700", color: "#ffffff", align: "center",
          }).setOrigin(0.5, 0.5);
          const cta = this.add.rectangle(width / 2, height - 50, Math.min(width - 44, 300), 48, Phaser.Display.Color.HexStringToColor(accent).color, 1)
            .setStrokeStyle(2, 0xffffff, 0.45)
            .setInteractive({ useHandCursor: true });
          this.add.text(width / 2, height - 50, schema.metadata.ctaLabel || "Play now", {
            fontFamily: "Arial, sans-serif", fontSize: "18px", fontStyle: "700", color: "#ffffff",
          }).setOrigin(0.5);
          cta.on("pointerup", () => {
            const bridge = window as Window & { FbPlayableAd?: { onCTAClick: () => void } };
            bridge.FbPlayableAd?.onCTAClick();
            this.showFeedback("CTA clicked — the delivery build will hand off to the app store.");
          });

          this.seedBoard();
        }

        private seedBoard() {
          this.tiles.forEach((tile) => tile?.container.destroy());
          this.tiles = values.map((value, index) => {
            const jitter = (this.level + index * 7) % 5;
            return this.createTile(index, jitter === 4 ? 8 : value);
          });
        }

        private createTile(index: number, value: number) {
          const column = index % BOARD_COLUMNS;
          const row = Math.floor(index / BOARD_COLUMNS);
          const x = this.boardOriginX + column * this.cellSize + this.cellSize / 2;
          const y = this.boardOriginY + row * this.cellSize + this.cellSize / 2;
          const color = colors[Math.min(colors.length - 1, Math.max(0, Math.log2(value) - 1))];
          const tile = this.add.container(x, y);
          const shadow = this.add.rectangle(3, 6, this.cellSize - 10, this.cellSize - 10, 0x06251e, 0.28);
          const card = this.add.rectangle(0, 0, this.cellSize - 10, this.cellSize - 10, color, 1).setStrokeStyle(2, 0xffffff, 0.5).setInteractive({ useHandCursor: true });
          const icon = this.add.text(0, -7, value >= 16 ? "✿" : value >= 8 ? "✦" : value >= 4 ? "◆" : "●", {
            fontFamily: "Arial, sans-serif", fontSize: `${Math.max(20, Math.round(this.cellSize * 0.29))}px`, color: "#ffffff", fontStyle: "700",
          }).setOrigin(0.5);
          const label = this.add.text(0, this.cellSize * 0.25, String(value), {
            fontFamily: "Arial, sans-serif", fontSize: `${Math.max(12, Math.round(this.cellSize * 0.15))}px`, color: "#17463a", fontStyle: "700",
          }).setOrigin(0.5);
          tile.add([shadow, card, icon, label]);
          card.on("pointerup", () => this.selectTile(index));
          return { value, container: tile };
        }

        private selectTile(index: number) {
          const candidate = this.tiles[index];
          if (!candidate) return;
          if (this.selectedIndex === null) {
            this.selectedIndex = index;
            candidate.container.setScale(1.08);
            this.showFeedback("Now choose another matching piece.");
            return;
          }
          const selected = this.tiles[this.selectedIndex];
          if (!selected) {
            this.selectedIndex = null;
            return;
          }
          if (this.selectedIndex === index) {
            selected.container.setScale(1);
            this.selectedIndex = null;
            return;
          }
          this.moves += 1;
          this.movesLabel.setText(`${this.moves} moves`);
          if (selected.value !== candidate.value) {
            selected.container.setScale(1);
            candidate.container.setScale(1.08);
            this.selectedIndex = index;
            this.showFeedback("Those pieces differ. Pick an identical value.");
            return;
          }
          const nextValue = Math.min(64, selected.value * 2);
          const destination = index;
          selected.container.destroy();
          candidate.container.destroy();
          this.tiles[this.selectedIndex] = null;
          this.tiles[destination] = this.createTile(destination, nextValue);
          this.selectedIndex = null;
          this.tweens.add({ targets: this.tiles[destination]?.container, scale: 1.18, duration: 140, yoyo: true, ease: "Back.Out" });
          this.addNewSeed();
          if (nextValue >= target) {
            this.blooms += 1;
            this.objectiveLabel.setText(`Grow ${titleForValue(target)} × ${this.blooms} / 3`);
            this.showFeedback(`${titleForValue(nextValue)} unlocked! Keep building your garden.`);
            if (this.blooms >= 3) this.advanceLevel();
          } else {
            this.showFeedback(`${nextValue} created. Merge again to grow it further.`);
          }
        }

        private addNewSeed() {
          const empty = this.tiles.findIndex((tile) => tile === null);
          if (empty < 0) return;
          this.tiles[empty] = this.createTile(empty, this.moves % 4 === 0 ? 4 : 2);
          this.tiles[empty]?.container.setScale(0.55);
          this.tweens.add({ targets: this.tiles[empty]?.container, scale: 1, duration: 220, ease: "Back.Out" });
        }

        private advanceLevel() {
          this.level += 1;
          this.blooms = 0;
          this.levelLabel.setText(`Level ${this.level}`);
          this.objectiveLabel.setText(`Grow ${titleForValue(target)} × 0 / 3`);
          this.showFeedback(`Level ${this.level} unlocked. The loop can continue for a long-form session.`);
          this.time.delayedCall(550, () => this.seedBoard());
        }

        private showFeedback(message: string) {
          this.feedbackLabel.setText(message);
        }
      }

      gameRef.current = new Phaser.Game({
        type: Phaser.AUTO,
        parent: mountId,
        width,
        height,
        backgroundColor: "#103f37",
        scene: MergeScene,
        scale: { mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_BOTH },
        render: { antialias: true, pixelArt: false },
      });
    }).catch((error: unknown) => {
      if (!disposed) setRuntimeError(error instanceof Error ? error.message : "Phaser could not initialize.");
    });

    return () => {
      disposed = true;
      gameRef.current?.destroy(true);
      gameRef.current = null;
    };
  }, [mountId, schema]);

  if (runtimeError) {
    return <div className="flex size-full items-center justify-center bg-slate-950 p-6 text-center text-sm font-medium text-white">Phaser preview failed to initialize: {runtimeError}</div>;
  }
  return <div id={mountId} className="size-full [&_canvas]:!h-full [&_canvas]:!w-full" />;
}
