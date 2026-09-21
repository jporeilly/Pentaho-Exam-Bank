import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Each test mounts its own tree; without this they accumulate in the same
// document and queries start matching a previous test's markup.
afterEach(cleanup);
