from obi_one.core.schema import SchemaKey


def order_schema_properties(schema: dict) -> None:
    properties = schema.get("properties")
    if not properties:
        return

    def priority(prop_schema: dict) -> float:
        return prop_schema.get(SchemaKey.PARAMETER_ORDER_PRIORITY, 0) or 0

    schema["properties"] = dict(sorted(properties.items(), key=lambda item: -priority(item[1])))
