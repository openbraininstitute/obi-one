from pandas import DataFrame

from obi_one.core.block import Block
from obi_one.scientific.blocks import distributions
from obi_one.scientific.blocks.distributions.base import Distribution
from obi_one.scientific.unions.unions_distributions import AllDistributionsReference


class SynapticModelBase(Block):
    _synapse_model_family: str | None = None

    @classmethod
    def synapse_model_family(cls) -> str:
        if cls._synapse_model_family is None:
            msg = (
                "Concrete subclasses of SynapticModelBase MUST set the class variable "
                "_synapse_model_family to a string that identifies the synapse model family. "
                "This is used to check compatibility of different SynapticModelBase subclasses."
            )
            raise NotImplementedError(msg)
        return cls._synapse_model_family

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
    def from_dict(
        cls, serialized_dict: dict
    ) -> tuple["SynapticModelBase", dict[str, Distribution]]:

        def dist_ref(name: str) -> AllDistributionsReference:
            """Helper to create a distribution reference."""
            return AllDistributionsReference(block_dict_name="distributions", block_name=name)

        if serialized_dict["class"] != cls.__name__:
            msg = (
                f"Expected class name {cls.__name__!r} in serialized dict",
                f"got {serialized_dict['class']!r}",
            )
            raise ValueError(msg)
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
        msg = (
            "Concrete subclasses of SynapticModelBase MUST implement the .sample() method to "
            "return a DataFrame of synapse parameters given a DataFrame of indices."
        )
        raise NotImplementedError(msg)
