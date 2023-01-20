import debugModule from 'debug';
import express from 'express';
import { handler as ssrHandler } from '../dist/server/entry.mjs';
const debug = debugModule('cookbook');

const host = process.env.HOST ? process.env.HOST : 'localhost';
const port = process.env.PORT ? Number.parseInt(process.env.PORT) : 3000;
const maxIdleSeconds = process.env.MAX_IDLE_SECONDS ? Number.parseInt(process.env.MAX_IDLE_SECONDS) : NaN;

let idleTimeout = null;
let activeRequests = 0;
function idleTimeoutMiddleware(req, res, next) {
  if (idleTimeout) {
    clearTimeout(idleTimeout);
    idleTimeout = null;
  }
  activeRequests++;
  debug('%s makes %d active requests.', req.url, activeRequests);
  res.once('finish', () => {
    activeRequests--;
    debug('Finished %s.', req.url);
    if (activeRequests === 0 && !isNaN(maxIdleSeconds)) {
      debug('Waiting for %d seconds after %s before shutting down.', maxIdleSeconds, new Date());
      idleTimeout = setTimeout(() => {
        console.log(`Server idle for ${maxIdleSeconds} seconds; shutting down.`);
        server.close();
      }, maxIdleSeconds * 1000);
    }
  });

  next();
}

const app = express();
app.use(idleTimeoutMiddleware);
app.use(express.static('dist/client/'))
app.use(ssrHandler);

const server = app.listen(port, host, () => {
  console.log(`Server listening at http://${host}:${port}`);
});
