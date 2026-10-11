# example/

Managed-runtime examples intended to exercise the PostGrip Agent TypeScript SDK end-to-end
against a live runtime service. Running an example locally submits a managed
`workflow.runtime` task to an existing agent pool. The SDK runtime worker path
runs only when a PostGrip host agent launches the example and injects
delegated runtime credentials.

## greeting

A managed-runtime demo: the local process submits the runtime command to an
agent pool, and the host-launched runtime registers one activity and one
workflow function.

```sh
cp example/.env.example .env
# set POSTGRIP_TOKEN to a common tenant management token; remove the old
# POSTGRIP_AGENT_TOKEN placeholder from .env so it cannot override the token
bun run example/greeting.ts
```

The generated `.env` file is ignored by git. The committed
`example/.env.example` contains placeholders only.

Optional overrides:

| Variable                       | Default                |
|:-------------------------------|:-----------------------|
| `POSTGRIP_AGENT_TASK_QUEUE`    | `typescript-example`   |

When a PostGrip host agent launches the example as a `workflow.runtime` task,
it injects delegated session credentials. The SDK does not enroll standalone
agents.

## In-repo development

The example imports the Agent entry point from the published `@postgrip/sdk`
package. From this repository, `bun run example/greeting.ts` resolves that
entry point through the local package without a separate link step.

The example launchers still read the legacy `POSTGRIP_AGENT_TOKEN` variable
as an explicit override. Leave it unset/absent; the SDK connection then reads
`POSTGRIP_TOKEN`. This is launcher compatibility, not a separate supported
management credential. See the [authentication owner](../../docs/authentication.md).

These launchers use their own pinned runtime image/command defaults; they do
not automatically execute the source in your checkout on the remote host.
Review the launcher's `SDK_EXAMPLE_RUNTIME_IMAGE`, `SDK_EXAMPLE_RUNTIME_COMMAND`
and `SDK_EXAMPLE_RUNTIME_ARGS_JSON` overrides before using a disposable pool.
These documentation checks
do not establish that the default live launcher succeeds.
