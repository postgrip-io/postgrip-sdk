import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import {
  Client as AgentClient,
  Connection,
} from "../../../typescript/src/agent/index.ts";
import { ServiceClient } from "../../../typescript/src/service/index.ts";
import { WorkerClient } from "../../../typescript/src/worker/index.ts";

interface Fixture {
  operationId: string;
  plane: "agent" | "worker" | "service";
  request: {
    pathParameters: Record<string, string>;
    query: Record<string, unknown>;
    headers: Record<string, string>;
    body: unknown;
    streamBodyBase64: string | null;
  };
}

const argumentsByName = new Map<string, string>();
for (let index = 2; index < process.argv.length; index += 2) {
  argumentsByName.set(process.argv[index]!, process.argv[index + 1]!);
}
const baseUrl = argumentsByName.get("--base-url");
const fixtureRoot = argumentsByName.get("--fixture-root");
const selectedPlane = argumentsByName.get("--plane") ?? "all";
if (!baseUrl || !fixtureRoot)
  throw new Error("base-url and fixture-root are required");

const token = process.env.POSTGRIP_TOKEN ?? "";
const connection = Connection.create({
  baseUrl,
  insecureDevelopment: true,
  authToken: token,
  agentAuth: {
    agentId: "recorded-agent",
    accessToken: process.env.POSTGRIP_AGENT_ACCESS_TOKEN,
    accessExpiresAt: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
    signingPrivateKey: process.env.POSTGRIP_AGENT_SIGNING_PRIVATE_KEY,
  },
});
const agent = new AgentClient({ connection });
const workers = new WorkerClient({ baseUrl, token, insecureDevelopment: true });
const services = new ServiceClient({
  baseUrl,
  token,
  insecureDevelopment: true,
});

const completed: string[] = [];
const planes = (
  selectedPlane === "all" ? ["agent", "worker", "service"] : [selectedPlane]
) as Array<"agent" | "worker" | "service">;
for (const plane of planes) {
  const directory = join(fixtureRoot, plane);
  for (const name of readdirSync(directory)
    .filter((value) => value.endsWith(".json"))
    .sort()) {
    const fixture = JSON.parse(
      readFileSync(join(directory, name), "utf8"),
    ) as Fixture;
    if (fixture.operationId === "connectSandboxSession") continue;
    if (fixture.operationId === "uploadWorkspace") {
      await agent.sandbox.uploadWorkspace(
        Buffer.from(fixture.request.streamBodyBase64 ?? "", "base64"),
        {
          repositoryName: fixture.request.headers["X-PostGrip-Repository"],
          revision: fixture.request.headers["X-PostGrip-Revision"],
        },
      );
    } else {
      const options = {
        pathParameters: fixture.request.pathParameters,
        query: fixture.request.query,
        headers: fixture.request.headers,
        ...(fixture.request.body === null
          ? {}
          : { body: fixture.request.body }),
      };
      if (plane === "agent") {
        await connection.openapi.request(
          fixture.operationId as never,
          options as never,
        );
      } else if (plane === "worker") {
        await workers.openapi.request(
          fixture.operationId as never,
          options as never,
        );
      } else {
        await services.openapi.request(
          fixture.operationId as never,
          options as never,
        );
      }
    }
    completed.push(fixture.operationId);
  }
}

process.stdout.write(
  `${JSON.stringify({ language: "typescript", operations: completed })}\n`,
);
