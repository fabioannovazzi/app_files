// Local library for reviewed connectors. Never register a tool that returns a login.
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const run = promisify(execFile);

export class VaultLoginError extends Error {}

/** Read only the named Login's two fields; do not enumerate accounts or items. */
export async function readVaultLogin({vault, item}) {
  for (const reference of [vault, item]) {
    if (typeof reference !== 'string' || !reference.trim() || reference.startsWith('-') ||
        /[\x00-\x1f\x7f]/u.test(reference) || reference.length > 256) {
      throw new VaultLoginError('Choose a valid 1Password vault and Login item.');
    }
  }
  try {
    const {stdout} = await run('op', ['item', 'get', item, '--vault', vault,
      '--fields', 'username,password', '--reveal', '--format', 'json'],
      {timeout: 60000, maxBuffer: 64 * 1024, windowsHide: true});
    const fields = JSON.parse(stdout);
    const value = id => fields.find(field => field.id === id)?.value;
    const username = value('username');
    const password = value('password');
    if (typeof username === 'string' && username && typeof password === 'string' && password) {
      return {username, password};
    }
  } catch { /* op errors can include vault content. Never forward them. */ }
  throw new VaultLoginError('Could not read the selected login. Check the vault, item, 1Password CLI and desktop authorization.');
}
