// Pure MJML -> HTML compilation. No side effects, so tests can import it directly.

import mjml2html from 'mjml';

export function render(mjmlSource, { validationLevel = 'soft', minify = false } = {}) {
  const { html, errors } = mjml2html(mjmlSource, { validationLevel, minify });
  return {
    html,
    errors: errors.map(({ line, message, tagName }) => ({ line, message, tagName })),
  };
}
