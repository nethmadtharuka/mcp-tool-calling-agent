import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom doesn't implement scrolling; the layout scrolls to top on navigation.
window.scrollTo = () => {};

afterEach(() => {
  cleanup();
  localStorage.clear();
});
