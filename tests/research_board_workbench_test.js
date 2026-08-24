const assert = require("node:assert/strict");
const test = require("node:test");

const workbench = require("../workbench/app.js");

test("the research board projects question, evidence stages, and uncertainty from shared state", () => {
  const view = workbench.workspaceView(workbench.createDemoState());

  assert.equal(view.research.question, view.work.goal);
  assert.deepEqual(
    view.research.stages.map((stage) => stage.id),
    ["scope", "evidence", "outline", "final"],
  );
  assert.deepEqual(
    view.research.stages.map((stage) => stage.evidenceStatus),
    ["WAITING", "WAITING", "WAITING", "WAITING"],
  );
  assert.equal(view.research.accepted, 0);
  assert.equal(view.research.total, 4);
});

test("research evidence status follows execution without owning a second state", () => {
  let state = workbench.approvePlan(workbench.createDemoState());
  state = workbench.recordDecision(state, "scope", "APPROVED");
  state = workbench.applyTaskAction(state, "scope");

  let view = workbench.workspaceView(state);
  assert.equal(view.research.stages[0].evidenceStatus, "COLLECTING");
  assert.equal(view.work.tasks.scope.status, "IN_PROGRESS");

  state = workbench.applyTaskAction(state, "scope");
  view = workbench.workspaceView(state);
  assert.equal(view.research.stages[0].evidenceStatus, "UNDER_REVIEW");

  state = workbench.applyTaskAction(state, "scope");
  view = workbench.workspaceView(state);
  assert.equal(view.research.stages[0].evidenceStatus, "ACCEPTED");
  assert.equal(view.research.accepted, 1);
});

test("research cards escape project content and expose evidence meaning", () => {
  assert.equal(typeof workbench.renderResearchCard, "function");
  const html = workbench.renderResearchCard({
    id: "evidence",
    title: "<img src=x onerror=alert(1)>",
    purpose: "来源与主张逐项对应",
    evidenceStatus: "COLLECTING",
    taskStatus: "IN_PROGRESS",
    acceptance: "证据可追溯",
  });

  assert.ok(html.includes("证据收集中"));
  assert.ok(html.includes("来源与主张逐项对应"));
  assert.ok(html.includes("&lt;img src=x onerror=alert(1)&gt;"));
  assert.ok(!html.includes("<img"));
});

test("small screens place the active board directly after the board switcher", () => {
  assert.equal(typeof workbench.scrollActiveBoardIntoView, "function");
  const calls = [];
  const panel = {
    dataset: { panel: "research" },
    scrollIntoView(options) { calls.push(options); },
  };
  const doc = {
    defaultView: {
      matchMedia(query) {
        return { matches: query === "(max-width: 980px)" };
      },
    },
    querySelectorAll() { return [panel]; },
  };

  assert.equal(workbench.scrollActiveBoardIntoView(doc, "research"), true);
  assert.deepEqual(calls, [{ behavior: "smooth", block: "start" }]);
});
