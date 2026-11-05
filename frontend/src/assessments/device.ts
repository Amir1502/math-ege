const DEVICE_KEY = 'math-ege:assessment-device-v1';
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
let devicePromise: Promise<string> | undefined;

function storedDevice(): string {
  const saved = sessionStorage.getItem(DEVICE_KEY);
  const id = saved && uuid.test(saved) ? saved : crypto.randomUUID();
  sessionStorage.setItem(DEVICE_KEY, id);
  return id;
}

async function lockDevice(id: string): Promise<boolean> {
  return new Promise<boolean>((resolve, reject) => {
    void navigator.locks.request(`math-ege:assessment-device:${id}`, { ifAvailable: true }, async (lock) => {
      if (!lock) { resolve(false); return; }
      resolve(true);
      // A copied sessionStorage must not impersonate an already-open tab. The browser
      // releases the lock on document destruction; a bfcached document retains its ID.
      await new Promise<void>((release) => {
        window.addEventListener('pagehide', (event) => { if (!event.persisted) release(); }, { once: true });
      });
    }).catch(reject);
  });
}

async function channelDevice(initial: string): Promise<string> {
  if (typeof BroadcastChannel === 'undefined') throw new Error('Браузер не поддерживает изоляцию вкладок. Откройте вариант в современном браузере.');
  const channel = new BroadcastChannel('math-ege:assessment-devices');
  const nonce = crypto.randomUUID();
  let id = initial;
  let claimed = false;
  channel.onmessage = (event: MessageEvent<{ type: string; id: string; nonce: string; target?: string }>) => {
    const message = event.data;
    if (!message || message.id !== id || message.nonce === nonce) return;
    if (message.type === 'probe' && (claimed || nonce < message.nonce)) {
      channel.postMessage({ type: 'occupied', id, nonce, target: message.nonce });
    }
    if (message.type === 'occupied' && message.target === nonce && !claimed) {
      id = crypto.randomUUID();
      sessionStorage.setItem(DEVICE_KEY, id);
      channel.postMessage({ type: 'probe', id, nonce });
    }
  };
  channel.postMessage({ type: 'probe', id, nonce });
  await new Promise<void>((resolve) => setTimeout(resolve, 180));
  claimed = true;
  window.addEventListener('pagehide', (event) => { if (!event.persisted) channel.close(); }, { once: true });
  return id;
}

async function acquireDevice(): Promise<string> {
  let id = storedDevice();
  if (!navigator.locks) return channelDevice(id);
  if (await lockDevice(id)) return id;
  id = crypto.randomUUID();
  sessionStorage.setItem(DEVICE_KEY, id);
  if (!await lockDevice(id)) throw new Error('Не удалось выделить вкладку. Перезагрузите страницу.');
  return id;
}

export function assessmentDevice(): Promise<string> {
  devicePromise ??= acquireDevice().catch((error: unknown) => { devicePromise = undefined; throw error; });
  return devicePromise;
}
