# 1.37.1 scoped review

The functional diff is limited to incremental_contract.template and packet_compaction
controls. All current execution-policy packet kinds receive submit plus explicit
argument/template/scratch bindings. Legacy direct action hints are overwritten,
while phase-specific operations, evidence instructions and handlers are retained.
Compaction cannot hide or change the action, arguments or template identity.

Patch-scope.json compares every skill Python file with 1.37.0: only these two
functional modules and product-version constants may differ. Guard, source/bind,
qualification/final/export and backend implementations remain byte-identical.
The runtime Python entry is unchanged. Existing task policies remain explicit.

Regression fixtures isolate command choice and routing; mocked recovery/final
terminal handlers do not claim quality acceptance. Separate actual installed
Windows/Linux workflow fixtures retain full current final gates and real render.
