const fs = require('node:fs');
const path = require('node:path');

// One protocol catalog is shared with Python. Packaged copies are build outputs.
const catalogPath = process.resourcesPath && fs.existsSync(path.join(process.resourcesPath, 'control_catalog.json'))
  ? path.join(process.resourcesPath, 'control_catalog.json')
  : path.resolve(__dirname, '..', '..', 'src', 'control_catalog.json');
const catalog = JSON.parse(fs.readFileSync(catalogPath, 'utf8'));
const controls = catalog.controls;
if (!Array.isArray(controls) || !controls.length || new Set(controls.map(item => item.id)).size !== controls.length) throw new Error('Invalid instrument control catalog.');
const publicControls = controls.map(({ id, label, group, kind, description, validation, max_count, context_dependent }) => ({ id, label, group, kind, description, validation, maxCount: max_count, contextDependent: Boolean(context_dependent) }));

function validatePanelAction(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input) || Object.keys(input).some(key => !['control', 'count'].includes(key))) throw new Error('Choose a named instrument control.');
  const control = controls.find(item => item.id === input.control);
  if (!control) throw new Error('Unknown instrument control.');
  const count = input.count === undefined ? 1 : input.count;
  const max = control.kind === 'rotary' ? 5 : 1;
  if (!Number.isInteger(count) || count < 1 || count > max) throw new Error(control.kind === 'rotary' ? 'Choose between 1 and 5 knob steps.' : 'Buttons accept one press at a time.');
  return { control, count };
}
module.exports = { publicControls, validatePanelAction };
