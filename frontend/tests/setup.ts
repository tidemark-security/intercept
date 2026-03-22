import "@testing-library/jest-dom";

class ResizeObserverMock {
	observe() {}
	unobserve() {}
	disconnect() {}
}

if (typeof globalThis.ResizeObserver === "undefined") {
	globalThis.ResizeObserver = ResizeObserverMock as typeof ResizeObserver;
}
