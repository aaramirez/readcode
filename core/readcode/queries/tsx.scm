; readcode additions for tsx (same as typescript.scm; applied after javascript.scm
; and the bundled javascript + tsx tags queries).

(type_alias_declaration name: (type_identifier) @name) @definition.type

(enum_declaration name: (identifier) @name) @definition.type

(type_identifier) @name @reference.type
