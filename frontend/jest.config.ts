/**
 * Jest configuration for the LegacyLens frontend.
 *
 * Jest is the test runner for TypeScript/React code.
 * Think of it like pytest for the JavaScript world.
 *
 * This config tells Jest:
 * - Where to find test files
 * - How to handle TypeScript and Next.js
 * - Where to find modules (the @ alias)
 * - How much coverage is required
 */
import type { Config } from 'jest'
import nextJest from 'next/jest.js'

// createJestConfig reads our Next.js config to set up the test environment
// correctly (handles special Next.js imports, environment variables, etc.)
const createJestConfig = nextJest({ dir: './' })

const config: Config = {
  // jsdom simulates a browser environment so React components can render in tests
  testEnvironment: 'jsdom',

  // Run our custom setup file after Jest initializes (adds custom matchers)
  setupFilesAfterEnv: ['<rootDir>/jest.setup.ts'],

  // Map the @ import alias to the src/ directory
  // This lets tests use: import { foo } from '@/lib/api' instead of '../../lib/api'
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },

  // Find test files in __tests__ directories or files ending in .test.ts(x)
  testMatch: ['**/__tests__/**/*.[jt]s?(x)', '**/*.test.[jt]s?(x)'],

  // Measure coverage for all source files, except:
  // - .d.ts type declaration files (no logic to test)
  // - Next.js API routes for auth (tested separately with integration tests)
  collectCoverageFrom: [
    'src/**/*.{ts,tsx}',
    '!src/**/*.d.ts',
    '!src/app/api/**',
  ],

  // Minimum coverage thresholds — the build fails if we drop below these.
  // Think of it as a grade floor: we won't accept less than 70% on any metric.
  coverageThreshold: {
    global: {
      branches: 70,    // 70% of if/else branches must be tested
      functions: 80,   // 80% of functions must be called in at least one test
      lines: 80,       // 80% of lines must be executed in at least one test
      statements: 80,  // 80% of statements must execute in at least one test
    },
  },
}

export default createJestConfig(config)
