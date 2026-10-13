; readcode additions on top of the bundled go tags query.
; Struct/interface kinds and method parents are refined in indexer.py.

(import_spec path: (interpreted_string_literal (interpreted_string_literal_content) @import.module))

; Package-level var/const only (direct children of the source file's declarations,
; including grouped blocks); function-local declarations are not indexed.
(source_file (var_declaration (var_spec name: (identifier) @name) @definition.variable))
(source_file (var_declaration (var_spec_list (var_spec name: (identifier) @name) @definition.variable)))
(source_file (const_declaration (const_spec name: (identifier) @name) @definition.constant))
