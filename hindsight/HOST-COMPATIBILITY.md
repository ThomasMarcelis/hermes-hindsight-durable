# Host dependency

Tested host correction commit: `cc83b0466b116756d8b1fe6d71da0c004b627160`.
Host baseline: `8ea88a768b48af0b191d9d9313aab7fc6a7de751`.
Release reference: Hermes v0.22.2, `d923a5eb487a17c0a68801bba9ef0f56c81040a8`.

Required public capability: `agent.memory_provider.MEMORY_LIFECYCLE_API_VERSION >= 1`.
The plugin checks this before availability and initialization. Stock v0.22.2 lacks
this contract. Do not substitute the version floor for the capability check.

This source delivery names the exact local Git identity. The parent publisher must
supply the final public host repository and integrated commit before public install
instructions can be completed. No public host URL is asserted here. Cherry-picking
these changes changes the commit identity; verify capability and rerun the offline
native installation and lifecycle suite against that final host.
