def estimate_task_resources(
    json_model: TaskLaunchSubmit, db_client: entitysdk.Client, task_definition: TaskDefinition
) -> ClusterResources:
    config = db_client.get_entity(
        entity_id=json_model.config_id,
        entity_type=models.Simulation,
    )
    circuit = db_client.get_entity(
        entity_id=config.entity_id,
        entity_type=models.Circuit,
    )
    number_of_neurons = circuit.number_of_neurons

    # TODO
    n_nodes = 1
    instance_type = "smalll"

    return task_definition.resources.model_copy(
        update={
            "instances": n_nodes,
            "instance_type": instance_type,
        }
    )
