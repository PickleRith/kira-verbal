import { describe, expect, it } from "vitest";

import { gradeLevels } from "./grading";

// Same cases as backend/tests/unit/test_grading.py: the two copies of the rule must agree.
describe("gradeLevels", () => {
  it("scores all levels", () => {
    expect(gradeLevels({ a: 3, b: 2, c: 2 })).toEqual({
      points: 7,
      max_points: 9,
      percent: 78,
      assessed: 3,
      total: 3,
      band: "proficient",
    });
  });

  it("never counts unknown as zero, and marks the grade incomplete", () => {
    const g = gradeLevels({ a: 3, b: null, c: 3 });
    expect([g.points, g.max_points, g.percent, g.band]).toEqual([6, 6, 100, "incomplete"]);
    expect(gradeLevels({ a: null }).percent).toBeNull();
    expect(gradeLevels({}).band).toBe("incomplete");
  });

  it.each([
    [{ a: 3, b: 3, c: 2 }, 89, "mastered"],
    [{ a: 2, b: 2, c: 2 }, 67, "proficient"],
    [{ a: 2, b: 1, c: 1 }, 44, "developing"],
    [{ a: 1, b: 1, c: 1 }, 33, "beginning"],
  ])("bands %j as %i%% %s", (levels, percent, band) => {
    const g = gradeLevels(levels);
    expect(g.percent).toBe(percent);
    expect(g.band).toBe(band);
  });

  it("rounds half up like the server", () => {
    const levels = Object.fromEntries(Array.from({ length: 8 }, (_, i) => [String(i), i === 0 ? 3 : 0]));
    expect(gradeLevels(levels).percent).toBe(13);
    expect(gradeLevels({ a: 2, b: 2, c: 1 }).percent).toBe(56);
  });
});
