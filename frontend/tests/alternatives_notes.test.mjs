// The alternatives' notes: how they were chosen, what is not compared, that safety carries over, and the information-only banner for
// a line that is not settled. Rendered as the server sent them.
//
//   npm run test:logic
import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AlternativesNotes, CONFIDENCE_EXPLANATION } from "../.test-build/entry.js";

const text = (html) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
const notes = (over = {}) => ({
  matched: ["the same active ingredients, each at the same strength", "the same dosage form"],
  not_compared: ["inactive ingredients", "the manufacturer's quality"],
  safety: "The active ingredients are the same, so its checks apply unchanged.",
  ask_first: "Do not change a prescribed medicine on your own: ask your doctor or pharmacist first.",
  information_only: null, ...over,
});
const render = (n) => text(renderToStaticMarkup(React.createElement(AlternativesNotes, { notes: n })));

test("it shows what was matched, what is not compared, and to ask first", () => {
  const out = render(notes());
  for (const needle of ["How these were chosen", "same active ingredients", "Not compared", "inactive ingredients", "ask your doctor or pharmacist first", "checks apply unchanged"]) assert.ok(out.includes(needle), needle);
  assert.ok(!out.includes("information only"));
});

test("a line that is not settled says its alternatives are for information only", () => {
  const out = render(notes({ information_only: "This line is not settled yet, so these alternatives are shown for information only and no saving is counted for it." }));
  assert.match(out, /shown for information only and no saving is counted/);
});

test("with no notes it renders nothing", () => {
  assert.equal(renderToStaticMarkup(React.createElement(AlternativesNotes, { notes: null })), "");
});

test("the confidence percentage is explained as similarity, not as a probability of being right", () => {
  assert.match(CONFIDENCE_EXPLANATION, /resembles this product/);
  assert.match(CONFIDENCE_EXPLANATION, /not the chance that the match is right/);
});
