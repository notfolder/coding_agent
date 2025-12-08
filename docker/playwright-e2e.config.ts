// playwright-e2e.config.ts
import { defineConfig, devices } from '@playwright/test';

/**
 * See playwright.dev.
 */
export default defineConfig({
  // Directory where test files are located
  testDir: './tests',

  // Pattern for files to be recognized as test files
  testMatch: '**/*.spec.ts',

  // Set baseURL as a relative path from the project root
  // This allows you to write page.goto('/') in your tests
  use: {
    // URL of the application under test
    // When using the webServer option, this URL becomes automatically accessible
    baseURL: 'http://localhost:3000',

    // Collect trace files (test execution videos, screenshots, etc.) after each test run
    // 'on-first-retry' collects only on the first failure
    trace: 'on-first-retry',

    // Enable/disable headless mode (true is common in CI environments)
    headless: true,

    // Video capture settings (save only on failure)
    video: 'on-first-retry',

    // Screenshot capture (save only on failure)
    screenshot: 'only-on-failure',
  },

  // Test execution timeout setting (milliseconds)
  timeout: 30 * 1000,

  // Maximum execution time allowed for each test
  expect: {
    timeout: 5000,
  },

  // Whether to terminate the build process on global test execution failure
  forbidOnly: !!process.env.CI,

  // Number of retries (typically set to about 2 times in CI)
  retries: process.env.CI ? 2 : 0,

  // Settings for reporting test results to CI server
  reporter: 'html',

  // The projects section below defines which browsers/devices to run tests on

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    }
  ],

  // Example usage of the webServer option mentioned above
  // Automatically starts a local development server before tests begin
  // This setting allows you to run tests without manually starting the server
  // Specify the command to start your application in 'command'
  webServer: {
    command: 'npm run start', // Startup command for Vite, Next.js, etc.
    // --- Specify the working directory here ---
    // Specify the directory where 'command' will be executed as a relative path from the project root
    cwd: '/workspace/project',
    url: 'http://localhost:3000',
    timeout: 120 * 1000, // Timeout for server startup
    reuseExistingServer: !process.env.CI, // Reuse existing server except in CI
  },
});
