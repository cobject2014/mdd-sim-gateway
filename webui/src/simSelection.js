export const linePresent = (line, cards = [], devices = []) => Boolean(line && (
  cards.some(c => c.present && (String(c.matched) === String(line.id) || (c.iccid && c.iccid === line.iccid))) ||
  devices.some(d => d.present && String(d.instance_id || '') === String(line.id))
))
export const selectableLines = (instances, cards, devices, includeOffline = false) =>
  includeOffline ? instances : instances.filter(i => linePresent(i, cards, devices))
