const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('finagentDesktop', {
  version: '0.1.0',
});
