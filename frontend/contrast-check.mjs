// Asserts every colour pairing in app/globals.css clears its WCAG floor.
// Run with `node contrast-check.mjs` after touching the palette.
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("./app/globals.css", import.meta.url), "utf8");
const token = (name) => {
  const m = css.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`));
  if (!m) throw new Error(`token --${name} missing from globals.css`);
  return m[1];
};

const lum = (hex) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const f = (c) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};
const ratio = (a, b) => {
  const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m);
  return (x + 0.05) / (y + 0.05);
};

const limestone = token("limestone");
const recessed = token("recessed");
const charcoal = token("charcoal");
const WHITE = "#ffffff";

// 4.5 = WCAG AA body text, 3 = AA non-text contrast for borders/rings that carry meaning.
const cases = [
  ["body text on limestone", charcoal, limestone, 4.5],
  ["body text on recessed surface", charcoal, recessed, 4.5],
  ["muted meta text on limestone", token("ink-muted"), limestone, 4.5],
  ["muted meta text on recessed surface", token("ink-muted"), recessed, 4.5],
  ["disclosure text on limestone", token("oak-ink"), limestone, 4.5],
  ["chip text on recessed surface", token("oak-ink"), recessed, 4.5],

  ["answer label ink", token("ink-answer"), limestone, 4.5],
  ["abstain label ink", token("ink-abstain"), limestone, 4.5],
  ["tool_call label ink", token("ink-tool"), limestone, 4.5],
  ["tool_call label ink on recessed", token("ink-tool"), recessed, 4.5],
  ["clarify label ink", token("ink-clarify"), limestone, 4.5],

  ["answer block edge", token("edge-answer"), limestone, 3],
  ["abstain block edge", token("edge-abstain"), limestone, 3],
  ["tool_call block edge", token("edge-tool"), limestone, 3],
  ["clarify block edge", token("edge-clarify"), limestone, 3],
  ["user block edge", token("edge-user"), limestone, 3],

  ["control borders (input, chips, segments)", token("stone"), limestone, 3],
  // The focus ring has to stay visible on every surface it can land on,
  // including the oak-filled Send button and active segment.
  ["focus ring on limestone", charcoal, limestone, 3],
  ["focus ring on recessed surface", charcoal, recessed, 3],
  ["focus ring on oak fill", charcoal, token("oak"), 3],
  ["focus ring on white input", charcoal, WHITE, 3],

  ["active segment / send label", WHITE, token("oak"), 4.5],
  ["send label on hover", WHITE, token("oak-hover"), 4.5],
  ["tool name on raw gold", charcoal, token("gold"), 4.5],
  ["disabled send label", token("ink-muted"), token("hairline"), 4.5],
];

let failed = 0;
for (const [label, fg, bg, min] of cases) {
  const r = ratio(fg, bg);
  if (r < min) failed++;
  console.log(
    `${r < min ? "FAIL" : "pass"}  ${label.padEnd(42)} ${fg} on ${bg}  ${r.toFixed(2).padStart(5)}:1  (min ${min})`
  );
}

console.log(`\n${cases.length - failed}/${cases.length} pairings pass`);
if (failed) throw new Error(`${failed} contrast check(s) failed`);
