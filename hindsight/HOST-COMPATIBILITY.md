# Host dependency

Paired host: [ThomasMarcelis/hermes-agent](https://github.com/ThomasMarcelis/hermes-agent/tree/0d7c749cff42cd4791e0342da226c6d499de5aeb).
Pin commit `0d7c749cff42cd4791e0342da226c6d499de5aeb` on branch `jd/thin-v0.22.2`.
Its tree is identical to the verified integrated host `9665bc551b1f2294d31175f0c480e02362a5d99b`.
Release reference: Hermes v0.22.2, `d923a5eb487a17c0a68801bba9ef0f56c81040a8`.

Required public capability: `agent.memory_provider.MEMORY_LIFECYCLE_API_VERSION >= 1`.
The plugin checks this before availability and initialization. Stock v0.22.2 lacks
this contract. Do not substitute the version floor for the capability check.

The paired fork retains an operator-provisioned SQLite 3.53.4 Python runtime pin.
That binary is not distributed by this plugin; provision the required host runtime
before installation. Verify capabilities and rerun the lifecycle suite when changing hosts.
