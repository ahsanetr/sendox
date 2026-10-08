// MJML render sidecar.
//
// The Design Agent (phase 1.8) builds MJML, posts it here, and stores the
// compiled HTML. Kept deliberately small: no templating, no state, no DB.

import { createServer } from 'node:http';

import { render } from './render.js';

const PORT = Number(process.env.PORT ?? 7070);
const MAX_BODY_BYTES = 2 * 1024 * 1024; // an email that large is a bug

function json(res, status, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(body),
  });
  res.end(body);
}

async function readJsonBody(req) {
  const chunks = [];
  let size = 0;

  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY_BYTES) {
      throw new Error(`request body exceeds ${MAX_BODY_BYTES} bytes`);
    }
    chunks.push(chunk);
  }

  const raw = Buffer.concat(chunks).toString('utf8');
  if (!raw) return {};

  try {
    return JSON.parse(raw);
  } catch {
    throw new Error('request body is not valid JSON');
  }
}

const server = createServer(async (req, res) => {
  const { pathname } = new URL(req.url, `http://${req.headers.host ?? 'localhost'}`);

  if (req.method === 'GET' && pathname === '/health') {
    return json(res, 200, { status: 'ok', service: 'mjml-renderer' });
  }

  if (req.method === 'POST' && pathname === '/render') {
    let body;
    try {
      body = await readJsonBody(req);
    } catch (error) {
      return json(res, 400, { error: error.message });
    }

    if (typeof body.mjml !== 'string' || body.mjml.trim() === '') {
      return json(res, 422, { error: "field 'mjml' is required and must be a non-empty string" });
    }

    try {
      const { html, errors } = render(body.mjml, {
        validationLevel: body.validation_level ?? 'soft',
        minify: Boolean(body.minify),
      });
      return json(res, 200, { html, errors });
    } catch (error) {
      // 'strict' validation throws; surface it as a client error, not a 500.
      return json(res, 422, { error: String(error.message ?? error) });
    }
  }

  return json(res, 404, { error: 'not found' });
});

server.listen(PORT, () => {
  console.log(JSON.stringify({ event: 'mjml.listening', port: PORT }));
});
