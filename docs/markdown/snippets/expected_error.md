## Deprecate `should_fail` and rename it to `expected_error`, also introduce `success_returncode`

In 1.8.0 `should_fail` has been renamed to `expected_error`. Before 1.8.0, there was no way to positively test a command/binary returning error/non-zero return code, `success_returncode` has been introduced to achieve this.