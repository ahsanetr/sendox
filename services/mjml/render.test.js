import assert from 'node:assert/strict';
import { test } from 'node:test';

import { render } from './render.js';

const VALID = `<mjml>
  <mj-body>
    <mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section>
  </mj-body>
</mjml>`;

test('compiles valid MJML to a full HTML document', () => {
  const { html, errors } = render(VALID);
  assert.deepEqual(errors, []);
  assert.match(html, /<!doctype html>/i);
  assert.match(html, /Hi/);
});

test('mj-text outside mj-column is reported, not thrown', () => {
  // MJML requires mj-text inside mj-column inside mj-section. Soft validation
  // reports that instead of raising, which is what the API relies on.
  const { errors } = render('<mjml><mj-body><mj-text>Hi</mj-text></mj-body></mjml>');
  assert.equal(errors.length, 1);
  assert.match(errors[0].message, /mj-text/);
  assert.equal(errors[0].tagName, 'mj-text');
});

test('minify shrinks the output', () => {
  const plain = render(VALID).html;
  const minified = render(VALID, { minify: true }).html;
  assert.ok(minified.length < plain.length);
});
