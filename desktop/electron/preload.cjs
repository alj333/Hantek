const { contextBridge, ipcRenderer } = require('electron');
const invoke = (name, ...args) => ipcRenderer.invoke(`scope:${name}`, ...args);
contextBridge.exposeInMainWorld('scopeApp', {
  getState: () => invoke('getState'),
  connect: () => invoke('connect'),
  disconnect: () => invoke('disconnect'),
  checkConnection: () => invoke('checkConnection'),
  capture: options => invoke('capture', options),
  setAcquisition: state => invoke('setAcquisition', state),
  panelAction: input => invoke('panelAction', input),
  readSettings: () => invoke('readSettings'),
  updateSettings: patch => invoke('updateSettings', patch),
  chooseStorageDirectory: () => invoke('chooseStorageDirectory'),
  listCaptures: () => invoke('listCaptures'),
  updateCapture: input => invoke('updateCapture', input),
  exportCapture: id => invoke('exportCapture', id),
  revealCapture: id => invoke('revealCapture', id),
  openStorage: () => invoke('openStorage'),
  onStateChanged: callback => {
    const handler = (_event, state) => callback(state);
    ipcRenderer.on('scope:state', handler);
    return () => ipcRenderer.removeListener('scope:state', handler);
  },
});
