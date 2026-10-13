; readcode additions on top of the bundled javascript tags query.

(import_statement source: (string (string_fragment) @import.module))

(export_statement source: (string (string_fragment) @import.module))

((call_expression
  function: (identifier) @_require
  arguments: (arguments . (string (string_fragment) @import.module)))
  (#eq? @_require "require"))

(call_expression
  function: (import)
  arguments: (arguments . (string (string_fragment) @import.module)))
