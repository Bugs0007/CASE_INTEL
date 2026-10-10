import { describe, it, expect } from "vitest";
import { jobPollInterval } from "@/hooks/use-advocate-search";

// Production bug: a cancelled advocate search kept polling its status
// endpoint every 1.5s forever (and in background tabs), because the stop
// rule only knew "succeeded" and "failed". Each poll makes the server load
// the job's whole result payload.

describe("jobPollInterval", () => {
  it("does not poll before the first response (a failed first fetch must not loop)", () => {
    expect(jobPollInterval(undefined, 1500)).toBe(false);
  });

  it("keeps polling while the job is queued or running", () => {
    expect(jobPollInterval({ status: "queued" }, 1500)).toBe(1500);
    expect(jobPollInterval({ status: "running" }, 3000)).toBe(3000);
  });

  it.each(["succeeded", "failed", "cancelled"])("stops once the job is %s", (status) => {
    expect(jobPollInterval({ status }, 1500)).toBe(false);
  });
});
