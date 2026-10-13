; readcode query for SQL (no bundled tags query). Only CREATE statements are defs.

(create_table (object_reference name: (identifier) @name)) @definition.table

(create_view (object_reference name: (identifier) @name)) @definition.other

(create_materialized_view (object_reference name: (identifier) @name)) @definition.other

(create_function (object_reference name: (identifier) @name)) @definition.other

(relation (object_reference name: (identifier) @name)) @reference.table
