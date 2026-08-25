from obi_one.core.schema import SchemaKey


def order_schema_properties(schema: dict) -> dict:
    """Return a copy of `schema` with its `properties` ordered by priority.

    Properties are sorted by descending `SchemaKey.PARAMETER_ORDER_PRIORITY`
    (absent or falsy priorities default to 0, ties keep their original order).
    The input `schema` is not modified.
    """
    properties = schema.get("properties")
    if not properties:
        return dict(schema)

    def priority(prop_schema: dict) -> float:
        return prop_schema.get(SchemaKey.PARAMETER_ORDER_PRIORITY, 0) or 0

    ordered = dict(sorted(properties.items(), key=lambda item: -priority(item[1])))
    return {**schema, "properties": ordered}
