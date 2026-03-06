/**
 * Manual mock for the mermaid package.
 *
 * Mermaid is an ESM-only package (type: "module") that Jest's CommonJS
 * runtime cannot require directly. This mock provides jest.fn() stubs for
 * the two methods used by ArchitectureDiagram so all unit tests can run
 * without a real browser rendering environment.
 *
 * Jest picks this file up via the moduleNameMapper in jest.config.ts:
 *   "^mermaid$": "<rootDir>/src/__mocks__/mermaid.ts"
 */

const mermaid = {
  initialize: jest.fn(),
  run: jest.fn().mockResolvedValue(undefined),
}

export default mermaid
