; readcode additions on top of the bundled python tags query.
; @import.module = module as written; @import.from marks `from X import a, b`.

(import_statement name: (dotted_name) @import.module)

(import_statement name: (aliased_import name: (dotted_name) @import.module))

(import_from_statement module_name: (_) @import.module) @import.from

; The bundled tags query expects (expression_statement (assignment)); the bundled
; grammar puts module-level assignments directly under (module).
(module (assignment left: (identifier) @name) @definition.constant)
