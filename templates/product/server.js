const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

const PORT = 3000;

const MIME_TYPES = {
  '.html': 'text/html',
  '.css': 'text/css',
  '.js': 'text/javascript',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml'
};

const server = http.createServer((req, res) => {
  let filePath = '.' + req.url;
  if (filePath === './') {
    filePath = './index.html';
  }

  const extname = String(path.extname(filePath)).toLowerCase();
  const contentType = MIME_TYPES[extname] || 'application/octet-stream';

  fs.readFile(filePath, (error, content) => {
    if (error) {
      if (error.code === 'ENOENT') {
        fs.readFile('./index.html', (err, indexContent) => {
          if (err) {
            res.writeHead(500);
            res.end(`Server Error: ${err.code}`);
          } else {
            res.writeHead(200, { 'Content-Type': 'text/html' });
            res.end(indexContent, 'utf-8');
          }
        });
      } else {
        res.writeHead(500);
        res.end(`Server Error: ${error.code}`);
      }
    } else {
      res.writeHead(200, { 'Content-Type': contentType });
      res.end(content, 'utf-8');
    }
  });
});

server.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT}/`);
  console.log(`Available pages:`);
  console.log(`- Home (Desktop): http://localhost:${PORT}/index.html`);
  console.log(`- Home (Mobile): http://localhost:${PORT}/index-mobile.html`);
  console.log(`- Product (Desktop): http://localhost:${PORT}/product.html`);
  console.log(`- Product (Mobile): http://localhost:${PORT}/product-mobile.html`);
  console.log(`- Collection (Desktop): http://localhost:${PORT}/collection.html`);
  console.log(`- Collection (Mobile): http://localhost:${PORT}/collection-mobile.html`);
  console.log(`- Overlays (Search/Cart): http://localhost:${PORT}/overlays.html`);
});
