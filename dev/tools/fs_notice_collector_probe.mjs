#!/usr/bin/env node
// Zero-quota stub-DOM probe for the Feature Studio notice collector.
//
// The collector is a string handed to Playwright, so a Python test can only
// prove that the string is passed through. This probe runs the *exact* string
// against a minimal DOM stub and reports what the collector returns, which is
// how the all-messages and severity rules are regression-tested without a
// browser, a page, or any Onshape quota.
//
// Usage: node fs_notice_collector_probe.mjs <input.json>
//   input.json: {"js": "<collector source>", "selectors": {...}, "scenario": name}
// Prints {"scenario": ..., "result": ...} on success,
//        {"scenario": ..., "error": ...} on failure. Always exits 0 so the
// caller can assert on the parsed payload.

import { readFileSync } from "node:fs";

class El {
  constructor(tag, classes = [], text = "") {
    this.tag = tag;
    this.classes = new Set(classes);
    this.ownText = text;
    this.children = [];
    this.style = { display: "block", visibility: "visible" };
    this.rect = { width: 120, height: 18 };
  }

  get className() {
    return [...this.classes].join(" ");
  }

  get textContent() {
    return [this.ownText, ...this.children.map((child) => child.textContent)]
      .filter((part) => part !== "")
      .join(" ");
  }

  get innerText() {
    return this.textContent;
  }

  add(child) {
    this.children.push(child);
    return this;
  }

  addAll(...children) {
    for (const child of children) this.add(child);
    return this;
  }

  descendants() {
    return this.children.flatMap((child) => [child, ...child.descendants()]);
  }

  matches(selector) {
    for (const part of selector.split(/(?=[.#])/)) {
      if (part.startsWith(".")) {
        if (!this.classes.has(part.slice(1))) return false;
      } else if (part && this.tag !== part) {
        return false;
      }
    }
    return true;
  }

  querySelectorAll(selector) {
    return this.descendants().filter((el) => el.matches(selector));
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] ?? null;
  }

  getBoundingClientRect() {
    return this.rect;
  }
}

function section(tag, classes, text) {
  return new El(tag, classes, text);
}

// One notice table: the message paragraphs, the line/column cells, and the
// severity class that Onshape puts on the table itself.
function noticeTable(messages, { line = "9", column = "44", severity = "warning", classes = [] } = {}) {
  const table = section("div", ["feature-script-notice-table", ...classes]);
  for (const message of messages) table.add(section("div", ["notice-location-message"], message));
  if (line !== null) table.add(section("span", ["notice-location-line-number"], line));
  if (column !== null) table.add(section("span", ["notice-location-column-number"], column));
  if (severity === "error") table.add(section("span", ["fs-notice-error"], ""));
  if (severity === "info") table.add(section("span", ["fs-notice-info"], ""));
  if (severity === "warning") table.add(section("span", ["fs-notice-warning"], ""));
  return table;
}

function noticePane({ tabName = "Feature Studio 1", tables = [], outOfDate = false } = {}) {
  const container = section("div", ["element-notice-set-container"]);
  container.add(section("div", ["element-notice-title"], tabName));
  if (outOfDate) container.add(section("div", ["notices-out-of-date"], "out of date"));
  container.addAll(...tables);
  return container;
}

function scenario(name) {
  const root = section("body");
  const document = {
    querySelector: (selector) => root.querySelector(selector),
    querySelectorAll: (selector) => root.querySelectorAll(selector),
  };
  const window = {
    getComputedStyle: (el) => el.style,
  };

  switch (name) {
    case "empty-surface":
      break;
    case "indicator-present-pane-closed": {
      root.add(section("button", ["notice-pane-toggle-button"]));
      break;
    }
    case "pane-open-multi-message": {
      root.add(section("button", ["notice-pane-toggle-button"]).add(
        section("span", ["flyout-toggle-button", "os-expanded"])
      ));
      const content = section("div", ["notices-content"]);
      content.add(noticePane({
        tables: [noticeTable(
          ["definition.outerDiameter: Expected bounds to be a map", "definition.outerDiameter: Expected a range"],
          { severity: "error" }
        )],
      }));
      root.add(content);
      break;
    }
    case "severity-and-location-variants": {
      const content = section("div", ["notices-content"]);
      content.add(noticePane({
        tables: [
          noticeTable(["hard failure"], { severity: "error", line: "3", column: "7" }),
          noticeTable(["informational note"], { severity: "info", line: "4", column: "2" }),
          noticeTable(["unknown severity"], { line: "5", column: "1" }),
          noticeTable(["no numeric location"], { line: "not-a-number", column: null }),
        ],
      }));
      root.add(content);
      break;
    }
    case "inactive-tab-skipped": {
      const content = section("div", ["notices-content"]);
      content.add(noticePane({ tabName: "Feature Studio 2", tables: [noticeTable(["other tab"])] }));
      content.add(noticePane({ tabName: "Feature Studio 1", tables: [noticeTable(["active tab"])] }));
      root.add(content);
      root.add(section("div", ["os-tab-bar-tab", "active"]).add(
        section("span", ["os-tab-name"], "Feature Studio 1")
      ));
      break;
    }
    case "out-of-date-container-skipped": {
      const content = section("div", ["notices-content"]);
      content.add(noticePane({ tables: [noticeTable(["stale result"])], outOfDate: true }));
      content.add(noticePane({ tables: [noticeTable(["fresh result"])] }));
      root.add(content);
      break;
    }
    case "message-less-table-skipped": {
      const content = section("div", ["notices-content"]);
      content.add(noticePane({ tables: [noticeTable([], { line: "1", column: "1" })] }));
      root.add(content);
      break;
    }
    case "invisible-toggle": {
      const toggle = section("button", ["notice-pane-toggle-button"]);
      toggle.style = { display: "none", visibility: "visible" };
      root.add(toggle);
      break;
    }
    default:
      return { error: `unknown scenario: ${name}` };
  }

  return { root, document, window };
}

const [inputPath] = process.argv.slice(2);
if (!inputPath) {
  console.log(JSON.stringify({ error: "usage: fs_notice_collector_probe.mjs <input.json>" }));
  process.exit(0);
}

const input = JSON.parse(readFileSync(inputPath, "utf8"));
const built = scenario(input.scenario);
if (built.error) {
  console.log(JSON.stringify({ scenario: input.scenario, error: built.error }));
  process.exit(0);
}

globalThis.document = built.document;
globalThis.window = built.window;

try {
  // The collector is authored as an arrow expression, exactly as Playwright
  // receives it, so it is evaluated rather than imported.
  const collector = new Function(`return (${input.js});`)();
  const result = collector(input.selectors);
  console.log(JSON.stringify({ scenario: input.scenario, result }));
} catch (error) {
  console.log(JSON.stringify({
    scenario: input.scenario,
    error: `${error && error.name ? error.name : "Error"}: ${error && error.message}`,
  }));
}
