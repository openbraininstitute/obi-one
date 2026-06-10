from pandas import DataFrame

from obi_one.core.block import Block
from obi_one.scientific.blocks import distributions


class SynapticModelBase(Block):
    """# def parameter_dictionaries(self) -> dict:
    #     raise NotImplementedError("This is an abstract class!")
    """

    @classmethod
    def synapse_model_family(cls):
        msg = (
            "Concrete subclasses of SynapticModelBase MUST implement the .synapse_model_family() "
            "class method to return a string that identifies the family of synapse models to which they belong."
        )
        raise NotImplementedError(msg)

    @classmethod
    def compatible_with(cls, other) -> None:
        """Tests whether this subclass of SynapticModelBase is compatible
        with another. A required but not sufficient condition is that
        they provide the same list of synapse parameters.
        More generally, compatibility means that the .default of one
        class is functionally identical to the one of the other.
        """
        if cls.synapse_model_family() != other.synapse_model_family():
            raise ValueError("Synapse models incompatible!")
        # Below should not be needed. Just to be safe...
        param_names = cls.parameter_names()
        other_names = other.parameter_names()
        for k in param_names:
            if k not in other_names:
                raise ValueError("Internal OBI-ONE error!")
        for k in other_names:
            if k not in param_names:
                raise ValueError("Internal OBI-ONE error!")

    @classmethod
    def parameter_names(cls) -> list[str]:
        """Returns the names of the synapse parameters provided by this class.
        Important: `SynapticModelBase` classes that share the same
        _synapse_model_family MUST return the same list of parameter names!
        """
        msg = (
            "Concrete subclasses of SynapticModelBase MUST implement the .parameter_names() "
            "class method to return a list of synapse parameter names."
        )
        raise NotImplementedError(msg)

    @classmethod
    def from_dict(cls, serialized_dict):
        from obi_one.scientific.unions.unions_distributions import AllDistributionsReference

        def dist_ref(name: str) -> AllDistributionsReference:
            """Helper to create a distribution reference."""
            return AllDistributionsReference(block_dict_name="distributions", block_name=name)

        assert serialized_dict["class"] == cls.__name__
        distr_obj_dict = {}
        distr_ref_dict = {}
        for param_name, distr_dict in serialized_dict["distributions"].items():
            distr_cls = distr_dict.pop("type")
            distr_obj_dict[param_name] = distributions.__dict__[distr_cls](**distr_dict)
            distr_ref_dict[param_name] = dist_ref(param_name)
            distr_ref_dict[param_name].block = distr_obj_dict[param_name]
        return cls(**distr_ref_dict), distr_obj_dict

    def sample(self, indices: DataFrame) -> DataFrame:
        """The main functionality of this class. Returns synapse parameters as
        specified. The input is a DataFrame with two columns: @source_node
        and @target_node. Its index is the edge index as used in SONATA.
        Returns DataFrame with one named column per parameter and the same index
        as the input.
        """
        raise NotImplementedError("This is an abstract class!")
