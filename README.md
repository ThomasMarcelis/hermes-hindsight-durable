# Durable Hindsight for Hermes

A separately packaged Hermes memory provider with session-owned delivery, bounded
settlement/retry, observation filtering and conservative rewind handling.

**Start with the [installed guide](hindsight/README.md)** for supported hosts, pinned
native installation per profile, configuration, tools and retention limits. Stock
Hermes v0.22.2 does not satisfy the required memory lifecycle API 1. The guide is the
single configuration reference and ships with the installed plugin.

## Development

Use a PM-prepared test interpreter that imports the paired Hermes checkout, including
its test helpers. The launcher creates isolated HOME/HERMES_HOME and scratch, checks
host import origins, and runs the host's canonical runner with file retries disabled.
No Hindsight server or model credentials are needed. The native install regression
clones the current committed plugin revision, so commit candidate changes first.

```bash
python3 /opt/hermes-hindsight-durable/scripts/test.py --host /opt/hermes --python /opt/hermes-test-env/bin/python --scratch /tmp --output /tmp/hindsight-test-evidence
```

Replace the absolute paths with your local paths. Tests use synthetic transports and
an offline wheel fixture for PM admission; this does not certify a server deployment
or resolve a fresh production host dependency graph.

## Provenance

Derived from the MIT-licensed NousResearch Hermes integration, including the owned
durable extensions. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
Source: [ThomasMarcelis/hermes-hindsight-durable](https://github.com/ThomasMarcelis/hermes-hindsight-durable).
The [host compatibility reference](hindsight/HOST-COMPATIBILITY.md) pins the paired host.
