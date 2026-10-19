// The photo-quality notes: plain warnings about why a photo may read badly. They never say the photo is good.
//
//   npm run test:logic
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { PhotoQualityNotes } from "../.test-build/entry.js";

const text = (html) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
const render = (props) => renderToStaticMarkup(React.createElement(PhotoQualityNotes, props));
const checked = ["size", "sharpness", "brightness", "contrast"];

test("each warning is listed in plain words, with the reminder that it is only a warning", () => {
  const out = text(render({ quality: { warnings: [
    { code: "blurry", text: "The photo looks blurry or out of focus." }, { code: "too_dark", text: "The photo is dark." },
  ], checked } }));
  assert.match(out, /About the photo/);
  assert.match(out, /blurry or out of focus/);
  assert.match(out, /The photo is dark/);
  assert.match(out, /warning only/);
  assert.match(out, /never guessed/);
});

test("with no warnings it shows nothing, unless asked, and then it never claims the photo is good", () => {
  const quality = { warnings: [], checked };
  assert.equal(render({ quality }), "");
  const out = text(render({ quality, showOk: true }));
  assert.match(out, /size, sharpness, brightness, contrast/);
  assert.match(out, /found no problems/);
  assert.match(out, /does not guarantee every word was read correctly/);
  assert.doesNotMatch(out, /good quality|excellent|perfect/i);
});

test("with no assessment (an unreadable file, a missing photo) it claims nothing", () => {
  for (const quality of [null, undefined]) assert.equal(render({ quality, showOk: true }), "");
});

test("the upload page and the analysis page show it", () => {
  const upload = readFileSync(new URL("../src/pages/UploadPrescription.jsx", import.meta.url), "utf8");
  assert.equal((upload.match(/<PhotoQualityNotes quality=\{result\.image_quality\} \/>/g) || []).length, 2);   // after success and after "too unclear"
  const report = readFileSync(new URL("../src/pages/PrescriptionReport.jsx", import.meta.url), "utf8");
  assert.match(report, /<PhotoQualityNotes quality=\{detail\.image_quality\} showOk \/>/);
});
