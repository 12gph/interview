// Registers the extra DOM matchers (`toBeDisabled`, `toHaveTextContent`, ...) and
// their TypeScript types, so assertion failures read as intent rather than as DOM
// trivia.
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Testing Library only auto-registers cleanup when the runner exposes its hooks
// globally, and this project deliberately does not enable `globals`. Without this,
// every render in a file would pile up in the same document and queries would start
// matching duplicates from earlier tests.
afterEach(() => {
  cleanup();
});
