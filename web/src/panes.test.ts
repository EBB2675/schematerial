import { describe, expect, it } from "vitest";

import { defaultPair, otherSide, SIDES } from "./panes";
import type { SchemaSummary } from "./types";

function summary(name: string, pkg: string | null, status: "ok" | "unsupported" = "ok") {
  return {
    name,
    status,
    source: { package: pkg, version: "1", dependencies: null },
  } as SchemaSummary;
}

describe("the pair a catalogue opens with", () => {
  it("puts two different sources side by side when both were loaded", () => {
    const pair = defaultPair([
      summary("general", "nomad-simulations"),
      summary("model_method", "nomad-simulations"),
      summary("object_types", "bam-masterdata"),
    ]);
    expect(pair).toEqual({ left: "general", right: "object_types" });
  });

  it("falls back to a second module of the same source", () => {
    const pair = defaultPair([
      summary("general", "nomad-simulations"),
      summary("model_method", "nomad-simulations"),
    ]);
    expect(pair).toEqual({ left: "general", right: "model_method" });
  });

  it("leaves the second side closed when only one schema is browsable", () => {
    expect(defaultPair([summary("general", "nomad-simulations")])).toEqual({
      left: "general",
      right: null,
    });
  });

  it("never opens onto a refused import while a usable schema exists", () => {
    const pair = defaultPair([
      summary("broken", "nomad-simulations", "unsupported"),
      summary("object_types", "bam-masterdata"),
    ]);
    expect(pair).toEqual({ left: "object_types", right: null });
  });

  it("still shows a refused import when it is all there is, so it is not hidden", () => {
    expect(defaultPair([summary("broken", "nomad-simulations", "unsupported")])).toEqual({
      left: "broken",
      right: null,
    });
  });

  it("closes both sides for an empty catalogue", () => {
    expect(defaultPair([])).toEqual({ left: null, right: null });
  });
});

describe("sides", () => {
  it("has exactly two, and each one's opposite", () => {
    expect(SIDES).toEqual(["left", "right"]);
    expect(otherSide("left")).toBe("right");
    expect(otherSide("right")).toBe("left");
  });
});
