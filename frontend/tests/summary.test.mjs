// The on-request summary: nothing is written or sent until asked, and the label always says who wrote it.
//
//   npm run test:logic
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ReportSummary, SummaryView } from "../.test-build/entry.js";

const text = (html) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

test("before it is asked for, it offers a button and states what is used and what is not", () => {
  const html = renderToStaticMarkup(React.createElement(ReportSummary, { prescriptionId: 5 }));
  const out = text(html);
  assert.match(out, /Write a plain-language summary/);
  assert.match(out, /Uses Google Gemini when it is set up on this server, otherwise PharmaCompare writes it/);
  assert.match(out, /never your name, the photo or the original text/);
  assert.doesNotMatch(out, /Written by/);              // nothing has been generated yet
});

test("the summary is shown as written, with the label of who wrote it", () => {
  const gemini = text(renderToStaticMarkup(React.createElement(SummaryView, { summary: { text: "4 lines were read.", label: "Written by Google Gemini from the figures in this report (medicine names, strengths, schedules and counts only). It can be wrong: check it against the report." } })));
  assert.match(gemini, /4 lines were read\./);
  assert.match(gemini, /Written by Google Gemini/);
  assert.match(gemini, /It can be wrong: check it against the report/);
  const local = text(renderToStaticMarkup(React.createElement(SummaryView, { summary: { text: "4 lines were read.", label: "Written by PharmaCompare from the figures in this report." } })));
  assert.match(local, /Written by PharmaCompare/);
});

test("it is requested only by the button, and the report page shows it", () => {
  const source = readFileSync(new URL("../src/components/results/ReportSummary.jsx", import.meta.url), "utf8");
  assert.equal((source.match(/getReportSummary\(/g) || []).length, 1);          // called from write() only
  assert.doesNotMatch(source, /useEffect/);                                    // never automatically
  const page = readFileSync(new URL("../src/pages/PrescriptionReport.jsx", import.meta.url), "utf8");
  assert.match(page, /<ReportSummary prescriptionId=\{prescriptionId\} \/>/);
});
