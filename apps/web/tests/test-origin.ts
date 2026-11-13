export const testPort = process.env.PLAYWRIGHT_PORT ?? "3001";
export const testOrigin = `http://127.0.0.1:${testPort}`;
