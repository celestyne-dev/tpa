import source from "./AdminApp.jsx?raw";
import { PAGE_LOADERS } from "./screens";

const screens = [...source.matchAll(/screen\("([^"]+)", "(\w+)"\)/g)].map((m) => [m[1], m[2]]);

describe("lazily loaded admin screens", () => {
  it("are not imported statically by the admin app", () => {
    expect(screens.length).toBeGreaterThan(50);
    for (const [module] of screens) {
      expect(source).not.toContain(`from "./pages/${module}"`);
    }
  });

  it.each(screens)("%s exports %s", async (module, name) => {
    expect(PAGE_LOADERS[module]).toBeTypeOf("function");
    const loaded = await PAGE_LOADERS[module]();
    expect(loaded[name]).toBeTypeOf("function");
  });
});
