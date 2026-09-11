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
function demoImage(phase = 0, controls = {}) {
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
    const wave = (x + (controls.timeOffset || 0)) / 42 * (controls.timeScale || 1) + phase;
    const y = 229 + (controls.ch1Offset || 0) - Math.sin(wave) * 102 * (controls.ch1Scale || 1);
    const y2 = 266 + (controls.ch2Offset || 0) - Math.sin(wave + 0.7) * 52 * (controls.ch2Scale || 1);
    for (let d = -1; d <= 1; d++) { pixel(x, y + d, [249, 217, 94]); pixel(x, y2 + d, [63, 193, 202]); }
  }
  if (controls.lastAction) {
    const triggerY = 240 + (controls.triggerOffset || 0);
    for (let x = 775; x < 800; x++) for (let y = triggerY - (x - 775) / 3; y <= triggerY + (x - 775) / 3; y++) pixel(x, y, [249, 217, 94]);
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
  const font = {
    A:['010','101','111','101','101'],B:['110','101','110','101','110'],C:['011','100','100','100','011'],D:['110','101','101','101','110'],E:['111','100','110','100','111'],F:['111','100','110','100','100'],G:['011','100','101','101','011'],H:['101','101','111','101','101'],I:['111','010','010','010','111'],J:['001','001','001','101','010'],K:['101','101','110','101','101'],L:['100','100','100','100','111'],M:['101','111','111','101','101'],N:['101','111','111','111','101'],O:['010','101','101','101','010'],P:['110','101','110','100','100'],Q:['010','101','101','111','011'],R:['110','101','110','101','101'],S:['011','100','010','001','110'],T:['111','010','010','010','010'],U:['101','101','101','101','111'],V:['101','101','101','101','010'],W:['101','101','111','111','101'],X:['101','101','010','101','101'],Y:['101','101','010','010','010'],Z:['111','001','010','100','111'],0:['111','101','101','101','111'],1:['010','110','010','010','111'],2:['110','001','010','100','111'],3:['110','001','010','001','110'],4:['101','101','111','001','001'],5:['111','100','110','001','110']
  };
  const text = String(controls.lastAction || 'SIMULATED SIGNAL').slice(0, 50);
  [...text].forEach((letter, column) => (font[letter] || []).forEach((row, y) => [...row].forEach((on, x) => {
    if (on === '1') for (let dy = 0; dy < 2; dy++) for (let dx = 0; dx < 2; dx++) pixel(26 + column * 8 + x * 2 + dx, 450 + y * 2 + dy, [136, 172, 188]);
  })));
  const header = Buffer.alloc(13); header.writeUInt32BE(width); header.writeUInt32BE(height, 4); header[8] = 8; header[9] = 2;
  return Buffer.concat([Buffer.from('89504e470d0a1a0a', 'hex'), chunk('IHDR', header), chunk('IDAT', zlib.deflateSync(rows)), chunk('IEND', Buffer.alloc(0))]);
}
module.exports = { demoImage };
