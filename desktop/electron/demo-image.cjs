const zlib = require('node:zlib');

function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}
function chunk(name, data) {
  const type = Buffer.from(name), size = Buffer.alloc(4), crc = Buffer.alloc(4);
  size.writeUInt32BE(data.length); crc.writeUInt32BE(crc32(Buffer.concat([type, data])));
  return Buffer.concat([size, type, data, crc]);
}
function demoImage(phase = 0) {
  const width = 800, height = 480, rows = Buffer.alloc((width * 3 + 1) * height);
  const pixel = (x, y, color) => {
    if (x < 0 || y < 0 || x >= width || y >= height) return;
    const i = Math.floor(y) * (width * 3 + 1) + 1 + Math.floor(x) * 3;
    rows[i] = color[0]; rows[i + 1] = color[1]; rows[i + 2] = color[2];
  };
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    const grid = x % 80 === 0 || y % 60 === 0;
    const axis = x === 400 || y === 240;
    pixel(x, y, axis ? [66, 83, 96] : grid ? [29, 45, 57] : [14, 26, 36]);
  }
  for (let x = 0; x < width; x++) {
    const y = 229 - Math.sin(x / 42 + phase) * 102;
    const y2 = 266 - Math.sin(x / 42 + phase + 0.7) * 52;
    for (let d = -1; d <= 1; d++) { pixel(x, y + d, [249, 217, 94]); pixel(x, y2 + d, [63, 193, 202]); }
  }
  // A baked-in DEMO label keeps the synthetic provenance visible after export.
  const letters = {D:['1110','1001','1001','1001','1110'],E:['1111','1000','1110','1000','1111'],M:['10001','11011','10101','10001','10001'],O:['0110','1001','1001','1001','0110']};
  let left = 26;
  for (const letter of 'DEMO') {
    const glyph = letters[letter];
    glyph.forEach((row, y) => [...row].forEach((on, x) => {
      if (on === '1') for (let dy = 0; dy < 3; dy++) for (let dx = 0; dx < 3; dx++) pixel(left + x * 3 + dx, 22 + y * 3 + dy, [136, 172, 188]);
    }));
    left += glyph[0].length * 3 + 6;
  }
  const header = Buffer.alloc(13); header.writeUInt32BE(width); header.writeUInt32BE(height, 4); header[8] = 8; header[9] = 2;
  return Buffer.concat([Buffer.from('89504e470d0a1a0a', 'hex'), chunk('IHDR', header), chunk('IDAT', zlib.deflateSync(rows)), chunk('IEND', Buffer.alloc(0))]);
}
module.exports = { demoImage };
