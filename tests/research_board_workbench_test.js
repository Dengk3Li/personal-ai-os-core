const assert = require("node:assert/strict");
const test = require("node:test");

const workbench = require("../workbench/app.js");

test("research is a dynamic business line inside work progress", () => {
  const state = workbench.createDemoState();
  const view = workbench.workspaceView(state);

  assert.deepEqual(view.boards.map((board) => board.id), ["global", "work", "decision"]);
  assert.ok(!view.boards.some((board) => board.id === "research"));
  assert.deepEqual(view.work.lines.map((line) => line.line_id), ["research", "product", "writing"]);
  assert.equal(view.work.activeLine.line_id, "research");
  assert.equal(view.work.activeLine.layout, "loop");
});

test("each business line can choose a layout without creating another state source", () => {
  let state = workbench.createDemoState();
  state = workbench.selectBusinessLine(state, "product");
  let view = workbench.workspaceView(state);
  assert.equal(view.work.activeLine.layout, "milestones");
  assert.equal(view.work.activeLine.tasks[0].status, state.taskStates[view.work.activeLine.tasks[0].task_id]);

  state = workbench.selectBusinessLine(state, "writing");
  view = workbench.workspaceView(state);
  assert.equal(view.work.activeLine.layout, "pipeline");
  assert.equal(workbench.selectBusinessLine(state, "unknown").activeLineId, "writing");
});

test("the research line declares the five-agent workflow boundary", () => {
  const research = workbench.workspaceView(workbench.createDemoState()).work.lines[0];
  assert.equal(research.traceStatus, "PRESET_READY");
  assert.match(research.note, /科学假设/);
  assert.match(research.note, /反馈优化/);
});
