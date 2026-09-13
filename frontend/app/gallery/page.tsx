"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

const ITEMS = [
  { id: "01_ember_lantern", name: "Ember Lantern", geometry: "multi-part", theme: "metal / ceremonial", group: "ceremonial" },
  { id: "02_slate_stair", name: "Slate Stair", geometry: "stairs", theme: "stone", group: "build" },
  { id: "03_cedar_slab", name: "Cedar Slab", geometry: "slab", theme: "wood", group: "build" },
  { id: "04_brass_pipe_column", name: "Brass Pipe Column", geometry: "pillar", theme: "mechanical", group: "mechanical" },
  { id: "05_prism_shard_cluster", name: "Prism Shard Cluster", geometry: "multi-part", theme: "crystal", group: "crystal" },
  { id: "06_wispfern_frond", name: "Wispfern Frond", geometry: "plant", theme: "organic", group: "nature" },
  { id: "07_terracotta_idol", name: "Terracotta Idol", geometry: "statue", theme: "ceremonial", group: "ceremonial" },
  { id: "08_sandstone_ruin_cap", name: "Sandstone Ruin Cap", geometry: "ruin", theme: "ancient", group: "build" },
  { id: "09_iron_war_pick", name: "Iron War Pick", geometry: "tool", theme: "metal", group: "tools" },
  { id: "10_honey_loaf", name: "Honey Loaf", geometry: "multi-part", theme: "food", group: "props" },
  { id: "11_cobalt_frost_brick", name: "Cobalt Frost Brick", geometry: "cube", theme: "ice / stone", group: "build" },
  { id: "12_glowcap_mushroom", name: "Glowcap Mushroom", geometry: "multi-part", theme: "organic", group: "nature" },
  { id: "13_copper_pressure_valve", name: "Copper Pressure Valve", geometry: "multi-part", theme: "mechanical", group: "mechanical" },
  { id: "14_obsidian_reliquary", name: "Obsidian Reliquary", geometry: "chest", theme: "ceremonial / dark", group: "ceremonial" },
  { id: "15_amethyst_bud_cluster", name: "Amethyst Bud Cluster", geometry: "multi-part", theme: "crystal", group: "crystal" },
] as const;

const FILTERS = [
  { id: "all", label: "All" },
  { id: "build", label: "Build" },
  { id: "mechanical", label: "Mechanical" },
  { id: "crystal", label: "Crystal" },
  { id: "nature", label: "Nature" },
  { id: "ceremonial", label: "Ceremonial" },
  { id: "tools", label: "Tools" },
  { id: "props", label: "Props" },
] as const;

type FilterId = (typeof FILTERS)[number]["id"];

export default function GalleryPage() {
  const [filter, setFilter] = useState<FilterId>("all");

  const visible = useMemo(
    () => (filter === "all" ? ITEMS : ITEMS.filter((item) => item.group === filter)),
    [filter],
  );

  return (
    <main className="gallery-page">
      <div className="gallery-top">
        <Link className="gallery-back" href="/">
          ← Support Assistant
        </Link>
        <div className="gallery-brand">
          <div className="brand-mark" aria-hidden="true" />
          <div>
            <p className="gallery-eyebrow">BlockForge · style pack</p>
            <h1>Asset gallery</h1>
          </div>
        </div>
        <p className="gallery-lede">
          Fifteen Java-format models in <span className="mono">assets/gallery/</span>. Part 4
          graded asset is <span className="mono">01_ember_lantern</span>. Use the filters to jump
          by mood — each tile shows the isometric preview plus geometry notes.
        </p>

        <div className="gallery-filters" role="tablist" aria-label="Filter assets">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              role="tab"
              aria-selected={filter === f.id}
              className={filter === f.id ? "gallery-filter is-active" : "gallery-filter"}
              onClick={() => setFilter(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>

        <p className="gallery-count" aria-live="polite">
          Showing <strong>{visible.length}</strong> of {ITEMS.length}
        </p>
      </div>

      <ul className="gallery-grid">
        {visible.map((item, i) => (
          <li key={item.id} className="gallery-item" style={{ animationDelay: `${Math.min(i, 8) * 30}ms` }}>
            <figure className="gallery-figure">
              <div className="gallery-stage">
                <img
                  src={`/gallery/${item.id}/preview.png`}
                  alt=""
                  width={420}
                  height={460}
                />
              </div>
              <figcaption>
                <span className="gallery-index mono">{item.id.slice(0, 2)}</span>
                <h2>{item.name}</h2>
                <p>
                  <span>{item.geometry}</span>
                  <span className="gallery-dot" aria-hidden="true">
                    ·
                  </span>
                  <span>{item.theme}</span>
                </p>
              </figcaption>
            </figure>
          </li>
        ))}
      </ul>

      {visible.length === 0 && (
        <p className="gallery-empty">Nothing in this filter — try All.</p>
      )}

      <footer className="gallery-foot">
        <p>
          Part 4 graded asset: <span className="mono">assets/gallery/01_ember_lantern/</span>.
          Rebuild pack: <span className="mono">python assets/gallery/build_gallery.py</span>.
        </p>
      </footer>
    </main>
  );
}
