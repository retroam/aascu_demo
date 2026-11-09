import test from 'node:test';
import assert from 'node:assert/strict';
import { tutorialStepForRoute as resolve } from '../web/tutorial_state.js';
const steps = [{route:'evidence'}, {route:'evidence'}, {route:'students'}, {route:'trends',routes:['gaps','models']}, {route:'sources'}, {route:'evidence'}, {route:'reports'}];
test('manual navigation follows the relevant tour step', () => {
  assert.equal(resolve(steps,0,'students'),2);
  assert.equal(resolve(steps,2,'sources'),4);
  assert.equal(resolve(steps,4,'reports'),6);
  assert.equal(resolve(steps,6,'evidence'),0);
  assert.equal(resolve(steps,1,'gaps'),3);
  assert.equal(resolve(steps,1,'models'),3);
});
test('Next and Back retain the requested step until routing finishes', () => {
  assert.equal(resolve(steps,2,'evidence','students'),2);
  assert.equal(resolve(steps,2,'students','students'),2);
  assert.equal(resolve(steps,1,'students','evidence'),1);
  assert.equal(resolve(steps,1,'evidence','evidence'),1);
});
test('re-renders preserve steps sharing a route and a closed tour stays closed', () => {
  assert.equal(resolve(steps,5,'evidence'),5);
  assert.equal(resolve(steps,1,'evidence'),1);
  assert.equal(resolve(steps,null,'students'),null);
  assert.equal(resolve(steps,2,'unknown-page'),2);
});
